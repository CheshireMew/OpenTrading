"""CLI adapter. All mutations use the same service as HTTP."""
import asyncio
import json
from pathlib import Path

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.signal_comparison import compare_signals
from app.domain.market.constants import timeframe_to_milliseconds
from app.infra.db import build_database_runtime
from app.infra.persistence.local_backtest_repository import TERMINAL
from app.services.local_backtest_service import LocalBacktestService, KINDS
from app.services.research_comparison import compare_runs, trade_breakdown
from config import settings


def add_parser(subparsers):
    parser = subparsers.add_parser("backtest", help="本地策略回测")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("strategies")
    listing = commands.add_parser("list")
    listing.add_argument("--archived", action="store_true")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=50)
    run = commands.add_parser("run")
    run.add_argument("--strategy", required=True)
    run.add_argument("--parameters", type=Path)
    run.add_argument("--symbol", default="BTC/USDT")
    run.add_argument("--timeframe", default="1h")
    run.add_argument('--execution-timeframe', choices=['1m','5m','15m','30m','1h'], help='可选细周期成交核对，信号周期不变')
    run.add_argument('--intrabar-profit-protection', action='store_true', help='在细周期收盘更新利润保护，下一根细K线生效')
    run.add_argument("--start", required=True, help="ISO 时间，必须包含时区")
    run.add_argument("--end", required=True)
    run.add_argument("--initial-cash", type=float, default=10000)
    run.add_argument("--position-pct", type=float, default=100)
    run.add_argument("--wait", action="store_true")
    run.add_argument('--data-gap-policy', choices=['reject', 'observed_bars'], default='reject', help='默认拒绝缺口；observed_bars 保留并记录空档，不补造K线')
    records = commands.add_parser('records', help='读取信号、指标条件或其它运行记录')
    records.add_argument('id')
    records.add_argument('--kind', choices=sorted(KINDS), required=True)
    records.add_argument('--offset', type=int, default=0)
    records.add_argument('--limit', type=int, default=500)
    compare = commands.add_parser('compare', help='与参考信号逐根比较，默认不允许偏移')
    compare.add_argument('id')
    compare.add_argument('--reference', type=Path, required=True)
    compare.add_argument('--tolerance-bars', type=int, default=0)
    pair = commands.add_parser('compare-runs', help='列出两次运行所有差异，检查能否归因于单一参数')
    pair.add_argument('first')
    pair.add_argument('second')
    breakdown = commands.add_parser('breakdown', help='直接统计旧交易的方向、退出原因、月份与持仓，无需重跑')
    breakdown.add_argument('id')
    for action in ("status", "result", "cancel", "rerun", "archive", "export"):
        command = commands.add_parser(action)
        command.add_argument("id")
        if action == "rerun":
            command.add_argument("--wait", action="store_true")
        if action == 'result':
            command.add_argument('--full', action='store_true', help='显式读取全部逐笔、K线和权益；默认只读摘要')
        if action == "export":
            command.add_argument("--format", choices=["json", "trades", "equity"], default="json")
            command.add_argument("--output", type=Path, required=True)


async def execute(args):
    database = build_database_runtime(settings)
    service = LocalBacktestService(database)
    try:
        def call():
            if args.action == "strategies":
                return service.catalog()
            if args.action == "list":
                if args.offset < 0 or not 1 <= args.limit <= 200:
                    raise ValueError("offset 必须非负，limit 应在 1–200")
                return service.repository.list(args.offset, args.limit, args.archived)
            if args.action == "run":
                values = {name: getattr(args, name) for name in ("strategy", "symbol", "timeframe", "start", "end", "initial_cash", "position_pct", "data_gap_policy")}
                values["parameters"] = json.loads(args.parameters.read_text(encoding="utf-8-sig")) if args.parameters else {}
                values.update(execution_timeframe=args.execution_timeframe,intrabar_profit_protection=args.intrabar_profit_protection)
                return service.create(LocalBacktestCommand.model_validate(values))
            if args.action == 'records':
                if args.offset < 0 or not 1 <= args.limit <= 5000:
                    raise ValueError('offset 必须非负，limit 应在 1–5000')
                return service.records(args.id, args.kind, args.offset, args.limit)
            if args.action == 'compare':
                result = json.loads(service.export(args.id, 'json')['content'])
                reference = json.loads(args.reference.read_text(encoding='utf-8-sig'))
                return compare_signals(result, reference, timeframe_to_milliseconds(result['run']['config']['timeframe']), args.tolerance_bars)
            if args.action == 'compare-runs':
                return compare_runs(service.repository.get(args.first), service.repository.get(args.second))
            if args.action == 'breakdown':
                return trade_breakdown(service, args.id)
            if args.action in ("cancel", "rerun", "archive"):
                return getattr(service, args.action)(args.id)
            if args.action == "export":
                result = service.export(args.id, args.format)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8", newline="") as f:
                    f.write(result["content"])
                return {"path": str(args.output.resolve()), "format": args.format}
            run = service.repository.get(args.id)
            if args.action == "result":
                if run["status"] != "completed":
                    raise ValueError(f"回测尚未完成：{run['status']}；{run.get('error') or ''}")
                if args.full:
                    return json.loads(service.export(args.id, "json")["content"])
                return {'id': run['id'], 'status': run['status'], 'config': run['config'], 'report': run['report'],
                        'artifacts': str(service.directory(run['id']).resolve()),
                        'details': '逐笔用 backtest records；完整文件用 backtest export；--full 返回全部内容'}
            return run
        result = await asyncio.to_thread(call)
        if getattr(args, "wait", False):
            while result["status"] not in TERMINAL:
                await asyncio.sleep(.5)
                result = await asyncio.to_thread(service.repository.get, result["id"])
            if result["status"] != "completed":
                raise RuntimeError(f"回测 {result['id']} {result['status']}: {result.get('error') or ''}")
        return result
    finally:
        database.dispose()
