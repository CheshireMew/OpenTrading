"""Bounded, resumable comparison using frozen project data and project workers.

No downloading, optimizer or duplicate simulator. Run prepare, run, analyze.
"""
import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from app.domain.local_backtest import Bar, simulate
from app.domain.cloud_trade_attribution import summary, periods, calendar_returns
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash, atomic_json
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from app.services.research_study_service import ResearchStudyService
from scripts.local_backtest_worker import execute
from config import settings

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/verification/eth-cloud-width-reentry-20260912'
BASE_ID = '4e65bfb4229646299932d76515ec0ac0'
BASE = ROOT/'.opentrading_runtime/local_backtests'/BASE_ID
SOURCE = ROOT/'strategies/trend_cloud_width_reentry_v1.py'
STEP = 900000
VARIANTS = [
    ('no_chase', '只取消不追远处限制', {'chase_mult': 0}),
    ('outer', '固定外线突破入场', {'entry_mode': 1}),
    ('cloud_switch', '通道宽窄切换入场', {'entry_mode': 2}),
    ('bb_switch', '布林宽窄切换入场', {'entry_mode': 3}),
    ('retry', '原版＋止损后补一次', {'stop_reentry': True}),
    ('width_stop', '原版＋随宽度止损', {'dynamic_stop': True}),
    ('width_stop_retry', '随宽度止损＋补一次', {'dynamic_stop': True, 'stop_reentry': True}),
    ('all_combined', '通道宽窄入场＋随宽度止损＋补一次', {'entry_mode': 2, 'dynamic_stop': True, 'stop_reentry': True}),
]


def keep(path, value):
    if path.exists():
        if read_json(path) != value:
            raise ValueError(f'不可覆盖已有证据：{path}')
    else:
        atomic_json(path, value)


class FrozenDataBacktests(LocalBacktestService):
    """Pin identical bytes at queue creation, before a background worker can claim.

    Uses the existing service's snapshot argument, as normal research retries do.
    This adapter is restricted to this study's exact symbol/period/warmup.
    """
    def prepare(self, command):
        config, source, metadata = super().prepare(command)
        original = read_json(BASE/'config.json')
        for key in ('symbol', 'timeframe', 'start', 'end', 'initial_cash', 'position_pct', 'data_gap_policy'):
            if config[key] != original[key]:
                raise ValueError(f'冻结行情范围不一致：{key}')
        if metadata['strategy']['warmup_bars'] != 650:
            raise ValueError('预热范围不一致')
        metadata.update(data_hash=file_hash(BASE/'data.json'), input_data_run=BASE_ID)
        return config, source, metadata

    def _create(self, config, source, metadata, parent_id=None, data=None, identifier=None):
        if data is None:
            data = (BASE/'data.json').read_bytes()
        from app.infra.research_files import sha
        if sha(data) != metadata['data_hash']:
            raise ValueError('冻结行情哈希不一致')
        return super()._create(config, source, metadata, parent_id, data, identifier)


def prepare(studies):
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'study.json').exists():
        return read_json(OUT/'study.json')
    old = read_json(BASE/'result.json')
    rows = read_json(BASE/'data.json')
    original_config = read_json(BASE/'config.json')
    bars = [Bar(*r) for r in rows]
    module, spec = load_strategy(SOURCE)
    p = validate_parameters(spec, {'record_indicators': False})
    replay = simulate(bars, module, p, warmup=650, step_ms=STEP)
    parity = {key: replay[key] == old[key] for key in ('report', 'trades', 'signals', 'fills', 'equity', 'levels')}
    keep(OUT/'baseline-parity.json', dict(checks=parity, baseline=BASE_ID,
         source_hash=file_hash(SOURCE), engine_hash=file_hash(ROOT/'app/domain/local_backtest.py'),
         data_hash=file_hash(BASE/'data.json'), original_result_hash=file_hash(BASE/'result.json'),
         report=replay['report']))
    if not all(parity.values()):
        raise ValueError(f'原版逐笔一致性失败：{parity}')
    print('原版完整逐笔、信号、权益一致性通过', flush=True)
    cases = [dict(id='baseline', name='原六年最高收益版', variant='baseline', period='六年已见历史',
                  role='exploration', previously_seen=True, command=original_config, reuse_run=BASE_ID)]
    for key, name, overrides in VARIANTS:
        command = {**original_config, 'strategy': SOURCE.stem,
                   'parameters': validate_parameters(spec, overrides)}
        cases.append(dict(id=key, name=name, variant=key, period='六年已见历史',
                          role='exploration', previously_seen=True, command=command))
    plan = dict(title='ETH 六年：宽窄入场、随宽度止损、止损后补一次', family='ema55_cloud',
        objective='逐项检查入场宽度、追价限制、波动止损、一次补仓及组合是否增加收益；保留全部逐笔。',
        decision_rule='按六年总收益比较，同时检查逐年、移除的原版盈亏单和新增补仓；不因局部案例修改参数。',
        stop_rule='完成预先固定的八个改版对照后停止，不细化参数或再追逐冠军。',
        change_reason='用户要求增加宽窄止损及一次补仓；固定日前参照与阈值，不使用结果选参。',
        max_new_runs=8, cases=cases,
        questions=[dict(id=k, text=v) for k, v in [
            ('chase', '去掉原不追远处限制有何影响？'),
            ('outer', '固定外线入场是否比原版和仅取消追价限制好？'),
            ('switch', '通道宽窄或布林宽窄切换是否增加收益、减少亏单？'),
            ('stop', '随宽度调整初始止损是否增加收益？'),
            ('retry', '止损后补一次是否接回行情且不重复开仓？'),
            ('combined', '全部组合是否比各单项和原版更好？'),
        ]])
    keep(OUT/'plan.json', plan)
    keep(OUT/'preview.json', studies.preview_summary(plan))
    created = studies.create(plan)
    keep(OUT/'study.json', created)
    return created


