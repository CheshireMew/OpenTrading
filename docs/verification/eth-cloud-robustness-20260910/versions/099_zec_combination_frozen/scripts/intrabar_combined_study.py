"""User-requested two-factor comparison with identical fine execution data."""
import argparse
import json

from app.infra.db import build_database_runtime
from app.infra.research_files import read_json,file_hash
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_strategy_versions import ROOT,snapshot
from scripts.cloud_width_reentry_study import keep
from scripts.intrabar_requested_followups import Frozen,case,NewPeriodAudit
from scripts import zec_intrabar_methods_study as shared

OUT=ROOT/'docs/verification/intrabar-combined-20260913'
SOURCE=ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
PARENTS={'eth':ROOT/'docs/verification/eth-intrabar-methods-20260913',
         'zec':ROOT/'docs/verification/intrabar-requested-followups-20260913/zec'}


def setup(db,kind):
    from app.services.local_backtest_service import LocalBacktestService
    previous=ResearchStudyService(LocalBacktestService(db))
    parent=read_json(PARENTS[kind]/'study.json')['id']
    chosen={c['id']:(c,rid,task) for c,rid,task in previous.case_runs(parent) if c['id'] in ('fine_control','fine_protect')}
    if len(chosen)!=2 or any(not t or t['status']!='completed' for _,_,t in chosen.values()):
        raise ValueError('前一轮两组细周期对照尚未完成，保留本次既定组合规则，完成后再创建。')
    base=previous.backtests.directory(chosen['fine_control'][1]);cfg=read_json(base/'config.json')
    fast=previous.backtests.directory(chosen['fine_protect'][1])
    assert file_hash(base/'data.json')==file_hash(fast/'data.json')
    assert file_hash(base/'execution_data.json')==file_hash(fast/'execution_data.json')
    studies=ResearchStudyService(Frozen(db,cfg,base/'data.json',base/'execution_data.json'))
    return studies,parent,chosen


def prepare(studies,kind,parent,chosen):
    out=OUT/kind;out.mkdir(parents=True,exist_ok=True)
    if (out/'study.json').exists():return
    cfg=studies.backtests.base_config
    cases=[case(cid,name,read_json(studies.backtests.directory(chosen[cid][1])/'config.json'),chosen[cid][1])
        for cid,name in [('fine_control','固定1%止损＋15分钟更新保护'),('fine_protect','固定1%止损＋5分钟更新保护')]]
    for cid,name,fast in [('fine_width_stop','振幅止损＋15分钟更新保护',False),('fine_combined','振幅止损＋5分钟更新保护',True)]:
        command={**cfg,'strategy':SOURCE.stem,'parameters':{**cfg['parameters'],'stop_method':1},'intrabar_profit_protection':fast}
        cases.append(case(cid,name,command))
    plan=dict(title=kind.upper()+'15分钟：振幅止损与更快利润保护组合',family='ema_cloud',parent=parent,
        objective='在相同5分钟成交数据下，检查振幅止损与更快利润保护叠加是否超过原版及单独改法。',
        change_reason='用户追加要求测试两个因素放在一起；原有单因素研究和参数保留。',
        decision_rule='固定1%/振幅止损与15分钟/5分钟保护形成四组；全部使用相同细行情，比较同一标的总收益。',
        stop_rule='每个标的只新增2次，复用前一轮2次；不改倍数、期限或其他参数。',max_new_runs=2,cases=cases,
        questions=[dict(id='combined',text='组合是否超过原版及两种单独改法？'),dict(id='factors',text='两个因素在保持另一个不变时分别有什么作用？')])
    rules=f'''# {kind.upper()} 15分钟组合固定规则

四组全用同一份15分钟信号数据、5分钟成交数据。固定1%止损/1.5倍平滑振幅止损（限制0.5%—2%），分别配15分钟收盘/5分钟收盘更新保护，下一根生效。复用前一轮固定止损的两组，只新增振幅止损的两组。

参数完全继承指定版本：{json.dumps(cfg['parameters'],ensure_ascii=False)}。仅stop_method在0/1切换、intrabar_profit_protection在false/true切换。ETH继续六年EMA55、2%启动/回吐50%；ZEC继续七年EMA144、1%启动/回吐35%。此次不是取消利润保护，不使用ETH另测的35%版本，不将ZEC改回30分钟。

无参数搜索，全部已见历史；全仓复利、不加杠杆、不计手续费和滑点。聚合细行情不匹配时四组均回退15分钟；5分钟内仍可能先后不明，最大回撤按15分钟收盘权益计算。按用户追加要求独立留档，原单因素结果不覆盖。
'''
    (out/'RULES.md').write_text(rules,encoding='utf8')
    keep(out/'plan.json',plan);state=studies.create(plan);keep(out/'study.json',state)
    snap=snapshot('099_'+kind+'_combination_frozen',[SOURCE,ROOT/'app/domain/local_backtest.py',ROOT/'scripts/intrabar_combined_study.py',
        ROOT/'scripts/intrabar_requested_followups.py',ROOT/'scripts/zec_intrabar_methods_study.py']+[p for p in out.iterdir() if p.is_file()])
    print(json.dumps(dict(kind=kind,study=state['id'],snapshot=snap['label'])),flush=True)


def analyze(studies,kind,identifier):
    base=next(x for x in studies.case_runs(identifier) if x[0]['id']=='fine_control')
    shared.OUT=OUT/kind;shared.BASE=studies.backtests.directory(base[1]);shared.STEP=900000
    shared.analyze(NewPeriodAudit(studies),identifier)


