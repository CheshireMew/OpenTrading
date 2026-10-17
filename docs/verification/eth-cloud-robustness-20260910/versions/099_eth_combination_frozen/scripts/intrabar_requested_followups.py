"""Two user-requested additions, reusing project execution and entry audits."""
import argparse
import json

from app.domain.backtest_history import align_execution_bars
from app.domain.local_backtest import Bar
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_strategy_versions import ROOT, snapshot
from scripts.cloud_width_reentry_study import keep
from scripts import zec_intrabar_methods_study as shared

OUT=ROOT/'docs/verification/intrabar-requested-followups-20260913'
SOURCE=ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
ETH_ID='af38948806a3f2144ad51ef04ddc8a94'
ZEC_PRIOR=ROOT/'docs/verification/zec-intrabar-methods-20260913'
ZEC_DATA=ROOT/'.heimdall_runtime/alt-cloud-transfer-20260911/zec-data.json'
FINE=ZEC_PRIOR/'execution-data.json'


class Frozen(LocalBacktestService):
    def __init__(self,db,config,data,fine=None):
        super().__init__(db);self.base_config=config;self.data_path=data;self.fine_path=fine

    def prepare(self,command):
        config,source,metadata=super().prepare(command)
        for key in ('symbol','timeframe','start','end','initial_cash','position_pct','data_gap_policy'):
            assert config[key]==self.base_config[key],key
        assert metadata['strategy']['warmup_bars']==650
        metadata.update(data_hash=file_hash(self.data_path),input_data_path=str(self.data_path.relative_to(ROOT)))
        if config.get('execution_timeframe'):
            assert self.fine_path is not None
            metadata.update(execution_data_hash=file_hash(self.fine_path),execution_source=str(self.fine_path.relative_to(ROOT)))
        return config,source,metadata

    def _create(self,config,source,metadata,parent_id=None,data=None,identifier=None,*,execution_data=None):
        if data is None:data=self.data_path.read_bytes()
        if config.get('execution_timeframe') and execution_data is None:execution_data=self.fine_path.read_bytes()
        return super()._create(config,source,metadata,parent_id,data,identifier,execution_data=execution_data)


def setup(db,kind):
    if kind=='eth':
        base=ROOT/'.heimdall_runtime/local_backtests'/ETH_ID
        cfg=read_json(base/'config.json');data=base/'data.json';fine=None
    else:
        cfg={**read_json(ROOT/'.heimdall_runtime/local_backtests/2a0c67e629a77db26e664880bab12d44/config.json'),'timeframe':'15m'}
        data=ZEC_DATA;fine=FINE
    return ResearchStudyService(Frozen(db,cfg,data,fine))


def case(cid,name,cfg,reuse=None):
    result=dict(id=cid,name=name,variant=cid,period='ETH六年' if cfg['symbol']=='ETH/USDT' else 'ZEC七年',
        role='exploration',previously_seen=True,command=cfg)
    if reuse:result['reuse_run']=reuse
    return result


