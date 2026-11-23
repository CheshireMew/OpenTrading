from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from hashlib import sha256
import math
from typing import Any, Literal

from signal_lab.immutability import deep_freeze
from signal_lab.structured_data import canonical_json_bytes


AssetClass = Literal[
    "stock", "etf", "index", "crypto", "fx", "commodity", "macro", "unknown",
]
PriceBasis = Literal["raw", "adjusted", "both"]


@dataclass(frozen=True, slots=True)
class Instrument:
    canonical_code: str
    name: str
    asset_class: AssetClass
    market: str
    exchange: str
    currency: str
    timezone: str
    listed_on: date | None = None
    is_continuous: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.canonical_code or not self.name:
            raise ValueError("instrument code and name are required")
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class PriceBar:
    observed_at: datetime
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: float | None = None
    dividend: float = 0.0
    split_factor: float = 1.0

    def __post_init__(self) -> None:
        observed_at = self.observed_at
        if observed_at.tzinfo is None:
            raise ValueError("price bar timestamp must be timezone-aware")
        object.__setattr__(self, "observed_at", observed_at.astimezone(timezone.utc))
        for name in ("open", "high", "low", "close", "adjusted_close", "dividend", "split_factor"):
            object.__setattr__(self, name, float(getattr(self, name)))
        if self.volume is not None:
            object.__setattr__(self, "volume", float(self.volume))
        numeric = (self.open, self.high, self.low, self.close, self.adjusted_close)
        if not all(math.isfinite(value) and value > 0 for value in numeric):
            raise ValueError("OHLC and adjusted close must be finite and positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid OHLC bounds")
        if self.volume is not None and (not math.isfinite(self.volume) or self.volume < 0):
            raise ValueError("volume must be finite and non-negative")
        if not math.isfinite(self.dividend):
            raise ValueError("dividend must be finite")
        if not math.isfinite(self.split_factor) or self.split_factor <= 0:
            raise ValueError("split factor must be finite and positive")

    @property
    def observation_date(self) -> date:
        return self.observed_at.date()


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    instrument: Instrument
    timeframe: str
    provider: str
    requested_start: date
    requested_end: date
    retrieved_at: datetime
    bars: tuple[PriceBar, ...]
    source_snapshot_hash: str
    price_basis: PriceBasis = "both"
    provider_symbol: str | None = None
    coverage_status: Literal["complete", "partial", "unchecked"] = "unchecked"
    metadata: dict[str, Any] = field(default_factory=dict)
    identity_version: Literal[1, 2] = 2
    _persisted_snapshot_hash: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _snapshot_hash: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.timeframe != "1d" and not self.metadata.get("internal_timeframe"):
            raise ValueError("public price snapshots support only the 1d timeframe")
        if self.requested_start > self.requested_end:
            raise ValueError("requested start must not be after requested end")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(timezone.utc))
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))
        times = [bar.observed_at for bar in self.bars]
        if times != sorted(times) or len(times) != len(set(times)):
            raise ValueError("price bars must be unique and increasing")
        identity = {
            "schema_version": "signal-lab-price-snapshot.v2",
            "instrument": self.instrument.canonical_code,
            "timeframe": self.timeframe,
            "provider": self.provider,
            "provider_symbol": self.provider_symbol,
            "requested_start": self.requested_start.isoformat(),
            "requested_end": self.requested_end.isoformat(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "source_snapshot_hash": self.source_snapshot_hash,
            "price_basis": self.price_basis,
            "coverage_status": self.coverage_status,
            "metadata": self.metadata,
            "bars": [
                [
                    bar.observed_at.isoformat(), bar.open, bar.high, bar.low, bar.close,
                    bar.adjusted_close, bar.volume, bar.dividend, bar.split_factor,
                ]
                for bar in self.bars
            ],
        }
        computed = sha256(canonical_json_bytes(identity)).hexdigest()
        if self.identity_version == 1:
            persisted = self._persisted_snapshot_hash
            if (
                persisted is None
                or len(persisted) != 64
                or any(character not in "0123456789abcdef" for character in persisted)
            ):
                raise ValueError("legacy price snapshots require a valid persisted content hash")
            object.__setattr__(self, "_snapshot_hash", persisted)
        elif self.identity_version == 2:
            if self._persisted_snapshot_hash is not None:
                raise ValueError("current price snapshots cannot override their content hash")
            object.__setattr__(self, "_snapshot_hash", computed)
        else:
            raise ValueError(f"unsupported price snapshot identity version: {self.identity_version}")

    @property
    def snapshot_hash(self) -> str:
        return self._snapshot_hash

    @property
    def actual_start(self) -> date | None:
        return self.bars[0].observation_date if self.bars else None

    @property
    def actual_end(self) -> date | None:
        return self.bars[-1].observation_date if self.bars else None
