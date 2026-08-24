from __future__ import annotations

from typing import Any

from app.contracts.dto.market_history import (
    CurrentPriceBatchItemResponse,
    CurrentPriceBatchResponse,
    CurrentPriceResponse,
    KlineTailResponse,
    MarketHistoryBatchItemResponse,
    MarketHistoryBatchResponse,
    MarketHistoryResponse,
    OhlcvPointResponse,
    RealtimeResponse,
    build_market_history_coverage,
)


def build_ohlcv_points(rows: list[list[float]]) -> list[OhlcvPointResponse]:
    return [
        OhlcvPointResponse(
            timestamp=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
        for row in rows
        if isinstance(row, list) and len(row) >= 6
    ]


def build_market_history_response(
    *,
    symbol: str,
    timeframe: str,
    rows: list[list[float]],
    missing_ranges: list[tuple[int, int]] | None = None,
) -> MarketHistoryResponse:
    return MarketHistoryResponse(
        symbol=symbol,
        timeframe=timeframe,
        items=build_ohlcv_points(rows),
        coverage=build_market_history_coverage(missing_ranges),
    )


def build_market_history_batch_response(
    *,
    timeframe: str,
    series_by_symbol: dict[str, tuple[list[list[float]], list[tuple[int, int]]]],
) -> MarketHistoryBatchResponse:
    return MarketHistoryBatchResponse(
        timeframe=timeframe,
        items=[
            MarketHistoryBatchItemResponse(
                symbol=symbol,
                items=build_ohlcv_points(rows),
                coverage=build_market_history_coverage(missing_ranges),
            )
            for symbol, (rows, missing_ranges) in series_by_symbol.items()
        ],
    )


def build_kline_tail_response(
    *,
    symbol: str,
    timeframe: str,
    timestamp: str,
    current_price: float | None,
    rows: list[list[float]],
) -> KlineTailResponse:
    return KlineTailResponse(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        current_price=current_price,
        kline_data=build_ohlcv_points(rows),
    )


def build_current_price_response(
    *,
    symbol: str,
    timeframe: str,
    timestamp: str,
    current_price: float | None,
) -> CurrentPriceResponse:
    return CurrentPriceResponse(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        current_price=current_price,
    )


def build_current_price_batch_item_response(
    *,
    symbol: str,
    timeframe: str,
    timestamp: str,
    current_price: float | None,
    source: str,
) -> CurrentPriceBatchItemResponse:
    return CurrentPriceBatchItemResponse(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        current_price=current_price,
        source=source,
    )


def build_current_price_batch_response(
    *,
    timeframe: str,
    items: list[CurrentPriceBatchItemResponse],
) -> CurrentPriceBatchResponse:
    return CurrentPriceBatchResponse(timeframe=timeframe, items=items)


def build_realtime_response(
    *,
    symbol: str,
    timestamp: str,
    current_price: float,
    indicators: dict[str, Any],
    ai_analysis: Any | None,
    rows: list[list[float]],
    timeframe: str | None,
    include_type: bool,
) -> RealtimeResponse:
    return RealtimeResponse(
        symbol=symbol,
        timestamp=timestamp,
        current_price=current_price,
        indicators=indicators,
        ai_analysis=ai_analysis,
        kline_data=build_ohlcv_points(rows),
        timeframe=timeframe,
        type="realtime" if include_type else None,
    )
