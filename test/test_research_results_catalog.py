import asyncio
from copy import deepcopy
import json

import pytest
from app.infra.research_files import atomic_json, file_hash, read_json
from app.services.research_catalog import ResearchCatalog
from app.services.research_results_catalog import ResearchResultsCatalog, legacy_entries
from scripts.local_backtest_worker import execute
from test.test_local_backtest_service import setup_service, complete


def report(value=10):
    return dict(return_pct=value, total_trades=3, initial_cash=10000, final_equity=10000*(1+value/100),
                max_drawdown_pct=4, win_rate=50)


def test_native_registration_query_archive_and_legacy_alias(setup_service, tmp_path):
    service, run = complete(setup_service)
    catalog = ResearchResultsCatalog(service)
    # Completion itself registers the run, before any reconciliation query.
    with catalog.connection() as db:
        assert db.execute('SELECT count(*) FROM results').fetchone()[0] == 1
    page = catalog.query(symbol=run['config']['symbol'], parameters={})
    assert page['total'] == 1 and page['items'][0]['run_id'] == run['id']
    assert page['items'][0]['cohort']
    assert catalog.query(reference_id='run:'+run['id'])['mode'] == 'same_conditions'
    source = tmp_path/'summary.json'
    atomic_json(source, {'rows': [dict(run_id=run['id'], config=run['config'], report=run['report'])]})
    catalog.refresh([source])
    assert catalog.query()['total'] == 1
    assert len(catalog.get('run:'+run['id'])['sources']) == 2
    service.archive(run['id'])
    assert catalog.query()['total'] == 0
    assert catalog.query(include_archived=True)['total'] == 1


def test_plan_matrix_context_and_counterfactual_are_separate(tmp_path, setup_service):
    service, _, _ = setup_service
    catalog = ResearchResultsCatalog(service)
    source = tmp_path/'matrix.json'
    document = dict(plan=dict(symbol='ETH/USDT', timeframe='15m',
        periods={'full': ['2020-01-01', '2026-01-01']},
        variants={'a': {'parameters': {'center_length': 55}}, 'b': {'parameters': {'center_length': 89}}}),
        results={'a': {'full': report(10)}, 'b': {'full': report(20)}},
        winners_only={'report': report(100000)}, comparison={'report': report(1000000)})
    atomic_json(source, document)
    assert catalog.refresh([source])['imported_references'] == 2
    assert catalog.query(symbol='ETH/USDT')['total'] == 2
    assert catalog.query(parameters={'center_length': 55})['items'][0]['report']['return_pct'] == 10
    assert catalog.query(parameters={'center_length': 55, 'unknown': 2})['total'] == 0
    entry = catalog.query()['items'][0]
    assert entry['report']['return_pct'] == 20 and entry['missing']
    with pytest.raises(ValueError, match='证据不足'):
        catalog.query(reference_id=entry['id'])
    assert catalog.refresh([source])['unchanged_files'] == 1
    document['results']['b']['full'] = report(5)
    atomic_json(source, document)
    catalog.refresh([source])
    assert catalog.query()['items'][0]['report']['return_pct'] == 10


def test_same_conditions_require_actual_provenance_and_execution(setup_service):
    service, run = complete(setup_service)
    for suffix, change in [('params', {'parameters': {'x': 1}}), ('size', {'position_pct': 50})]:
        other = deepcopy(run)
        other.update(id=suffix, config={**run['config'], **change})
        service.repository.create(other)
        service.repository.patch(suffix, status='completed')
    missing = deepcopy(run)
    missing.update(id='missing', metadata={})
    service.repository.create(missing)
    service.repository.patch('missing', status='completed')
    catalog = ResearchResultsCatalog(service)
    assert catalog.query()['total'] == 4
    paired = catalog.query(reference_id='run:'+run['id'])
    assert {e['run_id'] for e in paired['items']} == {run['id'], 'params'}
    with pytest.raises(ValueError, match='证据不足'):
        catalog.query(reference_id='run:missing')


def test_text_search_inherits_only_owning_object_context(tmp_path):
    source = tmp_path/'summary.json'
    atomic_json(source, dict(symbol='ETH/USDT', variants=[
        {'name': 'alpha', 'parameters': {'center_length': 55}},
        {'name': 'beta', 'parameters': {'center_length': 89}}]))
    catalog = ResearchCatalog(tmp_path/'text.sqlite')
    catalog.refresh([source])
    assert catalog.search('ETH 55')['total'] > 0
    assert catalog.search('alpha 89')['total'] == 0
    assert catalog.search('beta 55')['total'] == 0