def prepare(studies,kind):
    out=OUT/kind;out.mkdir(parents=True,exist_ok=True)
    if (out/'study.json').exists():return
    cfg=studies.backtests.base_config
    _,spec=load_strategy(SOURCE);params=validate_parameters(spec,cfg['parameters'])
    cases=[]
    if kind=='eth':
        cases=[case('baseline','原版：回吐50%',cfg,ETH_ID),
               case('giveback35','仅回吐改为35%',{**cfg,'strategy':SOURCE.stem,'parameters':{**params,'giveback_pct':35}})]
        parent=read_json(ROOT/'docs/verification/eth-intrabar-methods-20260913/study.json')['id']
        questions=[dict(id='giveback35',text='仅把ETH原版最高浮盈回吐50%改为35%，是否提高收益？')]
        rules='ETH用户指定版本，15分钟，2020-09-10至2026-09-10。只把giveback_pct从50改为35，保留EMA55/振幅31/门槛0.4/不追2/固定1%止损/浮盈2%启动及原15分钟收盘更新保护。入场为仅第2或第3根盘中突破信号实体。与原版直接比较，不同时换波动止损或5分钟保护。新增1次运行。'
    else:
        prior=read_json(ZEC_PRIOR/'results.json')['results']
        expected=read_json(ROOT/'docs/verification/alt-cloud-transfer-20260911/data.json')['zec']['data_hash']
        assert file_hash(ZEC_DATA)==expected
        assert file_hash(FINE)==prior['fine_control']['execution_data_hash']
        rows=read_json(ZEC_DATA);fine=read_json(FINE)
        assert rows[650][0]==1568073600000 and rows[-1][0]+900000==1788998400000
        _,aligned=align_execution_bars([Bar(*b) for b in rows[650:]],[Bar(*b) for b in fine],900000,300000)
        keep(out/'fine-data-check.json',dict(**aligned,data_hash=expected,fine_hash=file_hash(FINE)))
        for cid in ('baseline','width_stop','atr_stop','fine_control','fine_protect'):
            old=prior[cid];folder=ROOT/'.heimdall_runtime/local_backtests'/old['run_id']
            cases.append(case('old_'+cid,'30分钟：'+old['name'],read_json(folder/'config.json'),old['run_id']))
        for cid,name,changes in [('baseline','原1%止损',{}),('width_stop','1.5倍平滑振幅止损',{'stop_method':1}),
                ('atr_stop','1.5倍ATR14止损',{'stop_method':2}),('fine_control','5分钟成交，15分钟更新保护',{}),
                ('fine_protect','5分钟成交，5分钟更新保护',{})]:
            command={**cfg,'strategy':SOURCE.stem,'parameters':{**params,**changes}}
            if cid.startswith('fine_'):command.update(execution_timeframe='5m',intrabar_profit_protection=cid=='fine_protect')
            cases.append(case(cid,'15分钟：'+name,command))
        parent=read_json(ZEC_PRIOR/'study.json')['id']
        questions=[dict(id=k,text=v) for k,v in [('timeframe','ZEC各候选从30分钟改15分钟，七年收益是否改善？'),
            ('methods','在15分钟内，各改法相对同周期原版是否仍有帮助？'),('execution','周期之外是否保持参数，入场和细周期数据是否可核对？')]]
        rules='ZEC/USDT，2019-09-10至2026-09-10，同一七年。把上一轮30分钟的原版、1.5W止损、1.5ATR14止损、更快保护移到15分钟。保留EMA144、W31、门槛1.2W、不追3W、1%固定止损（波动版替换为0.5%—2%）、浮盈1%启动、回吐35%、仅第2或第3根盘中突破实体。周期改变后均线/等待按15分钟根数计算，不另调参数。增加同为5分钟成交、每15分钟更新保护的必要对照，分别区分周期与保护频率。复用5个30分钟版本、新增5个15分钟版本，不组合或调参。'
        print(json.dumps(dict(kind=kind,matched=aligned['matched'],fallback=aligned['fallback'])),flush=True)
    rules+=' 所有组全仓复利、不加杠杆、不计手续费滑点；所有历史已见。沿用项目已验证的策略和引擎，5分钟数据须完整且OHLC聚合一致，否则共同回退信号周期；最大回撤按各自信号周期收盘权益计算。规则先冻结，结果出来后不再改规则。'
    path=out/'RULES.md'
    if path.exists():assert path.read_text(encoding='utf8')==rules
    else:path.write_text(rules,encoding='utf8')
    plan=dict(title='ETH仅回吐35%对照' if kind=='eth' else 'ZEC候选迁移到15分钟',family='ema_cloud',parent=parent,
        objective=questions[0]['text'],change_reason='用户在ETH迁移测试运行时追加要求，旧计划保留，独立追加研究。',
        decision_rule='与明确对应的原版/30分钟版本比较总收益，同时列胜负、回撤和年度收益。',
        stop_rule='ETH只新增1次；ZEC只新增5次；不继续挑参数或组合。',max_new_runs=1 if kind=='eth' else 5,cases=cases,questions=questions)
    keep(out/'plan.json',plan);state=studies.create(plan);keep(out/'study.json',state)
    print(json.dumps(dict(kind=kind,study_id=state['id'],cases=len(cases))),flush=True)


