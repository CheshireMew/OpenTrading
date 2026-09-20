"""Durable parameter batches built on the existing study journal and run queue."""
import csv
import io
from collections import Counter
from copy import deepcopy
from app.contracts.parameter_sweep import ParameterSweepCommand
from app.contracts.local_backtest import LocalBacktestCommand
from app.infra.research_files import atomic_json, read_json, sha, encode, file_hash, lock
from app.services.local_backtest_service import LocalBacktestService
from app.services.research_study_service import ResearchStudyService, case_key
from app.services.research_comparison import paired_effect
from app.services.backtest_provenance import execution_summary


class SweepBacktests(LocalBacktestService):
    def __init__(self, existing, seed=None, batch=None):
        super().__init__(existing.repository.database, existing.root)
        self.seed = seed
        self.batch = batch
        self.prepared = {}

    def _create(self, config, source, metadata, *args, **kwargs):
        if self.batch:
            metadata = {**metadata, 'parameter_sweep_id': self.batch}
        return super()._create(config, source, metadata, *args, **kwargs)

    def prepare(self, command):
        key = encode(command.model_dump(mode='json'))
        if key not in self.prepared:
            self.prepared[key] = self._prepare(command)
        return deepcopy(self.prepared[key])

    def _prepare(self, command):
        cfg, source, meta = super().prepare(command)
        key = {k:cfg.get(k) for k in ('symbol','timeframe','start','end','execution_timeframe','data_gap_policy')}
        key.update(source=meta['source'], warmup=meta.get('warmup_bars', meta['strategy']['warmup_bars']))
        if self.seed:
            original, original_meta = self.seed['config'], self.seed['metadata']
            matches = all(cfg.get(k)==original.get(k) for k in ('symbol','timeframe','start','end','execution_timeframe','data_gap_policy'))
            if matches and meta['source']==original_meta['source'] and meta.get('warmup_bars', meta['strategy']['warmup_bars'])==original_meta.get('warmup_bars', original_meta['strategy']['warmup_bars']):
                meta['batch_seed_run'] = self.seed['id']
                key['seed_data_hash'] = original_meta['data_hash']
                key['seed_execution_hash'] = original_meta.get('execution_data_hash')
        # Shared only inside a batch; a future batch without explicit source_run
        # must be free to obtain corrected source data.
        meta['batch_snapshot_group'] = sha(encode(key))
        return cfg, source, meta


