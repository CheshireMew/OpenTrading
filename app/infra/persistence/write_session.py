"""Translate database-enforced write conflicts without leaking storage errors."""
from contextlib import contextmanager

from sqlalchemy.orm.exc import StaleDataError


@contextmanager
def write_session(database, conflict_error):
    try:
        with database.session_scope() as session:
            yield session
    except StaleDataError as exc:
        raise conflict_error("记录已在其它窗口更新，请重新载入后再试") from exc
