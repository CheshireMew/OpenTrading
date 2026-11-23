"""Replay selected study traces as normal project chart records; no strategy changes."""
from datetime import datetime,timezone

from app.contracts.local_backtest import LocalBacktestCommand
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import digest
from config import settings
from scripts.cloud_cross_asset_study import DOCS,RUNTIME,ROOT,compare_trace
from scripts.local_backtest_worker import execute
from scripts.profit_protection_study import read,save


def main():
    r=read(DOCS/'results.json')
    assert r['status']=='completed'
    # Same predeclared chart selection on both assets: return leader and the two early main candidates.
    targets=[(asset,key) for asset in ['eth','btc'] for key in dict.fromkeys([
        r['rankings'][asset]['full'][0], 'initial__ema31_atr','initial__high_low_ema'])]
    path=DOCS/'project-runs.json'
    receipt=read(path) if path.exists() else dict(plan_hash=r['provenance']['plan_hash'],runs={})
    assert receipt['plan_hash']==r['provenance']['plan_hash']
    db=build_database_runtime(settings)
    service=LocalBacktestService(db)
    try:
        old=read(ROOT/'docs/verification/eth-cloud-joint-six-year-20260911/project-runs.json')
        oldruns=[service.repository.get(v['run_id']) for v in old['runs'].values() if v['verified']]
        for asset,key in targets:
            ident=asset+'__'+key
            v=r['plan']['variants'][key]
            assert digest((ROOT/v['source']).read_bytes())==r['plan']['sources'][v['source']]['sha256']
            start,end=r['plan']['periods'][asset]['full']
            cmd=LocalBacktestCommand(strategy=ROOT.joinpath(v['source']).stem,parameters={**v['parameters'],'record_indicators':True},
                 symbol=r['data'][asset]['symbol'],timeframe='15m',start=start,end=end,initial_cash=10000,position_pct=100,data_gap_policy='observed_bars')
            if ident not in receipt['runs']:
                prior=next((x for x in oldruns if x['config']==cmd.model_dump(mode='json') and
                            x['metadata'].get('data_hash')==r['data'][asset]['data_hash'] and x['status']=='completed'),None)
                record=prior or service.create(cmd)
                receipt['runs'][ident]=dict(asset=asset,version=key,period='full',run_id=record['id'],verified=False,reused=prior is not None)
                save(path,receipt)
            item=receipt['runs'][ident]
            record=service.repository.get(item['run_id'])
            if record['status']=='queued' and service.repository.patch(record['id'],allowed={'queued'},status='preparing'):
                execute(service,record['id'])
                record=service.repository.get(record['id'])
            if record['status']!='completed':
                raise RuntimeError(f'Project replay {record["id"]}: {record["status"]}; rerun publisher after completion')
            actual=read(service.directory(record['id'])/'result.json')
            expected=read(RUNTIME/'traces'/asset/f'{key}-full.json')
            assert record['metadata']['data_hash']==r['data'][asset]['data_hash']
            assert record['metadata']['history_gaps']==r['data'][asset]['gaps']
            compare_trace(actual,expected)
            item.update(verified=True,verified_at=datetime.now(timezone.utc).isoformat())
            save(path,receipt)
            print(f'{ident}: chart {record["id"]} exact',flush=True)
    finally:
        db.dispose()


if __name__=='__main__':
    main()
