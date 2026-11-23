"""External agents submit compact parameter requests; the software runs them."""
import asyncio
from pathlib import Path
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json
from app.services.local_backtest_service import LocalBacktestService
from app.services.parameter_sweep_service import ParameterSweepService
from config import settings


def add_parser(subparsers):
    p=subparsers.add_parser('sweep',help='批量比较策略参数；后台自动运行、保存并排序')
    cmds=p.add_subparsers(dest='action',required=True)
    for name in ('preview','create'):
        q=cmds.add_parser(name);q.add_argument('--file',type=Path,required=True)
    q=cmds.add_parser('list');q.add_argument('--offset',type=int,default=0);q.add_argument('--limit',type=int,default=10)
    q=cmds.add_parser('status');q.add_argument('id');q.add_argument('--offset',type=int,default=0);q.add_argument('--limit',type=int,default=10)
    q.add_argument('--sort',choices=['return_pct','win_rate','max_drawdown_pct','total_trades'],default='return_pct')
    q.add_argument('--ascending',action='store_true');q.add_argument('--minimum-trades',type=int,default=0)
    for name in ('resume','cancel','effects','export'):
        q=cmds.add_parser(name);q.add_argument('id')
        if name=='export':q.add_argument('--output',type=Path,required=True)


async def execute(args):
    db=build_database_runtime(settings);s=ParameterSweepService(LocalBacktestService(db))
    def call():
        if args.action in ('preview','create'):return getattr(s,args.action)(read_json(args.file))
        if args.action=='list':return s.listing(args.offset,args.limit)
        if args.action=='status':return s.get(args.id,args.offset,args.limit,args.sort,not args.ascending,args.minimum_trades)
        if args.action=='export':
            v=s.export(args.id)
            with args.output.open('x',encoding='utf-8',newline='') as f:f.write(v['content'])
            return dict(path=str(args.output.resolve()))
        return getattr(s,args.action)(args.id)
    try:return await asyncio.to_thread(call)
    finally:db.dispose()
