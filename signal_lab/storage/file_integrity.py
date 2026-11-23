from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path


def file_sha256(path: Path) -> str:
    """Hash a file once per resolved path, size, and modification identity."""

    resolved = path.expanduser().resolve()
    stat = resolved.stat()
    return _cached_file_sha256(str(resolved), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=512)
def _cached_file_sha256(path: str, _mtime_ns: int, _size: int) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
