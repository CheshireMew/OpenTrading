"""Compact public entry point for external agents; no embedded agent runtime."""
import asyncio
from pathlib import Path
from app.infra.research_files import read_json
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.research_study_service import ResearchStudyService
from app.services.research_comparison import paired_effect
from config import settings


def add_parser(subparsers):
    parser = subparsers.add_parser('study', help='保存研究问题、版本、回测与结论；默认返回摘要')
    commands = parser.add_subparsers(dest='action', required=True)
    for name in ('preview', 'create'):
        command = commands.add_parser(name)
        command.add_argument('--plan', type=Path, required=True)
    for name in ('status', 'plan', 'complete', 'history', 'submit'):
        command = commands.add_parser(name)
        command.add_argument('id')
        if name == 'submit':
            command.add_argument('--retry', help='明确重试一个失败／中断案例；旧运行保留')
    listing = commands.add_parser('list')
    listing.add_argument('--query', default='')
    for command in (listing,):
        command.add_argument('--offset', type=int, default=0)
        command.add_argument('--limit', type=int, default=10)
    results = commands.add_parser('results')
    results.add_argument('id')
    results.add_argument('--offset', type=int, default=0)
    results.add_argument('--limit', type=int, default=10)
    for name in ('symbol', 'timeframe', 'role'):
        results.add_argument('--' + name)
    selection = commands.add_parser('select')
    selection.add_argument('id')
    selection.add_argument('--variant', action='append', required=True)
    selection.add_argument('--reason', required=True)
    stop = commands.add_parser('stop', help='停止本研究的新计算并保留未答问题和全部记录')
    stop.add_argument('id')
    stop.add_argument('--reason', required=True)
    answer = commands.add_parser('answer')
    answer.add_argument('id')
    answer.add_argument('--file', type=Path, required=True)
    attach = commands.add_parser('attach')
    attach.add_argument('id')
    attach.add_argument('--name', required=True)
    attach.add_argument('--file', type=Path, required=True)
    attach.add_argument('--description', required=True)
    effect = commands.add_parser('effect')
    effect.add_argument('id')
    effect.add_argument('--factor', required=True, help='例如 parameters.center_length')


async def execute(args):
    database = build_database_runtime(settings)
    service = ResearchStudyService(LocalBacktestService(database))
    def call():
        if args.action in {'preview', 'create'}:
            method = service.preview_summary if args.action == 'preview' else service.create
            return method(read_json(args.plan))
        if args.action == 'status':
            return service.summary(args.id)
        if args.action == 'plan':
            return service.plan(args.id)
        if args.action == 'history':
            return service.events(args.id)
        if args.action == 'complete':
            return service.complete(args.id)
        if args.action == 'submit':
            result = service.submit(args.id, args.retry)
            if result['errors']:
                raise ValueError(f'部分提交失败，已提交的不重跑；study status 可查进度：{result["errors"]}')
            return result
        if args.action == 'list':
            return service.listing(args.query, args.offset, args.limit)
        if args.action == 'results':
            return service.results(args.id, args.offset, args.limit, args.symbol, args.timeframe, args.role)
        if args.action == 'select':
            return service.select(args.id, args.variant, args.reason)
        if args.action == 'stop':
            return service.stop(args.id, args.reason)
        if args.action == 'answer':
            return service.answer(args.id, read_json(args.file))
        if args.action == 'attach':
            return service.attach(args.id, args.name, args.file, args.description)
        if args.action == 'effect':
            return paired_effect([run for _, _, run in service.case_runs(args.id) if run], args.factor)
        raise ValueError('未知研究操作')
    try:
        return await asyncio.to_thread(call)
    finally:
        database.dispose()
