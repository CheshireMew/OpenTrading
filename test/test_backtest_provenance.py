from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import sys

import pytest

from app.domain.local_backtest import Bar, Intent, simulate
from app.services.research_comparison import compare_runs, paired_effect
from app.services.backtest_provenance import current_bundle, execution_summary
from app.services.market.history_range_coordinator import OhlcvRangeResult
from scripts.local_backtest_worker import execute
from test.test_local_backtest_service import setup_service, complete


def comparable(identifier, n=10):
    return dict(id=identifier, status='completed',
        config=dict(strategy='test', symbol='ETH/USDT', timeframe='15m', start='2025-01-01T00:00:00Z',
            end='2025-01-02T00:00:00Z', initial_cash=10000, position_pct=100, data_gap_policy='reject', parameters={'n': n}),
        metadata=dict(environment={'python': '3', 'dependencies': {}}, source={'exchange': 'test'}, data_hash='data',
            strategy_hash='strategy', warmup_bars=0, execution_bundle={'hash': 'bundle'}), report={'return_pct': n})


def test_missing_provenance_never_proves_single_factor():
    a, b = comparable('a'), comparable('b', 20)
    assert compare_runs(a, b)['single_factor']
    for key in ('environment', 'source', 'data_hash', 'strategy_hash', 'warmup_bars', 'execution_bundle'):
        left, right = deepcopy(a), deepcopy(b)
        left['metadata'].pop(key)
        right['metadata'].pop(key)
        result = compare_runs(left, right)
        assert not result['single_factor']
        assert key in result['provenance'][0]['missing']
        assert not paired_effect([left, right], 'parameters.n')['pairs']


def test_timeframe_pairs_keep_distinct_evidence_and_input_scope():
    a, b = comparable('a'), comparable('b')
    b['config']['timeframe'] = '1h'
    b['metadata']['data_hash'] = 'different-aggregation'
    result = compare_runs(a, b)
    assert result['timeframe_comparison'] and not result['single_factor']
    assert paired_effect([a, b], 'timeframe')['pairs']
    b['config']['end'] = '2025-01-03T00:00:00Z'
    assert not compare_runs(a, b)['timeframe_comparison']
    assert not paired_effect([a, b], 'timeframe')['pairs']


def test_fine_data_and_alignment_are_required_only_when_enabled():
    a, b = comparable('a'), comparable('b', 20)
    assert compare_runs(a, b)['single_factor']
    for run in (a, b):
        run['config']['execution_timeframe'] = '5m'
    assert not compare_runs(a, b)['single_factor']
    for run in (a, b):
        run['metadata'].update(execution_data_hash='fine', execution_alignment_hash='alignment')
    assert compare_runs(a, b)['single_factor']
    b['metadata']['execution_alignment_hash'] = 'changed'
    assert not compare_runs(a, b)['single_factor']


def test_execution_close_drawdown_is_separate_and_fallback_is_attached():
    class Strategy:
        def on_bar(self, ctx):
            return Intent('long') if len(ctx.history) == 1 else None
    bars = [Bar(0, 100, 100, 100, 100, 3), Bar(900000, 100, 120, 80, 100, 3),
            Bar(1800000, 100, 110, 90, 100, 3)]
    detail = {0: [Bar(i*300000, 100, 100, 100, 100, 1) for i in range(3)], 900000: [
        Bar(900000, 100, 120, 100, 120, 1), Bar(1200000, 120, 120, 80, 80, 1), Bar(1500000, 80, 100, 80, 100, 1)]}
    result = simulate(bars, Strategy(), {}, warmup=0, step_ms=900000, execution_bars=detail)
    assert result['report']['max_drawdown_pct'] == 0
    assert result['report']['execution_close_max_drawdown_pct'] == pytest.approx(100/3)
    assert result['report']['execution_drawdown_basis'] == 'mixed_closes'
    assert result['trades'][0]['execution_fallback_times'] == [1800000]
    assert result['trades'][0]['entry_signal_id'] == result['signals'][0]['signal_id']
    assert any(e['event'] == 'entry' and e['signal_id'] == 1 for e in result['events'])


