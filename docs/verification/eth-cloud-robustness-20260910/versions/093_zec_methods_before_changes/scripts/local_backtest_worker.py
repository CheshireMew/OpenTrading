"""One run per process; invoked only by the existing background runtime."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import sys
import time
import traceback
from pathlib import Path
from app.infra.research_files import file_hash

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.local_backtest import simulate, validate_bars
from app.domain.backtest_history import validate_observed_bars
from app.domain.market.constants import timeframe_to_milliseconds
from app.infra.db import build_database_runtime
from app.infra.persistence.market.kline_store import KlineStore
from app.services.local_backtest_service import LocalBacktestService, write_json
from app.services.local_backtest_strategies import digest, load_strategy, environment, validate_parameters
from app.services.market.exchange_gateway import ExchangeGateway
from app.services.market.market_data_service import MarketDataService
from config import settings


def execute(service, identifier, market_data=None):
    print(f"准备回测 {identifier}", flush=True)
    repo = service.repository
    run = repo.get(identifier)
    folder = service.directory(identifier)
    command = LocalBacktestCommand.model_validate(run["config"])
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    if metadata["environment"] != environment():
        raise ValueError("引擎或依赖版本已变化，请重新创建任务")
    if metadata.get('engine_code_hash') and metadata['engine_code_hash'] != file_hash(Path(__file__).parents[1] / 'app/domain/local_backtest.py'):
        raise ValueError('引擎代码与研究冻结时不同，请另建版本')
    if digest((folder / "strategy.py").read_bytes()) != metadata["strategy_hash"]:
        raise ValueError("策略快照校验失败")
    strategy, spec = load_strategy(folder / "strategy.py")
    parameters = validate_parameters(spec, command.parameters)
    step = timeframe_to_milliseconds(command.timeframe)
    start, end = int(command.start.timestamp() * 1000), int(command.end.timestamp() * 1000)
    snapshot = folder / "data.json"
    if snapshot.exists():
        raw = snapshot.read_bytes()
        if digest(raw) != metadata.get("data_hash"):
            raise ValueError("数据快照校验失败")
        rows = json.loads(raw)
    else:
        if run["parent_id"]:
            raise ValueError("重跑缺少原始数据快照，拒绝重新下载")
        if market_data is None:
            market_data = MarketDataService(exchange_gateway=ExchangeGateway(metadata["source"]["exchange"]),
                                           kline_store=KlineStore(database_runtime=repo.database))
        result = market_data.load_ohlcv_range(command.symbol, command.timeframe,
            datetime.fromtimestamp((start - spec.warmup_bars * step) / 1000, timezone.utc),
            datetime.fromtimestamp((end - 1) / 1000, timezone.utc))
        rows = result.rows if command.data_gap_policy == 'observed_bars' else result.require_complete(symbol=command.symbol, timeframe=command.timeframe)
    gaps = []
    if command.data_gap_policy == 'observed_bars':
        bars, gaps = validate_observed_bars(rows, start, end, step, spec.warmup_bars, int(time.time() * 1000))
    else:
        bars = validate_bars(rows, start, end, step, spec.warmup_bars, int(time.time() * 1000))
    print(f"行情检查通过：{len(bars)} 根，预热 {spec.warmup_bars} 根", flush=True)
    if not snapshot.exists():
        write_json(snapshot, rows)
    metadata.update(data_hash=digest(snapshot.read_bytes()), data_start=bars[0].timestamp,
                    data_end=end, candle_count=len(bars), warmup_bars=spec.warmup_bars)
    if command.data_gap_policy == 'observed_bars':
        metadata.update(data_gap_policy=command.data_gap_policy, history_gaps=gaps,
                        history_gap_note='保留原始时间空档，不补造K线。指标按实际观测的K线更新；未成交信号和持仓延续至下一条实际行情，止损跳价按下一开盘处理。无法判断空档内部价格与止损触发。')
    write_json(folder / "metadata.json", metadata)
    if not repo.patch(identifier, allowed={"preparing"}, status="running", metadata=metadata):
        return

    def progress(value):
        if not repo.patch(identifier, allowed={"running"}, progress=value):
            raise InterruptedError("回测已取消或中断")

    result = simulate(bars, strategy, parameters, warmup=spec.warmup_bars,
        initial_cash=command.initial_cash, position_pct=command.position_pct, step_ms=step, progress=progress)
    write_json(folder / "result.json", result)
    metadata['result_hash'] = file_hash(folder / 'result.json')
    write_json(folder / 'metadata.json', metadata)
    if repo.finish(identifier, result, [asdict(b) for b in bars], metadata):
        print(f"回测完成：{result['report']['total_trades']} 笔交易，期末权益 {result['report']['final_equity']}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--managed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.managed and sys.stdin.buffer.read(1) != b"1":
        return 1
    database = build_database_runtime(settings)
    service = LocalBacktestService(database)
    try:
        execute(service, args.run_id)
        return 0
    except Exception as exc:
        traceback.print_exc()
        service.repository.patch(args.run_id, allowed={"preparing", "running"}, status="failed", error=str(exc))
        return 1
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
