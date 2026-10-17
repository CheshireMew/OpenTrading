import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest
from app.contracts.research_study import StudyPlan
from app.contracts.research_study import parse_plan
from app.infra.research_files import read_json, atomic_json
from app.services.research_study_service import ResearchStudyService
from app.services.research_comparison import compare_runs, paired_effect, trade_breakdown
from app.services.research_catalog import ResearchCatalog
from scripts.local_backtest_worker import execute
from test.test_local_backtest_service import setup_service


def payload(command):
    return dict(title='测试研究', family='通道', objective='检查一个明确问题',
                decision_rule='比较收益差', stop_rule='回答后停止', change_reason='初始记录',
                questions=[dict(id='width', text='加通道有用吗？')], max_new_runs=2,
                cases=[dict(id='baseline', name='基准', variant='base', period='历史',
                            role='exploration', previously_seen=True, command=command.model_dump(mode='json'))])


@pytest.fixture
def study(setup_service, tmp_path):
    backtest, command, market = setup_service
    service = ResearchStudyService(backtest, tmp_path / 'studies')
    return service, payload(command), market


def finish_queue(service, market):
    while identifier := service.backtests.repository.claim():
        execute(service.backtests, identifier, market)


def test_frozen_lifecycle_preserves_evidence_and_requires_answers(study, tmp_path):
    service, plan, market = study
    sid = service.create(plan)['id']
    frozen = service.plan(sid)
    assert frozen['cases'][0]['config']['parameters'] == {}
    result = service.submit(sid)
    rid = result['submitted'][0]['run_id']
    assert service.submit(sid)['submitted'] == []
    finish_queue(service, market)
    with pytest.raises(ValueError, match='问题未回答'):
        service.complete(sid)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text('{"fact":1}', encoding='utf-8')
    service.attach(sid, 'note-v1', evidence, '分析原始记录')
    evidence.write_text('{"fact":2}', encoding='utf-8')
    service.answer(sid, dict(question='width', conclusion='这个小样本不能证明有效',
                   evidence=['case:baseline', 'artifact:note-v1'], scope='测试数据',
                   limitation='不是市场检验', decision='inconclusive'))
    assert service.complete(sid)['status'] == 'completed'
    assert service.backtests.repository.get(rid)['status'] == 'completed'
    assert len(service.events(sid)) == 4
    with pytest.raises(ValueError, match='新建'):
        service.submit(sid)


def test_submission_recovers_after_queue_created_before_return(study, monkeypatch):
    service, plan, _ = study
    sid = service.create(plan)['id']
    create = service.backtests._create
    def interrupted(*args, **kwargs):
        create(*args, **kwargs)
        raise OSError('模拟进程退出')
    monkeypatch.setattr(service.backtests, '_create', interrupted)
    assert service.submit(sid)['errors']
    monkeypatch.setattr(service.backtests, '_create', create)
    assert service.submit(sid)['submitted'] == []
    assert service.backtests.repository.list()['total'] == 1


def test_submission_recovers_before_queue_created(study, monkeypatch):
    service, plan, _ = study
    sid = service.create(plan)['id']
    create = service.backtests._create
    def interrupted(*args, **kwargs):
        raise OSError('创建前中断')
    monkeypatch.setattr(service.backtests, '_create', interrupted)
    service.submit(sid)
    recorded = service.events(sid)[0]['run_id']
    monkeypatch.setattr(service.backtests, '_create', create)
    assert service.submit(sid)['submitted'][0]['run_id'] == recorded
    assert len(service.events(sid)) == 1


def test_duplicate_cases_share_run(study):
    service, plan, market = study
    plan['cases'].append({**plan['cases'][0], 'id': 'alias', 'name': '同一输入'})
    sid = service.create(plan)['id']
    assert service.preview_summary(plan)['new_runs'] == 1
    result = service.submit(sid)
    assert len({v['run_id'] for v in result['submitted']}) == 1
    assert service.backtests.repository.list()['total'] == 1
    finish_queue(service, market)
    assert service.summary(sid)['cases'] == {'completed': 2}


def test_retry_keeps_old_run_and_reuses_prepared_data(study):
    service, plan, market = study
    sid = service.create(plan)['id']
    rid = service.submit(sid)['submitted'][0]['run_id']
    finish_queue(service, market)
    service.backtests.repository.patch(rid, status='interrupted')
    retry = service.submit(sid, retry='baseline')['submitted'][0]['run_id']
    assert retry != rid
    assert service.backtests.repository.get(retry)['parent_id'] == rid
    assert service.backtests.repository.claim() == retry
    from types import SimpleNamespace
    execute(service.backtests, retry, SimpleNamespace(load_ohlcv_range=lambda *a: pytest.fail('不应重新获取数据')))
    assert service.backtests.repository.get(retry)['report'] == service.backtests.repository.get(rid)['report']


