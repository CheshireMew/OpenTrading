"""Content-addressed Pine runtime snapshots for reproducible local reruns."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.services.chart_workspace_store import ROOT


FILES = (
    "frontend/scripts/pine-workspace-worker.mjs",
    "frontend/src/modules/chartWorkspace/pineCompatibility.mjs",
    "frontend/src/modules/chartWorkspace/pineRuntimeCompat.mjs",
    "frontend/node_modules/pinets/package.json",
    "frontend/node_modules/pinets/dist/pinets.min.es.js",
    "frontend/node_modules/pinets/LICENSE",
)


def freeze_engine(root: Path) -> str:
    contents = {name: (ROOT / name).read_bytes() for name in FILES}
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
    encoded = json.dumps(manifest, sort_keys=True).encode()
    identity = hashlib.sha256(encoded).hexdigest()
    folder = root / "engines" / identity
    if not (folder / "manifest.json").exists():
        for name, data in contents.items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (folder / "manifest.json").write_bytes(encoded)
    engine_worker(root, identity)
    return identity


def engine_worker(root: Path, identity: str) -> Path:
    if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
        raise ValueError("缺少有效的 Pine 引擎快照，请新建运行")
    folder = root / "engines" / identity
    try:
        encoded = (folder / "manifest.json").read_bytes()
        if hashlib.sha256(encoded).hexdigest() != identity:
            raise ValueError("Pine 引擎快照清单已改变，不能按原快照重跑")
        manifest = json.loads(encoded)
        for name in FILES:
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != manifest.get(name):
                raise ValueError("Pine 引擎快照文件已改变，不能按原快照重跑")
    except FileNotFoundError as exc:
        raise ValueError("Pine 引擎快照文件不完整，请恢复原快照或新建运行") from exc
    return folder / FILES[0]
