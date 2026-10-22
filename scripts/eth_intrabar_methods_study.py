"""Apply the already frozen ZEC methods to the user's exact ETH candidate.

Reuse the project strategy, engine, service and prior study's execution/audit
functions. No new trading logic or parameter search.
"""
import argparse
from datetime import datetime, timezone
import json

from app.domain.backtest_history import align_execution_bars, validate_observed_bars
from app.domain.local_backtest import Bar, simulate
from app.infra.db import build_database_runtime
from app.infra.persistence.market.kline_store import KlineStore
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from app.services.market.exchange_gateway import ExchangeGateway
from app.services.market.market_data_service import MarketDataService
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_strategy_versions import ROOT, snapshot
from scripts.cloud_width_reentry_study import keep
from scripts import zec_intrabar_methods_study as shared

OUT=ROOT/'docs/verification/eth-intrabar-methods-20260913'
BASE_ID='af38948806a3f2144ad51ef04ddc8a94'
BASE=ROOT/'.opentrading_runtime/local_backtests'/BASE_ID
SOURCE=ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
FINE=ROOT/'.opentrading_runtime/cloud-walkforward-20260911/data/eth-5m.json'
STEP=900000
VARIANTS=[('width_stop','1.5倍平滑振幅止损，限制0.5%至2%',{'stop_method':1}),
          ('atr_stop','1.5倍ATR14止损，限制0.5%至2%',{'stop_method':2}),
          ('fine_control','5分钟成交核对，仍15分钟更新保护',{}),
          ('fine_protect','5分钟成交核对，每5分钟更新保护',{})]


def configure():
    # Separate CLI process; explicit context for the reused execution and audit.
    shared.OUT=OUT; shared.BASE_ID=BASE_ID; shared.BASE=BASE
    shared.SOURCE=SOURCE; shared.STEP=STEP; shared.FROZEN_FINE=OUT/'execution-data.json'


