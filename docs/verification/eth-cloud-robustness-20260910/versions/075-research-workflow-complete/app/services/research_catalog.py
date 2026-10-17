"""Incremental local evidence index. Indexing never launches a backtest.

Legacy documents are searchable evidence, not silently converted to current
engine results. Large raw candle/trade arrays stay in their original files.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
from app.infra.research_files import file_hash

SKIP_KEYS = {'trades', 'candles', 'bars', 'equity', 'signals', 'fills', 'levels', 'indicators', 'rows',
             'curve', 'daily_equity', 'equity_curve', 'sampled_equity'}
INDEX_VERSION = '2'


def chunks(path):
    if path.suffix.lower() == '.md':
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        for start in range(0, len(lines), 18):
            yield f'line:{start + 1}', '\n'.join(lines[start:start + 24])[:8000]
        return
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    def walk(node, pointer=''):
        if isinstance(node, dict):
            if ('timestamp' in node and ('equity' in node or 'open' in node)) or 'entry_time' in node:
                return  # raw curve / trade record stored under a legacy alias
            simple = {k: v for k, v in node.items() if not isinstance(v, (dict, list))}
            if simple:
                yield pointer or '/', json.dumps(simple, ensure_ascii=False)[:12000]
            for key, item in node.items():
                if key not in SKIP_KEYS and isinstance(item, (dict, list)):
                    token = key.replace('~', '~0').replace('/', '~1')
                    yield from walk(item, f'{pointer}/{token}')
        elif isinstance(node, list):
            if len(node) <= 10000:
                for i, item in enumerate(node):
                    if isinstance(item, (dict, list)):
                        yield from walk(item, f'{pointer}/{i}')
                    elif isinstance(item, str):
                        yield f'{pointer}/{i}', item[:12000]
    yield from walk(value)


class ResearchCatalog:
    def __init__(self, database_path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY, sha256 TEXT, bytes INTEGER, issue TEXT);
                CREATE TABLE IF NOT EXISTS excerpts (
                path TEXT, pointer TEXT, text TEXT, search TEXT);
                CREATE INDEX IF NOT EXISTS excerpt_path ON excerpts(path);''')
            db.execute('CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY,value TEXT)')

    def connection(self):
        return sqlite3.connect(self.path)

    def refresh(self, roots, max_json_bytes=32 * 1024 * 1024):
        scanned = indexed = unchanged = 0
        issues = []
        with self.connection() as db:
            version = db.execute("SELECT value FROM index_meta WHERE key='version'").fetchone()
            if not version or version[0] != INDEX_VERSION:
                db.execute("UPDATE files SET issue='索引算法更新，需要重新读取'")
                db.execute("INSERT OR REPLACE INTO index_meta VALUES ('version',?)", (INDEX_VERSION,))
        for root in roots:
            root = Path(root).resolve(strict=True)
            def files():
                if root.is_file():
                    yield root
                    return
                for folder, directories, names in os.walk(root):
                    directories[:] = sorted(d for d in directories if d not in {'versions', 'node_modules', '.git', 'artifacts'})
                    for name in sorted(names):
                        yield Path(folder) / name
            paths = files()
            for path in paths:
                if not path.is_file() or path.suffix.lower() not in {'.md', '.json'}:
                    continue
                if any(part in {'versions', 'node_modules', '.git', 'artifacts'} for part in path.relative_to(root.parent if root.is_file() else root).parts):
                    continue
                if path.name in {'data.json', 'result.json'}:  # full run arrays, not study summaries
                    continue
                scanned += 1
                source = str(path.resolve())
                digest = file_hash(path)
                size = path.stat().st_size
                with self.connection() as db:
                    old = db.execute('SELECT sha256,issue FROM files WHERE path=?', (source,)).fetchone()
                    if old and old[0] == digest and not old[1]:
                        unchanged += 1
                        continue
                    issue = None
                    if path.suffix == '.json' and size > max_json_bytes:
                        issue = '超过索引大小限制；保留原文件，未索引其内容'
                    entries = []
                    if not issue:
                        try:
                            entries = list(chunks(path))
                        except (ValueError, UnicodeError, OSError) as exc:
                            issue = str(exc)
                    # Only replace derived index rows; original research is never edited.
                    db.execute('DELETE FROM excerpts WHERE path=?', (source,))
                    db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?)', (source, digest, size, issue))
                    db.executemany('INSERT INTO excerpts VALUES (?,?,?,?)',
                                   [(source, p, t, f'{source} {p} {t}'.casefold()) for p, t in entries])
                    indexed += len(entries)
                    if issue:
                        issues.append({'path': source, 'issue': issue})
        with self.connection() as db:
            total = db.execute('SELECT count(*) FROM excerpts').fetchone()[0]
            if scanned and indexed:
                db.execute('VACUUM')
        return {'scanned_files': scanned, 'new_excerpts': indexed, 'total_excerpts': total, 'unchanged_files': unchanged,
                'issues': issues, 'index': str(self.path.resolve()),
                'coverage': '索引文档、计划和汇总 JSON；不重复索引 versions 副本，不读原始逐笔／K线数组；完整数据仍在原文件。旧引擎结果不冒充当前引擎结果。'}

    def search(self, query, offset=0, limit=8):
        if not query.strip() or offset < 0 or not 1 <= limit <= 100:
            raise ValueError('需要非空搜索词，offset 非负，limit 为 1–100')
        terms = re.split(r'\s+', query.strip().casefold())
        where = ' AND '.join('instr(e.search,?) > 0' for _ in terms)
        with self.connection() as db:
            count = db.execute(f'SELECT count(*) FROM excerpts e WHERE {where}', terms).fetchone()[0]
            rows = db.execute(f'''SELECT e.path,e.pointer,e.text,f.sha256 FROM excerpts e
                JOIN files f ON f.path=e.path WHERE {where} ORDER BY e.path,e.pointer LIMIT ? OFFSET ?''',
                              [*terms, limit, offset]).fetchall()
        items = []
        for path, pointer, text, digest in rows:
            locations = [text.casefold().find(t) for t in terms if t in text.casefold()]
            start = max(0, min(locations, default=0) - 100)
            items.append({'path': path, 'pointer': pointer, 'excerpt': text[start:start + 800],
                          'sha256_at_index': digest, 'exists': Path(path).is_file()})
        return {'total': count, 'offset': offset, 'items': items,
                'note': '摘录是原研究证据，不是自动结论。打开原文件核对范围；内容变更后 refresh 更新索引。'}
