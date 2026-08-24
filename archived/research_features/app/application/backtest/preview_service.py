from __future__ import annotations

from app.application.backtest.ports import BacktestMarketDataReader, BacktestStrategyRuntime
from app.application.backtest.preview_artifact_store import StoredStrategyPreview, StrategyPreviewArtifactStore
from app.application.backtest.preview_payload_builder import BacktestPreviewPayloadBuilder, command_payload_for_preview
from app.contracts.backtest import BacktestPreviewCommand, StrategyVersionRecord
from app.domain.backtest.backtest_symbols import normalize_backtest_symbols
from utils.time_utils import to_utc_naive_datetime


class BacktestPreviewService:
    def __init__(
        self,
        *,
        market_data_service: BacktestMarketDataReader,
        strategy_runtime: BacktestStrategyRuntime,
        artifact_store: StrategyPreviewArtifactStore,
        payload_builder: BacktestPreviewPayloadBuilder | None = None,
    ) -> None:
        self.market_data_service = market_data_service
        self.runtime = strategy_runtime
        self.artifact_store = artifact_store
        self.payload_builder = payload_builder or BacktestPreviewPayloadBuilder()

    def build_preview(
        self,
        *,
        strategy: StrategyVersionRecord,
        command: BacktestPreviewCommand,
    ) -> dict:
        start_date = to_utc_naive_datetime(command.start_datetime)
        end_date = to_utc_naive_datetime(command.end_datetime)
        symbols = normalize_backtest_symbols(command.portfolio.symbols)
        selected_config = self.runtime.validate_timeframe_compatibility(
            strategy.template,
            strategy.config,
            command.timeframe,
        )
        symbol_rows: dict[str, list[list[float]]] = {}
        symbol_frames = {}
        symbol_missing_ranges = {}
        for symbol in symbols:
            range_result = self.market_data_service.load_ohlcv_range(
                symbol,
                command.timeframe,
                start_date,
                end_date,
            )
            symbol_rows[symbol] = range_result.rows
            symbol_missing_ranges[symbol] = range_result.missing_ranges
            symbol_frames[symbol] = self.runtime.build_frame(
                strategy.template,
                selected_config,
                range_result.rows,
                command.timeframe,
            )
        stored = self.payload_builder.build_preview(
            strategy=strategy,
            command=command,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            selected_config=selected_config,
            symbol_frames=symbol_frames,
            symbol_rows=symbol_rows,
            symbol_missing_ranges=symbol_missing_ranges,
        )
        self.artifact_store.save(stored)
        return stored.artifact

    def require_approved(
        self,
        *,
        preview_id: str,
        approved_fingerprint: str,
        strategy: StrategyVersionRecord,
        command: BacktestPreviewCommand,
    ) -> StoredStrategyPreview:
        stored = self.artifact_store.get(preview_id)
        if stored is None:
            raise ValueError("回测前必须先生成策略K线预览")
        if stored.fingerprint != approved_fingerprint:
            raise ValueError("策略预览已失效，请重新生成并确认")
        start_date = to_utc_naive_datetime(command.start_datetime)
        end_date = to_utc_naive_datetime(command.end_datetime)
        expected_payload = command_payload_for_preview(
            strategy=strategy,
            command=command,
            symbols=normalize_backtest_symbols(command.portfolio.symbols),
            start_date=start_date,
            end_date=end_date,
        )
        if stored.command_payload != expected_payload:
            raise ValueError("回测参数和已确认预览不一致，请重新生成预览")
        return stored