def prepare(studies):
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'study.json').exists(): return
    config=read_json(BASE/'config.json');rows=read_json(BASE/'data.json')
    old=read_json(BASE/'result.json')
    expected=read_json(ROOT/'docs/verification/eth-intrabar-confirmation-20260913/results.json')['results']['body_touch_0']
    assert expected['run_id']==BASE_ID and old['report']['total_trades']==9288
    assert file_hash(BASE/'result.json')==expected['result_hash'] and file_hash(BASE/'data.json')==expected['data_hash']
    m,s=load_strategy(SOURCE);params=validate_parameters(s,config['parameters'])
    print('核对原版9288笔与现有引擎完全一致',flush=True)
    replay=simulate([Bar(*b) for b in rows],m,params,warmup=650,step_ms=STEP,
                    initial_cash=config['initial_cash'],position_pct=config['position_pct'])
    parity={k:replay[k]==old[k] for k in ('report','trades','signals','fills','equity','levels')}
    keep(OUT/'baseline-parity.json',dict(checks=parity,baseline=BASE_ID,data_hash=file_hash(BASE/'data.json'),
        result_hash=file_hash(BASE/'result.json'),source_hash=file_hash(SOURCE),engine_hash=file_hash(ROOT/'app/domain/local_backtest.py')))
    if not all(parity.values()):raise ValueError(parity)
    del replay,old
    fine_meta=read_json(ROOT/'docs/verification/cloud-walkforward-20260911/data.json')['eth']['5m']
    assert file_hash(FINE)==fine_meta['data_hash']
    fine=read_json(FINE);start=rows[650][0];end=rows[-1][0]+STEP
    if fine[0][0]>start:
        prefix_path=OUT/'execution-prefix.json'
        if prefix_path.exists():prefix=read_json(prefix_path)
        else:
            print('通过项目行情服务补齐已有5分钟快照之前的短段',flush=True)
            exchange=read_json(BASE/'metadata.json')['source']['exchange']
            market=MarketDataService(ExchangeGateway(exchange),KlineStore(database_runtime=studies.backtests.repository.database))
            result=market.load_ohlcv_range(config['symbol'],'5m',datetime.fromtimestamp(start/1000,timezone.utc),
                datetime.fromtimestamp((fine[0][0]-1)/1000,timezone.utc))
            prefix=result.require_complete(symbol=config['symbol'],timeframe='5m')
            keep(prefix_path,prefix)
        assert prefix and prefix[0][0]==start and prefix[-1][0]+300000==fine[0][0]
        fine=prefix+fine
    fine=[b for b in fine if start<=b[0]<end]
    fine_bars,gaps=validate_observed_bars(fine,start,end,300000,0,int(datetime.now(timezone.utc).timestamp()*1000))
    keep(OUT/'execution-data.json',fine)
    _,alignment=align_execution_bars([Bar(*b) for b in rows[650:]],fine_bars,STEP,300000)
    keep(OUT/'fine-data-check.json',dict(**alignment,fine_hash=file_hash(OUT/'execution-data.json'),
        original_fine_hash=file_hash(FINE),prefix_hash=file_hash(OUT/'execution-prefix.json') if (OUT/'execution-prefix.json').exists() else None,
        original_fine_path=str(FINE.relative_to(ROOT)),gaps=gaps))
    cases=[dict(id='baseline',name='原版：第2或第3根盘中突破实体＋1%止损',variant='baseline',
        period='ETH六年已见历史',role='exploration',previously_seen=True,command=config,reuse_run=BASE_ID)]
    for cid,name,changes in VARIANTS:
        command={**config,'strategy':SOURCE.stem,'parameters':validate_parameters(s,{**params,**changes})}
        if cid.startswith('fine_'):command.update(execution_timeframe='5m',intrabar_profit_protection=cid=='fine_protect')
        cases.append(dict(id=cid,name=name,variant=cid,period='ETH六年已见历史',role='exploration',previously_seen=True,command=command))
    plan=dict(title='ETH六年：将ZEC的波动止损和更快利润保护迁移到指定策略',family='ema_cloud',
        parent='4b4ea0969ed64bdb8a4e2d8c4257ac16',objective='检验ZEC有改善的两类规则在用户标注的ETH策略是否也有改善。',
        change_reason='用户指定六年54455.55%、9288笔的两根内实体盘中确认版本。',
        decision_rule='振幅和ATR止损分别对比原版；保护频率只比较两组使用相同5分钟行情的版本，按六年总收益判定并报告胜负和逐年结果。',
        stop_rule='只新增4次运行，不改EMA55或利润保护启动/回吐参数，不搜索倍数、不组合获胜方法。',max_new_runs=4,cases=cases,
        questions=[dict(id=k,text=v) for k,v in [('width_stop','平滑振幅止损能否提高ETH原版收益？'),
            ('atr_stop','ATR止损能否提高ETH原版收益？'),('protection','每5分钟更新利润保护能否改善ETH？'),
            ('execution','原版是否一致，细周期成交本身影响多少，是否遵守信号时序？')]])
    keep(OUT/'plan.json',plan);keep(OUT/'preview.json',studies.preview_summary(plan))
    rules='''# ETH固定比较规则

用户指定版本：af38948806a3f2144ad51ef04ddc8a94；六年累计+54455.55%、9288笔。ETH/USDT，Binance现货行情用于多空模拟，15分钟，2020-09-10至2026-09-10 UTC，650根预热。原始行情、时间范围和原信号完全不变。

中心EMA(hl2,55)，平滑振幅W=EMA(high-low,31)，原突破门槛0.4W、不追2W；原信号算第1根，仅第2/第3根盘中突破信号实体才入场，反向信号取消旧等待，每个信号最多成交一次。1%初始止损，浮盈2%启动保护，允许回吐最高浮盈50%，反向信号仍收盘确认后下一开盘平仓。

本次两类改善分别检验，不组合。止损的两个版本：1.5倍W或1.5倍ATR14，除以挂单时收盘价，百分比限制0.5%—2%，锚定实际入场价；开仓后不扩大。ATR首14根平均种子后Wilder平滑。这些倍数及上下限完全沿用ZEC研究，未在ETH重新挑参数。

利润保护：两组均使用同一份5分钟快照核对成交，仅更新频率不同：15分钟收盘或5分钟收盘，均下一根开始生效。保留ETH原2%启动和50%回吐，不借用ZEC的1%/35%。5分钟不是逐笔即时保护，仍有5分钟内先后不明。只有完整3根且OHLC聚合与15分钟一致时才使用细数据；否则两组都回退原15分钟，不改价格。

已有5分钟快照起点不足的短段通过项目MarketDataService补齐并冻结，完整快照及所有不匹配记录保存本地。未使用未来收盘值设置当前委托。所有版本全仓复利、不加杠杆、不计手续费或滑点，最大回撤按15分钟收盘权益计算。

本轮只复用原版、新增4次回测后停止。全部历史已看过，结论是规则迁移对照，不是未见样本证明。当前项目策略和引擎已经过上一轮97项检查；本轮不改交易代码，另核对原版逐笔一致及全部实际新入场的时序。旧版本与数据不覆盖。
'''
    rule_path=OUT/'RULES.md'
    if rule_path.exists():assert rule_path.read_text(encoding='utf8')==rules
    else:rule_path.write_text(rules,encoding='utf8')
    state=studies.create(plan);keep(OUT/'study.json',state)
    record=snapshot('097_eth_methods_frozen',[SOURCE,ROOT/'app/domain/local_backtest.py',ROOT/'scripts/zec_intrabar_methods_study.py',
        ROOT/'scripts/eth_intrabar_methods_study.py']+[p for p in OUT.iterdir() if p.is_file()])
    print(json.dumps(dict(study_id=state['id'],parity=parity,matched=alignment['matched'],fallback=alignment['fallback'],snapshot=record['label']),ensure_ascii=False),flush=True)


