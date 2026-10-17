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


async def execute(args):
    catalog = ResearchCatalog(settings.RUNTIME_ROOT_DIR / 'research_catalog.sqlite')
    if args.action == 'refresh':
        return await asyncio.to_thread(catalog.refresh, args.root or [BASE_DIR / 'docs/verification'])
    return await asyncio.to_thread(catalog.search, args.query, args.offset, args.limit)
