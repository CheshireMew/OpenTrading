from __future__ import annotations

from datetime import datetime, timezone

from app.domain.market.history.candles import Candle, CandleSeries, PriceSource, ensure_utc
from app.infra.market_data.binance_client import BinanceKlineClient
from app.infra.market_data.http import HttpPolicy, UrllibJsonTransport


class BinanceDataClient:
    def __init__(
        self,
        timeout: float = 30.0,
        transport: UrllibJsonTransport | None = None,
        kline_client: BinanceKlineClient | None = None,
    ) -> None:
        self.timeout = timeout
        self.transport = transport or UrllibJsonTransport(
            HttpPolicy(timeout_seconds=timeout),
        )
        self._client = kline_client or BinanceKlineClient(self.transport)

    def sync(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "15m",
    ) -> CandleSeries:
        start = ensure_utc(start)
        end = ensure_utc(end)
        if start >= end:
            raise ValueError("start must be earlier than end")
        perpetual = symbol.upper().endswith(":PERPETUAL")
        base_symbol = symbol.rsplit(":", 1)[0] if perpetual else symbol
        api_symbol = base_symbol.replace("/", "")
        source: PriceSource
        if perpetual:
            if not self._client.market_exists(api_symbol, spot=False):
                raise ValueError(f"symbol is unavailable on Binance perpetual markets: {base_symbol}")
            source = "perpetual"
            spot = False
        elif self._client.market_exists(api_symbol, spot=True):
            source = "spot"
            spot = True
        else:
            raise ValueError(
                f"symbol is unavailable on Binance spot: {symbol}; "
                "use an explicit :PERPETUAL instrument only when that contract is intended"
            )

        rows = self._client.download_klines(
            spot=spot,
            symbol=api_symbol,
            interval=timeframe,
            start_ms=int(start.timestamp() * 1000),
            end_ms=int(end.timestamp() * 1000),
        )
        candles = tuple(
            Candle(
                opened_at=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in rows
        )
        return CandleSeries(
            symbol=symbol,
            timeframe=timeframe,
            price_source=source,
            venue="binance",
            candles=candles,
        )
