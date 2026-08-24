from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.contracts.backtest import BacktestEquityPointRecord, BacktestSignalRecord, BacktestTradeRecord


class BacktestExecutionEngine(Protocol):
    market_data_service: Any

    def execute(self, **kwargs: Any) -> Any:
        ...


class BacktestReportBuilder(Protocol):
    def build_report(self, **kwargs: Any) -> Any:
        ...

    def quote_currency(self, symbol: str) -> str:
        ...


class BacktestMarketDataReader(Protocol):
    def load_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Any:
        ...


class BacktestStrategyRuntime(Protocol):
    def validate_timeframe_compatibility(
        self,
        template: str,
        config: Any,
        base_timeframe: str,
    ) -> Any:
        ...

    def build_frame(
        self,
        template: str,
        config: Any,
        candles: list[list[float]],
        timeframe: str,
    ) -> Any:
        ...


class BacktestRunReader(Protocol):
    def list_runs(self, execution_mode: str = "backtest") -> list[dict[str, Any]]:
        ...

    def get_run(
        self,
        backtest_id: int,
        page: int,
        page_size: int,
        execution_mode: str | None = None,
    ) -> dict[str, Any] | None:
        ...

    def delete_run(self, backtest_id: int, execution_mode: str | None = None) -> bool:
        ...

    def list_active_run_ids(self, *, execution_mode: str, engine: str) -> list[int]:
        ...


class BacktestRunWriter(Protocol):
    def create_run(self, **kwargs: Any) -> int:
        ...

    def store_completed_result(self, **kwargs: Any) -> None:
        ...

    def get_run(self, run_id: int) -> Any | None:
        ...

    def mark_run_failed(self, *, run_id: int, metadata: dict[str, Any]) -> bool:
        ...


class FactorBacktestRunWriter(Protocol):
    def store_completed_rows(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        status: str,
        execution_mode: str,
        engine: str,
        total_candles: int,
        signals: list[BacktestSignalRecord],
        trades: list[BacktestTradeRecord],
        equity_curve: list[BacktestEquityPointRecord],
        metadata: dict[str, Any],
    ) -> int:
        ...


class PaperRunWriter(Protocol):
    def create_run(self, **kwargs: Any) -> int:
        ...

    def get_run(self, run_id: int) -> Any | None:
        ...

    def get_running_paper_run(self, *, run_id: int, engine: str) -> Any | None:
        ...

    def store_paper_snapshot(self, **kwargs: Any) -> None:
        ...

    def list_trade_records(self, run_id: int) -> list[BacktestTradeRecord]:
        ...

    def list_equity_records(self, run_id: int) -> list[BacktestEquityPointRecord]:
        ...

    def get_paper_run(self, *, run_id: int, engine: str) -> Any | None:
        ...

    def set_paper_status(self, **kwargs: Any) -> None:
        ...


class FactorPaperRunWriter(Protocol):
    def append_factor_paper_increment(self, **kwargs: Any) -> None:
        ...


class StrategyReader(Protocol):
    def get_editor_contract(self) -> dict[str, Any]:
        ...

    def list_templates(self) -> list[dict[str, Any]]:
        ...

    def list_indicators(self) -> list[dict[str, Any]]:
        ...

    def list_indicator_engines(self) -> list[dict[str, Any]]:
        ...

    def list_strategies(self) -> list[dict[str, Any]]:
        ...

    def get_strategy_version(self, strategy_key: str, version: int | None = None) -> Any:
        ...


class StrategyWriter(Protocol):
    def create_indicator(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def create_template(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def create_strategy_version(self, **kwargs: Any) -> Any:
        ...


class StrategyDefinitionStore(Protocol):
    def list_custom_indicators(self) -> list[dict[str, Any]]:
        ...

    def list_custom_templates(self) -> list[dict[str, Any]]:
        ...

    def list_strategy_definitions(self) -> list[dict[str, Any]]:
        ...

    def list_strategy_versions(self, strategy_key: str | None = None) -> list[dict[str, Any]]:
        ...

    def create_indicator(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def create_template(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def create_strategy_version(self, **kwargs: Any) -> dict[str, Any]:
        ...
