"""Summarize saved public project runs, without simulating or tuning strategies."""
import bisect
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean

from app.domain.account_diagnostics import calendar_returns, compare_trades
from app.domain.backtest_diagnostics import summarize
from app.infra.db import build_database_runtime
from app.services.backtest_diagnostics_service import BacktestDiagnosticsService
from app.services.local_backtest_service import LocalBacktestService
from app.services.parameter_sweep_service import ParameterSweepService
from config import settings

OUT = Path(__file__).resolve().parent
NAMES = {'immediate':'触及即止损', 'next_bar_open':'下一根开盘判断',
         'next_bar_touch':'下一根开盘及盘中判断', 'next_bar_close':'下一根收盘判断'}


def ms(value):
    return int(datetime.fromisoformat(value).timestamp()*1000)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def period(points, start, end):
    times = [p['timestamp'] for p in points]
    a = points[bisect.bisect_right(times,start)-1]
    b = points[bisect.bisect_right(times,end)-1]
    return {'start':start,'end':end,'start_mark':a,'end_mark':b,
            'return_pct':100*(b['equity']/a['equity']-1)}


def main():
    db=build_database_runtime(settings)
    service=LocalBacktestService(db)
    reader=BacktestDiagnosticsService(service)
    sweep=ParameterSweepService(service)
    try:
        batches=json.loads((OUT/'batches.json').read_text())
        items=[]
        for name,identifier in batches.items():
            value=sweep.get(identifier)
            dump(OUT/(name+'-status.json'),value)
            if value['status']!='completed':
                print(name,value['counts']);return
            items.extend(value['items'])
        items.sort(key=lambda v:(v['parameters']['initial_stop_pct'],list(NAMES).index(v['parameters']['stop_confirmation']),v['parameters']['stop_range_lock']))
        output=[]
        base_trades=None
        hashes=[]
        for item in items:
            rid=item['run_id'];p=item['parameters'];run=service.repository.get(rid)
            trades=list(reader.rows(rid,'trades'))
            points=list(reader.rows(rid,'equity'))
            if base_trades is None:base_trades=trades
            name=f"{p['initial_stop_pct']:g}%：{NAMES[p['stop_confirmation']]}"+('＋止损区域限制' if p['stop_range_lock'] else '')
            scope_start,scope_end=ms('2026-09-16T12:00:00+08:00'),ms('2026-09-17T21:00:00+08:00')
            def exit_time(t):
                return t['exit_time']+(900000 if t['exit_phase']=='close' else 0)
            focal=[t for t in trades if scope_start<=exit_time(t)<scope_end]
            stops=[t for t in trades if t['exit_reason']=='stop_loss']
            lookup={(t['entry_time'],t['side']):t for t in trades}
            matched=[(t,lookup[(t['entry_time'],t['side'])]) for t in base_trades if t['exit_reason']=='stop_loss' and (t['entry_time'],t['side']) in lookup]
            row={'name':name,'run_id':rid,'parameters':p,'report':item['report'],
                 'trade_statistics':summarize(trades,include_streak=True),
                 'recent_two_years':period(points,ms('2024-09-18T00:00:00+00:00'),ms('2026-09-18T00:00:00+00:00')),
                 'annual':calendar_returns(points,'year'),
                 'screenshot_period':period(points,scope_start,scope_end),
                 'screenshot_closed_trades':focal,
                 'exit_counts':dict(Counter(t['exit_reason'] for t in trades)),
                 'short_losing_trades_15m_or_less':sum(t['profit']<0 and t['duration_minutes']<=15 for t in trades),
                 'losses_exceeding_one_pct':sum(t['return_pct'] < -1.000001 for t in trades),
                 'worst_trade':min(trades,key=lambda t:t['return_pct']),
                 'initial_stop_average_return_pct':mean(t['return_pct'] for t in stops) if stops else None,
                 'same_entry_original_stops':{'matched':len(matched),
                    'became_winners':sum(b['return_pct']>0 for a,b in matched),
                    'larger_losses':sum(b['return_pct']<a['return_pct']-1e-9 for a,b in matched),
                    'mean_change_pp':mean(b['return_pct']-a['return_pct'] for a,b in matched) if matched else None},
                 'comparison_to_original':compare_trades(base_trades,trades,limit=0),
                 'execution_matched_candles':run['metadata']['execution_matched_candles'],
                 'execution_fallback_candles':run['metadata']['execution_fallback_candles'],
                 'artifacts':service.artifacts(rid)}
            hashes.append((run['metadata']['data_hash'],run['metadata']['execution_data_hash']))
            output.append(row)
            dump(OUT/(rid+'-trades.json'),trades)
            print(name,'收益',round(item['report']['return_pct'],2),'近两年',round(row['recent_two_years']['return_pct'],2),
                  '胜率',round(item['report']['win_rate'],2),'回撤',round(item['report']['max_drawdown_pct'],2),
                  '最差单笔',round(row['worst_trade']['return_pct'],2),'截图段',round(row['screenshot_period']['return_pct'],2),flush=True)
        assert len(set(hashes))==1,'不同版本的数据哈希不一致，禁止直接归因'
        dump(OUT/'results.json',{'basis':'Same frozen prices, 15m signals and protection, 5m execution; no fees/slippage, 100% equity. Later period is a descriptive continuous-account slice, not unseen validation.',
             'data_hashes':hashes[0], 'rows':output})
        evidence={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app/domain/local_backtest.py'),Path('strategies/trend_cloud_stop_confirmation_v1.py'),Path('strategies/pine/eth_ema55_manual_chart_v7_2.pine')]}
        dump(OUT/'source-hashes.json',evidence)
    finally:
        db.dispose()


if __name__=='__main__':
    main()
