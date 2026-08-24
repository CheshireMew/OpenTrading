from __future__ import annotations

from datetime import datetime
from typing import Any

from app.domain.market.symbol_catalog import get_supported_crypto_symbols
from app.exceptions import NotFoundError
from app.services.market.market_data_service import MarketDataService
from app.services.persistence_ports import FactorResearchRepositoryPort, IndicatorRepositoryPort
from app.infra.executor import run_compute, run_database

from .analysis_service import FactorAnalysisService
from .catalog_service import FactorCatalogService
from .contracts import DEFAULT_CLEANING, DEFAULT_FORWARD_HORIZONS, SUPPORTED_TIMEFRAMES
from .dataset_service import FactorDatasetService
from .frame_builder import FactorFrameBuilder
from .math_utils import FactorMath


class FactorResearchService:
    def __init__(
        self,
        *,
        market_data_service: MarketDataService,
        indicator_repository: IndicatorRepositoryPort,
        repository: FactorResearchRepositoryPort,
    ) -> None:
        self.market_data_service = market_data_service
        self.indicator_repository = indicator_repository
        self.repository = repository
        self.math = FactorMath(DEFAULT_CLEANING)
        self.catalog_service = FactorCatalogService(self.indicator_repository)
        self.frame_builder = FactorFrameBuilder(
            market_data_service=self.market_data_service,
            indicator_repository=self.indicator_repository,
            math=self.math,
        )
        self.dataset_service = FactorDatasetService(
            repository=self.repository,
            frame_builder=self.frame_builder,
            math=self.math,
        )
        self.analysis_service = FactorAnalysisService(self.math)

    def get_catalog(self) -> dict[str, Any]:
        return self.catalog_service.get_catalog()

    async def get_catalog_async(self) -> dict[str, Any]:
        return await run_database(self.get_catalog)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.repository.list_research_runs(limit=limit)

    async def list_runs_async(self, limit: int = 20) -> list[dict[str, Any]]:
        return await run_database(lambda: self.list_runs(limit=limit))

    def get_run(self, run_id: int) -> dict[str, Any]:
        row = self._get_run_record(run_id)
        if row is None:
            raise NotFoundError("Factor run not found")
        return row

    async def get_run_async(self, run_id: int) -> dict[str, Any]:
        return await run_database(lambda: self.get_run(run_id))

    def build_stored_blend_frame(self, run_id: int):
        run = self._get_run_record(run_id)
        if not run:
            raise ValueError("因子研究记录不存在。")
        return run, self.dataset_service.build_stored_blend_frame(run)

    def build_live_blend_frame(self, run_id: int, *, end_date: datetime | None = None):
        run = self._get_run_record(run_id)
        if not run:
            raise ValueError("因子研究记录不存在。")
        selected_factor_ids = [item["factor_id"] for item in (run.get("blend") or {}).get("selected_factors") or []]
        definitions = self.catalog_service.select_factors([], selected_factor_ids)
        if not definitions:
            raise ValueError("当前研究记录没有可执行的组合因子。")
        return run, self.dataset_service.build_live_blend_frame(
            run=run,
            definitions=definitions,
            end_date=end_date,
        )

    def analyze(
        self,
        *,
        symbol: str,
        timeframe: str,
        days: int,
        horizon_bars: int,
        max_lag_bars: int,
        categories: list[str] | None = None,
        factor_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        supported_symbols = get_supported_crypto_symbols()
        if symbol not in supported_symbols:
            raise ValueError(f"无效交易对。可选: {supported_symbols}")
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"当前只支持这些周期: {list(SUPPORTED_TIMEFRAMES)}")

        selected_categories = list(categories or [])
        selected_factor_ids = list(factor_ids or [])
        definitions = self.catalog_service.select_factors(selected_categories, selected_factor_ids)
        if not definitions:
            raise ValueError("没有可研究的因子，请至少选择一个分类或因子。")

        forward_horizons = sorted({*DEFAULT_FORWARD_HORIZONS, int(horizon_bars)})
        dataset = self.dataset_service.load_or_build_dataset(
            symbol=symbol,
            timeframe=timeframe,
            days=days,
            primary_horizon=horizon_bars,
            forward_horizons=forward_horizons,
            categories=selected_categories,
            definitions=definitions,
            cleaning=DEFAULT_CLEANING,
        )
        frame = self.frame_builder.rows_to_frame(self.repository.get_dataset_rows(dataset["id"]), forward_horizons)
        if frame.empty:
            raise ValueError("可用因子样本不足，暂时无法完成研究。")

        factor_results: list[dict[str, Any]] = []
        for definition in definitions:
            factor_result = self.analysis_service.analyze_factor(
                definition=definition,
                frame=frame,
                primary_horizon=horizon_bars,
                forward_horizons=forward_horizons,
                max_lag_bars=max_lag_bars,
            )
            if factor_result:
                factor_results.append(factor_result)

        if not factor_results:
            raise ValueError("可用因子样本不足，暂时无法完成研究。")

        factor_results.sort(key=lambda item: item["scorecard"]["score"], reverse=True)
        blend = self.analysis_service.build_blend(
            factor_results=factor_results,
            primary_horizon=horizon_bars,
            forward_horizons=forward_horizons,
        )
        summary = self.analysis_service.build_summary(
            dataset=dataset,
            symbol=symbol,
            timeframe=timeframe,
            days=days,
            primary_horizon=horizon_bars,
            max_lag_bars=max_lag_bars,
            factor_count=len(factor_results),
            blend=blend,
        )
        run = self.repository.create_research_run(
            dataset_id=dataset["id"],
            request_payload={
                "symbol": symbol,
                "timeframe": timeframe,
                "days": days,
                "horizon_bars": horizon_bars,
                "max_lag_bars": max_lag_bars,
                "categories": selected_categories,
                "factor_ids": selected_factor_ids,
                "forward_horizons": forward_horizons,
            },
            summary=summary,
            ranking=[item["scorecard"] for item in factor_results],
            details=[item["detail"] for item in factor_results],
            blend=blend,
        )
        return {
            "run_id": run["id"],
            "dataset_id": dataset["id"],
            "summary": summary,
            "ranking": [item["scorecard"] for item in factor_results],
            "details": [item["detail"] for item in factor_results],
            "blend": blend,
        }

    async def analyze_async(
        self,
        *,
        symbol: str,
        timeframe: str,
        days: int,
        horizon_bars: int,
        max_lag_bars: int,
        categories: list[str] | None = None,
        factor_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return await run_compute(
            lambda: self.analyze(
                symbol=symbol,
                timeframe=timeframe,
                days=days,
                horizon_bars=horizon_bars,
                max_lag_bars=max_lag_bars,
                categories=categories,
                factor_ids=factor_ids,
            )
        )

    def _get_run_record(self, run_id: int) -> dict[str, Any] | None:
        return self.repository.get_research_run(run_id)