def test_replay_uses_saved_alignment_after_current_code_changes(setup_service, tmp_path, monkeypatch):
    from app.services import backtest_provenance
    s, command, market = setup_service
    command = command.model_copy(update={'execution_timeframe': '5m'})
    start = int(command.start.timestamp()*1000)
    fine = [[start+i*300000, 100, 101, 99, 100, 1] for i in range(48)]
    fetch = SimpleNamespace(load_ohlcv_range=lambda symbol, tf, *args:
        OhlcvRangeResult(fine, []) if tf == '5m' else market.load_ohlcv_range())
    first = s.create(command)
    s.repository.claim()
    execute(s, first['id'], fetch)
    original = json.loads(s.export(first['id'], 'json')['content'])
    alternate = tmp_path/'new_execution'
    alternate.mkdir()
    for name in backtest_provenance.MODULES:
        shutil.copy2(backtest_provenance.DOMAIN/f'{name}.py', alternate/f'{name}.py')
    with (alternate/'backtest_history.py').open('a', encoding='utf8') as f:
        f.write("\ndef align_execution_bars(*args):\n    raise ValueError('new alignment behavior')\n")
    monkeypatch.setattr(backtest_provenance, 'DOMAIN', alternate)
    assert current_bundle() != first['metadata']['execution_bundle']
    before_module = sys.modules['app.domain.local_backtest']
    replay = s.rerun(first['id'])
    s.repository.claim()
    execute(s, replay['id'], SimpleNamespace(load_ohlcv_range=lambda *a: pytest.fail('replay must use saved data')))
    restored = json.loads(s.export(replay['id'], 'json')['content'])
    for key in ('report', 'trades', 'signals', 'fills', 'equity', 'execution_equity', 'events'):
        assert original[key] == restored[key]
    assert sys.modules['app.domain.local_backtest'] is before_module
    migrated = s.migrate(first['id'])
    assert migrated['metadata']['migration_from'] == first['id']
    s.repository.claim()
    with pytest.raises(ValueError, match='new alignment behavior'):
        execute(s, migrated['id'])


def test_execution_gap_policy_rejects_or_records_fallback(setup_service):
    s, command, market = setup_service
    start = int(command.start.timestamp()*1000)
    fine = [[start+i*300000, 100, 101, 99, 100, 1] for i in range(48) if i != 18]
    fetch = SimpleNamespace(load_ohlcv_range=lambda symbol, tf, *args:
        OhlcvRangeResult(fine, []) if tf == '5m' else market.load_ohlcv_range())
    reject = s.create(command.model_copy(update={'execution_timeframe': '5m', 'execution_gap_policy': 'reject'}))
    s.repository.claim()
    with pytest.raises(ValueError, match='禁止回退'):
        execute(s, reject['id'], fetch)
    allowed = s.create(command.model_copy(update={'execution_timeframe': '5m', 'execution_gap_policy': 'coarse_fallback'}))
    s.repository.claim()
    execute(s, allowed['id'], fetch)
    summary = execution_summary(s.repository.get(allowed['id']))
    assert summary['fallback_intervals'] == 1 and summary['coverage_pct'] == 75


def test_execution_bundle_tampering_rejected_and_legacy_migration_explicit(setup_service):
    s, run = complete(setup_service)
    folder = s.directory(run['id'])
    with (folder/'execution/backtest_history.py').open('a', encoding='utf8') as f:
        f.write('\n# changed\n')
    with pytest.raises(ValueError, match='执行依赖快照校验失败'):
        s.rerun(run['id'])
    meta = json.loads((folder/'metadata.json').read_text(encoding='utf8'))
    meta.pop('execution_bundle')
    (folder/'metadata.json').write_text(json.dumps(meta), encoding='utf8')
    with pytest.raises(ValueError, match='旧记录缺少完整执行依赖'):
        s.rerun(run['id'])
    migrated = s.migrate(run['id'])
    assert migrated['metadata']['migration_from'] == run['id']
