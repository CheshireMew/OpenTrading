from __future__ import annotations

from dataclasses import asdict
from collections.abc import Iterable
from typing import Any

from app.domain.market.history.models import Instrument


class CatalogRecord:
    def __init__(
        self,
        instrument: Instrument,
        aliases: Iterable[tuple[str, str]],
        provider_mappings: dict[str, str],
        *,
        priority: int = 0,
    ) -> None:
        self.instrument = instrument
        self.aliases = set(aliases)
        self.provider_mappings = dict(provider_mappings)
        self.priority = priority


def instrument_payload(instrument: Instrument) -> dict[str, Any]:
    payload = asdict(instrument)
    payload["listed_on"] = instrument.listed_on.isoformat() if instrument.listed_on else None
    return payload