def report(studies,identifier):
    r=read_json(OUT/'results.json')['results'];b=r['baseline'];s=r['fine_control'];f=r['fine_protect']
    conclusions={}
    for cid in ('width_stop','atr_stop'):
        v=r[cid];p=v['report'];base=b['report'];improved=p['return_pct']>base['return_pct']
        conclusions[cid]=('keep' if improved else 'reject',
            f'{v["name"]}：六年收益{p["return_pct"]:+,.2f}%，原版{base["return_pct"]:+,.2f}%，'+('有改善。' if improved else '没有提高收益。')+
            f'胜率{p["win_rate"]:.2f}%，最大回撤{p["max_drawdown_pct"]:.2f}%；平均初始止损{v["initial_stop_pct"]["mean"]:.2f}%，平均亏损单{v["mean_loss_pct"]:+.2f}%。', ['baseline',cid])
    improved=f['report']['return_pct']>s['report']['return_pct']
    conclusions['protection']=('keep' if improved else 'reject',
        f'相同5分钟成交行情，保护从15分钟改为每5分钟更新，收益从{s["report"]["return_pct"]:+,.2f}%变为{f["report"]["return_pct"]:+,.2f}%，'+('有改善。' if improved else '没有改善。')+
        f'胜率{s["report"]["win_rate"]:.2f}%→{f["report"]["win_rate"]:.2f}%，最大回撤{s["report"]["max_drawdown_pct"]:.2f}%→{f["report"]["max_drawdown_pct"]:.2f}%，利润保护退出却亏损{s["protection_loss_count"]}→{f["protection_loss_count"]}笔。', ['fine_control','fine_protect'])
    data=read_json(OUT/'fine-data-check.json')
    conclusions['execution']=('keep',f'原版9288笔及全部成交/信号/权益与旧记录完全一致。只细化成交数据，收益从{b["report"]["return_pct"]:+,.2f}%变为{s["report"]["return_pct"]:+,.2f}%；这部分不算策略改进。同根先后不明从{b["entry_bar_ambiguous"]}变为{s["entry_bar_ambiguous"]}笔。{data["matched"]}根匹配、{data["fallback"]}根回退。全部5组原始信号一致，每笔确认根数和一次消费检查通过。',['baseline','fine_control'])
    answers=[dict(question=k,decision=v[0],conclusion=v[1],evidence=['artifact:results']+['case:'+c for c in v[2]],
        scope='ETH/USDT 15分钟，2020-09-10至2026-09-10，用户标注的EMA55两根内实体确认策略。',
        limitation='全仓复利，不计成本；历史已见，规则沿用ZEC但ETH基准原已挑选。细周期仍不是逐笔行情；未组合改法或重新调参数。') for k,v in conclusions.items()]
    keep(OUT/'answers.json',answers)
    prior=ROOT/'docs/verification/zec-intrabar-methods-20260913'
    old_parity=read_json(prior/'baseline-parity.json')
    assert file_hash(SOURCE)==old_parity['source_hash'] and file_hash(ROOT/'app/domain/local_backtest.py')==old_parity['engine_hash']
    keep(OUT/'test-results.json',dict(engine_and_strategy_unchanged=True,engine_hash=old_parity['engine_hash'],source_hash=old_parity['source_hash'],
        reused_tests=dict(path=str((prior/'test-results.json').relative_to(ROOT)),sha256=file_hash(prior/'test-results.json'),passed=97),
        baseline_parity=read_json(OUT/'baseline-parity.json')['checks'],checked_entries={k:v['checked_entries'] for k,v in r.items()}))
    lines=['# ETH：ZEC的改法能否迁移','',
        '针对用户标出的+54,455.55%、9,288笔版本。ETH/USDT 15分钟，2020-09-10至2026-09-10；全仓复利、不加杠杆、不计手续费和滑点。','',
        'EMA55、振幅31、突破0.4倍、不追2倍；原信号后的第1或第2根盘中突破实体才入场。保留浮盈2%启动、最高浮盈回吐50%和反向信号平仓。','',
        '| 改法 | 六年收益 | 交易 | 赚 | 亏 | 平 | 胜率 | 最大回撤 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    order=['baseline','width_stop','atr_stop','fine_control','fine_protect']
    for cid in order:
        v=r[cid];p=v['report']
        lines.append(f'| [{v["name"]}]({v["chart"]}) | {p["return_pct"]:+,.2f}% | {p["total_trades"]} | {p["wins"]} | {p["losses"]} | {p["breakeven"]} | {p["win_rate"]:.2f}% | {p["max_drawdown_pct"]:.2f}% |')
    lines+=['','前两个止损改法各与原版比较；最后两组独立比较更新频率，不能把细化行情造成的差异算成优化收益。','']+[v[1]+'\n' for v in conclusions.values()]
    lines+=['## 逐年收益','','首尾为不完整年度；连续权益计算，不按年重置本金。','',
        '| 年份 | 原版 | 振幅止损 | ATR止损 | 5分钟成交/15分钟保护 | 5分钟成交/5分钟保护 |','|---|---:|---:|---:|---:|---:|']
    for i,year in enumerate(b['annual']):lines.append('| '+year['label']+' | '+' | '.join(f'{r[c]["annual"][i]["return_pct"]:+.2f}%' for c in order)+' |')
    lines+=['','## 本地证据','',
        '只新增4次运行，无组合或重新调参。交易引擎与策略代码均未改动，复用上一轮97项已通过检查；本轮重新完成原版9288笔逐笔一致验证、全部新入场时序与原信号一致验证。研究ID：'+identifier+'。','',
        '5分钟保护只在收盘后更新、下一根生效，尚有细K线内部先后不明；聚合行情不一致的区间两组共同回退15分钟，完整清单保留。所有历史已见，不能由本次比较证明未来稳定盈利。','',
        '- [固定规则](RULES.md)、[完整参数和计划](plan.json)、[逐项答案](answers.json)、[结构化结果](results.json)。',
        '- [原版一致检查](baseline-parity.json)、[数据核对](fine-data-check.json)、[代码与逐笔检查](test-results.json)。',
        '- 每组 `*-lineage.json` 保存原信号→委托→成交；表中名称打开项目图表。完整行情、策略、逐笔、权益保存在 `.opentrading_runtime/local_backtests/<run_id>/`，run_id见results.json。','']
    content='\n'.join(lines);path=OUT/'README.md'
    if path.exists():assert path.read_text(encoding='utf8')==content
    else:path.write_text(content,encoding='utf8')
    print(json.dumps({k:v[1] for k,v in conclusions.items()},ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','analyze','report','finalize']);action=p.parse_args().action
    configure();db=build_database_runtime(settings);studies=ResearchStudyService(shared.FrozenBacktests(db))
    try:
        if action=='prepare':prepare(studies)
        elif action=='report':report(studies,read_json(OUT/'study.json')['id'])
        else:getattr(shared,action)(studies,read_json(OUT/'study.json')['id'])
    finally:db.dispose()


if __name__=='__main__':main()
