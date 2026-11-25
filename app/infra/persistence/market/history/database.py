from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.engine import Engine

from app.infra.persistence.market.history.catalog_schema import SCHEMA_VERSION as SCHEMA_VERSION
from app.infra.persistence.market.history.sql import CatalogConnection


class MarketHistoryDatabase:
    """Structured records share the OpenTrading database; the root owns files only."""

    def __init__(self, root: Path, *, engine: Engine) -> None:
        self.root = root.expanduser().resolve()
        self._engine = engine
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
