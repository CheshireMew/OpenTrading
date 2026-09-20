"""Versioned research notebook over the existing backtest queue and snapshots.

No optimization, strategy generation, model calls, or alternate execution engine.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

from app.contracts.research_study import StudyAnswer, parse_plan
from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.market.constants import timeframe_to_milliseconds
from app.infra.research_files import atomic_json, encode, sha, file_hash, read_json, lock
from app.services.local_backtest_strategies import environment
from app.services.backtest_provenance import save_bundle, verify_bundle, compatible_environment
from config import settings


def now():
    return datetime.now(timezone.utc).isoformat()


def page(items, offset=0, limit=20):
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError('offset 应非负，limit 应在 1–200')
    return {'total': len(items), 'offset': offset, 'items': items[offset:offset + limit]}


def case_key(case):
    return sha(encode({'config': case['config'], 'strategy_hash': case.get('strategy_hash') or sha(case['source']),
                       'metadata': {k: case['metadata'].get(k) for k in
                                    ('environment', 'engine_code_hash', 'execution_bundle', 'data_hash', 'execution_data_hash', 'source')}}))


class ResearchStudyService:
    def __init__(self, backtests, root=None):
        self.backtests = backtests
        self.root = Path(root or settings.RUNTIME_ROOT_DIR / 'research_studies')

    def folder(self, identifier):
        if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('无效研究标识')
        folder = self.root / identifier
        if not (folder / 'manifest.json').is_file():
            raise ValueError(f'研究不存在或创建未完成：{identifier}')
        return folder

    def plan(self, identifier):
        folder = self.folder(identifier)
        manifest = read_json(folder / 'manifest.json')
        if file_hash(folder / 'plan.json') != manifest['plan_hash']:
            raise ValueError('研究计划校验失败；修改必须另建版本')
        return read_json(folder / 'plan.json')

    def events(self, identifier):
        return [read_json(p) for p in sorted((self.folder(identifier) / 'events').glob('*.json'))]

    def append(self, identifier, kind, **values):
        events = self.events(identifier)
        event = dict(revision=len(events) + 1, created_at=now(), kind=kind, **values)
        atomic_json(self.folder(identifier) / 'events' / f'{event["revision"]:06d}.json', event)
        return event

    def preview(self, payload):
        plan = parse_plan(payload)
        prepared, warnings = [], []
        if plan.parent:
            old = self.plan(plan.parent)
            if old['family'] != plan.family:
                warnings.append('策略家族已改变；这不是原策略的参数对照')
        for case in plan.cases:
            if case.reuse_run:
                run = self.backtests.repository.get(case.reuse_run)
                self.verify_run(run)
                # Reuse is explicit: the old frozen dataset, not today's cache.
                config = case.command.model_dump(mode='json')
                old_config = LocalBacktestCommand.model_validate(run['config']).model_dump(mode='json')
                config['parameters'] = {**old_config['parameters'], **config['parameters']}
                if config != old_config:
                    raise ValueError(f'{case.id} 的输入与复用回测不一致')
                source = (self.backtests.directory(run['id']) / 'strategy.py').read_bytes()
                metadata = run['metadata']
            else:
                config, source, metadata = self.backtests.prepare(case.command)
            step = timeframe_to_milliseconds(config['timeframe'])
            bars = int((case.command.end - case.command.start).total_seconds() * 1000 / step)
            prepared.append(dict(**case.model_dump(mode='json', exclude={'command'}),
                                 config=config, metadata=metadata, source=source,
                                 expected_trade_bars=bars,
                                 warmup_calendar_hours=metadata.get('warmup_bars', metadata['strategy']['warmup_bars']) * step / 3600000))
            if case.role in {'validation', 'test'} and case.previously_seen:
                warnings.append(f'{case.id} 的历史已经看过，只能称历史复核，不能称未见验证')
        counts = Counter(case_key(c) for c in prepared)
        if any(v > 1 for v in counts.values()):
            warnings.append('存在相同策略和输入；提交时会复用同一份结果')
        return plan, prepared, warnings

    def preview_summary(self, payload):
        plan, cases, warnings = self.preview(payload)
        return {'title': plan.title, 'cases': len(cases),
                'new_runs': len({case_key(c) for c in cases if not c['reuse_run']}),
                'reused_cases': sum(bool(c['reuse_run']) for c in cases),
                'warnings': warnings, 'data_check': '复用结果校验快照；新数据由项目回测工作进程在计算前检查，预览不下载行情',
                'periods': sorted({(c['config']['start'], c['config']['end'], c['role']) for c in cases}),
                'max_warmup_calendar_hours': max(c['warmup_calendar_hours'] for c in cases)}

    def create(self, payload):
        plan, cases, warnings = self.preview(payload)
        identifier = uuid4().hex
        folder = self.root / identifier
        folder.mkdir(parents=True, exist_ok=False)
        for case in cases:
            source = case.pop('source')
            case['strategy_hash'] = sha(source)
            path = folder / 'sources' / f'{case["strategy_hash"]}.py'
            path.parent.mkdir(exist_ok=True)
            if not path.exists():
                path.write_bytes(source)
            bundle = case['metadata'].get('execution_bundle')
            if bundle:
                origin = self.backtests.directory(case['reuse_run'])/'execution' if case['reuse_run'] else None
                save_bundle(folder/'sources'/bundle['hash'], bundle, origin)
            engine_hash = case['metadata'].get('engine_code_hash')
            if engine_hash:
                engine_path = (self.backtests.directory(case['reuse_run']) / 'engine.py') if case['reuse_run'] else (Path(__file__).parents[1] / 'domain/local_backtest.py')
                engine = engine_path.read_bytes()
                if sha(engine) != engine_hash:
                    raise ValueError('创建期间引擎已改变，请重新创建')
                engine_path = folder / 'sources' / f'{engine_hash}.engine.py'
                if not engine_path.exists():
                    engine_path.write_bytes(engine)
        value = {**plan.model_dump(mode='json', exclude={'cases'}), 'cases': cases, 'warnings': warnings}
        atomic_json(folder / 'plan.json', value)
        atomic_json(folder / 'manifest.json', {'id': identifier, 'created_at': now(),
                    'schema_version': 1, 'plan_hash': file_hash(folder / 'plan.json')})
        return self.summary(identifier)

    def state(self, identifier):
        attempts, answers, artifacts, selection = {}, {}, {}, None
        status = 'open'
        for event in self.events(identifier):
            if event['kind'] == 'submission':
                attempts[event['case']] = event['run_id']
            elif event['kind'] == 'answer':
                answers[event['answer']['question']] = event
            elif event['kind'] == 'artifact':
                artifacts[event['name']] = event
            elif event['kind'] == 'selection':
                selection = event
            elif event['kind'] == 'complete':
                status = 'completed'
            elif event['kind'] == 'stop':
                status = 'stopped'
        return attempts, answers, artifacts, selection, status

    def ensure_open(self, identifier):
        if self.state(identifier)[4] != 'open':
            raise ValueError('研究已结束；请用 parent 新建后续版本')

    def case_runs(self, identifier):
        attempts = self.state(identifier)[0]
        rows = []
        for case in self.plan(identifier)['cases']:
            rid = case['reuse_run'] or attempts.get(case['id'])
            try:
                run = self.backtests.repository.get(rid) if rid else None
            except ValueError:
                run = None  # submission journal committed; queue creation interrupted
            rows.append((case, rid, run))
        return rows

    def submit(self, identifier, retry=None):
        with lock(self.folder(identifier)):
            self.ensure_open(identifier)
            rows = self.case_runs(identifier)
            selected = self.state(identifier)[3]
            if retry and retry not in {c['id'] for c, _, _ in rows}:
                raise ValueError('重试的 case 不存在')
            submitted, skipped, errors, shared = [], [], [], {}
            for case, rid, run in rows:
                key = case_key(case)
                if retry and case['id'] != retry:
                    continue
                if retry and (case['reuse_run'] or not run or run['status'] not in {'failed', 'cancelled', 'interrupted'}):
                    raise ValueError('只能重试失败、取消或中断的本研究回测')
                if not retry and run:
                    skipped.append(case['id'])
                    shared[key] = rid
                    continue
                if case['role'] in {'validation', 'test'}:
                    if not selected or case['variant'] not in selected['variants']:
                        skipped.append(case['id'])
                        continue
                try:
                    bundle = case['metadata'].get('execution_bundle')
                    resumable = bool(retry and (self.backtests.directory(run['id'])/'computed.json').exists())
                    if not resumable and not (compatible_environment(case['metadata']['environment'], environment()) if bundle else case['metadata']['environment'] == environment()):
                        raise ValueError('引擎环境已改变，请另建版本')
                    source = (self.folder(identifier) / 'sources' / f'{case["strategy_hash"]}.py').read_bytes()
                    if sha(source) != case['strategy_hash']:
                        raise ValueError('策略快照校验失败')
                    if not rid or retry:
                        revision = len(self.events(identifier)) + 1
                        rid = shared.get(key) if not retry else None
                        rid = rid or sha(f'{identifier}:{case["id"]}:{revision}'.encode())[:32]
                        self.append(identifier, 'submission', case=case['id'], run_id=rid,
                                    previous_run=run['id'] if retry else None)
                    if resumable:
                        queued = self.backtests.resume(run['id'], new_identifier=rid)
                        submitted.append({'case': case['id'], 'run_id': queued['id'], 'status': queued['status']})
                        shared[key] = rid
                        continue
                    data, metadata = None, case['metadata']
                    if retry:
                        previous_folder = self.backtests.directory(run['id'])
                        previous_metadata = read_json(previous_folder / 'metadata.json')
                        if previous_metadata.get('data_hash'):
                            data = self.backtests.data_path(run['id'])
                            if file_hash(data) != previous_metadata['data_hash']:
                                raise ValueError('上次数据快照损坏，不能继续重试')
                            metadata = previous_metadata
                    queued = self.backtests._create(case['config'], source, metadata,
                                                   parent_id=run['id'] if data is not None else None,
                                                   data=data, identifier=rid,
                                                   execution_source=self.folder(identifier)/'sources'/bundle['hash'] if bundle else None)
                    submitted.append({'case': case['id'], 'run_id': queued['id'], 'status': queued['status']})
                    shared[key] = rid
                except (ValueError, OSError) as exc:
                    errors.append({'case': case['id'], 'error': str(exc)})
            return {'submitted': submitted, 'skipped': skipped, 'errors': errors,
                    'execution': '由现有后台回测队列执行；status 查询进度，无需轮询整个结果'}

    def select(self, identifier, variants, rationale):
        with lock(self.folder(identifier)):
            self.ensure_open(identifier)
            if self.state(identifier)[3]:
                raise ValueError('选择已经锁定；改变选择必须另建研究')
            if not variants or not rationale.strip():
                raise ValueError('必须说明选择的版本和原因')
            rows = self.case_runs(identifier)
            available = {c['variant'] for c, _, _ in rows}
            if not set(variants) <= available:
                raise ValueError('未知版本')
            evidence = []
            for case, _, run in rows:
                if case['role'] in {'selection', 'exploration'}:
                    if not run or run['status'] != 'completed':
                        raise ValueError('先完成所有探索／选择案例，不能跳过失败结果只挑冠军')
                    evidence.append(self.verify_run(run))
                elif run and not case['previously_seen']:
                    raise ValueError('未见验证结果已关联，不能声称在查看前锁定；请修正 previously_seen 后新建研究')
            self.append(identifier, 'selection', variants=sorted(set(variants)), rationale=rationale,
                        evidence=evidence)
            return {'variants': variants, 'locked': True,
                    'note': '此后仅提交这些版本的验证／测试；历史是否看过仍以计划申明为准'}

    def verify_run(self, run):
        if run['status'] != 'completed':
            raise ValueError(f'回测未完成：{run["id"]} ({run["status"]})')
        folder = self.backtests.directory(run['id'])
        metadata = run['metadata']
        hashes = {}
        if metadata.get('execution_bundle'):
            verify_bundle(folder/'execution', metadata['execution_bundle'])
            hashes['execution_bundle_hash'] = metadata['execution_bundle']['hash']
        for filename, key in [('strategy.py', 'strategy_hash'), ('data.json', 'data_hash')]:
            path = self.backtests.data_path(run['id']) if filename == 'data.json' else folder/filename
            if not path.exists() or file_hash(path) != metadata.get(key):
                raise ValueError(f'{run["id"]} 的 {filename} 快照校验失败')
            hashes[key] = metadata[key]
        if run['config'].get('execution_timeframe'):
            if file_hash(self.backtests.data_path(run['id'], 'execution_data.json'))!=metadata.get('execution_data_hash'):
                raise ValueError('细周期行情快照校验失败')
            hashes['execution_data_hash']=metadata['execution_data_hash']
            if metadata.get('execution_alignment_hash'):
                if file_hash(folder/'execution_alignment.json') != metadata['execution_alignment_hash']:
                    raise ValueError('细周期对齐快照校验失败')
                hashes['execution_alignment_hash'] = metadata['execution_alignment_hash']
        hashes['result_hash'] = self.backtests.verify_result(run)
        return {'run_id': run['id'], **hashes, 'report': run['report'], 'path': str(folder.resolve())}

    def attach(self, identifier, name, path, description):
        with lock(self.folder(identifier)):
            self.ensure_open(identifier)
            if not name.strip() or name in self.state(identifier)[2]:
                raise ValueError('证据名称为空或已经存在，请为新版本另取名称')
            path = Path(path).resolve(strict=True)
            digest = file_hash(path)
            destination = self.folder(identifier) / 'artifacts' / digest
            destination.parent.mkdir(exist_ok=True)
            if not destination.exists():
                shutil.copyfile(path, destination)
            if file_hash(destination) != digest:
                raise ValueError('证据复制校验失败')
            return self.append(identifier, 'artifact', name=name, source=str(path),
                               sha256=digest, bytes=destination.stat().st_size, description=description)

    def answer(self, identifier, payload):
        answer = StudyAnswer.model_validate(payload)
        with lock(self.folder(identifier)):
            self.ensure_open(identifier)
            if answer.question not in {q['id'] for q in self.plan(identifier)['questions']}:
                raise ValueError('问题不在计划内')
            artifacts = self.state(identifier)[2]
            runs = {c['id']: run for c, _, run in self.case_runs(identifier)}
            evidence = []
            for ref in answer.evidence:
                kind, _, name = ref.partition(':')
                if kind == 'case' and runs.get(name):
                    evidence.append({'reference': ref, **self.verify_run(runs[name])})
                elif kind == 'artifact' and name in artifacts:
                    item = artifacts[name]
                    if file_hash(self.folder(identifier) / 'artifacts' / item['sha256']) != item['sha256']:
                        raise ValueError('证据快照已改变')
                    evidence.append({'reference': ref, 'sha256': item['sha256']})
                else:
                    raise ValueError(f'证据不存在：{ref}；请使用 case:<id> 或 artifact:<name>')
            self.append(identifier, 'answer', answer=answer.model_dump(), evidence=evidence)
        return self.summary(identifier)

    def summary(self, identifier):
        plan = self.plan(identifier)
        attempts, answers, artifacts, selection, status = self.state(identifier)
        counts = Counter(run['status'] if run else 'not_submitted' for _, _, run in self.case_runs(identifier))
        return {'id': identifier, 'title': plan['title'], 'family': plan['family'], 'parent': plan['parent'],
                'status': status, 'objective': plan['objective'], 'decision_rule': plan['decision_rule'],
                'cases': dict(counts), 'warnings': plan['warnings'],
                'answers': [{**answers[q['id']]['answer'], 'question_text': q['text']} for q in plan['questions'] if q['id'] in answers],
                'unanswered': [q for q in plan['questions'] if q['id'] not in answers],
                'selection': selection and selection['variants'], 'artifacts': len(artifacts),
                'path': str(self.folder(identifier).resolve())}

    def results(self, identifier, offset=0, limit=20, symbol=None, timeframe=None, role=None):
        items = []
        for case, rid, run in self.case_runs(identifier):
            config = case['config']
            if symbol and config['symbol'] != symbol or timeframe and config['timeframe'] != timeframe or role and case['role'] != role:
                continue
            items.append({'case': case['id'], 'name': case['name'], 'variant': case['variant'],
                          'period': case['period'], 'role': case['role'], 'previously_seen': case['previously_seen'],
                          'config': config, 'run_id': rid, 'status': run['status'] if run else 'not_submitted',
                          'report': run and run['report'], 'error': run and run['error'],
                          'chart_path': f'/research/backtests?run={rid}&view=chart' if run else None})
        return page(items, offset, limit)

    def complete(self, identifier):
        with lock(self.folder(identifier)):
            self.ensure_open(identifier)
            summary = self.summary(identifier)
            if summary['unanswered']:
                raise ValueError('还有问题未回答；收益排行榜不能代替问题结论')
            for case, _, run in self.case_runs(identifier):
                selected = summary['selection']
                excluded = case['role'] in {'test', 'validation'} and selected and case['variant'] not in selected
                if not excluded and (not run or run['status'] != 'completed'):
                    raise ValueError(f'{case["id"]} 尚未完成')
                if run:
                    self.verify_run(run)
            for item in self.state(identifier)[2].values():
                if file_hash(self.folder(identifier) / 'artifacts' / item['sha256']) != item['sha256']:
                    raise ValueError('证据快照校验失败')
            for answer in self.state(identifier)[1].values():
                for evidence in answer['evidence']:
                    if evidence.get('run_id'):
                        current = self.verify_run(self.backtests.repository.get(evidence['run_id']))
                        if any(current.get(k) != evidence.get(k) for k in ('strategy_hash', 'data_hash', 'result_hash', 'report')):
                            raise ValueError('回答所引用的结果已经改变，请重新核对')
            self.append(identifier, 'complete')
        return self.summary(identifier)

    def stop(self, identifier, reason):
        with lock(self.folder(identifier)):
            self.ensure_open(identifier)
            if not reason.strip():
                raise ValueError('请说明停止原因')
            cancelled = []
            for case, rid, run in self.case_runs(identifier):
                if not case['reuse_run'] and run and run['status'] in {'queued', 'preparing', 'running', 'saving'}:
                    self.backtests.cancel(rid)
                    cancelled.append(rid)
            self.append(identifier, 'stop', reason=reason, cancelled=sorted(set(cancelled)))
        return self.summary(identifier)

    def listing(self, query='', offset=0, limit=20):
        items = []
        for path in sorted(self.root.glob('*/manifest.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            summary = self.summary(path.parent.name)
            if query.casefold() in encode(summary).decode().casefold():
                items.append(summary)
        return page(items, offset, limit)
