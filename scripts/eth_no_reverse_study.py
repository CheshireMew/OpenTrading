"""One requested ETH exit ablation, with frozen inputs and existing audits."""
import argparse

from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_strategy_versions import ROOT, snapshot
from scripts.cloud_width_reentry_study import keep
from scripts.intrabar_requested_followups import Frozen
from scripts.paxg_intrabar_combined_study import save_text
from scripts.zec_intrabar_methods_study import run
from scripts import zec_paxg_entry_parameters_study as audit

OUT = ROOT/'docs/verification/eth-no-reverse-20260913'
BASE = ROOT/'.opentrading_runtime/local_backtests/3f31380c7267449f53743dc1fe5bcebd'
SOURCE = ROOT/'strategies/trend_cloud_intrabar_exit_v4.py'
OLD = ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
ENGINE = ROOT/'app/domain/local_backtest.py'
STEP = 900000


def prepare(studies):
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'study.json').exists():
        return
    cfg = read_json(BASE/'config.json')
    tests = read_json(ROOT/'docs/verification/paxg-exit-comparison-20260913/tests.json')
    assert file_hash(SOURCE) == tests['source_hash']
    assert file_hash(ENGINE) == tests['engine_hash'] == file_hash(BASE/'engine.py')
    assert file_hash(OLD) == tests['original_source_hash'] == file_hash(BASE/'strategy.py')
    assert cfg['timeframe'] == '15m' and cfg['execution_timeframe'] == '5m' and cfg['intrabar_profit_protection']
    cases = []
    for cid, name in [('baseline', '原版：1%止损＋反向平仓'), ('no_reverse', '取消反向平仓，保留1%止损')]:
        command = cfg if cid == 'baseline' else {**cfg, 'strategy': SOURCE.stem,
            'parameters': {**cfg['parameters'], 'reverse_exit': False}}
        case = dict(id=cid, name=name, variant=cid, period='2020-09-10至2026-09-10',
            role='exploration', previously_seen=True, command=command)
        if cid == 'baseline':
            case['reuse_run'] = BASE.name
        cases.append(case)
    plan = dict(title='ETH：取消反向平仓', family='ema_cloud',
        parent=read_json(ROOT/'docs/verification/eth-intrabar-methods-20260913/study.json')['id'],
        objective='仅取消反向平仓，与ETH六年+61,349.61%版本比较。',
        change_reason='用户指定该版本，仅关闭持仓中的反向退出与反手入场。',
        decision_rule='比较同一期间总收益、胜负次数和回撤，以退出原因辅助解释。',
        stop_rule='复用原版，只新增1次，不改其他参数。', max_new_runs=1, cases=cases,
        questions=[dict(id='no_reverse', text='仅取消反向平仓是否改善ETH原版？')])
    rules = '''ETH/USDT，15分钟，2020-09-10至2026-09-10。原版累计收益+61,349.613330260436%。EMA55，W=EMA(high-low,31)，门槛0.4W，不追2W，仅原信号第2或第3根盘中突破实体入场。固定1%止损；浮盈2%启动保护、回吐最高浮盈50%；每5分钟收盘更新保护，下一根生效。

只新增取消反向平仓一组：持仓中反向信号既不平仓，也不挂反向入场单；不排队保存持仓中的信号。止损或利润保护退出后，等待新的原信号，再按原确认规则入场。空仓未成交的等待仍可被反向信号替换。期末统一平仓。

复用已通过13项检查的独立v4策略，原v3和引擎均不改。两组使用同一份15分钟和5分钟行情快照，650根预热。细行情须完整且OHLC一致，否则共同回退原周期；5分钟内仍可能先后不明。全仓复利、不加杠杆、不计手续费滑点；最大回撤按15分钟收盘权益。历史已见。完整代码、参数、行情、交易、订单和资金曲线均保存至项目各run_id目录。
'''
    save_text(OUT/'RULES.md', rules)
    keep(OUT/'plan.json', plan)
    keep(OUT/'checks-reused.json', dict(source='docs/verification/paxg-exit-comparison-20260913/tests.json',
        hash_verified=True, **tests))
    keep(OUT/'study.json', studies.create(plan))
    snapshot('108_eth_no_reverse_frozen', [SOURCE, OLD, ENGINE, ROOT/'scripts/eth_no_reverse_study.py',
        ROOT/'test/test_intrabar_reverse_exit.py'] + list(OUT.glob('*.json')) + [OUT/'RULES.md'])
    print('已冻结：原版复用，只新增取消反向平仓1组。', flush=True)


