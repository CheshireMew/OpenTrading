"""Two requested PAXG runs; retain the old full-history trace without rerunning."""
import argparse
from bisect import bisect_left
from collections import Counter
from datetime import datetime
from math import isclose, prod
from statistics import mean

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.backtest_history import align_execution_bars, validate_observed_bars
from app.domain.cloud_trade_attribution import calendar_returns, periods
from app.domain.local_backtest import Bar
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_strategy_versions import ROOT, snapshot
from scripts.cloud_width_reentry_study import keep
from scripts.intrabar_requested_followups import Frozen
from scripts.zec_intrabar_methods_study import run

OUT = ROOT/'docs/verification/paxg-intrabar-combined-20260913'
PRIOR = ROOT/'docs/verification/cloud-timeframe-20260911'
OLD = ROOT/'.opentrading_runtime/cloud-timeframe-20260911/traces/paxg/recent1-1h-full.json'
SOURCE = ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
ENGINE = ROOT/'app/domain/local_backtest.py'
STEP = 3600000
stamp = lambda s: int(datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()*1000)


def save_text(path, content):
    if path.exists():
        assert path.read_text(encoding='utf8') == content
    else:
        path.write_text(content, encoding='utf8')


def config(stop_method=0):
    old = read_json(OLD)
    _, spec = load_strategy(SOURCE)
    inherited = {k:v for k,v in old['parameters'].items() if k in spec.parameters}
    params = validate_parameters(spec, {**inherited, 'confirmation_level':3, 'max_wait_bars':2,
        'price_tick':.01, 'entry_bar_assumption':0, 'stop_method':stop_method,
        'stop_mult':1.5, 'stop_floor_pct':.5, 'stop_cap_pct':2,
        'direction_filter':False, 'stop_reentry':False})
    return LocalBacktestCommand(strategy=SOURCE.stem, parameters=params, symbol='PAXG/USDT',
        timeframe='1h', start=old['period'][0], end=old['period'][1], initial_cash=10000,
        position_pct=100, data_gap_policy='observed_bars', execution_timeframe='5m',
        intrabar_profit_protection=True).model_dump(mode='json')


def setup(db):
    return ResearchStudyService(Frozen(db, config(), OUT/'data.json', OUT/'execution-data.json'))