def run(studies, identifier):
    submitted = studies.submit(identifier)
    if submitted['errors']:
        raise ValueError(submitted['errors'])
    for case, rid, task in studies.case_runs(identifier):
        if case['reuse_run'] or task['status'] == 'completed':
            continue
        repo = studies.backtests.repository
        if not repo.patch(rid, allowed={'queued'}, status='preparing'):
            raise ValueError(f'{case["id"]} 状态 {repo.get(rid)["status"]}，先查状态，不重复执行')
        started = time.monotonic()
        print(f'开始 {case["name"]} {rid}', flush=True)
        folder = studies.backtests.directory(rid)
        try:
            with (folder/'run.log').open('a', encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
                execute(studies.backtests, rid)
        except Exception as exc:
            repo.patch(rid, allowed={'preparing', 'running'}, status='failed', error=str(exc))
            raise
        result = repo.get(rid)
        if result['status'] != 'completed':
            raise ValueError(f'未完成：{rid}')
        if result['metadata']['data_hash'] != file_hash(BASE/'data.json'):
            raise ValueError('对照数据发生变化')
        print(json.dumps(dict(case=case['id'], seconds=round(time.monotonic()-started, 1),
            **{k: result['report'][k] for k in ('return_pct', 'total_trades', 'wins', 'losses')}), ensure_ascii=False), flush=True)


def trade_keys(trades):
    return {(t['entry_time'], t['side']): t for t in trades}


def analyze(studies, identifier):
    rows = read_json(BASE/'data.json')
    base = read_json(BASE/'result.json')
    baseline = trade_keys(base['trades'])
    results = {}
    for case, rid, run in studies.case_runs(identifier):
        studies.verify_run(run)
        result = read_json(studies.backtests.directory(rid)/'result.json')
        current = trade_keys(result['trades'])
        omitted = [t for k, t in baseline.items() if k not in current]
        added = [t for k, t in current.items() if k not in baseline]
        retry_ids = {f['trade_id'] for f in result['fills'] if f['reason'] == '初始止损后补一次' and f['action'] in ('long', 'short')}
        retry_trades = [t for t in result['trades'] if t['trade_id'] in retry_ids]
        identical_entry_changed_exit = sum(k in baseline and (t['exit_time'], t['exit_price']) !=
            (baseline[k]['exit_time'], baseline[k]['exit_price']) for k, t in current.items())
        paired = [(baseline[k], t) for k, t in current.items() if k in baseline]
        stopped_pairs = [(a, b) for a, b in paired if a['exit_reason'] == 'stop_loss']
        same_entry_effects = dict(pairs=len(paired),
            improved=sum(b['return_pct'] > a['return_pct']+1e-10 for a, b in paired),
            worsened=sum(b['return_pct'] < a['return_pct']-1e-10 for a, b in paired),
            mean_return_change_percentage_points=sum(b['return_pct']-a['return_pct'] for a, b in paired)/len(paired) if paired else None,
            original_initial_stop_pairs=len(stopped_pairs),
            original_stop_now_winner=sum(b['return_pct'] > 0 for a, b in stopped_pairs),
            original_stop_now_larger_loss=sum(b['return_pct'] < a['return_pct']-1e-10 for a, b in stopped_pairs))
        per_year = calendar_returns(result['equity'], rows,
            periods(result['equity'][0]['timestamp'], result['equity'][-1]['timestamp'], 'year'))
        summaries = dict(omitted_baseline=summary(omitted), added_actual=summary(added), retries=summary(retry_trades))
        stop_signals = [s['stop_loss_pct'] for s in result['signals'] if s['action'] in ('long', 'short') and s['status'] == 'executed']
        retry_checks = []
        if retry_trades:
            signal_by_time = {s['timestamp']: s for s in result['signals']}
            observation_by_time = {o['timestamp']: o for o in result['indicators']}
            previous_timestamp = {int(rows[i][0]): int(rows[i-1][0]) for i in range(1, len(rows))}
            close_by_time = {int(r[0]): r[4] for r in rows}
            for t in retry_trades:
                signal_time = previous_timestamp[t['entry_time']]
                obs = observation_by_time[signal_time]
                prior = result['trades'][t['trade_id']-2]
                d = 1 if t['side'] == 'long' else -1
                boundary = obs['values']['外侧上沿' if d == 1 else '外侧下沿']
                valid = (prior['exit_reason'] == 'stop_loss' and prior['side'] == t['side'] and
                         prior['exit_time'] <= signal_time and d*(close_by_time[signal_time]-boundary) > 0 and
                         signal_by_time[signal_time]['reason'] == '初始止损后补一次')
                if not valid:
                    raise ValueError(f'补仓事件不符合规则：{rid} trade {t["trade_id"]}')
                retry_checks.append(dict(trade_id=t['trade_id'], preceding_stop_trade_id=prior['trade_id'],
                    signal_time=signal_time, close=close_by_time[signal_time], boundary=boundary, valid=valid))
            del observation_by_time
        row = dict(name=case['name'], run_id=rid, report=result['report'], annual=per_year,
            exit_reasons=dict(Counter(t['exit_reason'] for t in result['trades'])),
            same_entry_changed_exit=identical_entry_changed_exit, same_entry_effects=same_entry_effects, **summaries,
            entry_stop_pct=dict(min=min(stop_signals), max=max(stop_signals), mean=sum(stop_signals)/len(stop_signals),
                at_min=sum(abs(x-.5) < 1e-10 for x in stop_signals), at_max=sum(abs(x-2) < 1e-10 for x in stop_signals)),
            ignored_same_side_signals=sum(s['status'] == 'ignored_same_side' for s in result['signals']),
            retry_execution_checks_passed=len(retry_checks),
            source_hash=run['metadata']['strategy_hash'], data_hash=run['metadata']['data_hash'],
            result_hash=file_hash(studies.backtests.directory(rid)/'result.json'),
            chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart&theme=light&tz=8')
        results[case['id']] = row
        keep(OUT/f'{case["id"]}-trade-comparison.json', dict(
            omitted_baseline_trade_ids=[t['trade_id'] for t in omitted],
            added_actual_trade_ids=[t['trade_id'] for t in added], retry_trade_ids=sorted(retry_ids),
            retry_execution_checks=retry_checks,
            note='按入场时间与方向配对。缺少原版入场不等于单纯过滤；可能已持仓。组内累计值不是改版增量收益。', **summaries))
    keep(OUT/'results.json', dict(study_id=identifier, baseline_run=BASE_ID, results=results,
        note='Binance ETH/USDT 15m，2020-09-10 至 2026-09-10 UTC；全仓复利、无成本。所有历史已见。'))
    print(json.dumps({k: {**{x: v['report'][x] for x in ('return_pct', 'total_trades', 'wins', 'losses', 'win_rate')},
        'retry_trades': v['retries']['trades']} for k, v in results.items()}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'analyze'])
    args = parser.parse_args()
    db = build_database_runtime(settings)
    studies = ResearchStudyService(FrozenDataBacktests(db))
    try:
        if args.action == 'prepare':
            print(json.dumps(prepare(studies), ensure_ascii=False))
        else:
            identifier = read_json(OUT/'study.json')['id']
            if args.action == 'run':
                run(studies, identifier)
            else:
                analyze(studies, identifier)
    finally:
        db.dispose()


if __name__ == '__main__':
    main()
