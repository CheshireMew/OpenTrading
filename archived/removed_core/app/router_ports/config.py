from __future__ import annotations

from typing import Any, Protocol


class DatabaseRuntimePort(Protocol):
    engine: Any
    source: str


class CurrencyRatePort(Protocol):
    async def get_rates(self) -> dict[str, Any]: ...


class LlmConfigPort(Protocol):
    def read_config(self) -> dict[str, Any]: ...
    def save_config(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class FredApiConfigPort(Protocol):
    def read_config(self) -> dict[str, Any]: ...
    def save_config(self, payload: dict[str, Any]) -> dict[str, Any]: ...
