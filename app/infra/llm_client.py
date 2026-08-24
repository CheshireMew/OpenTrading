from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from app.application.model_contracts import ModelCallResult, ModelCallStatus
from app.infra.llm_provider import LLMProviderAdapter
from app.infra.structured_json import decode_strict_json_object
from config import settings
from utils.logger import logger


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 1.0
MAX_RETRY_DELAY_SECONDS = 30.0
ModelOutputT = TypeVar("ModelOutputT", bound=BaseModel)


class LLMClientFactory:
    def __init__(self, llm_config_service: Any) -> None:
        self._llm_config_service = llm_config_service
        self._http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )

    def __call__(self) -> "LLMClient":
        return LLMClient(
            llm_config=self._llm_config_service.read_effective_config(),
            http_client=self._http_client,
        )

    async def aclose(self) -> None:
        await self._http_client.aclose()


class LLMClient:
    def __init__(
        self,
        llm_config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._provider = LLMProviderAdapter(llm_config)
        self.provider = self._provider.provider
        self.model = self._provider.model
        self.request_timeout = self._provider.request_timeout
        self._http_client = http_client

    async def analyze(
        self,
        prompt: str,
        *,
        response_model: type[ModelOutputT],
        purpose: str,
    ) -> ModelCallResult[ModelOutputT]:
        request_id = uuid4().hex
        started_at = perf_counter()
        if not self._provider.configured:
            return self._finish(
                request_id=request_id,
                started_at=started_at,
                purpose=purpose,
                status="unavailable",
                error_code="model_not_configured",
            )

        try:
            payload = self._provider.build_payload(prompt, response_model)
        except ValueError:
            return self._finish(
                request_id=request_id,
                started_at=started_at,
                purpose=purpose,
                status="unavailable",
                error_code="structured_output_mode_unsupported",
            )

        if settings.LLM_TRACE_CONTENT:
            logger.debug(
                "event=model_trace_request request_id=%s provider=%s model=%s purpose=%s prompt=%r",
                request_id,
                self.provider,
                self.model,
                purpose,
                prompt,
            )

        last_error_code = "provider_transport_error"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            logger.info(
                "event=model_call_started request_id=%s provider=%s model=%s purpose=%s attempt=%s",
                request_id,
                self.provider,
                self.model,
                purpose,
                attempt,
            )
            try:
                response = await self._http_client.post(
                    self._provider.endpoint(),
                    headers=self._provider.headers(),
                    json=payload,
                    timeout=httpx.Timeout(
                        timeout=self.request_timeout,
                        connect=min(self.request_timeout, 10.0),
                    ),
                )
            except httpx.TimeoutException:
                last_error_code = "provider_timeout"
                if attempt < MAX_ATTEMPTS:
                    await self._wait_before_retry(request_id, purpose, attempt, last_error_code)
                    continue
                break
            except httpx.RequestError:
                last_error_code = "provider_transport_error"
                if attempt < MAX_ATTEMPTS:
                    await self._wait_before_retry(request_id, purpose, attempt, last_error_code)
                    continue
                break

            if response.status_code in RETRYABLE_STATUS_CODES:
                last_error_code = "provider_temporarily_unavailable"
                if attempt < MAX_ATTEMPTS:
                    await self._wait_before_retry(
                        request_id,
                        purpose,
                        attempt,
                        last_error_code,
                        retry_after=response.headers.get("Retry-After"),
                    )
                    continue
                break
            if response.is_error:
                return self._finish(
                    request_id=request_id,
                    started_at=started_at,
                    purpose=purpose,
                    status="failed",
                    error_code=f"provider_http_{response.status_code}",
                )
            if len(response.content) > settings.LLM_RESPONSE_MAX_BYTES:
                return self._finish(
                    request_id=request_id,
                    started_at=started_at,
                    purpose=purpose,
                    status="failed",
                    error_code="provider_response_too_large",
                )

            try:
                envelope = decode_strict_json_object(response.text)
                content, response_error = self._provider.extract_content(envelope)
            except (TypeError, ValueError, KeyError):
                return self._finish(
                    request_id=request_id,
                    started_at=started_at,
                    purpose=purpose,
                    status="failed",
                    error_code="invalid_response_envelope",
                )

            if response_error:
                status: ModelCallStatus = "refused" if response_error == "model_refused" else "failed"
                return self._finish(
                    request_id=request_id,
                    started_at=started_at,
                    purpose=purpose,
                    status=status,
                    error_code=response_error,
                )
            if not content.strip():
                return self._finish(
                    request_id=request_id,
                    started_at=started_at,
                    purpose=purpose,
                    status="failed",
                    error_code="empty_model_output",
                )
            if len(content.encode("utf-8")) > settings.LLM_RESPONSE_MAX_BYTES:
                return self._finish(
                    request_id=request_id,
                    started_at=started_at,
                    purpose=purpose,
                    status="failed",
                    error_code="model_output_too_large",
                )

            if settings.LLM_TRACE_CONTENT:
                logger.debug(
                    "event=model_trace_response request_id=%s provider=%s model=%s purpose=%s content=%r",
                    request_id,
                    self.provider,
                    self.model,
                    purpose,
                    content,
                )
            try:
                decoded = decode_strict_json_object(content)
            except (TypeError, ValueError):
                return self._finish(
                    request_id=request_id,
                    started_at=started_at,
                    purpose=purpose,
                    status="failed",
                    error_code="invalid_model_json",
                )
            try:
                output = response_model.model_validate(decoded)
            except ValidationError:
                return self._finish(
                    request_id=request_id,
                    started_at=started_at,
                    purpose=purpose,
                    status="failed",
                    error_code="model_schema_invalid",
                )
            return self._finish(
                request_id=request_id,
                started_at=started_at,
                purpose=purpose,
                status="success",
                output=output,
            )

        return self._finish(
            request_id=request_id,
            started_at=started_at,
            purpose=purpose,
            status="failed",
            error_code=last_error_code,
        )

    async def _wait_before_retry(
        self,
        request_id: str,
        purpose: str,
        attempt: int,
        error_code: str,
        *,
        retry_after: str | None = None,
    ) -> None:
        delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                pass
        delay = max(0.0, min(delay, MAX_RETRY_DELAY_SECONDS))
        logger.warning(
            "event=model_call_retry request_id=%s provider=%s model=%s purpose=%s attempt=%s error_code=%s delay_seconds=%.1f",
            request_id,
            self.provider,
            self.model,
            purpose,
            attempt,
            error_code,
            delay,
        )
        await asyncio.sleep(delay)

    def _finish(
        self,
        *,
        request_id: str,
        started_at: float,
        purpose: str,
        status: ModelCallStatus,
        error_code: str | None = None,
        output: ModelOutputT | None = None,
    ) -> ModelCallResult[ModelOutputT]:
        logger.info(
            "event=model_call_finished request_id=%s provider=%s model=%s purpose=%s status=%s error_code=%s duration_ms=%s",
            request_id,
            self.provider,
            self.model,
            purpose,
            status,
            error_code or "none",
            round((perf_counter() - started_at) * 1000),
        )
        return ModelCallResult(
            status=status,
            output=output,
            error_code=error_code,
            request_id=request_id,
        )
