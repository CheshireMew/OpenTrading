from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.services.market.symbol_catalog import resolve_market_asset
from app.services.market.market_data_service import MarketDataService
from app.services.market.index_data_service import IndexDataService
from app.services.sentiment_service import SentimentService
from config import settings
from utils.logger import logger
from utils.time import now_in_timezone, to_utc


class DCAService:
    def __init__(
        self,
        market_data_service: MarketDataService | None = None,
        sentiment_service: SentimentService | None = None,
        index_data_service: IndexDataService | None = None,
    ) -> None:
        if market_data_service is None or sentiment_service is None or index_data_service is None:
            raise ValueError("DCAService 需要显式注入 market_data_service、sentiment_service 和 index_data_service")
        self.market_data_service = market_data_service
        self.sentiment_service = sentiment_service
        self.index_data_service = index_data_service

    def calculate_dca(
        self,
        *,
        symbol: str,
        start_date_str: str,
        end_date_str: str | None,
        daily_investment: float,
        target_time_str: str = "23:00",
        timezone: str = "Asia/Shanghai",
        strategy: str = "standard",
        strategy_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            from app.services.tools.dca_calculator import prepare_dca_dataset, simulate_dca_schedule

            target_h, target_m = map(int, target_time_str.split(":"))
            now_local = now_in_timezone(timezone)

            start_dt_local = datetime.strptime(start_date_str, "%Y-%m-%d")
            current_end = not end_date_str
            if end_date_str:
                end_dt_local = datetime.strptime(end_date_str, "%Y-%m-%d")
                if end_dt_local.date() == now_local.date():
                    current_end = True
                    end_dt_local = now_local.replace(tzinfo=None)
                else:
                    end_dt_local = end_dt_local.replace(hour=23, minute=59, second=59)
            else:
                end_dt_local = now_local.replace(tzinfo=None)

            logger.info(
                f"计算定投: {symbol}, 日投 {daily_investment}, {start_dt_local} - {end_dt_local} (Local), 时区 {timezone}"
            )

            buffer_days = settings.DCA_INDICATOR_BUFFER_DAYS
            fetch_start_utc = to_utc(start_dt_local - timedelta(days=buffer_days + 1), timezone)
            fetch_end_local = end_dt_local if current_end else end_dt_local + timedelta(days=1)
            fetch_end_utc = to_utc(fetch_end_local, timezone)
            if current_end:
                fetch_end_utc = fetch_end_utc.replace(minute=0, second=0, microsecond=0)
            resolved_asset = resolve_market_asset(symbol)
            if not resolved_asset or resolved_asset["asset_class"] == "cash":
                return {"error": "无效标的"}

            normalized_symbol = resolved_asset["symbol"]
            is_index = resolved_asset["asset_class"] == "index"
            if is_index and strategy in {"ahr999", "fear_greed"}:
                return {"error": "指数定投不支持 AHR999 或恐惧贪婪策略"}
            if is_index:
                index_pricing = self.index_data_service.get_pricing_history(
                    symbol=normalized_symbol,
                    timeframe="1d",
                    start_date=fetch_start_utc.strftime("%Y-%m-%d"),
                    end_date=fetch_end_utc.strftime("%Y-%m-%d"),
                )
                klines = [
                    [point.timestamp, point.open, point.high, point.low, point.close, point.volume]
                    for point in index_pricing.data
                ]
            else:
                klines = self.market_data_service.load_ohlcv_range(
                    normalized_symbol,
                    "1h",
                    fetch_start_utc,
                    fetch_end_utc,
                ).require_complete(symbol=normalized_symbol, timeframe="1h")
            if not klines:
                return {"error": "该时间段无数据"}

            target_klines = prepare_dca_dataset(
                klines,
                timezone=timezone,
                start_dt_local=start_dt_local,
                target_hour=None if is_index else target_h,
            )

            sentiment_map: dict[str, int] = {}
            if strategy == "fear_greed":
                sentiment_map = self.sentiment_service.get_sentiment_history(start_dt_local, end_dt_local)

            history, total_invested, total_coins = simulate_dca_schedule(
                target_klines,
                daily_investment=daily_investment,
                strategy=strategy,
                strategy_params=strategy_params,
                sentiment_map=sentiment_map,
            )

            if not history:
                return {"error": "无符合时间的数据点 (可能数据太短)"}

            uses_synthetic_btc_history = (
                not is_index
                and normalized_symbol == "BTC/USDT"
                and "timestamp" in target_klines.columns
                and not target_klines.empty
                and int(target_klines["timestamp"].min()) < settings.BTC_SYNTHETIC_HISTORY_CUTOFF_TS
            )

            if is_index:
                current_price = klines[-1][4]
            else:
                try:
                    latest = self.market_data_service.get_recent_candles(normalized_symbol, "1m", limit=1)
                    current_price = float(latest[-1][4]) if latest and len(latest[-1]) > 4 else history[-1]["price"]
                except Exception as exc:
                    logger.warning(f"无法获取实时价格，降级使用最后一次定投价格: {exc}")
                    current_price = history[-1]["price"]

            final_value = total_coins * current_price
            profit_loss = final_value - total_invested
            roi_percent = (profit_loss / total_invested) * 100 if total_invested > 0 else 0
            return {
                "symbol": normalized_symbol,
                "asset_class": "index" if is_index else "crypto",
                "price_basis": "proxy_etf" if is_index else "spot",
                "pricing_symbol": index_pricing.pricing_symbol if is_index else normalized_symbol,
                "pricing_name": index_pricing.pricing_name if is_index else normalized_symbol,
                "pricing_currency": index_pricing.pricing_currency if is_index else "USDT",
                "data_quality": (
                    "index_proxy"
                    if is_index
                    else "synthetic_and_exchange_proxy"
                    if uses_synthetic_btc_history
                    else "exchange"
                ),
                "start_date": start_date_str,
                "end_date": end_dt_local.strftime("%Y-%m-%d"),
                "target_time": target_time_str,
                "total_days": len(history),
                "total_invested": round(total_invested, 2),
                "final_value": round(final_value, 2),
                "total_coins": round(total_coins, 6),
                "roi": round(roi_percent, 2),
                "average_cost": round(history[-1]["avg_cost"], 2),
                "profit_loss": round(profit_loss, 2),
                "current_price": current_price,
                "history": history,
            }
        except Exception as exc:
            logger.error(f"DCA Error: {exc}", exc_info=True)
            return {"error": "定投所需行情暂时不完整，请稍后重试"}
