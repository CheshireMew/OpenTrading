import asyncio
from pathlib import Path
from app.services.research_catalog import ResearchCatalog
from config import settings
from config.settings import BASE_DIR


def add_parser(subparsers):
    parser = subparsers.add_parser('catalog', help='查找以前测过的参数、周期与结论，不重跑')
    commands = parser.add_subparsers(dest='action', required=True)
    refresh = commands.add_parser('refresh')
    refresh.add_argument('--root', type=Path, action='append', help='默认 docs/verification；可多次指定')
    search = commands.add_parser('search')
    search.add_argument('query', help='多个词用空格隔开，要求同时匹配')
    search.add_argument('--offset', type=int, default=0)
    search.add_argument('--limit', type=int, default=8)
    results = commands.add_parser('results', help='查询结构化结果；同条件排序须指定参照记录')
    for key in ('symbol', 'strategy', 'family', 'timeframe', 'start', 'end', 'execution-timeframe', 'reference-id'):
        results.add_argument('--' + key)
    results.add_argument('--parameter', action='append', default=[], metavar='KEY=JSON')
    results.add_argument('--protection', choices=['signal', 'execution'])
    results.add_argument('--sort', choices=['return_pct', 'win_rate', 'max_drawdown_pct', 'total_trades'], default='return_pct')
    results.add_argument('--ascending', action='store_true')
    results.add_argument('--minimum-trades', type=int, default=0)
    results.add_argument('--include-archived', action='store_true')
    results.add_argument('--offset', type=int, default=0)
    results.add_argument('--limit', type=int, default=30)
    imports = commands.add_parser('import', help='导入有明确来源的旧汇总，不运行回测')
    imports.add_argument('--root', type=Path, action='append')
    detail = commands.add_parser('get')
    detail.add_argument('entry_id')


async def execute(args):
    if args.action in {'results', 'import', 'get'}:
        import json
        from app.infra.db import build_database_runtime
        from app.services.local_backtest_service import LocalBacktestService
        from app.services.research_results_catalog import ResearchResultsCatalog
        database = build_database_runtime(settings)
        try:
            results = ResearchResultsCatalog(LocalBacktestService(database))
            if args.action == 'import':
                return await asyncio.to_thread(results.refresh, args.root or [BASE_DIR/'docs/verification'])
            if args.action == 'get':
                return await asyncio.to_thread(results.get, args.entry_id)
            params = {}
            for value in args.parameter:
                key, sep, raw = value.partition('=')
                if not sep or not key:
                    raise ValueError('--parameter 应为 KEY=JSON，例如 center_length=55')
                params[key] = json.loads(raw)
            query = {k: getattr(args, k) for k in ('symbol', 'strategy', 'family', 'timeframe', 'start', 'end',
                'execution_timeframe', 'reference_id', 'sort', 'minimum_trades', 'include_archived', 'offset', 'limit')}
            query.update(parameters=params, descending=not args.ascending,
                         intrabar_profit_protection=None if args.protection is None else args.protection == 'execution')
            return await asyncio.to_thread(results.query, **query)
        finally:
            database.dispose()
    catalog = ResearchCatalog(settings.RUNTIME_ROOT_DIR / 'research_catalog.sqlite')
    if args.action == 'refresh':
        return await asyncio.to_thread(catalog.refresh, args.root or [BASE_DIR / 'docs/verification'])
    return await asyncio.to_thread(catalog.search, args.query, args.offset, args.limit)