def test_validation_requires_selection_and_cannot_be_reselected(study):
    service, plan, market = study
    plan['cases'][0]['role'] = 'selection'
    second = deepcopy(plan['cases'][0])
    second.update(id='later', period='以后', role='test', previously_seen=False)
    second['command'].update(start='2025-02-01T00:00:00Z', end='2025-02-01T04:00:00Z')
    plan['cases'].append(second)
    sid = service.create(plan)['id']
    assert len(service.submit(sid)['submitted']) == 1
    with pytest.raises(ValueError, match='先完成'):
        service.select(sid, ['base'], '预先固定')
    finish_queue(service, market)
    service.select(sid, ['base'], '选择期内保留基准')
    assert service.submit(sid)['submitted'][0]['case'] == 'later'
    with pytest.raises(ValueError, match='已经锁定'):
        service.select(sid, ['base'], '重新选择')


def test_budget_time_roles_and_tampering(study):
    service, plan, market = study
    plan['max_new_runs'] = 0
    with pytest.raises(ValueError, match='max_new_runs'):
        service.create(plan)
    plan['max_new_runs'] = 2
    plan['cases'][0]['role'] = 'selection'
    plan['cases'].append({**plan['cases'][0], 'id': 'test', 'role': 'test'})
    with pytest.raises(ValueError, match='不重叠'):
        StudyPlan.model_validate(plan)
    plan['cases'].pop()
    sid = service.create(plan)['id']
    path = service.folder(sid) / 'plan.json'
    original = read_json(path)
    original['objective'] = '偷改目标'
    atomic_json(path, original)
    with pytest.raises(ValueError, match='校验'):
        service.submit(sid)


def test_explicit_reuse_verifies_and_does_not_queue(study):
    service, plan, market = study
    sid = service.create(plan)['id']
    rid = service.submit(sid)['submitted'][0]['run_id']
    finish_queue(service, market)
    old_config = dict(service.backtests.repository.get(rid)['config'])
    old_config.pop('data_gap_policy')  # early runs predate this explicit default
    service.backtests.repository.patch(rid, config=old_config)
    plan['cases'][0]['reuse_run'] = rid
    plan['max_new_runs'] = 0
    plan['parent'] = sid
    second = service.create(plan)['id']
    assert service.submit(second)['submitted'] == []
    assert service.summary(second)['cases'] == {'completed': 1}
    folder = service.backtests.directory(rid)
    (folder / 'data.json').write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError, match='校验'):
        service.create(plan)


def test_invalid_evidence_and_answer_revision(study):
    service, plan, market = study
    sid = service.create(plan)['id']
    answer = dict(question='width', conclusion='未完成不算证据', evidence=['case:baseline'],
                  scope='测试', limitation='没有', decision='inconclusive')
    with pytest.raises(ValueError, match='不存在'):
        service.answer(sid, answer)
    service.submit(sid)
    finish_queue(service, market)
    service.answer(sid, answer)
    service.answer(sid, {**answer, 'conclusion': '修订后的结论'})
    assert len([e for e in service.events(sid) if e['kind'] == 'answer']) == 2
    assert service.summary(sid)['answers'][0]['conclusion'] == '修订后的结论'


def fake_run(identifier, n, profit, **config):
    return dict(id=identifier, status='completed', config=dict(parameters={'n': n}, symbol='ETH/USDT', **config),
                metadata=dict(data_hash='same', strategy_hash='same', environment='same'), report={'return_pct': profit})


def test_paired_comparison_rejects_confounders_and_deduplicates():
    a, b, c = fake_run('a', 10, 5), fake_run('b', 20, 10), fake_run('c', 20, 90, initial_cash=5000)
    assert compare_runs(a, b)['single_factor']
    assert not compare_runs(a, c)['single_factor']
    result = paired_effect([a, b, b, c], 'parameters.n')
    assert result['pairs'][0]['paired_comparisons'] == 1
    assert result['pairs'][0]['median_return_difference_percentage_points'] == 5
    b['metadata']['data_hash'] = 'corrected_dataset'
    assert not paired_effect([a, b], 'parameters.n')['pairs']


def test_breakdown_uses_saved_trades(study):
    service, plan, market = study
    sid = service.create(plan)['id']
    rid = service.submit(sid)['submitted'][0]['run_id']
    finish_queue(service, market)
    result = trade_breakdown(service.backtests, rid)
    assert result['trade_summary']['trades'] == 1
    assert result['groups']['exit_year']['2025']['trades'] == 1
    assert result['trade_summary']['profit'] == result['report']['profit']


def test_legacy_catalog_incremental_search_reports_invalid_json(tmp_path):
    root = tmp_path / 'old'
    root.mkdir()
    text = root / 'CONCLUSIONS.md'
    text.write_text('PAXG EMA89 1h 历史盈利，四年与六年不同。', encoding='utf-8')
    (root / 'plan.json').write_text('{"parameters":{"EMA":89},"trades":[{"profit":1234567}]}', encoding='utf-8')
    (root / 'broken.json').write_text('{', encoding='utf-8')
    catalog = ResearchCatalog(tmp_path / 'index.sqlite')
    assert len(catalog.refresh([root])['issues']) == 1
    assert catalog.search('PAXG EMA89 1h')['total'] == 1
    assert catalog.search('1234567')['total'] == 0
    assert catalog.refresh([root])['unchanged_files'] == 2
    text.write_text('PAXG EMA89 日线', encoding='utf-8')
    catalog.refresh([root])
    assert catalog.search('PAXG 1h')['total'] == 0


