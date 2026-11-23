"""One ZEC threshold comparison and a frozen 54-case PAXG parameter matrix."""
import argparse
from bisect import bisect_left
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout, redirect_stderr
from itertools import product
from statistics import median

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.backtest_history import align_execution_bars, validate_observed_bars
from app.domain.cloud_trade_attribution import calendar_returns
from app.domain.local_backtest import Bar
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_service import LocalBacktestService
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_strategy_versions import ROOT, snapshot
from scripts.cloud_width_reentry_study import keep
from scripts.paxg_intrabar_combined_study import save_text, summarize, stamp
from scripts.local_backtest_worker import execute

OUT=ROOT/'docs/verification/zec-paxg-entry-parameters-20260913'
SOURCE=ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
ENGINE=ROOT/'app/domain/local_backtest.py'
ORIGINAL={'zec':'b44a8ccf09545f17b66f0b277477c64b','paxg':'762c40fac52d84afa302232863a1d7df'}
STEPS={'30m':1800000,'1h':3600000,'4h':14400000}
AXES={'center_length':[55,89,144],'width_length':[31,50],'trigger_mult':[.4,.8,1.2]}
START='2021-01-22T00:00:00Z';SPLIT='2024-09-10T00:00:00Z';END='2026-09-10T00:00:00Z'


def original(kind):return ROOT/'.opentrading_runtime/local_backtests'/ORIGINAL[kind]


class Frozen(LocalBacktestService):
    def __init__(self,db,kind):
        super().__init__(db);self.kind=kind

    def paths(self,cfg):
        if self.kind=='zec':return original('zec')/'data.json',original('zec')/'execution_data.json'
        return OUT/'paxg/data'/f'{cfg["timeframe"]}.json',OUT/'paxg/data/5m-20210122.json'

    def prepare(self,command):
        cfg,source,metadata=super().prepare(command)
        base=read_json(original(self.kind)/'config.json')
        fixed=['symbol','end','initial_cash','position_pct','data_gap_policy','execution_timeframe','intrabar_profit_protection']
        for key in fixed:assert cfg[key]==base[key],key
        if self.kind=='zec':
            assert cfg['start']==base['start'] and cfg['timeframe']==base['timeframe']
            assert cfg['parameters']=={**base['parameters'],'trigger_mult':.4}
        else:
            assert cfg['start']==START and cfg['timeframe'] in STEPS
            assert all(cfg['parameters'][k] in v for k,v in AXES.items())
            assert {k:v for k,v in cfg['parameters'].items() if k not in AXES}=={k:v for k,v in base['parameters'].items() if k not in AXES}
        data,fine=self.paths(cfg)
        metadata.update(data_hash=file_hash(data),execution_data_hash=file_hash(fine),
            input_data_path=str(data.relative_to(ROOT)),execution_source=str(fine.relative_to(ROOT)))
        return cfg,source,metadata

    def _create(self,cfg,source,metadata,parent_id=None,data=None,identifier=None,*,execution_data=None):
        coarse,fine=self.paths(cfg)
        return super()._create(cfg,source,metadata,parent_id,coarse.read_bytes() if data is None else data,
            identifier,execution_data=fine.read_bytes() if execution_data is None else execution_data)


def setup(db,kind):return ResearchStudyService(Frozen(db,kind))


