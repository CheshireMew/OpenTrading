"""Immutable compressed record pages, with a durable computed-result boundary.

Large arrays are recorded during simulation. A small mutable tail retains the
signals whose status can change on the next bar and the final equity point.
The published manifest is the authoritative result; DB rows are summaries.
"""
from collections.abc import Sequence
import gzip
import json
import os
from pathlib import Path
from uuid import uuid4

from app.infra.research_files import atomic_json, encode, sha, file_hash, read_json, native_path

PAGE_SIZE = 2048
TAIL_SIZE = 16


def timestamp(item):
    return item.get('timestamp', item.get('entry_time', 0))


class RecordPages(Sequence):
    def __init__(self, store, kind):
        self.store, self.kind = store, kind
        self.parts, self.tail, self.count = [], [], 0

    def __len__(self):
        return self.count

    def append(self, item):
        self.tail.append(item)
        self.count += 1
        if len(self.tail) >= PAGE_SIZE+TAIL_SIZE:
            self._flush(PAGE_SIZE)

    def _flush(self, count):
        if count:
            self.parts.append(self.store.write_page(self.tail[:count]))
            self.tail = self.tail[count:]

    def __getitem__(self, key):
        if isinstance(key, slice):
            return list(self)[key]
        index = key if key >= 0 else self.count+key
        if not 0 <= index < self.count:
            raise IndexError(key)
        sealed = self.count-len(self.tail)
        if index >= sealed:
            return self.tail[index-sealed]
        for part in self.parts:
            if index < part['count']:
                return self.store.read_page(part)[index]
            index -= part['count']
        raise IndexError(key)

    def __iter__(self):
        for part in self.parts:
            yield from self.store.read_page(part)
        yield from self.tail

    def seal(self):
        self._flush(len(self.tail))
        return {'count': self.count, 'parts': list(self.parts)}


class BacktestRecordStore:
    def __init__(self, root):
        self.root = native_path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def object_path(self, digest):
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('无效记录块校验值')
        return self.root/'objects'/digest[:2]/f'{digest}.json.gz'

    def write_page(self, items):
        blob = gzip.compress(encode(items), compresslevel=3, mtime=0)
        digest = sha(blob)
        path = self.object_path(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f'.{digest}.{uuid4().hex}.tmp')
            with temporary.open('xb') as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        times = [timestamp(x) for x in items]
        return {'hash': digest, 'count': len(items), 'min_time': min(times), 'max_time': max(times), 'bytes': len(blob)}

    def read_page(self, part):
        blob = self.object_path(part['hash']).read_bytes()
        if sha(blob) != part['hash']:
            raise ValueError('记录块校验失败')
        items = json.loads(gzip.decompress(blob))
        if len(items) != part['count']:
            raise ValueError('记录块数量不符')
        return items

    def collection(self, kind):
        return RecordPages(self, kind)

    def candle_index(self, data_hash, bars, progress=None):
        """One derived price-chart index per immutable native dataset."""
        from dataclasses import asdict
        path = self.root/'datasets'/f'{data_hash}.candles.json'
        if path.exists():
            saved = read_json(path)
            if saved.get('data_hash') != data_hash or saved['records']['count'] != len(bars):
                raise ValueError('行情图表索引与数据快照不同')
            return saved['records']
        pages = self.collection('candles')
        for index, bar in enumerate(bars):
            pages.append(asdict(bar))
            if progress and (index % PAGE_SIZE == 0 or index == len(bars)-1):
                progress((index+1)/len(bars))
        records = pages.seal()
        atomic_json(path, {'data_hash': data_hash, 'records': records})
        return records

    def seal(self, folder, result, candles, fingerprint):
        arrays, extra = {}, {}
        for kind, value in result.items():
            if isinstance(value, RecordPages):
                arrays[kind] = value.seal()
            elif isinstance(value, list):
                pages = self.collection(kind)
                for row in value:
                    pages.append(row)
                arrays[kind] = pages.seal()
            else:
                extra[kind] = value
        arrays['candles'] = candles
        manifest = {'format': 'record-pages-v1', 'fingerprint': fingerprint, 'arrays': arrays, 'extra': extra}
        # Once this atomic file exists the calculation is recoverable without
        # executing the strategy again, including after cancellation in saving.
        atomic_json(Path(folder)/'computed.json', manifest)
        return manifest

    def manifest(self, folder, expected_hash=None):
        path = native_path(folder)/'computed.json'
        if expected_hash and file_hash(path) != expected_hash:
            raise ValueError('完整结果清单校验失败')
        value = read_json(path)
        if value.get('format') != 'record-pages-v1':
            raise ValueError('不支持的记录存储版本')
        return value

    def verify(self, manifest, progress=None):
        parts = [p for array in manifest['arrays'].values() for p in array['parts']]
        seen = set()
        for index, part in enumerate(parts):
            if part['hash'] not in seen:
                if file_hash(self.object_path(part['hash'])) != part['hash']:
                    raise ValueError('完整结果记录块校验失败')
                seen.add(part['hash'])
            if progress:
                progress((index+1)/max(1, len(parts)))
        for array in manifest['arrays'].values():
            if sum(p['count'] for p in array['parts']) != array['count']:
                raise ValueError('完整结果记录数量不符')

    def records(self, manifest, kind, offset=0, limit=500, start=None, end=None):
        array = manifest['arrays'].get(kind, {'count': 0, 'parts': []})
        selected, total = [], 0
        for part in array['parts']:
            if start is not None and part['max_time'] < start or end is not None and part['min_time'] > end:
                continue
            complete = (start is None or part['min_time'] >= start) and (end is None or part['max_time'] <= end)
            if complete:
                count = part['count']
                if total+count > offset and total < offset+limit:
                    rows = self.read_page(part)
                    selected.extend(rows[max(0, offset-total):max(0, min(count, offset+limit-total))])
            else:
                rows = [r for r in self.read_page(part) if (start is None or timestamp(r) >= start) and (end is None or timestamp(r) <= end)]
                count = len(rows)
                if total+count > offset and total < offset+limit:
                    selected.extend(rows[max(0, offset-total):max(0, min(count, offset+limit-total))])
            total += count
        return {'items': selected, 'total': total, 'offset': offset}

    def result(self, manifest):
        return {**manifest['extra'], **{kind: [row for part in array['parts'] for row in self.read_page(part)]
                                      for kind, array in manifest['arrays'].items() if kind != 'candles'}}


def computation_fingerprint(run):
    meta = run['metadata']
    config = {'data_gap_policy': 'reject', 'execution_timeframe': None, 'intrabar_profit_protection': False,
              'execution_gap_policy': 'coarse_fallback', **run['config']}
    return sha(encode({'config': config, 'strategy_hash': meta.get('strategy_hash'),
        'execution_bundle': meta.get('execution_bundle'), 'execution_recipe': meta.get('execution_recipe'),
        'environment': meta.get('environment'), 'data_hash': meta.get('data_hash'),
        'execution_data_hash': meta.get('execution_data_hash'), 'execution_alignment_hash': meta.get('execution_alignment_hash')}))
