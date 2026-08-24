from __future__ import annotations

from typing import Protocol


class IndicatorProvider(Protocol):
    async def fetch_data(self) -> list[object]:
        ...


class MarketIndicatorWriter(Protocol):
    def upsert_points(self, data_points: list[object], indicator_meta: dict[str, tuple[str, str, str]]) -> None:
        ...

    def get_latest_timestamps(self, indicator_ids: list[str]) -> dict[str, object]:
        ...