def report(studies,kind,identifier):
    out=OUT/kind;r=read_json(out/'results.json')['results'];ret={k:v['report']['return_pct'] for k,v in r.items()}
    hashes={(v['data_hash'],v['execution_data_hash']) for v in r.values()};assert len(hashes)==1
    configs={c['id']:c['config'] for c,_,_ in studies.case_runs(identifier)}
    base_cfg=configs['fine_control']
    for cid,cfg in configs.items():
        expected={**base_cfg['parameters'],'stop_method':1 if cid in ('fine_width_stop','fine_combined') else 0}
        assert cfg['parameters']==expected
        assert cfg['intrabar_profit_protection']==(cid in ('fine_protect','fine_combined'))
        for key in ('symbol','timeframe','start','end','initial_cash','position_pct','data_gap_policy','execution_timeframe'):
            assert cfg[key]==base_cfg[key]
    combined=ret['fine_combined'];best=max(ret,key=ret.get)
    text='；'.join(f'{v["name"]}：{ret[k]:+,.2f}%' for k,v in r.items())+'。本次最高为'+r[best]['name']+'。'
    effects=[]
    for a,b,label in [('fine_control','fine_width_stop','保持原保护速度，只换振幅止损'),
        ('fine_protect','fine_combined','保持更快保护，只换振幅止损'),
        ('fine_control','fine_protect','保持固定止损，只加快保护'),
        ('fine_width_stop','fine_combined','保持振幅止损，只加快保护')]:
        effects.append(f'{label}：{ret[a]:+,.2f}%→{ret[b]:+,.2f}%')
    answers=[dict(question=k,conclusion=t,decision=d,evidence=['artifact:results']+['case:'+c for c in r],
        scope=kind.upper()+'15分钟，沿用指定原版时间范围、参数和同一份5分钟数据。',limitation='全仓复利，不计费用；历史已见，没有继续调参。5分钟成交并非逐笔还原，收益不能保证未来表现。')
        for k,t,d in [('combined',text,'keep' if best=='fine_combined' else 'reject'),('factors','；'.join(effects),'keep')]]
    keep(out/'answers.json',answers)
    lines=['# '+kind.upper()+'：振幅止损＋更快利润保护','',text,'',
        '| 组合 | 总收益 | 交易 | 赚 | 亏 | 平 | 胜率 | 最大回撤 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for k,v in r.items():
        p=v['report'];lines.append(f'| [{v["name"]}]({v["chart"]}) | {p["return_pct"]:+,.2f}% | {p["total_trades"]} | {p["wins"]} | {p["losses"]} | {p["breakeven"]} | {p["win_rate"]:.2f}% | {p["max_drawdown_pct"]:.2f}% |')
    lines+=['','全部是相同5分钟成交数据，原买卖信号仍是15分钟；这里的原版收益与旧粗周期成交数字可能不同，不能把数据细化的变化算作策略改善。','']+[t+'\n' for t in effects]
    lines+=['## 年度收益','','首尾不完整年度，连续权益计算。','','| 年份 | '+' | '.join(v['name'] for v in r.values())+' |','|---|'+'---:|'*len(r)]
    for i,y in enumerate(r['fine_control']['annual']):lines.append('| '+y['label']+' | '+' | '.join(f'{v["annual"][i]["return_pct"]:+.2f}%' for v in r.values())+' |')
    lines+=['','已核对四组行情哈希和原始信号一致，逐笔确认时序正确，每个原信号最多成交一次；策略和引擎代码复用此前97项检查通过版本。完整参数见plan.json，逐笔来源见各*-lineage.json，原始行情、策略副本及全部订单/交易/权益在项目run_id目录保留。所有历史已见，不代表未见验证。','']
    path=out/'README.md';content='\n'.join(lines)
    if path.exists():assert path.read_text(encoding='utf8')==content
    else:path.write_text(content,encoding='utf8')
    keep(out/'verification.json',dict(same_signal_and_fine_hashes=[list(x) for x in sorted(hashes)],entries_audited={k:v['checked_entries'] for k,v in r.items()},
        source_hash=file_hash(SOURCE),engine_hash=file_hash(ROOT/'app/domain/local_backtest.py')))
    print(text,flush=True)


def finalize(studies,kind,identifier):
    out=OUT/kind
    if studies.state(identifier)[4]=='completed':return
    for name,file in [('rules','RULES.md'),('results','results.json'),('report','README.md'),('verification','verification.json')]:
        if name not in studies.state(identifier)[2]:studies.attach(identifier,name,out/file,name)
    for a in read_json(out/'answers.json'):
        if a['question'] not in studies.state(identifier)[1]:studies.answer(identifier,a)
    state=studies.complete(identifier);keep(out/'completion.json',state);print(kind,state['status'],state['cases'])


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','analyze','report','finalize']);p.add_argument('kind',choices=['eth','zec']);args=p.parse_args()
    db=build_database_runtime(settings)
    try:
        studies,parent,chosen=setup(db,args.kind)
        if args.action=='prepare':prepare(studies,args.kind,parent,chosen)
        else:
            identifier=read_json(OUT/args.kind/'study.json')['id']
            if args.action=='run':shared.run(studies,identifier)
            else:globals()[args.action](studies,args.kind,identifier)
    finally:db.dispose()


if __name__=='__main__':main()