def prepare(kind):
    out=OUT/kind;out.mkdir(parents=True,exist_ok=True)
    if (out/'study.json').exists():return
    base=read_json(original(kind)/'config.json')
    assert file_hash(original(kind)/'strategy.py')==file_hash(SOURCE)
    assert file_hash(original(kind)/'engine.py')==file_hash(ENGINE)
    cases=[]
    if kind=='zec':
        cases=[dict(id='baseline',name='原1.2倍门槛',variant='baseline',period='原七年',role='exploration',previously_seen=True,
                    command=base,reuse_run=ORIGINAL[kind]),
               dict(id='trigger04',name='只改0.4倍门槛',variant='trigger04',period='原七年',role='exploration',previously_seen=True,
                    command={**base,'parameters':{**base['parameters'],'trigger_mult':.4}})]
        parent=read_json(ROOT/'docs/verification/zec-intrabar-methods-20260913/study.json')['id']
        questions=[dict(id='trigger',text='ZEC30分钟582.26%版本只将1.2改0.4是否改善？')]
        rules='ZEC/USDT，2019-09-10至2026-09-10，30分钟。复用582.26%原结果，只新增门槛0.4一组；EMA144、振幅31、不追3倍、仅第2/3根盘中突破信号实体、固定1%止损、浮盈1%启动、回吐35%、每5分钟收盘更新保护下一根生效、原反向信号平仓均不变。同一份原始30分钟/5分钟行情，最多每原信号成交一次，不加重进。'
        count=1
    else:
        data_dir=out/'data';data_dir.mkdir(exist_ok=True)
        earlier=read_json(ROOT/'docs/verification/cloud-timeframe-20260911/data.json')['paxg']
        four=read_json(ROOT/'docs/verification/cross-market-trend-20260911-r2/data.json')['paxg']['4h']
        fine_meta=earlier['5m'];fine_path=ROOT/fine_meta['path']
        assert file_hash(fine_path)==fine_meta['data_hash']
        lo,hi=stamp(START),stamp(END)
        fine=[b for b in read_json(fine_path) if lo<=b[0]<hi]
        fine_bars,_=validate_observed_bars(fine,lo,hi,300000,0,hi)
        keep(data_dir/'5m-20210122.json',fine);records={}
        for tf,step in STEPS.items():
            meta=four if tf=='4h' else earlier[tf];path=ROOT/meta['path']
            assert file_hash(path)==meta['data_hash']
            rows=read_json(path);times=[b[0] for b in rows];i,j=bisect_left(times,lo),bisect_left(times,hi)
            rows=rows[i-650:j];bars,gaps=validate_observed_bars(rows,lo,hi,step,650,hi)
            _,alignment=align_execution_bars(bars[650:],fine_bars,step,300000)
            keep(data_dir/f'{tf}.json',rows)
            records[tf]=dict(source=meta,data_hash=file_hash(data_dir/f'{tf}.json'),history_gaps=gaps,**alignment)
        keep(out/'data-check.json',dict(timeframes=records,execution_data_hash=file_hash(data_dir/'5m-20210122.json'),fine_source=fine_meta,
            start_adjustment='Original January 1 preparation found missing December 2020 hourly/30-minute warmup bars. January 22 is the earliest shared midnight with 650 contiguous warmup bars for all three timeframes. The unused January 1 fine-data copy is retained.'))
        for tf,values in product(STEPS,product(*AXES.values())):
            p={**base['parameters'],**dict(zip(AXES,values))}
            cid=f'{tf}_c{values[0]}_w{values[1]}_t{values[2]:g}'.replace('.','p')
            cfg={**base,'timeframe':tf,'start':START,'parameters':p}
            cases.append(dict(id=cid,name=f'{tf} EMA{values[0]} 振幅{values[1]} 门槛{values[2]:g}',variant=cid,
                period='共同2021-01-22至2026-09-10',role='exploration',previously_seen=True,command=cfg))
        count=54;assert len(cases)==count
        parent=read_json(ROOT/'docs/verification/paxg-intrabar-combined-20260913/study.json')['id']
        questions=[dict(id='ranking',text='固定54组中收益最高的组合是什么，相对同区间原参数是否改善？'),
                   dict(id='factors',text='EMA、振幅周期、突破门槛和周期各自是否有一致改善？'),
                   dict(id='later',text='前段选出的组合在后两年怎样，总收益冠军是否依赖后段？')]
        rules='PAXG/USDT。固定54组联合组合：EMA55/89/144，振幅周期31/50，突破0.4/0.8/1.2倍，30分钟/1小时/4小时。保留不追1.5倍、固定2%止损、浮盈2%启动、回吐50%、仅第2/3根盘中突破信号实体、5分钟收盘更新保护下一根生效、原反向平仓，不加重进或振幅止损。原定2021-01-01起点的预热区间存在2020年12月缺口，因此在任何PAXG新回测开始前统一顺延至2021-01-22至2026-09-10；三种周期都有完整650根预热。原EMA89/振幅31/门槛0.8/1小时在同一区间作对照；此前+7.83%从2020-09-25起，保留旧记录，不把不同期间当作同一次回测。仅从这些已冻结组合比较，不按结果扩展。完整结果同时列2024-09-10之前和之后连续权益收益；前段收益最高者预先作为后段对照规则，跨分界持仓自然延续，不重置账户。全部历史已见，不能称未见验证。周期变化的配对包含实际观测行情差异，缺口明示。'
    rules+=' 所有组全仓复利、不加杠杆、不计手续费滑点。细行情仅在完整且聚合OHLC一致时使用，否则回退信号周期；5分钟内仍可能先后不明。最大回撤按各自信号周期收盘计算，不能精确当作相同采样频率的风险比较。保存参数、行情、策略及引擎快照、逐笔交易、订单、指标、权益和逐年结果。'
    save_text(out/'RULES.md',rules)
    plan=dict(title=kind.upper()+'盘中确认版本参数对照',family='ema_cloud',parent=parent,
        objective=questions[0]['text'],change_reason='用户指定ZEC单独改门槛，PAXG比较四个参数，其余退出规则不变。',
        decision_rule='按已冻结范围比较总收益；同时报告配对因素及前后分段，不从事后冠军推断长期最优。',
        stop_rule=f'只新增{count}次，已完成结果复用，不扩大范围。',max_new_runs=count,cases=cases,questions=questions)
    keep(out/'plan.json',plan)
    db=build_database_runtime(settings)
    try:keep(out/'study.json',setup(db,kind).create(plan))
    finally:db.dispose()
    snapshot('103_'+kind+'_entry_parameters_frozen',[SOURCE,ENGINE,ROOT/'scripts/zec_paxg_entry_parameters_study.py',
        ROOT/'scripts/paxg_intrabar_combined_study.py',out/'plan.json',out/'study.json',out/'RULES.md']+
        ([out/'data-check.json'] if kind=='paxg' else []))
    print(kind,'已冻结',count,'次新运行',flush=True)