def prepare(studies):
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'study.json').exists():
        return
    assert file_hash(OLD) == '2cc09bb54a8a0e49f4c3ec565dbdc438332a755460d1fa666d263bb4b8fb87ae'
    old = read_json(OLD); prior = read_json(PRIOR/'results.json')
    assert old['metrics'] == prior['results']['paxg']['recent1']['1h']['full']
    verified = read_json(ROOT/'docs/verification/zec-intrabar-methods-20260913/baseline-parity.json')
    assert file_hash(SOURCE) == verified['source_hash'] and file_hash(ENGINE) == verified['engine_hash']
    data = read_json(PRIOR/'data.json')['paxg']; start, end = map(stamp, old['period'])
    raw = ROOT/data['1h']['path']; fine = ROOT/data['5m']['path']
    assert file_hash(raw) == data['1h']['data_hash'] and file_hash(fine) == data['5m']['data_hash']
    rows = read_json(raw); times = [b[0] for b in rows]
    i,j = bisect_left(times,start),bisect_left(times,end)
    rows = rows[i-650:j]
    bars,gaps = validate_observed_bars(rows,start,end,STEP,650,end)
    fine_rows = [b for b in read_json(fine) if start <= b[0] < end]
    fine_bars,_ = validate_observed_bars(fine_rows,start,end,300000,0,end)
    _, aligned = align_execution_bars(bars[650:],fine_bars,STEP,300000)
    keep(OUT/'data.json',rows); keep(OUT/'execution-data.json',fine_rows)
    keep(OUT/'baseline-trace.json',old)
    keep(OUT/'baseline-origin.json',dict(path=str(OLD.relative_to(ROOT)),sha256=file_hash(OLD),
        prior_results_hash=file_hash(PRIOR/'results.json'), prior_provenance=old['provenance'],
        selection='原EMA通道候选共同四年内的PAXG最高版本：1小时EMA89，+101.23%。本次比较同一版本完整近六年，原收益+1.48%；未重新筛选其他策略。',
        full_period=old['period'],original_hourly=data['1h'],original_fine=data['5m']))
    keep(OUT/'fine-data-check.json',dict(**aligned,history_gaps=gaps,
        data_hash=file_hash(OUT/'data.json'),execution_data_hash=file_hash(OUT/'execution-data.json')))
    rules='''# PAXG：原版与两个组合

按用户最后要求只新增两次回测，原版使用已有逐笔结果，不重跑原版，不加单因素或搜参。

共同范围：PAXG/USDT，1小时信号，2020-09-25至2026-09-10（UTC），650根相同预热数据。原EMA通道共同四年比较第一为EMA89版本（+101.23%）；完整近六年旧收益+1.48%。不把不同起点的累计收益混在一起比较。

共同参数：中心EMA89（最高最低均价），W=EMA(最高价−最低价,31)，突破门槛0.8W，不追超过1.5W；浮盈2%启动保护，回吐最高浮盈50%；保留原始反向信号平仓。

旧版：原信号后下根开盘入场，固定2%止损，1小时收盘更新保护。
新固定止损版：仅信号后的两根K线（信号算第1根，故第2或第3根）盘中突破信号实体入场，固定2%止损，每根5分钟收盘更新保护、下一根5分钟生效。
新振幅止损版：与新固定止损版完全相同，仅把止损换为1.5倍W，限制0.5%—2%。W和百分比用挂单前已完成K线计算，以实际成交价固定止损距离，持仓中不放宽。

突破方向、委托价格和追价上限在前一根1小时收盘确定，突破一个0.01价格单位才触发；反向信号取消旧等待，超时作废，每个信号最多成交一次，持仓不重复入场，不增加止损后重进。保留2%启动和50%回吐，不加入35%等过去无改善方向。

两个新版本都用同一份5分钟行情核对成交。5分钟行情不完整或聚合OHLC不一致时，沿用项目的1小时回退处理，清单保留。旧版沿用原1小时成交估计，故旧/新差异同时包含规则和成交精度变化；两个新版本之间可以单独比较止损。5分钟仍不是逐笔行情。

全仓复利、不加杠杆、不计手续费滑点。最大回撤按1小时收盘权益计算；已见历史探索，不是未见验证。所有规则在运行前固定，保留行情、参数、策略/引擎副本、逐笔交易、权益和年度结果。
'''
    save_text(OUT/'RULES.md',rules)
    cases=[dict(id=cid,name=name,variant=cid,period='PAXG完整近六年',role='exploration',
                previously_seen=True,command=config(method)) for cid,name,method in [
        ('fine_fixed','盘中确认＋更快保护＋固定2%止损',0),
        ('fine_width','盘中确认＋更快保护＋振幅止损',1)]]
    plan=dict(title='PAXG原版与盘中确认、更快保护组合：固定/振幅止损',family='ema_cloud',
        objective='两个组合比原版收益是否改善，换成振幅止损是否进一步改善。',
        change_reason='用户最终指定原版复用，只新增固定止损组合、振幅止损组合两次。',
        decision_rule='比较同一近六年总收益；两个新版本仅止损不同，原版来自已保存历史。',
        stop_rule='只新增两次，不重跑原版，不追加参数搜索。',max_new_runs=2,cases=cases,
        questions=[dict(id='combined',text='两个组合相对旧版是否改善？'),dict(id='stop',text='相同确认和保护下，振幅止损是否超过固定2%？')])
    keep(OUT/'plan.json',plan); state=studies.create(plan); keep(OUT/'study.json',state)
    snapshot('101_paxg_combination_frozen',[SOURCE,ENGINE,ROOT/'scripts/paxg_intrabar_combined_study.py',
        ROOT/'scripts/intrabar_requested_followups.py',ROOT/'scripts/zec_intrabar_methods_study.py',
        ROOT/'strategies/trend_cloud_timeframe_v6.py',ROOT/'strategies/trend_cloud_parameters_v4.py']+
        list(OUT.glob('*.json'))+[OUT/'RULES.md'])
    print('规则已冻结，新增2次；细行情匹配',aligned['matched'],'回退',aligned['fallback'],flush=True)


