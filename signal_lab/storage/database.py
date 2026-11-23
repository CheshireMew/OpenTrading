from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from signal_lab.storage.catalog_schema import SCHEMA_VERSION as SCHEMA_VERSION
from signal_lab.storage.sql import CatalogConnection


@dataclass(frozen=True)
class DatabaseBinding:
    engine: Engine
    root: Path


_binding: ContextVar[DatabaseBinding | None] = ContextVar("signal_lab_database", default=None)


@contextmanager
def bind_database(engine: Engine, root: Path):
    token = _binding.set(DatabaseBinding(engine, root.resolve()))
    try:
        yield
    finally:
        _binding.reset(token)


class SignalLabDatabase:
    """Structured records share the OpenTrading database; the root owns files only."""

    def __init__(self, root: Path) -> None:
        binding = _binding.get()
        if binding is None:
            raise RuntimeError("Signal Lab requires an OpenTrading database binding")
        self.root = root.expanduser().resolve()
        if self.root != binding.root:
            raise ValueError("data root must match the OpenTrading Signal Lab artifact directory")
        self._engine = binding.engine
        self.location = (
            str(Path(self._engine.url.database).resolve())
            if self._engine.dialect.name == "sqlite" and self._engine.url.database not in (None, ":memory:")
            else f"OpenTrading ({self._engine.dialect.name})"
        )
        self.cache_key = (id(self._engine), self.root)

    @contextmanager
    def connect(self):
        with self._engine.begin() as connection:
            yield CatalogConnection(connection)

    def size_bytes(self, connection: CatalogConnection) -> int | None:
        return connection.size_bytes()
