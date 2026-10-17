"""Compare completed project-engine runs; independently verify capital sizing."""
from datetime import datetime, timezone
from pathlib import Path
from math import isclose
import json
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from app.infra.research_files import read_json, file_hash
from app.domain.cloud_trade_attribution import calendar_returns, periods, date
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.parameter_sweep_service import ParameterSweepService
from config import settings

OUT=Path(__file__).parent
BASE='657b2b8086588a254442b82b128d34df'
BATCHES={50:'c6097f6d688a459aa0445f7623069a27',25:'60d466e1efd549389e393396591b07e6'}


def save(name,value):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


def inspect(service,rid,pct,reference=None):
    db_run=service.repository.get(rid)
    assert db_run['status']=='completed',(rid,db_run['status'])
    folder=service.directory(rid);meta=read_json(folder/'metadata.json');cfg=read_json(folder/'config.json')
    assert cfg['position_pct']==pct
    for name,key in [('data.json','data_hash'),('result.json','result_hash'),('strategy.py','strategy_hash'),('engine.py','engine_code_hash')]:
        assert file_hash(folder/name)==meta[key],name
    raw=read_json(folder/'result.json');bars=read_json(folder/'data.json')
    ts,eq,report=raw['trades'],raw['equity'],raw['report']
    source={k:meta[k] for k in ['data_hash','execution_data_hash','execution_alignment_hash','strategy_hash','engine_code_hash']}
    if reference:
        oldcfg,oldsource,oldtrades=reference
        assert {k:v for k,v in cfg.items() if k!='position_pct'}=={k:v for k,v in oldcfg.items() if k!='position_pct'}
        assert source==oldsource
        assert len(ts)==len(oldtrades)==7903
        exact=['entry_time','exit_time','side','entry_price','exit_price','exit_reason','entry_order_signal_time','entry_bar_ambiguous']
        for a,b in zip(ts,oldtrades):
            assert all(a[k]==b[k] for k in exact),(a['trade_id'],'trade path differs')
            assert isclose(a['return_pct'],b['return_pct'],abs_tol=1e-10)
    capital=cfg['initial_cash'];fraction=pct/100
    for t in ts:
        assert isclose(t['principal'],capital*fraction,rel_tol=1e-9,abs_tol=1e-6)
        assert isclose(t['profit'],t['principal']*t['return_pct']/100,rel_tol=1e-9,abs_tol=1e-6)
        capital*=1+fraction*t['return_pct']/100
    assert isclose(capital,report['final_equity'],rel_tol=1e-9)
    assert isclose(sum(t['profit'] for t in ts),report['profit'],abs_tol=1e-6)
    peak=0;worst=(0,0,0)
    for i,e in enumerate(eq):
        if e['equity']>=eq[peak]['equity']:peak=i
        dd=100*(1-e['equity']/eq[peak]['equity'])
        if dd>worst[0]:worst=(dd,peak,i)
    dd,pi,ti=worst;p,t=eq[pi],eq[ti]
    assert isclose(dd,report['max_drawdown_pct'],abs_tol=1e-8)
    recovery=next((e for e in eq[ti+1:] if e['equity']>=p['equity']),None)
    years=calendar_returns(eq,bars,periods(eq[0]['timestamp'],eq[-1]['timestamp'],'year'))
    row=dict(position_pct=pct,run_id=rid,config=cfg,report=report,
        annualized_return_pct=100*((report['final_equity']/cfg['initial_cash'])**(1/8)-1),
        drawdown=dict(pct=dd,peak_time=date(p['timestamp']),trough_time=date(t['timestamp']),
            peak_equity=p['equity'],trough_equity=t['equity'],
            recovery_time=date(recovery['timestamp']) if recovery else None,
            days_to_trough=(t['timestamp']-p['timestamp'])/86400000,
            days_peak_to_recovery=(recovery['timestamp']-p['timestamp'])/86400000 if recovery else None),
        yearly=years,source=source,result_hash=meta['result_hash'],
        execution_matched_candles=meta['execution_matched_candles'],execution_fallback_candles=meta['execution_fallback_candles'],
        independently_checked_final_equity=capital,
        chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart',path=str(folder.resolve()))
    return row,(cfg,source,ts)


def main():
    db=build_database_runtime(settings);service=LocalBacktestService(db);sweep=ParameterSweepService(service)
    try:
        baseline,reference=inspect(service,BASE,100);rows=[baseline]
        for pct,batch in BATCHES.items():
            s=sweep.get(batch);assert s['status']=='completed',(batch,s['counts'])
            row,_=inspect(service,s['items'][0]['run_id'],pct,reference);rows.append(row)
        result=dict(created_at=datetime.now(timezone.utc).isoformat(),rows=rows,batches=BATCHES,
            plan_hash=file_hash(OUT/'plan.json'),analysis_hash=file_hash(Path(__file__)),
            verification=dict(only_position_pct_changed=True,same_data_and_source=True,all_7903_trade_paths_equal=True,
                per_trade_capital_and_final_equity_checked=True,maximum_drawdowns_checked=True),
            notes=['由项目现有引擎执行，100%复用原结果，50%和25%各新跑一次；此脚本只读取结果并核算资金。',
                   '每笔按当时账户余额分配，其余保留现金无利息，手续费和滑点均为0。',
                   '年度收益按账户连续收盘权益计算，包含浮盈；最大回撤按15分钟收盘权益，盘中成交及保护更新用5分钟。',
                   '单笔价格收益、交易路径和胜率一致，但账户收益随投入比例变化。固定2%止损仍相对开仓价。',
                   '完整区间恰为8年；2018和2026自然年不完整。年化收益是8年几何平均，不代表每年都能获得。'])
        save('results.json',result)
        print(json.dumps([dict(position_pct=r['position_pct'],report=r['report'],annualized=r['annualized_return_pct'],
            drawdown=r['drawdown'],yearly=[dict(year=y['label'],return_pct=y['return_pct']) for y in r['yearly']]) for r in rows],ensure_ascii=False))
    finally:db.dispose()


if __name__=='__main__':main()
