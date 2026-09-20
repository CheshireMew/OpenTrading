import json
import math
from pathlib import Path

import pytest
from app.contracts.local_backtest import LocalBacktestPreview, LocalBacktestStrategy
from app.contracts.parameter_sweep import ParameterSweepPreview
from app.infra.db.schema import Kline
from app.services.local_backtest_strategies import inspect_strategy, resolve_warmup, validate_parameters, rules_summary
from app.services.backtest_preflight import coverage, intersect_intervals
from app.services.parameter_sweep_service import ParameterSweepService
from test.test_local_backtest_service import setup_service


def test_parameter_warmup_convergence_options_and_saved_rules():
    path = Path('strategies/trend_cloud_intrabar_methods_v3.py')
    spec = inspect_strategy(path.read_bytes(), path.name)
    values = validate_parameters(spec, {})
    count, _ = resolve_warmup(spec, values)
    assert (1 - 2 / 56) ** (count - 8) <= 1e-8
    longer, _ = resolve_warmup(spec, {**values, 'center_length': 200})
    assert longer > count
    with pytest.raises(ValueError, match='下限'):
        validate_parameters(spec, {'stop_floor_pct': 3, 'stop_cap_pct': 2})
    text = ' '.join(rules_summary(spec, values))
    assert '固定百分比' in text and '波动止损倍数' not in text
    assert '波动止损倍数' in ' '.join(rules_summary(spec, {**values, 'stop_method': 2}))
    bad = spec.model_copy(deep=True)
    bad.parameters['stop_method'].options = bad.parameters['stop_method'].options[:1]
    with pytest.raises(ValueError, match='选项'):
        validate_parameters(bad, {'stop_method': 1})
    legacy = spec.model_copy(update={'warmup_rule': None})
    assert resolve_warmup(legacy, values)[0] == 650


def test_sma_uses_required_window_and_all_static_metadata_resolves():
    for path in Path('strategies').glob('*.py'):
        if path.stem in {'trend_cloud_direct_v7', 'trend_cloud_timeframe_v6', 'trend_cloud_atr_confirm_v5'}:
            continue  # Research-only imported dependencies are intentionally not queue strategies.
        spec = inspect_strategy(path.read_bytes(), path.name)
        values = validate_parameters(spec, {})
        assert resolve_warmup(spec, values)[0] > 0
    path = Path('strategies/ma_cross.py')
    spec = inspect_strategy(path.read_bytes(), path.name)
    assert resolve_warmup(spec, validate_parameters(spec, {'slow': 200}))[0] == 201
    assert resolve_warmup(spec, validate_parameters(spec, {'slow': 30}))[0] == 31
    with pytest.raises(ValueError, match='快线'):
        validate_parameters(spec, {'fast': 40, 'slow': 30})


def test_cache_preview_is_read_only_and_gaps_preserve_full_warmup(setup_service):
    service, command, _ = setup_service
    start = int(command.start.timestamp()*1000)
    step = 3600000
    with service.repository.database.session_scope() as session:
        for i in (-1, 0, 2, 3):
            session.add(Kline(symbol='BTC/USDT', timeframe='1h', timestamp=start+i*step, open=100, high=101, low=99, close=100, volume=1))
    preview = service.preview(command)
    typed = LocalBacktestPreview.model_validate(preview)
    assert typed.signal_data.missing_bars == 1
    assert typed.comparable_intervals[0].model_dump() == dict(start_ms=start, end_ms=start+step)
    assert typed.comparable_intervals[1].model_dump() == dict(start_ms=start+3*step, end_ms=start+4*step)
    assert typed.config['start'] == command.model_dump(mode='json')['start']
    assert service.repository.list()['total'] == 0 and not service.root.exists()
    assert intersect_intervals([dict(start_ms=1,end_ms=8)], [dict(start_ms=2,end_ms=3),dict(start_ms=5,end_ms=10)]) == [dict(start_ms=2,end_ms=3),dict(start_ms=5,end_ms=8)]


def test_batch_freezes_common_parameter_warmup_and_previews_do_not_queue(setup_service, tmp_path):
    service, command, _ = setup_service
    path = tmp_path/'test_strategy.py'
    path.write_text('''from app.domain.local_backtest import Intent
STRATEGY = {'id':'test_strategy','name':'test','description':'example','api_version':'1','warmup_bars':650,
 'parameters': {'length':{'type':'int','default':2,'min':2,'max':20}},
 'warmup_rule': {'terms':[{'kind':'window','period':'length','extra_bars':1}],'explanation':'history window'}}
def on_bar(c): return None
''', encoding='utf8')
    sweep = ParameterSweepService(service, tmp_path/'studies')
    payload = dict(title='warmup', base=command.model_dump(mode='json'), axes={'parameters.length':[2,10]})
    preview = ParameterSweepPreview.model_validate(sweep.preview(payload))
    assert [v.warmup_bars for v in preview.data_previews] == [11,11]
    assert service.repository.list()['total'] == 0
    created = sweep.create(payload)
    runs = [service.repository.get(item['run_id']) for item in created['items']]
    assert {r['metadata']['warmup_bars'] for r in runs} == {11}
    assert {r['metadata']['execution_recipe']['warmup_bars'] for r in runs} == {11}
    assert {r['metadata']['parameter_warmup_bars'] for r in runs} == {3,11}
    assert len({r['metadata']['batch_snapshot_group'] for r in runs}) == 1
    assert created['strategy']['warmup_rule']['terms'][0]['period'] == 'length'