def summarize(result,rows):
    ts=result['trades']; report=result['report']
    assert len(ts)==report['total_trades']==report['wins']+report['losses']+report['breakeven']
    assert isclose(100*(prod(1+t['return_pct']/100 for t in ts)-1),report['return_pct'],abs_tol=1e-6)
    eq=result['equity']
    return dict(report=report,annual=calendar_returns(eq,rows,periods(eq[0]['timestamp'],eq[-1]['timestamp'],'year')),
        exits=dict(Counter(t['exit_reason'] for t in ts)),loss_exits=dict(Counter(t['exit_reason'] for t in ts if t['profit']<0)),
        protection_loss_count=sum(t['profit']<0 and t['exit_reason']=='profit_protection' for t in ts),
        mean_win_pct=mean(t['return_pct'] for t in ts if t['profit']>0),mean_loss_pct=mean(t['return_pct'] for t in ts if t['profit']<0))


def finish(studies,identifier):
    if studies.state(identifier)[4]=='completed':return
    rows=read_json(OUT/'data.json');idx={b[0]:i for i,b in enumerate(rows)}
    old=read_json(OUT/'baseline-trace.json')
    # Audit the original formula only: no orders executed, no extra backtest.
    from strategies.trend_cloud_parameters_v4 import Calculation
    calc=Calculation({**old['parameters'],'record_indicators':True});checks=[]
    for i,row in enumerate(rows):
        observation=calc.update(Bar(*row),decisions=i>=650)
        if i>=650:checks.append((row[0],observation.checks['原做多信号'],observation.checks['原做空信号']))
    result=dict(baseline=dict(name='原版：固定2%止损',parameters=old['parameters'],**summarize(old,rows)))
    hashes=set();verification={}
    for case,rid,task in studies.case_runs(identifier):
        studies.verify_run(task);folder=studies.backtests.directory(rid);r=read_json(folder/'result.json')
        assert [(x['timestamp'],x['checks']['原做多信号'],x['checks']['原做空信号']) for x in r['indicators']]==checks
        observations={x['timestamp']:x['values'] for x in r['indicators']};used=Counter();lineage=[]
        for t in r['trades']:
            posted=t['entry_order_signal_time'];v=observations[posted];origin=int(v['确认起点时间'])
            bar_time=t['entry_time']//STEP*STEP;wait=idx[bar_time]-idx[origin]
            assert idx[bar_time]==idx[posted]+1 and wait in (1,2)
            assert t['entry_trigger']==v['下根突破入场价'] and not v['重进委托']
            signal=rows[idx[origin]];assert v['信号原始价位']==(max(signal[1],signal[4]) if t['side']=='long' else min(signal[1],signal[4]))
            used[origin,t['side']]+=1;assert used[origin,t['side']]==1
            lineage.append(dict(trade_id=t['trade_id'],origin=origin,posted=posted,entry=t['entry_time'],wait=wait,
                trigger=t['entry_trigger'],side=t['side'],return_pct=t['return_pct'],exit_reason=t['exit_reason']))
        risk=[s['stop_loss_pct'] for s in r['signals'] if s.get('order_type')=='stop_entry' and s['status']=='executed']
        assert len(risk)==len(r['trades'])
        assert all(.5<=x<=2 for x in risk) if case['id']=='fine_width' else all(x==2 for x in risk)
        hashes.add((task['metadata']['data_hash'],task['metadata']['execution_data_hash']))
        keep(OUT/f'{case["id"]}-lineage.json',lineage)
        result[case['id']]=dict(name=case['name'],run_id=rid,parameters=case['config']['parameters'],
            **summarize(r,rows),initial_stop_pct=dict(min=min(risk),max=max(risk),mean=mean(risk)),
            execution_detail=r['execution_detail'],entry_bar_ambiguous=sum(t['entry_bar_ambiguous'] for t in r['trades']),
            result_hash=file_hash(folder/'result.json'),data_hash=task['metadata']['data_hash'],execution_data_hash=task['metadata']['execution_data_hash'],
            chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart&theme=light&tz=8')
        verification[case['id']]=dict(entries_checked=len(lineage),original_signals_equal=True,no_duplicate_signal_fills=True)
    assert len(hashes)==1 and len(result)==3
    cases=studies.case_runs(identifier);a,b=[c[0]['config'] for c in cases]
    assert {**a,'parameters':{**a['parameters'],'stop_method':1}}==b
    keep(OUT/'results.json',dict(study_id=identifier,results=result))
    keep(OUT/'verification.json',dict(new_runs=2,baseline_reruns=0,same_data_hashes=list(hashes),checks=verification,
        source_hash=file_hash(SOURCE),engine_hash=file_hash(ENGINE),
        prior_tests='docs/verification/zec-intrabar-methods-20260913/test-results.json'))
    ret={k:v['report']['return_pct'] for k,v in result.items()}
    conclusion='；'.join(f'{v["name"]}：{ret[k]:+,.2f}%' for k,v in result.items())+'。'
    stop='振幅止损'+('提高' if ret['fine_width']>ret['fine_fixed'] else '降低')+'了本次组合的累计收益。'
    lines=['# PAXG：三个版本比较','',conclusion+stop,'',
        '1小时，EMA89，2020-09-25至2026-09-10；原版复用，仅新增两次。全仓复利，不计手续费滑点。','',
        '| 版本 | 累计收益 | 交易 | 赚 | 亏 | 平 | 胜率 | 最大回撤 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for v in result.values():
        p=v['report'];name=f'[{v["name"]}]({v["chart"]})' if v.get('chart') else v['name']
        lines.append(f'| {name} | {p["return_pct"]:+,.2f}% | {p["total_trades"]} | {p["wins"]} | {p["losses"]} | {p["breakeven"]} | {p["win_rate"]:.2f}% | {p["max_drawdown_pct"]:.2f}% |')
    lines+=['','新组合都为第2或第3根盘中突破信号实体，每5分钟收盘更新保护、下一根生效。固定止损2%；振幅止损1.5W、限制0.5%—2%。仍浮盈2%启动，回吐50%。','',
        '旧版沿用1小时成交估计，新组合用5分钟核对成交，因此旧/新比较包含成交精度变化；两个新组合之间只有止损不同，可以直接判断止损的影响。没有单独拆分入场确认与保护各自贡献。','',
        '| 年份 | 原版 | 组合固定止损 | 组合振幅止损 |','|---|---:|---:|---:|']
    for i,y in enumerate(result['baseline']['annual']):
        lines.append('| '+y['label']+' | '+' | '.join(f'{v["annual"][i]["return_pct"]:+.2f}%' for v in result.values())+' |')
    lines+=['','首尾为不完整年度；年度收益从同一次连续回测权益计算。历史已见，未追加调参；不代表未来稳定盈利。','',
        'RULES.md记录规则，plan.json记录完整参数，baseline-origin.json记录旧版选取依据，baseline-trace.json保留旧交易与权益。results.json记录新run_id、结果和图表入口；项目各run_id目录保留行情、策略、引擎、订单、逐笔交易、指标和权益。verification.json及*-lineage.json记录核对。','']
    save_text(OUT/'README.md','\n'.join(lines))
    answers=[dict(question=q,conclusion=text,decision=decision,evidence=['artifact:baseline','artifact:results','case:fine_fixed','case:fine_width'],
        scope='PAXG近六年1小时，同参数组合比较。',limitation='旧版为1小时成交，新版为5分钟成交；全仓复利无费用，历史已见。') for q,text,decision in [
        ('combined',conclusion,'keep' if max(ret['fine_fixed'],ret['fine_width'])>ret['baseline'] else 'reject'),
        ('stop',stop,'keep' if ret['fine_width']>ret['fine_fixed'] else 'reject')]]
    keep(OUT/'answers.json',answers)
    for name,file in [('baseline','baseline-trace.json'),('rules','RULES.md'),('results','results.json'),('report','README.md'),('verification','verification.json')]:
        if name not in studies.state(identifier)[2]:studies.attach(identifier,name,OUT/file,name)
    for answer in answers:
        if answer['question'] not in studies.state(identifier)[1]:studies.answer(identifier,answer)
    keep(OUT/'completion.json',studies.complete(identifier))
    snapshot('102_paxg_combination_completed',[ROOT/'scripts/paxg_intrabar_combined_study.py']+
        [p for p in OUT.iterdir() if p.is_file() and p.name not in ('data.json','execution-data.json','baseline-trace.json')])
    print(conclusion+stop,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run','finish']);args=parser.parse_args()
    db=build_database_runtime(settings)
    try:
        studies=setup(db)
        if args.action=='prepare':prepare(studies)
        else:globals()[args.action](studies,read_json(OUT/'study.json')['id'])
    finally:db.dispose()
