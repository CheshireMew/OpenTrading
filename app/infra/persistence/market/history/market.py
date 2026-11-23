from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from app.domain.market.history.candles import PriceSource

from app.domain.market.history.models import Instrument, PriceBar, PriceSnapshot
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.price_repository import PriceRepository


class MarketDataStore:
    """Canonical SQLite repository for normalized OHLCV series."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        database = MarketHistoryDatabase(self.root)
        self.path = database.location
        self._repository = PriceRepository(database)

    def save(self, series: Any, *, source_note: str | None = None) -> str:
        if not series.candles:
            raise ValueError(f"cannot save an empty market series for {series.symbol}")
        canonical_code = _canonical_code(series.symbol, series.venue)
        instrument = Instrument(
            canonical_code=canonical_code,
            name=series.symbol,
            asset_class="crypto" if "/" in series.symbol else "unknown",
            market="crypto" if "/" in series.symbol else series.venue,
            exchange=series.venue,
            currency=series.symbol.split("/")[-1] if "/" in series.symbol else "unknown",
            timezone="UTC",
        )
        snapshot = PriceSnapshot(
            instrument=instrument,
            timeframe=series.timeframe,
            provider=series.price_source,
            provider_symbol=series.symbol,
            requested_start=series.candles[0].opened_at.date(),
            requested_end=series.candles[-1].opened_at.date(),
            retrieved_at=series.candles[-1].opened_at,
            source_snapshot_hash=series.data_hash,
            price_basis="raw",
            coverage_status="unchecked",
            metadata={
                "internal_timeframe": series.timeframe != "1d",
                "price_source": series.price_source,
                "venue": series.venue,
                "source_note": source_note,
            },
            bars=tuple(
                PriceBar(
                    observed_at=item.opened_at, open=item.open, high=item.high, low=item.low,
                    close=item.close, adjusted_close=item.close, volume=item.volume,
                )
                for item in series.candles
            ),
        )
        return self._repository.save_price_snapshot(snapshot)

    def load(self, symbol: str, timeframe: str) -> Any:
        from app.domain.market.history.candles import Candle, CandleSeries

        canonical_code = _canonical_code(symbol, "binance" if "/" in symbol else None)
        snapshot = self._repository.load_price_snapshot(canonical_code, timeframe=timeframe)
        if snapshot.timeframe != timeframe:
            raise FileNotFoundError(f"market series does not exist: {symbol} {timeframe}")
        metadata = snapshot.metadata
        price_source = str(metadata.get("price_source", snapshot.provider))
        if price_source not in {"spot", "perpetual"}:
            raise ValueError(f"unsupported market price source: {price_source}")
        series = CandleSeries(
            symbol=snapshot.provider_symbol,
            timeframe=snapshot.timeframe,
            price_source=cast(PriceSource, price_source),
            venue=str(metadata.get("venue", snapshot.instrument.exchange)),
            candles=tuple(
                Candle(
                    opened_at=bar.observed_at, open=bar.open, high=bar.high,
                    low=bar.low, close=bar.close, volume=bar.volume or 0.0,
                )
                for bar in snapshot.bars
            ),
        )
        if series.data_hash != snapshot.source_snapshot_hash:
            raise ValueError(f"market data hash mismatch: {symbol} {timeframe}")
        return series

    def inventory(self) -> list[dict[str, Any]]:
        return self._repository.price_inventory()


def _canonical_code(symbol: str, venue: str | None) -> str:
    if "/" in symbol:
        return f"{symbol.upper()}@{(venue or 'UNKNOWN').upper()}"
    return symbol.upper()