class NewPeriodAudit:
    def __init__(self,studies):self.studies=studies;self.backtests=studies.backtests
    def verify_run(self,task):return self.studies.verify_run(task)
    def case_runs(self,identifier):return [x for x in self.studies.case_runs(identifier) if not x[0]['id'].startswith('old_')]


def analyze(studies,kind,identifier):
    baseline=next(x for x in studies.case_runs(identifier) if x[0]['id']=='baseline')
    shared.OUT=OUT/kind;shared.BASE=studies.backtests.directory(baseline[1]);shared.STEP=900000
    shared.analyze(NewPeriodAudit(studies),identifier)


def report(studies,kind,identifier):
    out=OUT/kind;r=read_json(out/'results.json')['results'];answers=[]
    def answer(key,content,evidence,decision='keep'):
        answers.append(dict(question=key,conclusion=content,evidence=['artifact:results']+['case:'+c for c in evidence],decision=decision,
            scope='ETH六年15分钟原版，仅回吐35%' if kind=='eth' else 'ZEC七年30分钟与15分钟候选配对比较',
            limitation='全仓复利，不计手续费滑点；全部历史已见，未调参或检验未来数据。5分钟不是逐笔行情，回撤按各自信号周期收盘计算。'))
    lines=['# '+('ETH：仅回吐35%' if kind=='eth' else 'ZEC：改成15分钟是否改善'),'',(out/'RULES.md').read_text(encoding='utf8'),'']
    if kind=='eth':
        b=r['baseline']['report'];n=r['giveback35']['report'];improved=n['return_pct']>b['return_pct']
        answer('giveback35',f'只把回吐50%改为35%，六年收益从{b["return_pct"]:+,.2f}%变为{n["return_pct"]:+,.2f}%；胜率从{b["win_rate"]:.2f}%变为{n["win_rate"]:.2f}%，最大回撤从{b["max_drawdown_pct"]:.2f}%变为{n["max_drawdown_pct"]:.2f}%。'+('累计收益有改善。' if improved else '累计收益没有改善。'),['baseline','giveback35'],'keep' if improved else 'reject')
    else:
        old=read_json(ZEC_PRIOR/'results.json')['results']
        pairs=[]
        lines+=['| 同一组参数与方法 | 30分钟收益 | 15分钟收益 | 周期变化 |','|---|---:|---:|---|']
        for cid in r:
            a=old[cid]['report']['return_pct'];b=r[cid]['report']['return_pct'];improved=b>a
            pairs.append(dict(case=cid,old_run=old[cid]['run_id'],new_run=r[cid]['run_id'],old_return_pct=a,new_return_pct=b,improved=improved))
            lines.append(f'| {r[cid]["name"].replace("15分钟：","")} | {a:+,.2f}% | {b:+,.2f}% | '+('提高' if improved else '降低')+' |')
        keep(out/'timeframe-comparison.json',pairs)
        answer('timeframe','；'.join(f'{r[p["case"]]["name"]}：{p["old_return_pct"]:+,.2f}%→{p["new_return_pct"]:+,.2f}%' for p in pairs),[x for p in pairs for x in ('old_'+p['case'],p['case'])], 'keep' if all(p['improved'] for p in pairs) else 'inconclusive' if any(p['improved'] for p in pairs) else 'reject')
        comparisons=[]
        for cid,ref in [('width_stop','baseline'),('atr_stop','baseline'),('fine_protect','fine_control')]:
            comparisons.append(f'{r[cid]["name"]}对比{r[ref]["name"]}：{r[ref]["report"]["return_pct"]:+,.2f}%→{r[cid]["report"]["return_pct"]:+,.2f}%')
        answer('methods','；'.join(comparisons),list(r))
        data=read_json(out/'fine-data-check.json')
        answer('execution',f'全部新15分钟组原始信号一致，各笔只在信号后的第1或第2根成交且同一信号不重复成交。细数据匹配{data["matched"]}根，回退{data["fallback"]}根。除timeframe和原周期保护频率随之变化外，对应30分钟版本的交易参数完全相同。',list(r))
        for case_,_,task in studies.case_runs(identifier):
            if case_['id'].startswith('old_'):studies.verify_run(task)
    lines+=['','| 方法 | 收益 | 笔数 | 赚 | 亏 | 平 | 胜率 | 最大回撤 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for cid,v in r.items():
        p=v['report'];lines.append(f'| [{v["name"]}]({v["chart"]}) | {p["return_pct"]:+,.2f}% | {p["total_trades"]} | {p["wins"]} | {p["losses"]} | {p["breakeven"]} | {p["win_rate"]:.2f}% | {p["max_drawdown_pct"]:.2f}% |')
    lines+=['']+[a['conclusion']+'\n' for a in answers]
    lines+=['## 年度收益','','首尾为不完整年度，连续权益计算。','','| 年份 | '+' | '.join(r[c]['name'] for c in r)+' |','|---|'+'---:|'*len(r)]
    for i,y in enumerate(r['baseline']['annual']):lines.append('| '+y['label']+' | '+' | '.join(f'{v["annual"][i]["return_pct"]:+.2f}%' for v in r.values())+' |')
    lines+=['','规则和全部参数在RULES.md、plan.json；结果、逐笔来源在results.json与各*-lineage.json；旧30分钟数据及逐年结果见上一轮ZEC记录。原始数据/策略/订单/交易/资金曲线均在项目各run_id目录留存。研究ID：'+identifier+'。','']
    content='\n'.join(lines);path=out/'README.md'
    if path.exists():assert path.read_text(encoding='utf8')==content
    else:path.write_text(content,encoding='utf8')
    keep(out/'answers.json',answers)
    verified=read_json(ZEC_PRIOR/'baseline-parity.json')
    assert file_hash(SOURCE)==verified['source_hash'] and file_hash(ROOT/'app/domain/local_backtest.py')==verified['engine_hash']
    keep(out/'verification.json',dict(source_hash=verified['source_hash'],engine_hash=verified['engine_hash'],
        tests_reused=str((ZEC_PRIOR/'test-results.json').relative_to(ROOT)),tests_hash=file_hash(ZEC_PRIOR/'test-results.json'),
        entries_audited={k:v['checked_entries'] for k,v in r.items()}))
    print(json.dumps(answers,ensure_ascii=False),flush=True)


def finalize(studies,kind,identifier):
    out=OUT/kind
    if studies.state(identifier)[4]=='completed':return
    artifacts=[('rules','RULES.md'),('results','results.json'),('report','README.md'),('verification','verification.json')]
    if kind=='zec':artifacts += [('data','fine-data-check.json'),('timeframe','timeframe-comparison.json')]
    for name,file in artifacts:
        if name not in studies.state(identifier)[2]:studies.attach(identifier,name,out/file,name)
    for a in read_json(out/'answers.json'):
        if a['question'] not in studies.state(identifier)[1]:studies.answer(identifier,a)
    state=studies.complete(identifier);keep(out/'completion.json',state);print(kind,state['status'],state['cases'])


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','analyze','report','finalize']);p.add_argument('kind',choices=['eth','zec']);args=p.parse_args()
    db=build_database_runtime(settings);studies=setup(db,args.kind)
    try:
        if args.action=='prepare':prepare(studies,args.kind)
        else:
            identifier=read_json(OUT/args.kind/'study.json')['id']
            if args.action=='run':shared.run(studies,identifier)
            else:globals()[args.action](studies,args.kind,identifier)
    finally:db.dispose()


if __name__=='__main__':main()
