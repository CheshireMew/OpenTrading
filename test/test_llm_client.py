from __future__ import annotations

import json
import io
import logging

import httpx
import pytest

from app.application.model_contracts import TradeSetupModelOutput
from app.infra.llm_client import LLMClient, LLMClientFactory
from config import settings
from utils.logger import logger


def llm_config(provider: str, structured_output_mode: str) -> dict[str, str]:
    return {
        "provider": provider,
        "apiKey": "sk-valid-test-key",
        "baseUrl": "https://model.example/v1",
        "modelId": "test-model",
        "structuredOutputMode": structured_output_mode,
    }


def valid_trade_plan() -> dict[str, object]:
    return {
        "side": "LONG",
        "entry": 100.0,
        "target": 120.0,
        "stop": 90.0,
        "confidence": 75,
        "reason": "趋势和动量一致",
    }


class StaticLlmConfigService:
    def read_effective_config(self):
        return llm_config("openai", "json_schema")


@pytest.mark.asyncio
async def test_factory_reuses_one_http_connection_pool():
    factory = LLMClientFactory(StaticLlmConfigService())
    try:
        first = factory()
        second = factory()
        assert first._http_client is second._http_client
    finally:
        await factory.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_request_uses_json_schema_and_validates_output():
    requests: list[dict[str, object]] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(valid_trade_plan(), ensure_ascii=False)},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        client = LLMClient(llm_config("openai", "json_schema"), http_client=http_client)
        result = await client.analyze(
            "请返回 JSON",
            response_model=TradeSetupModelOutput,
            purpose="trade_setup",
        )

    assert result.succeeded is True
    assert result.output is not None and result.output.side == "LONG"
    response_format = requests[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False


@pytest.mark.asyncio
async def test_deepseek_request_uses_official_json_object_mode():
    requests: list[dict[str, object]] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(valid_trade_plan())}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        client = LLMClient(llm_config("deepseek", "json_object"), http_client=http_client)
        result = await client.analyze(
            "return JSON",
            response_model=TradeSetupModelOutput,
            purpose="trade_setup",
        )

    assert result.succeeded is True
    assert requests[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_anthropic_request_uses_output_config_and_maps_refusal():
    requests: list[dict[str, object]] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"stop_reason": "refusal", "content": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        client = LLMClient(llm_config("anthropic", "anthropic_json_schema"), http_client=http_client)
        result = await client.analyze(
            "return JSON",
            response_model=TradeSetupModelOutput,
            purpose="trade_setup",
        )

    assert result.status == "refused"
    assert result.error_code == "model_refused"
    assert requests[0]["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_invalid_json_is_not_retried_and_has_stable_error_code():
    request_count = 0

    async def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        client = LLMClient(llm_config("openai", "json_schema"), http_client=http_client)
        result = await client.analyze(
            "return JSON",
            response_model=TradeSetupModelOutput,
            purpose="trade_setup",
        )

    assert request_count == 1
    assert result.status == "failed"
    assert result.error_code == "invalid_model_json"


@pytest.mark.asyncio
async def test_schema_violation_and_missing_configuration_remain_distinguishable():
    async def handle(_request: httpx.Request) -> httpx.Response:
        invalid_plan = valid_trade_plan() | {"confidence": 120}
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(invalid_plan)}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        configured = LLMClient(llm_config("openai", "json_schema"), http_client=http_client)
        schema_result = await configured.analyze(
            "return JSON",
            response_model=TradeSetupModelOutput,
            purpose="trade_setup",
        )

        missing = LLMClient(llm_config("openai", "json_schema") | {"apiKey": ""}, http_client=http_client)
        missing_result = await missing.analyze(
            "return JSON",
            response_model=TradeSetupModelOutput,
            purpose="trade_setup",
        )

    assert schema_result.error_code == "model_schema_invalid"
    assert missing_result.status == "unavailable"
    assert missing_result.error_code == "model_not_configured"


@pytest.mark.asyncio
async def test_normal_model_logs_exclude_prompt_and_response_content(monkeypatch):
    secret_prompt = "PROMPT_SECRET_92374"  # gitleaks:allow
    secret_reason = "RESPONSE_SECRET_81364"
    plan = valid_trade_plan() | {"reason": secret_reason}

    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}]},
        )

    monkeypatch.setattr(settings, "LLM_TRACE_CONTENT", False)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    previous_disabled = logger.disabled
    previous_level = logger.level
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
            client = LLMClient(llm_config("openai", "json_schema"), http_client=http_client)
            result = await client.analyze(
                secret_prompt,
                response_model=TradeSetupModelOutput,
                purpose="trade_setup",
            )
    finally:
        logger.removeHandler(handler)
        logger.disabled = previous_disabled
        logger.setLevel(previous_level)

    captured = stream.getvalue()
    assert result.succeeded is True
    assert "event=model_call_finished" in captured
    assert secret_prompt not in captured
    assert secret_reason not in captured
