"""Summarize the four authorized completed runs; no backtest or selection."""
from bisect import bisect_right
from datetime import datetime, timezone
from math import isclose
from pathlib import Path
import json
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_service import LocalBacktestService
from app.services.parameter_sweep_service import ParameterSweepService
from app.domain.cloud_trade_attribution import summary, group, calendar_returns, periods, date
from config import settings

OUT=Path(__file__).parent
BASE='657b2b8086588a254442b82b128d34df'


def save(name,value):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


def inspect(service,rid,name,interval):
    run=service.repository.get(rid);assert run['status']=='completed',(rid,run['status'])
    folder=service.directory(rid);meta=read_json(folder/'metadata.json')
    for file,key in [('result.json','result_hash'),('data.json','data_hash')]:assert file_hash(folder/file)==meta[key]
    r=read_json(folder/'result.json');rows=read_json(folder/'data.json');ts=r['trades'];eq=r['equity']
    losses=[t for t in ts if t['profit']<0]
    years=calendar_returns(eq,rows,periods(eq[0]['timestamp'],eq[-1]['timestamp'],'year'))
    peak=0;worst=(0,0,0)
    for i,e in enumerate(eq):
        if e['equity']>=eq[peak]['equity']:peak=i
        dd=100*(1-e['equity']/eq[peak]['equity'])
        if dd>worst[0]:worst=dd,peak,i
    dd,pi,ti=worst;p,t=eq[pi],eq[ti]
    recovery=next((x for x in eq[ti+1:] if x['equity']>=p['equity']),None)
    times=[e['timestamp'] for e in eq];a,b=[eq[bisect_right(times,v)-1] for v in interval]
    during=[x for x in ts if interval[0]<=x['exit_time']<interval[1]]
    if name=='15m_gate':
        exits=[x for x in ts if x['exit_reason']=='signal']
        assert all(x['protection_active'] and x['profit_peak_pct']>=2-1e-9 for x in exits)
        assert all(x['exit_reason'] in ['signal','stop_loss','profit_protection','end_of_backtest'] for x in ts)
    assert isclose(dd,r['report']['max_drawdown_pct'],abs_tol=1e-8)
    assert isclose(sum(x['profit'] for x in ts),r['report']['profit'],abs_tol=1e-6)
    record=dict(name=name,run_id=rid,config=run['config'],report=r['report'],source={key:meta.get(key) for key in
        ['data_hash','execution_data_hash','result_hash','strategy_hash','engine_code_hash','execution_matched_candles','execution_fallback_candles']},
        all=summary(ts),losing_exits=group(losses,'exit_reason'),sides=group(ts,'side'),
        yearly=years,drawdown=dict(pct=dd,peak_time=date(p['timestamp']),trough_time=date(t['timestamp']),
            recovery_time=date(recovery['timestamp']) if recovery else None,days_to_recover=(recovery['timestamp']-p['timestamp'])/86400000 if recovery else None),
        original_drawdown_period=dict(start=date(interval[0]),end=date(interval[1]),return_pct=100*(b['equity']/a['equity']-1),closed=summary(during)),
        path=str(folder.resolve()),chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart')
    return record,ts


def main():
    db=build_database_runtime(settings);service=LocalBacktestService(db);sweep=ParameterSweepService(service)
    try:
        records=[('baseline',BASE)]
        for batch in ['943c93e7e6934d12b55ab7cf2104da45','0ba8771046304e45a71039d85e717e8d','71f8a765f0dd4f2194d2f90081607fb5']:
            s=sweep.get(batch);assert s['status']=='completed',(batch,s['counts'])
            records.extend((('15m_stop1' if batch=='71f8a765f0dd4f2194d2f90081607fb5' else '15m_gate') if i['timeframe']=='15m' else i['timeframe'],i['run_id']) for i in s['items'])
        interval=(1659118500000,1705770000000);rows=[];trades={}
        for name,rid in records:
            row,ts=inspect(service,rid,name,interval);rows.append(row);trades[name]=ts
        old,changed=trades['baseline'],trades['15m_gate']
        key=lambda x:(x['entry_time'],x['side'],x['entry_price'])
        bykey={key(x):x for x in changed};pairs=[]
        for t in old:
            if t['exit_reason']=='signal' and t['profit']<0 and key(t) in bykey:
                v=bykey[key(t)]
                pairs.append(dict(old_trade_id=t['trade_id'],new_trade_id=v['trade_id'],entry_time=t['entry_time'],side=t['side'],
                    old_return_pct=t['return_pct'],new_return_pct=v['return_pct'],old_exit=t['exit_time'],new_exit=v['exit_time'],new_reason=v['exit_reason']))
        def avg(xs):return sum(xs)/len(xs) if xs else None
        rescued=[p for p in pairs if p['new_return_pct']>0]
        worse=[p for p in pairs if p['new_return_pct']<p['old_return_pct']-1e-9]
        paired=dict(matched=len(pairs),original_signal_losses=sum(t['exit_reason']=='signal' and t['profit']<0 for t in old),
            rescued_winners=len(rescued),larger_losses=len(worse),other=len(pairs)-len(rescued)-len(worse),
            original_mean_return_pct=avg([p['old_return_pct'] for p in pairs]),new_mean_return_pct=avg([p['new_return_pct'] for p in pairs]),
            rescued_mean_pct=avg([p['new_return_pct'] for p in rescued]),larger_loss_mean_pct=avg([p['new_return_pct'] for p in worse]),
            note='只配对时间、方向、价格完全相同的入场。持仓时间改变会影响其余入场机会，不能把这些配对当作全部原亏损单的独立反事实。')
        base=next(r for r in rows if r['name']=='baseline');gate=next(r for r in rows if r['name']=='15m_gate')
        assert base['source']['data_hash']==gate['source']['data_hash']
        assert len({r['source']['execution_data_hash'] for r in rows})==1
        save('results.json',dict(created_at=datetime.now(timezone.utc).isoformat(),rows=rows,paired=paired,
            verification=dict(gate_signal_and_execution_data_equal_to_baseline=True,all_execution_data_equal=True,
                gate_signal_exits_all_after_activation=True,max_drawdown_and_total_profit_reconciled=True),
            notes=['仅四组用户指定改动，原版直接复用。','所有版本采用同一8年区间、全仓复利、零手续费与滑点。',
                   '30分钟/1小时仍使用EMA55和振幅50，这两个参数对应的实际时间长度随交易周期变化。',
                   '2%反向退出门槛随引擎保护标志锁定；被忽略的旧反向信号不会等到达标后追溯补执行。',
                   '这段历史此前已查看，结果属于探索性比较，不能声称未见数据验证通过。']))
        save('same-entry-pairs.json',pairs)
        print(json.dumps(dict(rows=[dict(name=r['name'],run_id=r['run_id'],report=r['report'],drawdown=r['drawdown'],
            original_dd_period_return_pct=r['original_drawdown_period']['return_pct'],
            year2023=next(y['return_pct'] for y in r['yearly'] if y['label']=='2023'),
            losing_exits={k:v['trades'] for k,v in r['losing_exits'].items()}) for r in rows],paired=paired),ensure_ascii=False))
    finally:db.dispose()


if __name__=='__main__':main()
