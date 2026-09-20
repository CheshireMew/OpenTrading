"""One run per process; invoked only by the existing background runtime."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import inspect
import sys
import time
import traceback
from pathlib import Path
from app.infra.research_files import file_hash
from app.services.backtest_provenance import execution_modules, compatible_environment, verify_replay
from app.services.backtest_record_store import computation_fingerprint

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.local_backtest import simulate, validate_bars
from app.domain.backtest_history import validate_observed_bars, align_execution_bars
from app.domain.market.constants import timeframe_to_milliseconds
from app.infra.db import build_database_runtime
from app.infra.persistence.market.kline_store import KlineStore
from app.services.local_backtest_service import LocalBacktestService, write_json
from app.services.local_backtest_strategies import digest, load_strategy, environment, validate_parameters
from app.services.market.exchange_gateway import ExchangeGateway
from app.services.market.market_data_service import MarketDataService
from config import settings


def execute(service, identifier, market_data=None):
    metadata = service.repository.get(identifier)['metadata']
    if metadata.get('resume_result_from'):
        return service.publish_computed(identifier, metadata['resume_result_from'])
    if metadata.get('execution_bundle'):
        if not compatible_environment(metadata['environment'], environment()):
            raise ValueError('Python 或数值依赖与冻结版本不同')
        verify_replay(service.directory(identifier)/'execution', metadata)
        with execution_modules(service.directory(identifier)/'execution', metadata['execution_bundle']) as frozen:
            return _execute(service, identifier, market_data, frozen)
    return _execute(service, identifier, market_data)


def _execute(service, identifier, market_data=None, frozen=None):
    print(f"准备回测 {identifier}", flush=True)
    repo = service.repository
    run = repo.get(identifier)
    folder = service.directory(identifier)
    command = LocalBacktestCommand.model_validate(run["config"])
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    if frozen is None and metadata["environment"] != environment():
        raise ValueError("引擎或依赖版本已变化，请重新创建任务")
    if frozen is None and metadata.get('engine_code_hash') and metadata['engine_code_hash'] != file_hash(Path(__file__).parents[1] / 'app/domain/local_backtest.py'):
        raise ValueError('引擎代码与研究冻结时不同，请另建版本')
    if digest((folder / "strategy.py").read_bytes()) != metadata["strategy_hash"]:
        raise ValueError("策略快照校验失败")
    strategy, spec = load_strategy(folder / "strategy.py")
    parameters = validate_parameters(spec, command.parameters)
    recipe = metadata.get('execution_recipe', {})
    warmup = recipe.get('warmup_bars', spec.warmup_bars)
    step = timeframe_to_milliseconds(command.timeframe)
    start, end = int(command.start.timestamp() * 1000), int(command.end.timestamp() * 1000)
    from app.services.backtest_batch_data import shared_batch_data
    from app.services.backtest_history_loader import load_history
    def preparing(fraction):
        if not repo.patch(identifier, allowed={'preparing'}, progress=fraction):
            raise InterruptedError('回测数据准备已取消或中断')
    with shared_batch_data(service, run, folder, metadata) as history_cache:
        snapshot = service.datasets.resolve(folder, 'data.json')
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
            rows = load_history(market_data,command.symbol,command.timeframe,start-warmup*step,end,
                history_cache/'history_chunks',lambda v:preparing(v*.08), allow_gaps=command.data_gap_policy == 'observed_bars')
        gaps = []
        if frozen:
            bars, _, gaps, _ = frozen.prepare_history(rows, None, {**recipe, 'execution_step_ms': None})
        elif command.data_gap_policy == 'observed_bars':
            bars, gaps = validate_observed_bars(rows, start, end, step, warmup, int(time.time() * 1000))
        else:
            bars = validate_bars(rows, start, end, step, warmup, int(time.time() * 1000))
        print(f"行情检查通过：{len(bars)} 根，预热 {warmup} 根", flush=True)
        if not snapshot.exists():
            snapshot, _ = service.datasets.install(folder, 'data.json', rows)
        metadata.update(data_hash=digest(snapshot.read_bytes()), data_start=bars[0].timestamp,
                        data_end=end, candle_count=len(bars), warmup_bars=warmup)
        write_json(folder / 'metadata.json', metadata)
        if command.data_gap_policy == 'observed_bars':
            metadata.update(data_gap_policy=command.data_gap_policy, history_gaps=gaps,
                            history_gap_note='保留原始时间空档，不补造K线。指标按实际观测的K线更新；未成交信号和持仓延续至下一条实际行情，止损跳价按下一开盘处理。无法判断空档内部价格与止损触发。')
        execution_bars=None
        if command.execution_timeframe:
            fine_snapshot=service.datasets.resolve(folder, 'execution_data.json')
            if fine_snapshot.exists():
                raw=fine_snapshot.read_bytes()
                if digest(raw)!=metadata.get('execution_data_hash'):
                    raise ValueError('细周期行情快照校验失败')
                fine_rows=json.loads(raw)
            else:
                if metadata.get('execution_data_hash') or (run['parent_id'] and repo.get(run['parent_id'])['status']=='completed'):
                    raise ValueError('缺少已冻结的细周期行情，拒绝换用新数据')
                if market_data is None:
                    market_data=MarketDataService(exchange_gateway=ExchangeGateway(metadata['source']['exchange']),
                        kline_store=KlineStore(database_runtime=repo.database))
                fine_rows=load_history(market_data,command.symbol,command.execution_timeframe,start,end,
                    history_cache/'history_chunks',lambda v:preparing(.08+v*.10))
                fine_snapshot, _ = service.datasets.install(folder, 'execution_data.json', fine_rows)
                metadata['execution_data_hash']=file_hash(fine_snapshot)
                write_json(folder/'metadata.json',metadata)
            fine_step=timeframe_to_milliseconds(command.execution_timeframe)
            if frozen:
                bars, execution_bars, gaps, alignment = frozen.prepare_history(rows, fine_rows, recipe)
            else:
                fine_bars,_=validate_observed_bars(fine_rows,start,end,fine_step,0,int(time.time()*1000))
                execution_bars,alignment=align_execution_bars(bars[warmup:],fine_bars,step,fine_step)
                if alignment['fallback'] and command.execution_gap_policy == 'reject':
                    raise ValueError('细周期行情缺失或不匹配，当前设置禁止回退')
            write_json(folder/'execution_alignment.json',alignment)
            metadata.update(execution_data_hash=file_hash(fine_snapshot),execution_alignment_hash=file_hash(folder/'execution_alignment.json'),
                            execution_matched_candles=alignment['matched'],execution_fallback_candles=alignment['fallback'])
        write_json(folder / "metadata.json", metadata)
    candles_index = service.record_store.candle_index(metadata['data_hash'], bars, lambda v: preparing(.18+.02*v))
    if not repo.patch(identifier, allowed={"preparing"}, status="running", metadata=metadata,progress=.2):
        return

    def progress(value):
        if not repo.patch(identifier, allowed={"running"}, progress=.2+.6*value,
            progress_detail={'phase': 'running', 'unit': 'bars', 'done': round(value*(len(bars)-warmup)), 'total': len(bars)-warmup}):
            raise InterruptedError("回测已取消或中断")

    if frozen:
        options = {'record_factory': service.record_store.collection} if 'record_factory' in inspect.signature(frozen.run).parameters else {}
        result = frozen.run(bars, execution_bars, strategy, parameters, recipe, progress, **options)
    else:
        result = simulate(bars, strategy, parameters, warmup=warmup,
            initial_cash=command.initial_cash, position_pct=command.position_pct, step_ms=step, progress=progress,
            execution_bars=execution_bars,intrabar_profit_protection=command.intrabar_profit_protection)
    service.record_store.seal(folder, result, candles_index, computation_fingerprint({'config': run['config'], 'metadata': metadata}))
    service.publish_computed(identifier)
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
        service.repository.patch(args.run_id, allowed={"preparing", "running", "saving"}, status="failed", error=str(exc))
        return 1
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
