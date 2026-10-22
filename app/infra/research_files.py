"""Small local, crash-safe files; locks are retained, never cleaned by the agent."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from config.settings import BASE_DIR


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def relocated_project_path(path):
    """Resolve saved absolute paths after the project folder was renamed."""
    path = Path(path)
    if path.exists():
        return path
    parts = path.parts
    for index, part in enumerate(parts):
        if part.casefold() not in {"heimdall", "opentrading"}:
            continue
        relative = list(parts[index + 1:])
        if relative and relative[0] == ".heimdall_runtime":
            relative[0] = ".opentrading_runtime"
        candidate = BASE_DIR.joinpath(*relative)
        if candidate.exists():
            return candidate
    return path


def native_path(path):
    """Windows also needs extended paths for hash-named temporary snapshots."""
    path = relocated_project_path(path)
    if os.name == 'nt' and not str(path).startswith('\\\\?\\'):
        resolved = str(path.resolve())
        return Path('\\\\?\\UNC\\' + resolved[2:] if resolved.startswith('\\\\') else '\\\\?\\' + resolved)
    return path


def file_hash(path):
    result = hashlib.sha256()
    with native_path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    return json.loads(native_path(path).read_text(encoding="utf-8-sig"))


def atomic_json(path, value):
    path = native_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with temporary.open("xb") as stream:
        stream.write(encode(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def lock(folder):
    """OS releases ownership after a killed process; no stale PID lock to delete."""
    folder = native_path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".lock").open("a+b") as stream:
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