class ParameterSweepService:
    def __init__(self, backtests, root=None):
        self.backtests = backtests
        self.studies = ResearchStudyService(backtests, root)

    def _prepare(self, payload):
        request = ParameterSweepCommand.model_validate(payload)
        axes, commands = request.expand()
        seed = None
        if request.source_run:
            seed = self.backtests.repository.get(request.source_run)
            self.studies.verify_run(seed)
        service = ResearchStudyService(SweepBacktests(self.backtests, seed), self.studies.root)
        # Equal history within each source/timeframe group lets parameter effects
        # remain attributable even when individual EMA lengths need more warmup.
        groups = {}
        for cmd in commands:
            cfg, _, meta = service.backtests.prepare(cmd)
            key = tuple(cfg.get(k) for k in ('symbol', 'timeframe', 'start', 'end', 'execution_timeframe', 'data_gap_policy'))
            groups[key] = max(groups.get(key, 0), meta['warmup_bars'])
        for cfg, _, meta in service.backtests.prepared.values():
            key = tuple(cfg.get(k) for k in ('symbol', 'timeframe', 'start', 'end', 'execution_timeframe', 'data_gap_policy'))
            required = meta['warmup_bars']
            common = groups[key]
            meta['parameter_warmup_bars'] = required
            meta['warmup_bars'] = common
            meta['execution_recipe']['warmup_bars'] = common
            meta['warmup_explanation'] += f' 同源同周期组合统一使用本批最大值 {common} 根，本组单独需要 {required} 根。'
            if common != required:
                meta.pop('batch_seed_run', None)
            group = dict(source=meta['source'], warmup=common, **dict(zip(('symbol', 'timeframe', 'start', 'end', 'execution_timeframe', 'data_gap_policy'), key)))
            if meta.get('batch_seed_run'):
                group.update(seed_data_hash=seed['metadata']['data_hash'], seed_execution_hash=seed['metadata'].get('execution_data_hash'))
            meta['batch_snapshot_group'] = sha(encode(group))
        for prepared in list(service.backtests.prepared.values()):
            normalized = LocalBacktestCommand.model_validate(prepared[0]).model_dump(mode='json')
            service.backtests.prepared[encode(normalized)] = prepared
        cases = []
        for index, cmd in enumerate(commands):
            cfg, source, meta = service.backtests.prepare(cmd)
            label = ', '.join(f'{key.removeprefix("parameters.")}={cfg["parameters"].get(key.removeprefix("parameters.")) if key.startswith("parameters.") else cfg.get(key, False if key == "intrabar_profit_protection" else None)}' for key in axes) or '固定参数'
            case = dict(id=f'v{index+1}', name=label, variant=f'v{index+1}', period='全期', role='exploration',
                previously_seen=True, command=cfg)
            if seed and LocalBacktestCommand.model_validate(cfg)==LocalBacktestCommand.model_validate(seed['config']) and sha(source)==seed['metadata']['strategy_hash'] and all(meta.get(k)==seed['metadata'].get(k) for k in ('environment','execution_bundle','engine_code_hash','source','warmup_bars')):
                case['reuse_run'] = seed['id']
            cases.append(case)
        plan = dict(title=request.title, family='parameter_sweep', objective='比较指定范围内各参数组合的历史表现',
            decision_rule='按历史收益排序，同时保留失败、零交易、胜负次数及回撤；排名不代表未来最佳。',
            stop_rule='只计算用户提供的组合，不自动扩大范围。', change_reason='用户创建参数批量比较',
            parent=request.parent, questions=[dict(id='ranking',text='这些组合的历史表现如何？')],
            max_new_runs=request.max_runs, cases=cases)
        return request, axes, plan, service

    def preview(self, payload):
        request, axes, plan, service = self._prepare(payload)
        _, cases, warnings = service.preview(plan)
        first = cases[0]['config']['parameters']
        from app.services.backtest_preflight import preview_prepared, intersect_intervals
        cache, previews = {}, []
        common = None
        for case in cases:
            item = preview_prepared(self.backtests.repository.database, case['config'], case['metadata'], cache)
            item['case'] = case['id']
            previews.append(item)
            common = item['comparable_intervals'] if common is None else intersect_intervals(common, item['comparable_intervals'])
        return dict(count=len(plan['cases']), new_runs=len({case_key(c) for c in cases if not c['reuse_run']}), reused_runs=sum(bool(c['reuse_run']) for c in cases), axes=axes,
            fixed_parameters={k:v for k,v in first.items() if f'parameters.{k}' not in axes},
            data_previews=previews, comparable_intervals=common or [],
            warnings=warnings+['按指定历史区间比较；结果不代表未见行情中的最佳参数。'])

    def create(self, payload):
        request, axes, plan, service = self._prepare(payload)
        created = service.create(plan)
        folder = service.folder(created['id'])
        value = dict(request=request.model_dump(mode='json'), axes=axes)
        atomic_json(folder/'sweep.json',value)
        atomic_json(folder/'sweep-manifest.json',dict(hash=file_hash(folder/'sweep.json')))
        # Publication precedes submission; resume safely repairs partial queueing.
        self.resume(created['id'])
        return self.get(created['id'])

    def definition(self, identifier):
        folder = self.studies.folder(identifier)
        if not (folder/'sweep-manifest.json').exists():
            raise ValueError('这不是批量参数比较记录')
        if file_hash(folder/'sweep.json')!=read_json(folder/'sweep-manifest.json')['hash']:
            raise ValueError('批量参数快照被改变；请另建版本')
        return read_json(folder/'sweep.json')

    def resume(self, identifier):
        self.definition(identifier)
        rows = self.studies.case_runs(identifier)
        # Frozen metadata is copied into queue records, while the immutable plan
        # itself remains unchanged. The batch ID scopes the shared dataset.
        study = ResearchStudyService(SweepBacktests(self.backtests, batch=identifier), self.studies.root)
        errors = study.submit(identifier)['errors']
        for case, _, run in rows:
            if not case['reuse_run'] and run and run['status'] in {'failed','cancelled','interrupted'}:
                errors.extend(study.submit(identifier, retry=case['id'])['errors'])
        with lock(study.folder(identifier)):
            study.append(identifier, 'batch_submission', errors=errors)
        return self.get(identifier)

    def cancel(self, identifier):
        self.definition(identifier)
        with lock(self.studies.folder(identifier)):
            for case, rid, run in self.studies.case_runs(identifier):
                if not case['reuse_run'] and run and run['status'] in {'queued','preparing','running','saving'}:
                    self.backtests.cancel(rid)
            self.studies.append(identifier,'batch_cancel')
        return self.get(identifier)

    def get(self, identifier, offset=0, limit=30, sort='return_pct', descending=True, minimum_trades=0):
        if sort not in {'return_pct','win_rate','max_drawdown_pct','total_trades'}:
            raise ValueError('不支持的排序字段')
        if offset<0 or not 1<=limit<=512 or minimum_trades<0:
            raise ValueError('分页或最低交易笔数无效')
        definition = self.definition(identifier)
        errors = {}
        for event in self.studies.events(identifier):
            if event['kind']=='batch_submission':
                errors = {e['case']:e['error'] for e in event['errors']}
        items=[]
        saved_strategy = None
        for case,rid,run in self.studies.case_runs(identifier):
            if saved_strategy is None:
                saved_strategy = case['metadata'].get('strategy')
            items.append(dict(case=case['id'],name=case['name'],parameters=case['config']['parameters'],timeframe=case['config']['timeframe'],
                run_id=rid,status=run['status'] if run else 'not_submitted',progress=run['progress'] if run else 0.,
                report=run and run['report'],error=(run and run['error']) or errors.get(case['id']),chart_path=f'/research/backtests?run={rid}&view=chart' if run else None))
            items[-1]['execution_summary'] = execution_summary(run) if run else {}
            items[-1]['config'] = case['config']
        counts=dict(Counter(i['status'] for i in items))
        state='completed' if counts.get('completed',0)==len(items) else 'running' if any(counts.get(s) for s in ('queued','preparing','running','saving')) else 'attention'
        selected=[i for i in items if not minimum_trades or i['report'] and i['report'].get('total_trades',0)>=minimum_trades]
        def order(i):
            value=i['report'].get(sort) if i['report'] else None
            return (value is None, (-value if descending else value) if value is not None else 0, i['case'])
        selected.sort(key=order)
        folder=self.studies.folder(identifier)
        warnings=['所有组合均完整留存；排序只描述这段历史。']
        if state=='attention':warnings.append('存在未提交、失败、中断或取消的项目；恢复只处理这些项目。')
        if state=='completed':
            # Save a compact local table once per attempt set, without reopening
            # gigabytes of trade traces on every status poll.
            h=sha(encode([(i['run_id'],i['status']) for i in items]))
            path=folder/'rankings'/f'{h}.json'
            if not path.exists():atomic_json(path,dict(items=sorted(items,key=lambda i:(-(i['report'].get('return_pct') or 0),i['case']))))
        return dict(id=identifier,title=definition['request']['title'],created_at=read_json(folder/'manifest.json')['created_at'],
            status=state,total=len(items),counts=counts,progress=sum(1 if i['status']=='completed' else i['progress'] for i in items)/len(items),
            request=definition['request'],axes=definition['axes'],warnings=warnings,path=str(folder.resolve()),
            items=selected[offset:offset+limit],offset=offset,filtered_total=len(selected),strategy=saved_strategy)

    def listing(self, offset=0, limit=20):
        if offset<0 or not 1<=limit<=100:raise ValueError('分页范围无效')
        paths=sorted(self.studies.root.glob('*/sweep-manifest.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        items=[]
        for path in paths[offset:offset+limit]:
            v=self.get(path.parent.name,limit=1)
            items.append({k:v[k] for k in ('id','title','created_at','status','total','counts','progress')})
        return dict(items=items,total=len(paths))

    def effects(self, identifier):
        definition=self.definition(identifier)
        runs=[run for _,_,run in self.studies.case_runs(identifier) if run and run['status']=='completed']
        return dict(effects=[paired_effect(runs,factor) for factor in definition['axes']])

    def export(self, identifier):
        result=self.get(identifier,limit=512)
        out=io.StringIO(newline='');writer=csv.writer(out)
        axes=list(result['axes']);writer.writerow(['组合','状态','run_id',*axes,'收益率%','胜率%','盈利笔数','亏损笔数','总笔数','最大回撤%','错误'])
        for i in result['items']:
            r=i['report'] or {}
            writer.writerow([i['name'],i['status'],i['run_id'],*[i['parameters'].get(k.removeprefix('parameters.')) if k.startswith('parameters.') else i['config'].get(k, False if k == 'intrabar_profit_protection' else None) for k in axes],
                *[r.get(k) for k in ('return_pct','win_rate','wins','losses','total_trades','max_drawdown_pct')],i['error']])
        return dict(filename=f'{identifier}-parameters.csv',content='\ufeff'+out.getvalue(),media_type='text/csv')
