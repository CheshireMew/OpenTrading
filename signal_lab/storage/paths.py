from __future__ import annotations

from pathlib import Path


def default_data_dir() -> Path:
    from config import settings

    return settings.RUNTIME_ROOT_DIR / "signal-lab"


def managed_path_reference(root: Path, path: Path) -> str:
    """Persist a path relative to the movable data root."""

    base = root.expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(base).as_posix()
    except ValueError as exc:
        raise ValueError(f"managed path escapes the data root: {resolved}") from exc


def resolve_managed_path(root: Path, reference: str) -> Path:
    """Resolve current relative references and safely rebase legacy absolute references."""

    base = root.expanduser().resolve()
    candidate = Path(reference)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(base)
        except ValueError:
            relative = _legacy_relative_path(resolved)
    else:
        relative = candidate
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"managed path reference escapes the data root: {reference}") from exc
    return resolved


def normalize_managed_path_reference(root: Path, reference: str) -> str:
    return managed_path_reference(root, resolve_managed_path(root, reference))


def _legacy_relative_path(path: Path) -> Path:
    parts = path.parts
    for marker in ("runs", "research", "exports", "raw", ".operations", "archive"):
        matching = [index for index, part in enumerate(parts) if part.casefold() == marker.casefold()]
        if matching:
            return Path(*parts[matching[-1]:])
    raise ValueError(f"legacy managed path cannot be rebased: {path}")
