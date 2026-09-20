"""Shared immutable raw datasets; legacy run-local JSON snapshots stay readable."""
from pathlib import Path
import os
import shutil
from uuid import uuid4
from app.infra.research_files import atomic_json, encode, sha, file_hash, read_json, native_path


class BacktestDatasets:
    def __init__(self, root):
        self.root = native_path(root)

    def resolve(self, folder, name):
        folder = native_path(folder)
        if (folder/name).exists():
            return folder/name
        reference = folder/f'{name}.ref.json'
        if not reference.exists():
            return folder/name
        digest = read_json(reference)['sha256']
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('无效行情引用')
        return self.root/f'{digest}.json'

    def install(self, folder, name, value, expected=None):
        source = native_path(value) if isinstance(value, Path) else None
        blob = None if source else value if isinstance(value, bytes) else encode(value)
        digest = file_hash(source) if source else sha(blob)
        if expected and digest != expected:
            raise ValueError('行情快照校验失败')
        path = self.root/f'{digest}.json'
        if not path.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f'.{digest}.{uuid4().hex}.tmp')
            if source:
                shutil.copyfile(source, temporary)
            else:
                with temporary.open('xb') as stream:
                    stream.write(blob)
                    stream.flush()
                    os.fsync(stream.fileno())
            if file_hash(temporary) != digest:
                raise ValueError('共享行情写入校验失败')
            os.replace(temporary, path)
        elif file_hash(path) != digest:
            raise ValueError('已有共享行情快照校验失败')
        atomic_json(native_path(folder)/f'{name}.ref.json', {'format': 'dataset-reference-v1', 'sha256': digest})
        return path, digest
