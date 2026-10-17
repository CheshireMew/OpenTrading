"""Read only: summarize the two completed project backtests against the baseline."""
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from math import isclose
import gc
import json
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from app.infra.research_files import file_hash, read_json
from app.domain.cloud_trade_attribution import summary, calendar_returns, periods, date
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.parameter_sweep_service import ParameterSweepService
from app.contracts.local_backtest import LocalBacktestCommand
from config import settings

OUT=Path(__file__).parent
BASE='657b2b8086588a254442b82b128d34df'
BATCHES={'5m':'68da22792f3347fdaacfdc2ca245b1d3','stop4':'c5303ac733fb43c79db4d78649a96c21'}


def inspect(service,rid,name,base=None):
    run=service.repository.get(rid);assert run['status']=='completed',(rid,run['status'])
    folder=service.directory(rid);meta=read_json(folder/'metadata.json');cfg=read_json(folder/'config.json')
    files={'result.json':'result_hash','data.json':'data_hash','strategy.py':'strategy_hash','engine.py':'engine_code_hash'}
    if cfg.get('execution_timeframe'):files['execution_data.json']='execution_data_hash'
    for f,k in files.items():assert file_hash(folder/f)==meta[k],f
    raw=read_json(folder/'result.json');bars=read_json(folder/'data.json')
    ts,eq=raw['trades'],raw['equity'];report=raw['report']
    assert isclose(sum(t['profit'] for t in ts),report['profit'],abs_tol=1e-5)
    assert isclose(summary(ts)['compound_return_pct'],report['return_pct'],rel_tol=1e-9,abs_tol=1e-6)
    assert len(ts)==report['total_trades']
    peak=0;worst=(0,0,0)
    for i,e in enumerate(eq):
        if e['equity']>=eq[peak]['equity']:peak=i
        dd=100*(1-e['equity']/eq[peak]['equity'])
        if dd>worst[0]:worst=(dd,peak,i)
    dd,pi,ti=worst;p,t=eq[pi],eq[ti]
    assert isclose(dd,report['max_drawdown_pct'],abs_tol=1e-8)
    recovery=next((e for e in eq[ti+1:] if e['equity']>=p['equity']),None)
    years=calendar_returns(eq,bars,periods(eq[0]['timestamp'],eq[-1]['timestamp'],'year'))
    row=dict(name=name,run_id=rid,config=cfg,report=report,all=summary(ts),yearly=years,
        losing_exits=dict(Counter(t['exit_reason'] for t in ts if t['profit']<0)),
        drawdown=dict(pct=dd,peak_time=date(p['timestamp']),trough_time=date(t['timestamp']),
            recovery_time=date(recovery['timestamp']) if recovery else None,
            days_peak_to_recovery=(recovery['timestamp']-p['timestamp'])/86400000 if recovery else None),
        source={k:meta.get(k) for k in ['data_hash','execution_data_hash','strategy_hash','engine_code_hash','result_hash',
            'execution_matched_candles','execution_fallback_candles']},path=str(folder.resolve()),
        chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart')
    del raw,ts,eq
    if base:
        expected=json.loads(json.dumps(base['config']))
        if name=='stop4':expected['parameters']['initial_stop_pct']=4
        else:expected.update(timeframe='5m',execution_timeframe=None,intrabar_profit_protection=False)
        # Saved legacy-compatible configs omit false/None execution defaults.
        assert LocalBacktestCommand.model_validate(cfg)==LocalBacktestCommand.model_validate(expected)
        for k in ['strategy_hash','engine_code_hash']:assert meta[k]==base['source'][k],k
        if name=='stop4':
            for k in ['data_hash','execution_data_hash']:assert meta[k]==base['source'][k],k
        else:
            fine=read_json(service.directory(BASE)/'execution_data.json')
            start=int(datetime.fromisoformat(cfg['start'].replace('Z','+00:00')).timestamp()*1000)
            end=int(datetime.fromisoformat(cfg['end'].replace('Z','+00:00')).timestamp()*1000)
            native=[b for b in bars if start<=b[0]<end]
            fine=[b for b in fine if start<=b[0]<end]
            assert native==fine,'5分钟实际交易区间与原版成交价格不同'
            row['five_minute_prices_checked']=len(native)
    return row


def main():
    db=build_database_runtime(settings);service=LocalBacktestService(db);sweep=ParameterSweepService(service)
    try:
        runs=[]
        for name,batch in BATCHES.items():
            s=sweep.get(batch);assert s['status']=='completed',(batch,s['counts'])
            runs.append((name,s['items'][0]['run_id']))
        baseline=inspect(service,BASE,'baseline');rows=[baseline];gc.collect()
        for name,rid in runs:
            rows.append(inspect(service,rid,name,baseline));gc.collect()
        result=dict(created_at=datetime.now(timezone.utc).isoformat(),rows=rows,batches=BATCHES,
            plan_hash=file_hash(OUT/'plan.json'),analysis_hash=file_hash(Path(__file__)),
            verification=dict(config_differences_as_planned=True,strategy_and_engine_unchanged=True,
                stop4_same_native_and_execution_data=True,five_minute_active_prices_equal_to_baseline_execution=True,
                total_profit_compound_and_drawdown_checked=True),
            notes=['100%资金投入，BNB原版，两个独立改动，不叠加。',
                '5分钟组原生5分钟收盘即更新保护；15分钟组通过细周期数据每5分钟更新，频率相同。',
                '最大回撤按信号周期收盘权益：5分钟组每5分钟，原版/4%止损组每15分钟；采样精度不同。',
                'EMA及等待根数不变，5分钟级别对应的实际时间跨度缩短。',
                '不计手续费和滑点；沿用项目空档和盘中先后不明规则；历史比较不证明未来效果。'])
        with (OUT/'results.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
        print(json.dumps([dict(name=r['name'],report=r['report'],drawdown=r['drawdown'],
            all=r['all'],losing_exits=r['losing_exits'],
            years=[dict(year=y['label'],return_pct=y['return_pct']) for y in r['yearly']]) for r in rows],ensure_ascii=False))
    finally:db.dispose()


if __name__=='__main__':main()
