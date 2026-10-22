"""ETH15m, fixed 8-week lookback / 2-week reviews; only EMA and trigger vary."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from itertools import product
from math import isclose

from app.domain.local_backtest import Bar, simulate
from app.domain.backtest_history import align_execution_bars
from app.domain.cloud_intrabar_selection_v1 import ScheduledCloud, choose, past_score
from app.domain.cloud_trade_attribution import summary, compound, calendar_returns, periods
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_strategies import load_strategy
from scripts.cloud_strategy_versions import ROOT, snapshot
from scripts.cloud_width_reentry_study import keep
from scripts.paxg_intrabar_combined_study import save_text
from scripts.cloud_walkforward_study import read_zip, write_zip
from scripts.trend_cloud_study import stamp

OUT=ROOT/'docs/verification/eth-intrabar-short-window-20260913'
RUNTIME=ROOT/'.opentrading_runtime/eth-intrabar-short-window-20260913'
BASE=ROOT/'.opentrading_runtime/local_backtests/3f31380c7267449f53743dc1fe5bcebd'
SOURCE=ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
STEP=900000
WEEK=7*86400000
START=stamp('2020-12-28T00:00:00Z')
END=stamp('2026-09-10T00:00:00Z')
SPLIT=stamp('2024-09-09T00:00:00Z')
FIXED='c55_t0p4'


def prepare():
    if (OUT/'plan.json').exists():return
    OUT.mkdir(parents=True,exist_ok=True)
    cfg=read_json(BASE/'config.json')
    assert file_hash(SOURCE)==file_hash(BASE/'strategy.py')
    assert file_hash(ROOT/'app/domain/local_backtest.py')==file_hash(BASE/'engine.py')
    candidates={f'c{n}_t{x:g}'.replace('.','p'):{**cfg['parameters'],'center_length':n,'trigger_mult':x}
        for n,x in product((34,55,89),(.4,.8))}
    files=[SOURCE,ROOT/'app/domain/local_backtest.py',ROOT/'app/domain/cloud_intrabar_selection_v1.py',
        ROOT/'scripts/eth_intrabar_short_window_study.py',ROOT/'test/test_cloud_intrabar_selection.py']
    plan=dict(symbol='ETH/USDT',timeframe='15m',execution_timeframe='5m',start=START,end=END,split=SPLIT,
        lookback_weeks=8,update_weeks=2,minimum_closed_trades=20,candidates=candidates,fixed=FIXED,
        dates=list(range(START,END,2*WEEK)),initial_cash=10000,position_pct=100,fees=0,slippage=0,leverage=1,
        source_hashes={str(p.relative_to(ROOT)):file_hash(p) for p in files},
        data={name:dict(path=str((BASE/name).relative_to(ROOT)),sha256=file_hash(BASE/name)) for name in ('data.json','execution_data.json')},
        reused_candidate=dict(id=FIXED,path=str((BASE/'result.json').relative_to(ROOT)),sha256=file_hash(BASE/'result.json')),
        tests=dict(passed=4,command='python -m pytest -q test/test_cloud_intrabar_selection.py'),
        scope='One adaptive policy and same-period fixed control. Five new candidate paths; original candidate reused. No other window, parameter or timeframe search.',
        selection='Rank trailing marked-equity return; positive return and >=20 round trips opened in window and known completed by review close. Exclude next-open exits at the review boundary. Ties by candidate ID; no eligible candidate means cash.',
        transitions='Same choice preserves position, protection and confirmation state. Changed choice cancels old pending entries and sends close at review close for next actual open, then waits for a fresh signal. Original simulator gap stops retain priority at that open. All inactive indicators remain causally updated.',
        limitations='Historically selected 8w/2w method and previously seen data; this is descriptive, not untouched validation. Native 5m ambiguity remains. Full history baseline +61349.61% is not the same date range as this comparison.')
    rules='''ETH固定15分钟，仅在EMA34/55/89 × 门槛0.4/0.8倍，共6组中选择。振幅31、不追2倍、仅原信号第2或第3根盘中突破实体、固定1%止损、浮盈2%启动、回吐50%、每5分钟收盘更新保护下一根生效、原反向平仓均固定。

每隔2周、UTC周一00:00检查最近8周的账户权益收益。要求正收益且窗口内开仓、在检查前已知完整平仓至少20笔；同收益按候选ID。没有合格者则空仓。评分包含窗口起点之前已持有仓位的窗口内浮动盈亏，完整交易门槛只数窗口内往返。检查时刻才发生的开盘退出不用于之前收盘的决策。检查日、门槛与方法均不按新结果调整。

参数不变继续原持仓及挂单；参数改变取消旧确认，下一实际开盘平旧仓，新参数等待自己的新收盘信号。开盘跳空触发的原止损优先，沿用原引擎。所有候选的指标持续按过去行情计算，不在切换日重新启动EMA。

使用项目原ETH15分钟和5分钟完整快照，六年原候选复用，其余5条候选路径用于只读取当时以前的评分。自动方案与固定EMA55/0.4方案统一从2020-12-28空仓开始，到2026-09-10结束；前面行情只供指标与8周观察。不直接拿此区间与2020-09-10起的+61,349.61%比较。所有版本全仓复利，无手续费滑点和杠杆。保留代码、行情哈希、完整路径、逐次评分选择和年度。8周/2周来自此前事后排名，当前数据也已见，本轮不是独立未来验证。
'''
    save_text(OUT/'RULES.md',rules)
    keep(OUT/'plan.json',plan)
    snapshot('110_eth_intrabar_short_window_frozen',files+[OUT/'plan.json',OUT/'RULES.md'])
    print('冻结：ETH15分钟，6组候选，8周观察/2周检查，仅1种自动方案。',flush=True)


def plan():
    p=read_json(OUT/'plan.json')
    for path,h in p['source_hashes'].items():assert file_hash(ROOT/path)==h,path
    return p


@lru_cache(maxsize=1)
def loaded():
    p=plan()
    for v in p['data'].values():assert file_hash(ROOT/v['path'])==v['sha256']
    rows=read_json(BASE/'data.json');bars=[Bar(*r) for r in rows]
    fine=[Bar(*r) for r in read_json(BASE/'execution_data.json')]
    detail,check=align_execution_bars(bars[650:],fine,STEP,300000)
    return rows,bars,detail,check


def candidate(cid):
    out=OUT/'candidates'/f'{cid}.json'
    if out.exists():return read_json(out)
    p=plan()
    if cid==FIXED:
        path=ROOT/p['reused_candidate']['path'];assert file_hash(path)==p['reused_candidate']['sha256']
        report=read_json(path)['report']
    else:
        _,bars,detail,_=loaded();mod,_=load_strategy(SOURCE)
        r=simulate(bars,mod,p['candidates'][cid],warmup=650,step_ms=STEP,execution_bars=detail,intrabar_profit_protection=True)
        path=RUNTIME/'candidates'/f'{cid}.json.gz';write_zip(path,r);report=r['report']
    record=dict(id=cid,path=str(path.relative_to(ROOT)),sha256=file_hash(path),parameters=p['candidates'][cid],report=report)
    keep(out,record)
    return record


def candidates(workers):
    p=plan();pending=[cid for cid in p['candidates'] if not (OUT/'candidates'/f'{cid}.json').exists()]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for f in as_completed([pool.submit(candidate,cid) for cid in pending]):
            r=f.result();print('候选路径保存',r['id'],flush=True)


def lock():
    if (OUT/'selection-lock.json').exists():return
    p=plan();rows,_,_,check=loaded();times={r[0] for r in rows}
    fallback={x['timestamp'] for x in check['rejected']}
    scores={str(t):{} for t in p['dates']}
    for cid in p['candidates']:
        meta=read_json(OUT/'candidates'/f'{cid}.json');path=ROOT/meta['path']
        assert file_hash(path)==meta['sha256']
        trace=read_zip(path) if path.suffix=='.gz' else read_json(path)
        for at in p['dates']:
            assert at in times and at-STEP in times and at-8*WEEK in times
            scores[str(at)][cid]=past_score(trace,at-8*WEEK,at,fallback=fallback)
        print('过去评分已保存',cid,flush=True)
    decisions=[]
    for at in p['dates']:
        s=choose(scores[str(at)])
        decisions.append(dict(at=at,history_start=at-8*WEEK,**s))
    keep(OUT/'past-scores.json',scores)
    keep(OUT/'selection-lock.json',dict(plan_hash=file_hash(OUT/'plan.json'),scores_hash=file_hash(OUT/'past-scores.json'),decisions=decisions))
    keep(OUT/'data-check.json',check)
    print('选择已冻结：',len(decisions),'次检查，尚未计算自动方案后续收益。',flush=True)


def audit_entries(result,rows,decisions):
    observations={o['timestamp']:o for o in result['indicators']};idx={r[0]:i for i,r in enumerate(rows)}
    dates=[d['at'] for d in decisions];used=Counter();lineage=[]
    for t in result['trades']:
        posted=t['entry_order_signal_time'];v=observations[posted]['values'];origin=int(v['确认起点时间'])
        at=t['entry_time']//STEP*STEP
        assert idx[at]==idx[posted]+1 and idx[at]-idx[origin] in (1,2)
        assert t['entry_trigger']==v['下根突破入场价'] and not v['重进委托']
        cp=decisions[bisect_right(dates,posted)-1]['chosen'];assert cp is not None
        used[cp,origin,t['side']]+=1;assert used[cp,origin,t['side']]==1
        sig=rows[idx[origin]];assert v['信号原始价位']==(max(sig[1],sig[4]) if t['side']=='long' else min(sig[1],sig[4]))
        lineage.append(dict(trade=t['trade_id'],candidate=cp,origin=origin,posted=posted,entry=t['entry_time']))
    risk=[s for s in result['signals'] if s.get('order_type')=='stop_entry' and s['status']=='executed']
    assert len(risk)==len(lineage)
    assert all(s['stop_loss_pct']==1 and s['profit_protection']==dict(activation_pct=2,giveback_pct=50) for s in risk)
    return lineage


def policy(name):
    out=OUT/'policies'/f'{name}.json'
    if out.exists():return read_json(out)
    p=plan();locked=read_json(OUT/'selection-lock.json')
    assert locked['plan_hash']==file_hash(OUT/'plan.json') and locked['scores_hash']==file_hash(OUT/'past-scores.json')
    rows,bars,detail,check=loaded();warmup=bisect_left([r[0] for r in rows],START)
    mod,_=load_strategy(SOURCE)
    decisions=locked['decisions'] if name=='adaptive' else [dict(at=START,chosen=FIXED)]
    strategy=ScheduledCloud(mod.Calculation,p['candidates'],decisions,start=START) if name=='adaptive' else mod
    r=simulate(bars,strategy,p['candidates'][FIXED],warmup=warmup,step_ms=STEP,execution_bars=detail,intrabar_profit_protection=True)
    lineage=audit_entries(r,rows,decisions)
    keep(OUT/'lineage'/f'{name}.json',lineage)
    transitions=strategy.transitions if name=='adaptive' else []
    switches={s['decision_time'] for s in r['signals'] if s['action']=='close' and s['reason']=='parameter_change' and s['status']=='executed'}
    derived=[{**t,'exit_category':'parameter_change' if t['exit_time'] in switches and t['exit_reason']=='signal' and t['exit_phase']=='open' else t['exit_reason']} for t in r['trades']]
    stats=summary(derived)
    assert isclose(stats['compound_return_pct'],r['report']['return_pct'],rel_tol=1e-9,abs_tol=1e-6)
    years=calendar_returns(r['equity'],rows,periods(START,END,'year'))
    split=calendar_returns(r['equity'],rows,[('early',START,SPLIT),('later',SPLIT,END)])
    path=RUNTIME/'policies'/f'{name}.json.gz';write_zip(path,r)
    usage=Counter()
    for i,d in enumerate(decisions):usage[str(d['chosen'])]+=((decisions[i+1]['at'] if i+1<len(decisions) else END)-d['at'])/86400000
    value=dict(name=name,path=str(path.relative_to(ROOT)),sha256=file_hash(path),report=r['report'],statistics=stats,annual=years,segments=split,
        transitions=transitions,changes=len(transitions),reviews=len(decisions),days_by_candidate=dict(usage),
        exit_counts=dict(Counter(t['exit_category'] for t in derived)),entries_checked=len(lineage),execution_detail=r['execution_detail'])
    keep(out,value);print(name,'完成',r['report']['return_pct'],r['report']['total_trades'],flush=True)
    return value


def run():
    for name in ('fixed','adaptive'):policy(name)


def finish():
    if (OUT/'results.json').exists():return
    p=plan();r={k:read_json(OUT/'policies'/f'{k}.json') for k in ('fixed','adaptive')}
    for v in r.values():assert file_hash(ROOT/v['path'])==v['sha256']
    locked=read_json(OUT/'selection-lock.json');scores=read_json(OUT/'past-scores.json')
    for d in locked['decisions']:assert choose(scores[str(d['at'])])=={k:d[k] for k in ('chosen','eligible')}
    keep(OUT/'verification.json',dict(source_hashes_checked=True,data_hashes_checked=True,decisions_checked=len(locked['decisions']),
        entries_checked={k:v['entries_checked'] for k,v in r.items()},source_tests=p['tests'],same_timeframe='15m',same_dates=[START,END],
        candidate_count=6,lookback_weeks=8,update_weeks=2,no_added_parameter_search=True))
    b,n=r['fixed']['report'],r['adaptive']['report']
    conclusion=f'同期间固定版{b["return_pct"]:+,.2f}%，8周/2周自动选择{n["return_pct"]:+,.2f}%；胜率{b["win_rate"]:.2f}%→{n["win_rate"]:.2f}%，最大回撤{b["max_drawdown_pct"]:.2f}%→{n["max_drawdown_pct"]:.2f}%。'
    lines=['# ETH15分钟：8周观察、每2周换参数','',conclusion,'',
        '固定15分钟，只选EMA34/55/89与门槛0.4/0.8。其他规则与+61,349.61%版本一致。两组比较期统一2020-12-28至2026-09-10，因此固定对照数值不同于2020-09-10起的六年结果。全仓复利，不计手续费滑点。','',
        '| 版本 | 收益 | 笔数 | 盈利 | 亏损 | 胜率 | 最大回撤 |','|---|---:|---:|---:|---:|---:|---:|']
    for name,v in r.items():
        q=v['report'];lines.append(f'| {name} | {q["return_pct"]:+,.2f}% | {q["total_trades"]} | {q["wins"]} | {q["losses"]} | {q["win_rate"]:.2f}% | {q["max_drawdown_pct"]:.2f}% |')
    lines+=['','| 年份 | 固定版 | 自动选择 |','|---|---:|---:|']
    for a,b in zip(r['fixed']['annual'],r['adaptive']['annual']):
        assert a['label']==b['label'];lines.append(f'| {a["label"]} | {a["return_pct"]:+,.2f}% | {b["return_pct"]:+,.2f}% |')
    lines+=['',f'检查{r["adaptive"]["reviews"]}次，实际改变选择{r["adaptive"]["changes"]}次，空仓选择合计{r["adaptive"]["days_by_candidate"].get("None",0):.1f}天。',
        '', '过去8周成绩与每次选择在past-scores.json和selection-lock.json；完整交易、订单、指标、权益在本轮runtime路径，文件哈希和汇总在policies与candidates目录。原版全部保留。',
        '', '每次选参只使用当时已知数据，但8周/2周本身来自先前事后挑选，且这些历史已经研究过，因此即使改善也不能据此宣布排除过拟合。后段数据仅作描述，不是未接触的验证。首尾年度不完整。', '']
    save_text(OUT/'README.md','\n'.join(lines))
    keep(OUT/'results.json',dict(conclusion=conclusion,results=r))
    snapshot('111_eth_intrabar_short_window_completed',[ROOT/'scripts/eth_intrabar_short_window_study.py']+list(OUT.glob('*.json'))+[OUT/'README.md'])
    print(conclusion,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','candidates','lock','run','finish']);parser.add_argument('--workers',type=int,default=2)
    a=parser.parse_args()
    if a.action=='candidates':candidates(a.workers)
    else:globals()[a.action]()
