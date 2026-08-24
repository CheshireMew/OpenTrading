from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from app.application.errors import InvalidRequestError

from app.infra.cache import RedisService, optional_cache_aget, optional_cache_aset
from app.domain.market.index_catalog import get_index_instrument
from app.services.market.symbol_catalog import get_supported_crypto_symbols, resolve_market_asset
from app.infra.executor import run_tool
from app.contracts.tools import ComparePairsCommand, DCA_MAX_DAYS, DCA_STRATEGY_KEYS, SimulateDcaCommand
from app.services.tools.dca_service import DCAService
from app.services.tools.pair_compare_service import PairCompareService
from config import settings
from utils.logger import logger
from utils.time import now_in_timezone


class ToolsAppService:
    def __init__(
        self,
        dca_service: DCAService,
        pair_compare_service: PairCompareService,
        cache_service: RedisService | None = None,
    ) -> None:
        self.dca_service = dca_service
        self.pair_compare_service = pair_compare_service
        self.cache_service = cache_service

    @staticmethod
    def _dca_cache_key(command: SimulateDcaCommand, start_date_str: str) -> str:
        raw = (
            f"{command.symbol}:{start_date_str}:{command.amount}:{command.investment_time}:"
            f"{command.timezone}:{command.strategy}:{json.dumps(command.strategy_params or {}, sort_keys=True)}"
        )
        return f"dca:{hashlib.md5(raw.encode()).hexdigest()}"

    def _validate_dca(self, command: SimulateDcaCommand) -> None:
        resolved_asset = resolve_market_asset(command.symbol)
        if resolved_asset is None or resolved_asset["asset_class"] == "cash":
            raise InvalidRequestError("无效标的")
        if command.strategy not in DCA_STRATEGY_KEYS:
            raise InvalidRequestError(f"无效策略。可选: {list(DCA_STRATEGY_KEYS)}")

    def _validate_compare(self, command: ComparePairsCommand) -> tuple[str, str]:
        symbol_a = command.symbol_a.upper()
        symbol_b = command.symbol_b.upper()
        valid_symbols = set(get_supported_crypto_symbols())
        valid_bases = {symbol.split("/")[0] for symbol in valid_symbols}
        if symbol_a not in valid_bases and symbol_a not in valid_symbols and get_index_instrument(symbol_a) is None:
            raise InvalidRequestError(f"无效标的 {symbol_a}")
        if symbol_b not in valid_bases and symbol_b not in valid_symbols and get_index_instrument(symbol_b) is None:
            raise InvalidRequestError(f"无效标的 {symbol_b}")
        if symbol_a == symbol_b:
            raise InvalidRequestError("两个标的不能相同")
        return symbol_a, symbol_b

    async def simulate_dca(self, command: SimulateDcaCommand) -> dict:
        self._validate_dca(command)
        try:
            today = now_in_timezone(command.timezone).date()
        except Exception as exc:
            raise InvalidRequestError("无效时区") from exc
        start_date = command.start_date or (today - timedelta(days=command.days or 365))
        if start_date > today:
            raise InvalidRequestError("定投开始日期不能晚于今天")
        if (today - start_date).days > DCA_MAX_DAYS:
            raise InvalidRequestError(f"定投历史范围不能超过 {DCA_MAX_DAYS} 天")
        start_date_str = start_date.isoformat()
        cache_key = self._dca_cache_key(command, start_date_str)
        cached = await optional_cache_aget(self.cache_service, cache_key)
        if cached:
            return cached

        result = await run_tool(
            lambda: self.dca_service.calculate_dca(
                symbol=command.symbol,
                start_date_str=start_date_str,
                end_date_str=None,
                daily_investment=command.amount,
                target_time_str=command.investment_time,
                timezone=command.timezone,
                strategy=command.strategy,
                strategy_params=command.strategy_params,
            ),
        )
        if "error" in result:
            raise InvalidRequestError(str(result.get("error")))
        await optional_cache_aset(
            self.cache_service,
            cache_key,
            result,
            ttl=settings.DCA_CACHE_TTL,
            default_ttl=settings.DCA_CACHE_TTL,
        )
        return result

    async def compare_pairs(self, command: ComparePairsCommand) -> dict:
        symbol_a, symbol_b = self._validate_compare(command)
        logger.info(f"标的对比请求: {symbol_a} vs {symbol_b}, {command.days}天, {command.timeframe}")
        result = await run_tool(
            lambda: self.pair_compare_service.compare_pairs(symbol_a, symbol_b, command.days, command.timeframe),
        )
        if "error" in result:
            raise InvalidRequestError(str(result.get("error")))
        return result
