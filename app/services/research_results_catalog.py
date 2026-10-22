"""Derived result directory. Never executes strategies or rewrites source evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import re

from app.infra.research_files import file_hash, relocated_project_path
from app.services.backtest_provenance import evidence_status, execution_summary
from app.services.research_strategy_families import strategy_family
from config.settings import BASE_DIR

IMPORT_VERSION = '3'

CONFIG_KEYS = ('strategy', 'symbol', 'timeframe', 'start', 'end', 'initial_cash', 'position_pct',
               'execution_timeframe', 'intrabar_profit_protection', 'data_gap_policy', 'execution_gap_policy')
EVIDENCE_KEYS = ('source', 'environment', 'strategy_hash', 'data_hash', 'execution_data_hash',
                 'execution_alignment_hash', 'execution_bundle', 'warmup_bars')
METRICS = ('return_pct', 'win_rate', 'max_drawdown_pct', 'total_trades')
RAW_KEYS = {'trades', 'candles', 'bars', 'equity', 'signals', 'fills', 'levels', 'indicators', 'events',
            'execution_equity', 'daily_equity', 'equity_curve', 'curve', 'sampled_equity'}
NOTE = '历史排序只回答已登记记录的数值高低；同条件排序还要求区间、行情、策略代码、引擎、仓位及执行规则一致。参数可以不同，不自动构成单因素结论。'


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def identity(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def compact(value):
    """Reports may contain raw arrays. The catalog stores only their scalar summary."""
    return {k: v for k, v in value.items() if isinstance(v, (str, int, float, bool)) or v is None}


def date_key(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000, timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return str(value)


def normalized_config(config, *, native=False):
    result = {k: config[k] for k in CONFIG_KEYS if k in config}
    result['parameters'] = config.get('parameters', {})
    for k in ('start', 'end'):
        if k in result:
            result[k] = date_key(result[k])
    if native:
        for k, v in dict(execution_timeframe=None, intrabar_profit_protection=False,
                         data_gap_policy='reject', execution_gap_policy='coarse_fallback').items():
            result.setdefault(k, v)
    return result


def make_entry(identifier, config, report, metadata, source_type, label, *, run_id=None, archived=False, family=None):
    has_parameters = 'parameters' in config
    config = normalized_config(config, native=source_type == 'native')
    summary = execution_summary({'config': config, 'metadata': metadata})
    if source_type != 'native':
        if 'execution_gap_policy' not in config:
            summary['execution_gap_policy'] = None
        if 'execution_timeframe' not in config:
            summary['execution_timeframe'] = None
        if 'intrabar_profit_protection' not in config:
            summary['protection_timeframe'] = None
    metadata = {k: metadata[k] for k in EVIDENCE_KEYS if k in metadata}
    missing = [f'config.{k}' for k in CONFIG_KEYS if k not in config or (config[k] is None and k != 'execution_timeframe')]
    if not has_parameters:
        missing.append('config.parameters')
    evidence = evidence_status({'config': config, 'metadata': metadata})
    missing += [f'metadata.{k}' for k in evidence['missing']]
    cohort = None if missing else identity({'config': {k: v for k, v in config.items() if k != 'parameters'}, 'metadata': metadata})
    return dict(id=identifier, run_id=run_id, source_type=source_type, label=label, family=family or strategy_family(config.get('strategy')),
                archived=archived, config=config, report=compact(report), metadata=metadata,
                missing=missing, cohort=cohort, execution_summary=summary,
                sources=[])


def pointer_token(key):
    return str(key).replace('~', '~0').replace('/', '~1')


def legacy_identity(item, source):
    artifact = item.get('artifact')
    if artifact:
        path = Path(artifact['path'])
        absolute = (path if path.is_absolute() else BASE_DIR/path).resolve()
        return 'legacy:' + identity([str(absolute), artifact['sha256']])[:24]
    return 'legacy:' + identity([source, item['pointer']])[:24]


def legacy_metadata(owner, base=None):
    metadata = {**(base or {}), **owner.get('metadata', {})}
    detail = owner.get('execution_detail', {})
    if isinstance(detail, dict):
        for source, target in [('detailed_candles', 'execution_matched_candles'), ('fallback_candles', 'execution_fallback_candles')]:
            if source in detail:
                metadata[target] = detail[source]
    return metadata


def legacy_entries(document):
    """Accept explicit report objects and declared plan matrices, not arbitrary metrics.

    Context follows ancestors and named plan variants. Siblings never contribute
    parameters to each other. Unknown fields stay absent instead of using defaults.
    """
    if not isinstance(document, dict):
        return
    plan = document.get('plan', {})
    if not isinstance(plan, dict):
        plan = {}
    base = {k: plan[k] for k in CONFIG_KEYS if k in plan}
    provenance = document.get('provenance', {})
    if not isinstance(provenance, dict):
        provenance = {}
    base_meta = {k: provenance[k] for k in EVIDENCE_KEYS if k in provenance}
    for key in ('data_hash', 'warmup_bars'):
        if key in plan:
            base_meta[key] = plan[key]
    # Only explicit family declarations; a filename or parameter shape is not proof.
    family = plan.get('family') or document.get('family')
    variants, periods = plan.get('variants', {}), plan.get('periods', {})
    def report(value):
        return isinstance(value, dict) and all(k in value for k in ('return_pct', 'total_trades', 'initial_cash', 'final_equity'))
    def walk(node, pointer='', config=None, metadata=None, label=None):
        if isinstance(node, list):
            for i, child in enumerate(node):
                if isinstance(child, (dict, list)):
                    yield from walk(child, f'{pointer}/{i}', config, metadata, label)
            return
        if not isinstance(node, dict):
            return
        if 'entry_time' in node or ('timestamp' in node and ('equity' in node or 'open' in node)):
            return
        own_config = {**(config or base), **{k: node[k] for k in CONFIG_KEYS if k in node}}
        if isinstance(node.get('config'), dict):
            own_config.update(node['config'])
        if isinstance(node.get('parameters'), dict):
            own_config['parameters'] = node['parameters']
        own_meta = {**(metadata or base_meta), **{k: node[k] for k in EVIDENCE_KEYS if k in node}}
        own_meta = legacy_metadata(node, own_meta)
        own_label = node.get('name') or label or pointer or '旧研究结果'
        if report(node.get('report')):
            run_id = node.get('run_id') or (node.get('run') if isinstance(node.get('run'), str) else None)
            if isinstance(node.get('run'), dict):
                saved = node['run']
                run_id = saved.get('id')
                own_config = {**saved.get('config', {}), **own_config}
                own_meta = {**saved.get('metadata', {}), **own_meta}
            artifact_path = node.get('path') or node.get('trace_path')
            artifact_hash = node.get('sha256') or node.get('trace_hash')
            artifact = {'path': artifact_path, 'sha256': artifact_hash} if isinstance(artifact_path, str) and isinstance(artifact_hash, str) and re.fullmatch('[a-f0-9]{64}', artifact_hash) else None
            yield dict(pointer=pointer or '/', config=own_config, report=node['report'], metadata=own_meta,
                       label=own_label, run_id=run_id, family=node.get('family') or family, artifact=artifact)
            return
        # Only a period declared by the plan can turn a bare metrics object into a run.
        if report(node):
            tokens = pointer.split('/')
            if len(tokens) == 4 and tokens[1] == 'results' and tokens[2] in variants and tokens[3] in periods:
                variant, period = variants[tokens[2]], periods[tokens[3]]
                if isinstance(variant, dict) and isinstance(period, list) and len(period) == 2:
                    own_config.update(start=period[0], end=period[1], parameters=variant.get('parameters', {}))
                    yield dict(pointer=pointer, config=own_config, report=node, metadata=own_meta,
                               label=f"{variant.get('name', tokens[2])} · {tokens[3]}", run_id=None, family=family)
            return
        for key, child in node.items():
            # Derived diagnostics and counterfactual results are not independent backtests.
            if key in RAW_KEYS or key in {'plan', 'metadata', 'provenance', 'parameters', 'config', 'winner_only',
                                          'winners_only', 'counterfactual', 'annual', 'monthly', 'breakdown', 'comparison'}:
                continue
            if isinstance(child, (dict, list)):
                yield from walk(child, f'{pointer}/{pointer_token(key)}', own_config, own_meta, own_label)
    yield from walk(document)


class ResearchResultsCatalog:
    def __init__(self, backtests):
        self.backtests = backtests
        self.path = backtests.root.parent / 'research_results.sqlite'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS results (
                id TEXT PRIMARY KEY, source_type TEXT, symbol TEXT, strategy TEXT, family TEXT,
                timeframe TEXT, cohort TEXT, archived INTEGER, payload TEXT);
                CREATE INDEX IF NOT EXISTS result_scope ON results(symbol,strategy,timeframe);
                CREATE INDEX IF NOT EXISTS result_cohort ON results(cohort);
                CREATE TABLE IF NOT EXISTS sources (path TEXT, pointer TEXT, result_id TEXT, sha256 TEXT,
                    PRIMARY KEY(path,pointer));
                CREATE TABLE IF NOT EXISTS imports (path TEXT PRIMARY KEY, sha256 TEXT, entries INTEGER, issue TEXT);''')
            db.execute('CREATE TABLE IF NOT EXISTS catalog_meta (key TEXT PRIMARY KEY, value TEXT)')
            version = db.execute("SELECT value FROM catalog_meta WHERE key='import_version'").fetchone()
            if not version or version[0] != IMPORT_VERSION:
                db.execute("UPDATE imports SET issue='导入规则更新，待重新读取'")
                db.execute("INSERT OR REPLACE INTO catalog_meta VALUES ('import_version',?)", (IMPORT_VERSION,))

    def connection(self):
        return sqlite3.connect(self.path, timeout=30)

    @staticmethod
    def _put(db, entry):
        c = entry['config']
        db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?,?,?)',
                   (entry['id'], entry['source_type'], c.get('symbol'), c.get('strategy'), entry.get('family'),
                    c.get('timeframe'), entry['cohort'], int(entry['archived']), encode(entry)))

    def register(self, run, db=None):
        if run['status'] != 'completed' or not run.get('report'):
            return False
        metadata = run.get('metadata', {})
        strategy = metadata.get('strategy', {})
        study = metadata.get('study', {})
        entry = make_entry('run:' + run['id'], run['config'], run['report'], metadata, 'native',
                           run.get('name') or strategy.get('name') or run['config'].get('strategy') or run['id'],
                           run_id=run['id'], archived=run.get('archived', False),
                           family=strategy.get('family') or study.get('family'))
        if db is None:
            with self.connection() as conn:
                self._put(conn, entry)
        else:
            self._put(db, entry)
        return True

    def sync_native(self):
        """Reconcile lightweight DB summaries, including old completions and archives."""
        count = 0
        with self.connection() as db:
            for archived in (False, True):
                offset = 0
                while True:
                    page = self.backtests.repository.list(offset, 200, archived)
                    for run in page['items']:
                        count += int(self.register(run, db))
                        if run['status'] != 'completed':
                            db.execute('DELETE FROM results WHERE id=?', ('run:' + run['id'],))
                    offset += len(page['items'])
                    if offset >= page['total'] or not page['items']:
                        break
        return count

    def refresh(self, roots, max_json_bytes=32 * 1024 * 1024):
        native = self.sync_native()
        scanned = imported = unchanged = 0
        issues = []
        manifests = []
        # Withdraw declarations before scanning. A removed/invalid/empty map
        # must not keep its old enrichment through another source reference.
        with self.connection() as db:
            old_maps = [r[0] for r in db.execute("SELECT DISTINCT s.path FROM sources s JOIN results r ON r.id=s.result_id WHERE s.pointer LIKE '/entries/%' AND r.source_type='legacy' AND r.payload LIKE '%\"context_note\"%'")]
        for name in old_maps:
            self.reset_manifest(relocated_project_path(name), max_json_bytes)
            if not relocated_project_path(name).is_file():
                issues.append(dict(path=name, issue='来源映射已不可读，已撤回其声明；原报告仍可查看。'))
        for root in roots:
            root = relocated_project_path(root).resolve(strict=True)
            def paths():
                if root.is_file():
                    yield root
                else:
                    for folder, dirs, names in os.walk(root):
                        dirs[:] = sorted(d for d in dirs if d not in {'versions', 'node_modules', '.git', 'artifacts'})
                        for name in sorted(names):
                            if name.endswith('.json') and name not in {'data.json', 'result.json', 'execution_data.json', 'execution-data.json'}:
                                yield Path(folder) / name
            for path in paths():
                if path.suffix.lower() != '.json':
                    continue
                scanned += 1
                source = str(path.resolve())
                size = path.stat().st_size
                digest = file_hash(path)
                with self.connection() as db:
                    old = db.execute('SELECT sha256,issue FROM imports WHERE path=?', (source,)).fetchone()
                    if old and old[0] == digest and not old[1]:
                        unchanged += 1
                        continue
                    entries, issue = [], None
                    if size > max_json_bytes:
                        issue = '超过摘要导入大小限制；请使用带来源位置的精简汇总。原文件保留。'
                    else:
                        try:
                            document = json.loads(path.read_text(encoding='utf-8-sig'))
                            if isinstance(document, dict) and document.get('catalog_manifest_version') == 1:
                                manifests.append((path, document))
                            entries = list(legacy_entries(document))
                        except (OSError, ValueError, TypeError) as exc:
                            issue = str(exc)
                    # Replace this source's derived rows only. Native run identity is canonical.
                    previous = db.execute('SELECT result_id FROM sources WHERE path=?', (source,)).fetchall()
                    db.execute('DELETE FROM sources WHERE path=?', (source,))
                    for (rid,) in previous:
                        db.execute("DELETE FROM results WHERE id=? AND source_type='legacy' AND NOT EXISTS (SELECT 1 FROM sources WHERE result_id=?)", (rid, rid))
                    for item in entries:
                        rid = 'run:' + item['run_id'] if item.get('run_id') else None
                        native_row = db.execute("SELECT payload FROM results WHERE id=? AND source_type='native'", (rid,)).fetchone() if rid else None
                        if native_row:
                            actual = json.loads(native_row[0])
                            if any(actual['report'].get(k) != item['report'].get(k) for k in METRICS if k in item['report']):
                                issues.append(dict(path=source, issue=f"{item['pointer']} 引用的运行与报告数值不同，保留为独立旧证据"))
                                native_row = None
                        if not native_row:
                            rid = legacy_identity(item, source)
                            existing = db.execute('SELECT payload FROM results WHERE id=?', (rid,)).fetchone()
                            if existing and json.loads(existing[0])['report'] != compact(item['report']):
                                rid = 'legacy:' + identity([source, item['pointer']])[:24]
                                issues.append(dict(path=source, issue=f"{item['pointer']} 同一明细来源的摘要不同，保留独立证据"))
                            entry = make_entry(rid, item['config'], item['report'], item['metadata'], 'legacy',
                                               item['label'], family=item['family'])
                            self._put(db, entry)
                        db.execute('INSERT INTO sources VALUES (?,?,?,?)', (source, item['pointer'], rid, digest))
                        imported += 1
                    db.execute('INSERT OR REPLACE INTO imports VALUES (?,?,?,?)', (source, digest, len(entries), issue))
                    if issue:
                        issues.append(dict(path=source, issue=issue))
        # Apply explicit context maps after generic imports so folder order cannot
        # discard an enrichment. Also re-read unchanged manifests: source hashes
        # and source reports may have changed independently of the manifest.
        with self.connection() as db:
            known = db.execute('SELECT path FROM imports').fetchall()
        done = {str(p.resolve()) for p, _ in manifests}
        for (name,) in known:
            p = relocated_project_path(name)
            if name not in done and p.is_file() and p.stat().st_size < 1024 * 1024:
                try:
                    doc = json.loads(p.read_text(encoding='utf-8-sig'))
                    if isinstance(doc, dict) and doc.get('catalog_manifest_version') == 1:
                        manifests.append((p, doc))
                except (OSError, ValueError):
                    pass
        for path, document in manifests:
            self.reset_manifest(path, max_json_bytes)
            try:
                imported += self.import_manifest(path, document, max_json_bytes)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                issues.append(dict(path=str(path), issue=str(exc)))
        return dict(native_runs=native, scanned_files=scanned, imported_references=imported, unchanged_files=unchanged,
                    issues=issues, index=str(self.path.resolve()), note='仅导入有明确 report 的汇总和计划声明的参数矩阵；没有来源字段的内容保留为未知，不按文件名猜测。')

    def reset_manifest(self, path, max_json_bytes):
        """Withdraw old declarations before checking a changed context map."""
        with self.connection() as db:
            ids = [r[0] for r in db.execute('SELECT result_id FROM sources WHERE path=?', (str(path.resolve()),))]
            targets = [(p, t) for rid in ids for p, t in db.execute('SELECT path,pointer FROM sources WHERE result_id=? AND path<>?', (rid, str(path.resolve())))]
            for rid in ids:
                db.execute("DELETE FROM results WHERE id=? AND source_type='legacy'", (rid,))
                db.execute('DELETE FROM sources WHERE result_id=?', (rid,))
            # Restore only context present in the source itself. If it is no
            # longer a recognizable result it stays out of the ranking.
            for name, pointer in targets:
                target = relocated_project_path(name)
                if not target.is_file() or target.stat().st_size > max_json_bytes:
                    continue
                try:
                    document = json.loads(target.read_text(encoding='utf-8-sig'))
                    for item in legacy_entries(document):
                        if item['pointer'] == pointer:
                            rid = legacy_identity(item, name)
                            entry = make_entry(rid, item['config'], item['report'], item['metadata'], 'legacy', item['label'], family=item['family'])
                            self._put(db, entry)
                            db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?)', (name, pointer, rid, file_hash(target)))
                except (OSError, ValueError, TypeError):
                    continue

    def import_manifest(self, path, document, max_json_bytes):
        """A small, reviewable map can connect old report files to saved plans.

        It cannot supply a report or invent replay evidence. Every input file is
        hash checked; the declared context remains distinct from engine metadata.
        """
        source = str(path.resolve())
        digest = file_hash(path)
        entries = []
        def read_pointer(node, pointer):
            for part in pointer.strip('/').split('/') if pointer.strip('/') else []:
                part = part.replace('~1', '/').replace('~0', '~')
                node = node[int(part)] if isinstance(node, list) else node[part]
            return node
        for i, item in enumerate(document.get('entries', [])):
            target = (path.parent / item['source']['path']).resolve(strict=True)
            if target.stat().st_size > max_json_bytes:
                raise ValueError(f'来源超过摘要读取上限：{target}')
            actual_hash = file_hash(target)
            if actual_hash != item['source']['sha256']:
                raise ValueError(f'来源已变化，请重新核对映射：{target}')
            for evidence in item.get('context_sources', []):
                evidence_path = (path.parent/evidence['path']).resolve(strict=True)
                if file_hash(evidence_path) != evidence['sha256']:
                    raise ValueError(f'上下文证据已变化：{evidence_path}')
            if not item.get('context_sources'):
                raise ValueError('上下文映射必须提供原计划或规则文件及其校验值')
            raw = json.loads(target.read_text(encoding='utf-8-sig'))
            pointer = item['source'].get('pointer', '/')
            owner = read_pointer(raw, pointer)
            report = owner.get('report', owner)
            if not all(k in report for k in ('return_pct', 'total_trades', 'initial_cash', 'final_equity')):
                raise ValueError('映射必须指向实际回测摘要，不能使用预期收益或事后筛选统计')
            config = {**owner.get('config', {}), **item.get('config', {})}
            for key, value in owner.get('config', {}).items():
                if key in item.get('config', {}) and value != item['config'][key]:
                    raise ValueError(f'映射与报告原配置冲突：{key}')
            with self.connection() as db:
                indexed = db.execute('SELECT result_id FROM sources WHERE path=? AND pointer=?', (str(target), pointer)).fetchone()
            rid = indexed[0] if indexed and indexed[0].startswith('legacy:') else 'legacy:' + identity([str(target), pointer])[:24]
            entry = make_entry(rid, config, report, legacy_metadata(owner), 'legacy',
                               item.get('label') or owner.get('name') or pointer, family=item.get('family'))
            entry['context_note'] = item.get('note', '配置由独立旧计划关联；缺失执行证据仍保留为未知。')
            entries.append((entry, target, pointer, actual_hash, i))
        with self.connection() as db:
            # A changed map never leaves its previous annotations behind.
            db.execute('DELETE FROM sources WHERE path=?', (source,))
            for entry, target, pointer, actual_hash, i in entries:
                self._put(db, entry)
                db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?)', (str(target), pointer, entry['id'], actual_hash))
                db.execute('INSERT INTO sources VALUES (?,?,?,?)', (source, f'/entries/{i}', entry['id'], digest))
        return len(entries)

    def get(self, identifier, *, sync=True):
        if sync:
            self.sync_native()
        with self.connection() as db:
            row = db.execute('SELECT payload FROM results WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise ValueError('结果目录记录不存在')
            entry = json.loads(row[0])
            entry['sources'] = [dict(path=str(relocated_project_path(p)), pointer=t, sha256_at_import=h, exists=relocated_project_path(p).is_file())
                                for p, t, h in db.execute('SELECT path,pointer,sha256 FROM sources WHERE result_id=? ORDER BY path,pointer', (identifier,))]
        if sync:
            for evidence in entry['sources']:
                evidence['unchanged'] = evidence['exists'] and file_hash(Path(evidence['path'])) == evidence['sha256_at_import']
        if entry['run_id']:
            folder = self.backtests.root / entry['run_id']
            entry['sources'].insert(0, dict(path=str((folder/'metadata.json').resolve()), pointer='/',
                                          sha256_at_import=None, exists=(folder/'metadata.json').is_file()))
        return entry

    def query(self, *, symbol=None, strategy=None, family=None, timeframe=None, start=None, end=None,
              execution_timeframe=None, intrabar_profit_protection=None, parameters=None, reference_id=None,
              sort='return_pct', descending=True, minimum_trades=0, include_archived=False, offset=0, limit=30):
        if sort not in METRICS or offset < 0 or not 1 <= limit <= 200 or minimum_trades < 0:
            raise ValueError('排序字段或分页范围无效')
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError('parameters 必须是参数对象')
        self.sync_native()
        where, args = ['1=1'], []
        for key, value in [('symbol', symbol), ('strategy', strategy), ('family', family), ('timeframe', timeframe)]:
            if value:
                where.append(f'{key}=?')
                args.append(value)
        if not include_archived:
            where.append('archived=0')
        if reference_id:
            reference = self.get(reference_id, sync=False)
            if not reference['cohort']:
                raise ValueError('参照记录证据不足，不能建立同条件排序：' + '、'.join(reference['missing']))
            where.append('cohort=?')
            args.append(reference['cohort'])
        with self.connection() as db:
            rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM results WHERE ' + ' AND '.join(where), args)]
        expected = {k: v for k, v in dict(start=date_key(start), end=date_key(end),
                    execution_timeframe=execution_timeframe, intrabar_profit_protection=intrabar_profit_protection).items() if v is not None}
        if execution_timeframe == 'none':
            expected['execution_timeframe'] = None
        def matches(entry):
            c, r = entry['config'], entry['report']
            return (all(k in c and c[k] == v for k, v in expected.items())
                    and all(k in c['parameters'] and c['parameters'][k] == v for k, v in (parameters or {}).items())
                    and (r.get('total_trades') or 0) >= minimum_trades)
        rows = [r for r in rows if matches(r)]
        def order(entry):
            value = entry['report'].get(sort)
            available = isinstance(value, (int, float)) and math.isfinite(value)
            return (0 if available else 1, (-value if descending else value) if available else 0, entry['id'])
        rows.sort(key=order)
        items = [self.get(r['id'], sync=False) for r in rows[offset:offset + limit]]
        return dict(items=items, total=len(rows), offset=offset,
                    mode='same_conditions' if reference_id else 'historical', reference_id=reference_id, note=NOTE)