def test_large_source_and_invalid_json_are_reported_without_import(setup_service, tmp_path):
    service, _, _ = setup_service
    good, bad = tmp_path/'big.json', tmp_path/'broken.json'
    atomic_json(good, {'report': report(), 'trades': [{'profit': i} for i in range(1000)]})
    bad.write_text('{', encoding='utf8')
    outcome = ResearchResultsCatalog(service).refresh([good, bad], max_json_bytes=500)
    assert len(outcome['issues']) == 2 and outcome['imported_references'] == 0


def test_cli_and_api_return_same_catalog_contract(setup_service, monkeypatch):
    from scripts.research_cli import build_parser, execute as cli
    from app.routers.local_backtests import query_research_results
    from app.contracts.research_results import ResearchResultQuery, ResearchResultPage
    service, run = complete(setup_service)
    monkeypatch.setattr('app.infra.db.build_database_runtime', lambda _: service.repository.database)
    monkeypatch.setattr(service.repository.database, 'dispose', lambda: None)
    monkeypatch.setattr('app.services.local_backtest_service.LocalBacktestService', lambda _: service)
    cli_page = asyncio.run(cli(build_parser().parse_args(['catalog', 'results', '--symbol', run['config']['symbol']])))
    api_page = asyncio.run(query_research_results(ResearchResultQuery(symbol=run['config']['symbol']), service))
    assert cli_page == api_page
    assert ResearchResultPage.model_validate(api_page).total == 1


def test_manifest_preserves_context_evidence_and_withdraws_stale_mapping(setup_service, tmp_path):
    service, _, _ = setup_service
    catalog = ResearchResultsCatalog(service)
    data, plan, mapping = tmp_path/'policy.json', tmp_path/'plan.json', tmp_path/'sources.json'
    atomic_json(data, {'name': 'fixed', 'report': report(123)})
    atomic_json(plan, {'symbol': 'ETH/USDT', 'parameters': {'center_length': 55}})
    atomic_json(mapping, dict(catalog_manifest_version=1, entries=[dict(
        source=dict(path=data.name, pointer='/', sha256=file_hash(data)),
        context_sources=[dict(path=plan.name, sha256=file_hash(plan))],
        config=dict(symbol='ETH/USDT', parameters={'center_length': 55}), family='EMA 通道')]))
    assert not catalog.refresh([data, mapping])['issues']
    assert catalog.query(symbol='ETH/USDT', family='EMA 通道')['total'] == 1
    assert catalog.refresh([mapping])['unchanged_files'] == 1
    assert catalog.query()['total'] == 1
    # A changed plan cannot leave yesterday's claimed parameter mapping active.
    atomic_json(plan, {'symbol': 'BTC/USDT'})
    assert catalog.refresh([mapping])['issues']
    assert catalog.query(symbol='ETH/USDT')['total'] == 0
    assert catalog.query()['items'][0]['report']['return_pct'] == 123
    atomic_json(plan, {'symbol': 'ETH/USDT', 'parameters': {'center_length': 55}})
    assert not catalog.refresh([mapping])['issues']
    assert catalog.query(symbol='ETH/USDT')['total'] == 1
    original_mapping = read_json(mapping)
    atomic_json(mapping, dict(catalog_manifest_version=1, entries=[]))
    catalog.refresh([mapping])
    assert catalog.query(symbol='ETH/USDT')['total'] == 0
    atomic_json(mapping, original_mapping)
    catalog.refresh([mapping])
    mapping.rename(tmp_path/'archived-map.txt')
    assert catalog.refresh([data])['issues']
    assert catalog.query(symbol='ETH/USDT')['total'] == 0


def test_catalog_keeps_real_execution_coverage(setup_service):
    from app.services.research_results_catalog import make_entry
    service, run = complete(setup_service)
    run['config'].update(execution_timeframe='5m', intrabar_profit_protection=True)
    run['metadata'].update(execution_matched_candles=98, execution_fallback_candles=2)
    item = make_entry('run:test',run['config'],run['report'],run['metadata'],'native','test')
    assert item['execution_summary']['coverage_pct'] == 98
    assert item['execution_summary']['fallback_intervals'] == 2