def test_cli_is_compact_and_plan_does_not_submit(study, monkeypatch, tmp_path):
    from scripts.research_cli import build_parser, execute as cli_execute
    service, plan, market = study
    monkeypatch.setattr('scripts.research_study_cli.build_database_runtime', lambda _: service.backtests.repository.database)
    monkeypatch.setattr('scripts.research_study_cli.ResearchStudyService', lambda _: service)
    monkeypatch.setattr(service.backtests.repository.database, 'dispose', lambda: None)
    path = tmp_path / 'plan.json'
    atomic_json(path, plan)
    args = build_parser().parse_args(['study', 'create', '--plan', str(path)])
    summary = asyncio.run(cli_execute(args))
    assert service.backtests.repository.list()['total'] == 0
    assert summary['unanswered']
    sid = summary['id']
    rid = service.submit(sid)['submitted'][0]['run_id']
    finish_queue(service, market)
    monkeypatch.setattr('scripts.local_backtest_cli.build_database_runtime', lambda _: service.backtests.repository.database)
    monkeypatch.setattr('scripts.local_backtest_cli.LocalBacktestService', lambda _: service.backtests)
    compact = asyncio.run(cli_execute(build_parser().parse_args(['backtest', 'result', rid])))
    full = asyncio.run(cli_execute(build_parser().parse_args(['backtest', 'result', rid, '--full'])))
    assert 'trades' not in compact and 'trades' in full
    assert compact['report'] == full['report']


def test_compact_matrix_expands_without_shared_parameter_mutation(study):
    _, plan, _ = study
    base = plan.pop('cases')[0]['command']
    design = {**plan, 'max_new_runs': 4, 'base': base,
              'axes': {'parameters.fast': [10, 12]},
              'periods': [dict(name='一', start='2024-01-01T00:00:00Z', end='2025-01-01T00:00:00Z', role='selection', previously_seen=True),
                          dict(name='二', start='2025-01-01T00:00:00Z', end='2026-01-01T00:00:00Z', role='test', previously_seen=True)]}
    result = parse_plan(design)
    assert [c.command.parameters['fast'] for c in result.cases] == [10, 10, 12, 12]
    assert [c.variant for c in result.cases] == ['v1', 'v1', 'v2', 'v2']
    with pytest.raises(ValueError, match='超过'):
        parse_plan({**design, 'max_new_runs': 3})


def test_snapshot_tampering_rejected_before_queue_and_answer(study):
    service, plan, market = study
    sid = service.create(plan)['id']
    case = service.plan(sid)['cases'][0]
    source = service.folder(sid) / 'sources' / f'{case["strategy_hash"]}.py'
    original = source.read_bytes()
    source.write_bytes(original + b'\n# altered')
    assert '校验' in service.submit(sid)['errors'][0]['error']
    assert service.backtests.repository.list()['total'] == 0
    source.write_bytes(original)
    rid = service.submit(sid)['submitted'][0]['run_id']
    finish_queue(service, market)
    (service.backtests.directory(rid) / 'result.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='结果快照'):
        service.verify_run(service.backtests.repository.get(rid))


def test_stop_cancels_own_queue_preserves_records_and_unanswered(study):
    service, plan, _ = study
    sid = service.create(plan)['id']
    rid = service.submit(sid)['submitted'][0]['run_id']
    summary = service.stop(sid, '没有继续研究的依据')
    assert summary['status'] == 'stopped'
    assert summary['unanswered']
    assert service.backtests.repository.get(rid)['status'] == 'cancelled'
    assert (service.backtests.directory(rid) / 'strategy.py').exists()
    assert service.backtests.repository.claim() is None


def test_cli_preview_stdout_contains_only_json(tmp_path, installed_database_runtime):
    import os
    import subprocess
    import sys
    from app.contracts.local_backtest import LocalBacktestCommand
    plan = payload(LocalBacktestCommand(strategy='ma_cross', start='2025-01-01T00:00:00Z', end='2025-01-02T00:00:00Z'))
    path = tmp_path / 'preview.json'
    atomic_json(path, plan)
    result = subprocess.run([sys.executable, '-m', 'scripts.research_cli', 'study', 'preview', '--plan', str(path)],
                            capture_output=True, text=True, encoding='utf-8', timeout=30,
                            env={**os.environ, 'DATABASE_URL': installed_database_runtime.database_url, 'PYTHONUTF8': '1'})
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output['ok'] and output['data']['new_runs'] == 1
    assert len(result.stdout.splitlines()) == 1