def finish(studies, sid):
    if studies.state(sid)[4] == 'completed':
        return
    audit.OUT = OUT
    audit.STEPS['15m'] = STEP
    cfg = read_json(BASE/'config.json')
    records, hashes, checks = {}, set(), None
    for case, rid, task in studies.case_runs(sid):
        studies.verify_run(task)
        folder = studies.backtests.directory(rid)
        result = read_json(folder/'result.json')
        raw = [(x['timestamp'], x['checks']['原做多信号'], x['checks']['原做空信号']) for x in result['indicators']]
        if checks is None:
            checks = raw
        else:
            assert checks == raw
        expected = cfg if case['id'] == 'baseline' else {**cfg, 'strategy': SOURCE.stem,
            'parameters': {**cfg['parameters'], 'reverse_exit': False}}
        assert case['config'] == expected
        if case['id'] == 'no_reverse':
            assert all(s['action'] != 'close' for s in result['signals'])
            assert all(t['exit_reason'] in ('stop_loss', 'profit_protection', 'end_of_backtest') for t in result['trades'])
            for prev, curr in zip(result['trades'], result['trades'][1:]):
                assert curr['entry_order_signal_time'] + STEP > prev['exit_time']
        audit.audit_case('eth', case, rid, task, studies.backtests)
        value = read_json(OUT/'eth/cases'/f'{case["id"]}.json')
        records[case['id']] = value
        hashes.add((value['data_hash'], value['execution_data_hash']))
    assert len(hashes) == 1
    keep(OUT/'results.json', dict(study_id=sid, results=records))
    keep(OUT/'verification.json', dict(same_raw_signals=True, same_data_hashes=list(hashes), new_runs=1,
        no_reverse_has_no_close_or_reversal=True, entries_checked={k:v['entries_checked'] for k,v in records.items()}))
    b, n = records['baseline']['report'], records['no_reverse']['report']
    conclusion = f'仅取消反向平仓：收益{b["return_pct"]:+,.2f}%→{n["return_pct"]:+,.2f}%；胜率{b["win_rate"]:.2f}%→{n["win_rate"]:.2f}%；交易{b["total_trades"]}→{n["total_trades"]}笔；最大回撤{b["max_drawdown_pct"]:.2f}%→{n["max_drawdown_pct"]:.2f}%。'
    answer = dict(question='no_reverse', conclusion=conclusion, decision='keep' if n['return_pct']>b['return_pct'] else 'reject',
        evidence=['artifact:results', 'case:baseline', 'case:no_reverse'], scope='ETH六年15分钟，只有反向平仓开关不同。',
        limitation='全仓复利不计费用，历史已见；5分钟并非逐笔行情。')
    keep(OUT/'answers.json', [answer])
    lines = ['# ETH：取消反向平仓', '', conclusion, '',
        '| 版本 | 收益 | 笔数 | 赚 | 亏 | 平 | 胜率 | 最大回撤 |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for v in records.values():
        r = v['report']
        lines.append(f'| [{v["name"]}]({v["chart"]}) | {r["return_pct"]:+,.2f}% | {r["total_trades"]} | {r["wins"]} | {r["losses"]} | {r["breakeven"]} | {r["win_rate"]:.2f}% | {r["max_drawdown_pct"]:.2f}% |')
    lines += ['', '| 版本 | 固定止损退出 | 反向退出 | 保护退出 | 平均盈利单 | 平均亏损单 | 平均持仓小时 |', '|---|---:|---:|---:|---:|---:|---:|']
    for v in records.values():
        e = v['exits']
        lines.append(f'| {v["name"]} | {e.get("stop_loss",0)} | {e.get("signal",0)+e.get("reversal",0)} | {e.get("profit_protection",0)} | {v["mean_win_pct"]:.2f}% | {v["mean_loss_pct"]:.2f}% | {v["report"]["average_duration_minutes"]/60:.2f} |')
    lines += ['', '| 年份 | 原版 | 取消反向平仓 |', '|---|---:|---:|']
    for a, b in zip(records['baseline']['annual'], records['no_reverse']['annual']):
        assert a['label'] == b['label']
        lines.append(f'| {a["label"]} | {a["return_pct"]:+,.2f}% | {b["return_pct"]:+,.2f}% |')
    lines += ['', '2020、2026不是完整年度。两组固定1%止损，2%启动保护、回吐50%，每5分钟更新。无反向版退出后仍须新信号确认，不自动重进。原始信号、数据哈希及逐笔入场时序已核对。仅新增一次运行，所有旧版本保留。', '',
        'RULES.md记录规则；results.json记录完整参数、run_id、年度及统计；eth/lineage保存每笔确认来源。项目run目录保存行情、代码、引擎、订单、交易和权益。全仓复利、不计费用，结果只适用于所测已见历史。', '']
    save_text(OUT/'README.md', '\n'.join(lines))
    for name, file in [('rules','RULES.md'), ('results','results.json'), ('report','README.md'), ('verification','verification.json'), ('checks','checks-reused.json')]:
        if name not in studies.state(sid)[2]:
            studies.attach(sid, name, OUT/file, name)
    if 'no_reverse' not in studies.state(sid)[1]:
        studies.answer(sid, answer)
    keep(OUT/'completion.json', studies.complete(sid))
    snapshot('109_eth_no_reverse_completed', [ROOT/'scripts/eth_no_reverse_study.py'] + list(OUT.glob('*.json')) + [OUT/'README.md'])
    print(conclusion, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run', 'finish'])
    args = parser.parse_args()
    db = build_database_runtime(settings)
    try:
        studies = ResearchStudyService(Frozen(db, read_json(BASE/'config.json'), BASE/'data.json', BASE/'execution_data.json'))
        if args.action == 'prepare':
            prepare(studies)
        else:
            globals()[args.action](studies, read_json(OUT/'study.json')['id'])
    finally:
        db.dispose()
