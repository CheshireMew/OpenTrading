"""Resolve Node through project configuration or PATH, on every supported host."""
from __future__ import annotations

import shutil
from pathlib import Path


def resolve_node() -> str:
    from config import settings

    configured = settings.NODE_EXECUTABLE.strip()
    executable = shutil.which(configured or "node")
    if not executable and configured and Path(configured).is_file():
        executable = str(Path(configured).resolve())
    if not executable:
        raise ValueError("找不到 Node.js，请安装项目要求的版本并加入 PATH，或设置 NODE_EXECUTABLE")
    return executable