def audit_case(kind,case,rid,task,service):
    out=OUT/kind;folder=service.directory(rid);r=read_json(folder/'result.json');rows=read_json(folder/'data.json')
    idx={b[0]:i for i,b in enumerate(rows)};step=STEPS[case['config']['timeframe']]
    observations={o['timestamp']:o for o in r['indicators']};used=Counter();lineage=[]
    for t in r['trades']:
        posted=t['entry_order_signal_time'];v=observations[posted]['values'];origin=int(v['确认起点时间'])
        bar_time=t['entry_time']//step*step
        assert idx[bar_time]==idx[posted]+1 and idx[bar_time]-idx[origin] in (1,2)
        assert t['entry_trigger']==v['下根突破入场价'] and not v['重进委托']
        sig=rows[idx[origin]];assert v['信号原始价位']==(max(sig[1],sig[4]) if t['side']=='long' else min(sig[1],sig[4]))
        used[origin,t['side']]+=1;assert used[origin,t['side']]==1
        lineage.append(dict(trade=t['trade_id'],origin=origin,posted=posted,entry=t['entry_time'],side=t['side'],trigger=t['entry_trigger']))
    risk=[s['stop_loss_pct'] for s in r['signals'] if s.get('order_type')=='stop_entry' and s['status']=='executed']
    assert len(risk)==len(r['trades']) and all(x==case['config']['parameters']['initial_stop_pct'] for x in risk)
    keep(out/'lineage'/f'{case["id"]}.json',lineage)
    eq=r['equity'];split=stamp(SPLIT)
    periods=calendar_returns(eq,rows,[('early',eq[0]['timestamp'],split),('later',split,eq[-1]['timestamp'])])
    value=dict(id=case['id'],name=case['name'],run_id=rid,config=case['config'],**summarize(r,rows),
        segments={p['label']:p for p in periods},entries_checked=len(lineage),execution_detail=r['execution_detail'],
        entry_bar_ambiguous=sum(t['entry_bar_ambiguous'] for t in r['trades']),
        result_hash=file_hash(folder/'result.json'),data_hash=task['metadata']['data_hash'],execution_data_hash=task['metadata']['execution_data_hash'],
        chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart&theme=light&tz=8')
    keep(out/'cases'/f'{case["id"]}.json',value)
    return {k:value[k] for k in ('id','run_id','report')}


def worker(kind,case,rid):
    db=build_database_runtime(settings);studies=setup(db,kind)
    try:
        folder=studies.backtests.directory(rid)
        with (folder/'run.log').open('a',encoding='utf8') as log,redirect_stdout(log),redirect_stderr(log):
            execute(studies.backtests,rid)
        task=studies.backtests.repository.get(rid);studies.verify_run(task)
        return audit_case(kind,case,rid,task,studies.backtests)
    except Exception as e:
        studies.backtests.repository.patch(rid,allowed={'preparing','running'},status='failed',error=str(e));raise
    finally:db.dispose()


def run(kind,workers):
    db=build_database_runtime(settings);studies=setup(db,kind);sid=read_json(OUT/kind/'study.json')['id']
    try:
        response=studies.submit(sid)
        if response['errors']:raise ValueError(response['errors'])
        pending=[]
        for case,rid,task in studies.case_runs(sid):
            if task['status']=='completed':
                if not (OUT/kind/'cases'/f'{case["id"]}.json').exists():
                    studies.verify_run(task);audit_case(kind,case,rid,task,studies.backtests)
                continue
            assert studies.backtests.repository.patch(rid,allowed={'queued'},status='preparing'),rid
            pending.append((case,rid))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            jobs=[pool.submit(worker,kind,case,rid) for case,rid in pending]
            for n,job in enumerate(as_completed(jobs),1):
                v=job.result();print(kind,n,'/',len(jobs),v['id'],f'{v["report"]["return_pct"]:+.2f}%',v['report']['total_trades'],'笔',flush=True)
    finally:db.dispose()


def finish(kind):
    out=OUT/kind;db=build_database_runtime(settings);studies=setup(db,kind);sid=read_json(out/'study.json')['id']
    try:
        if studies.state(sid)[4]=='completed':return
        records={}
        for c,rid,t in studies.case_runs(sid):
            studies.verify_run(t);v=read_json(out/'cases'/f'{c["id"]}.json')
            assert v['run_id']==rid and v['result_hash']==t['metadata']['result_hash'];records[c['id']]=v
        ret=lambda v:v['report']['return_pct']
        if kind=='zec':
            a,b=records['baseline'],records['trigger04'];assert a['data_hash']==b['data_hash'] and a['execution_data_hash']==b['execution_data_hash']
            assert b['config']=={**a['config'],'parameters':{**a['config']['parameters'],'trigger_mult':.4}}
            text=f'1.2倍门槛{ret(a):+,.2f}%，只改0.4倍{ret(b):+,.2f}%；'+('改善。' if ret(b)>ret(a) else '没有改善。')
            conclusions=[('trigger',text,'keep' if ret(b)>ret(a) else 'reject')];shown=[a,b];extra=[]
        else:
            base=records['1h_c89_w31_t0p8'];ranked=sorted(records.values(),key=ret,reverse=True);best=ranked[0]
            early=sorted(records.values(),key=lambda v:(-v['segments']['early']['return_pct'],v['id']))[0]
            factors={}
            for field,values in {'timeframe':list(STEPS),**AXES}.items():
                data=[]
                for i,first in enumerate(values):
                    for second in values[i+1:]:
                        pairs=[]
                        for v in records.values():
                            p=v['config'];value=p[field] if field=='timeframe' else p['parameters'][field]
                            if value!=first:continue
                            target={**p,field:second} if field=='timeframe' else {**p,'parameters':{**p['parameters'],field:second}}
                            other=next(w for w in records.values() if w['config']==target)
                            pairs.append(dict(first=v['id'],second=other['id'],first_return=ret(v),second_return=ret(other),delta_pp=ret(other)-ret(v)))
                        data.append(dict(first=first,second=second,pairs=len(pairs),improved=sum(p['delta_pp']>0 for p in pairs),
                            median_delta_pp=median(p['delta_pp'] for p in pairs),comparisons=pairs))
                factors[field]=data
            keep(out/'factor-comparisons.json',factors)
            text=f'同区间原参数{ret(base):+,.2f}%；54组总收益最高{best["name"]}：{ret(best):+,.2f}%。'
            later=f'只按前段收益选出{early["name"]}，前段{early["segments"]["early"]["return_pct"]:+.2f}%，后两年{early["segments"]["later"]["return_pct"]:+.2f}%，全期{ret(early):+.2f}%。前后均为同一次连续回测，边界持仓未平仓重置；全部历史已见。'
            facts='；'.join(f'{field}：'+','.join(f'{x["first"]}→{x["second"]}在{x["improved"]}/{x["pairs"]}组改善' for x in values) for field,values in factors.items())
            conclusions=[('ranking',text,'keep' if ret(best)>ret(base) else 'reject'),('factors',facts,'inconclusive'),('later',later,'inconclusive')]
            shown=[base]+[v for v in ranked[:5] if v['id']!=base['id']];extra=[later,'',facts]
            keep(out/'ranking.json',dict(baseline=base['id'],highest_full=best['id'],early_selected=early['id'],ranked=[v['id'] for v in ranked]))
        keep(out/'results.json',dict(study_id=sid,results=records))
        lines=['# '+kind.upper()+'参数对照','',text,'',(out/'RULES.md').read_text(encoding='utf8'),'','| 参数组 | 全期收益 | 前段收益 | 后两年收益 | 交易 | 赚 | 亏 | 胜率 |','|---|---:|---:|---:|---:|---:|---:|---:|']
        for v in shown:
            p=v['report'];lines.append(f'| [{v["name"]}]({v["chart"]}) | {ret(v):+,.2f}% | {v["segments"]["early"]["return_pct"]:+.2f}% | {v["segments"]["later"]["return_pct"]:+.2f}% | {p["total_trades"]} | {p["wins"]} | {p["losses"]} | {p["win_rate"]:.2f}% |')
        lines+=['']+extra+['','## 全部组合','','| 配置 | 总收益 | 交易 | 胜率 | 最大回撤 |','|---|---:|---:|---:|---:|']
        for v in sorted(records.values(),key=ret,reverse=True):
            p=v['report'];lines.append(f'| {v["name"]} | {ret(v):+,.2f}% | {p["total_trades"]} | {p["win_rate"]:.2f}% | {p["max_drawdown_pct"]:.2f}% |')
        lines+=['','所有逐年收益与完整参数见results.json，各组逐笔信号来源见lineage目录；每个run_id在项目中保留行情、成交、指标、权益、策略和引擎副本。未修改策略或引擎源码，沿用先前97项检查通过的版本。','']
        save_text(out/'README.md','\n'.join(lines))
        keep(out/'verification.json',dict(checked_runs=len(records),entries_checked=sum(v['entries_checked'] for v in records.values()),
            source_hash=file_hash(SOURCE),engine_hash=file_hash(ENGINE),tests_reused='docs/verification/zec-intrabar-methods-20260913/test-results.json'))
        answers=[dict(question=q,conclusion=t,decision=d,evidence=['artifact:results','artifact:report'],scope=kind.upper()+'已冻结参数范围，时间见规则。',
            limitation='全仓复利无费用；历史已见，按总收益排名不是长期最优证明。5分钟仍不是逐笔行情。') for q,t,d in conclusions]
        keep(out/'answers.json',answers)
        for name,file in [('rules','RULES.md'),('results','results.json'),('report','README.md'),('verification','verification.json')]:
            if name not in studies.state(sid)[2]:studies.attach(sid,name,out/file,name)
        for a in answers:
            if a['question'] not in studies.state(sid)[1]:studies.answer(sid,a)
        keep(out/'completion.json',studies.complete(sid))
        snapshot('104_'+kind+'_entry_parameters_completed',[ROOT/'scripts/zec_paxg_entry_parameters_study.py']+[p for p in out.iterdir() if p.is_file()])
        print(text,flush=True)
    finally:db.dispose()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','finish']);p.add_argument('kind',choices=['zec','paxg']);p.add_argument('--workers',type=int,default=3);a=p.parse_args()
    if a.action=='run':run(a.kind,a.workers)
    else:globals()[a.action](a.kind)
