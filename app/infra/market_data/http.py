from __future__ import annotations

from dataclasses import dataclass
import logging
from time import sleep
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.product import APP_VERSION
from app.infra.structured_data import dumps_json, load_json_response, read_bounded_response


LOGGER = logging.getLogger("app.infra.market_data.http")
DEFAULT_USER_AGENT = f"OpenTrading/{APP_VERSION}"


@dataclass(frozen=True, slots=True)
class HttpPolicy:
    timeout_seconds: float = 60.0
    attempts: int = 3
    retry_delay_seconds: float = 0.5
    max_response_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("HTTP timeout must be positive")
        if self.attempts < 1:
            raise ValueError("HTTP attempts must be at least one")
        if self.retry_delay_seconds < 0:
            raise ValueError("HTTP retry delay cannot be negative")
        if self.max_response_bytes < 1:
            raise ValueError("HTTP response budget must be positive")


class JsonTransport(Protocol):
    def get_json(self, url: str, params: dict[str, str], headers: dict[str, str]) -> Any: ...


class HttpTransport(JsonTransport, Protocol):
    def get_bytes(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        *,
        max_response_bytes: int | None = None,
    ) -> bytes: ...


class UrllibJsonTransport:
    def __init__(self, policy: HttpPolicy | None = None) -> None:
        self.policy = policy or HttpPolicy()

    def get_json(self, url: str, params: dict[str, str], headers: dict[str, str]) -> Any:
        request = Request(_url_with_query(url, params), headers=_request_headers(headers))
        return read_json_request(request, policy=self.policy)

    def get_bytes(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        *,
        max_response_bytes: int | None = None,
    ) -> bytes:
        request = Request(
            _url_with_query(url, params or {}),
            headers=_request_headers(headers),
        )
        return read_request(
            request,
            policy=self.policy,
            max_response_bytes=max_response_bytes,
        )


def read_json_request(request: Request, *, policy: HttpPolicy | None = None) -> Any:
    effective = policy or HttpPolicy()
    return _request_with_retry(
        request,
        effective,
        lambda response: load_json_response(
            response,
            source=_safe_endpoint(request.full_url),
            budget=_json_budget(effective.max_response_bytes),
        ),
    )


def read_request(
    request: Request,
    *,
    policy: HttpPolicy | None = None,
    max_response_bytes: int | None = None,
) -> bytes:
    effective = policy or HttpPolicy()
    limit = max_response_bytes or effective.max_response_bytes
    return _request_with_retry(
        request,
        effective,
        lambda response: read_bounded_response(
            response,
            source=_safe_endpoint(request.full_url),
            max_bytes=limit,
        ),
    )


def _request_with_retry(request: Request, policy: HttpPolicy, reader: Any) -> Any:
    endpoint = _safe_endpoint(request.full_url)
    for attempt in range(1, policy.attempts + 1):
        try:
            with urlopen(request, timeout=policy.timeout_seconds) as response:  # noqa: S310
                return reader(response)
        except HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt == policy.attempts:
                _log_failure(endpoint, attempt, policy.attempts, exc)
                raise
            _log_retry(endpoint, attempt, policy.attempts, exc)
        except (TimeoutError, URLError, OSError) as exc:
            if attempt == policy.attempts:
                _log_failure(endpoint, attempt, policy.attempts, exc)
                raise
            _log_retry(endpoint, attempt, policy.attempts, exc)
        sleep(policy.retry_delay_seconds * (2 ** (attempt - 1)))
    raise RuntimeError("HTTP retry loop ended without a result")


def _log_retry(endpoint: str, attempt: int, attempts: int, error: Exception) -> None:
    LOGGER.warning(dumps_json({
        "schema_version": "signal-lab.http-client-log.v1",
        "event": "http_retry",
        "endpoint": endpoint,
        "attempt": attempt,
        "attempts": attempts,
        "error_type": type(error).__name__,
    }))


def _log_failure(endpoint: str, attempt: int, attempts: int, error: Exception) -> None:
    LOGGER.error(dumps_json({
        "schema_version": "signal-lab.http-client-log.v1",
        "event": "http_failure",
        "endpoint": endpoint,
        "attempt": attempt,
        "attempts": attempts,
        "error_type": type(error).__name__,
    }))


def _safe_endpoint(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _url_with_query(url: str, params: dict[str, str]) -> str:
    if not params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def _request_headers(headers: dict[str, str] | None) -> dict[str, str]:
    return {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}


def _json_budget(max_bytes: int):
    from app.infra.structured_data import DEFAULT_JSON_BUDGET, JsonBudget

    return JsonBudget(
        max_bytes=max_bytes,
        max_depth=DEFAULT_JSON_BUDGET.max_depth,
        max_nodes=DEFAULT_JSON_BUDGET.max_nodes,
        max_string_chars=DEFAULT_JSON_BUDGET.max_string_chars,
        max_number_chars=DEFAULT_JSON_BUDGET.max_number_chars,
        max_exponent=DEFAULT_JSON_BUDGET.max_exponent,
    )
