from __future__ import annotations
from sqlalchemy import select, update, func, insert
from app.infra.db.schema import LocalBacktestRunRow as Run, LocalBacktestRecordRow as Record

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
ACTIVE = {"preparing", "running"}


class LocalBacktestRepository:
    def __init__(self, database):
        self.database = database

    def create(self, payload):
        with self.database.session_scope() as s:
            s.add(Run(id=payload["id"], status="queued", payload=payload))
        return payload

    def get(self, identifier):
        with self.database.session_scope() as s:
            row = s.get(Run, identifier)
            if row is None:
                raise ValueError(f"回测不存在：{identifier}")
            return {**row.payload, "status": row.status}

    def patch(self, identifier, *, allowed=None, **values):
        with self.database.session_scope() as s:
            row = s.scalar(select(Run).where(Run.id == identifier).with_for_update())
            if row is None:
                raise ValueError(f"回测不存在：{identifier}")
            if allowed is not None and row.status not in allowed:
                return False
            old_status = row.status
            data = {**row.payload, "status": row.status, **values}
            result = s.execute(update(Run).where(Run.id == identifier, Run.status == old_status)
                               .values(status=data.get("status", old_status), payload=data))
            return result.rowcount == 1

    def list(self, offset=0, limit=50, archived=False):
        # Archive flag uses a JSON predicate supported by SQLite and PostgreSQL.
        predicate = Run.payload["archived"].as_boolean() == archived
        with self.database.session_scope() as s:
            total = s.scalar(select(func.count()).select_from(Run).where(predicate))
            rows = s.scalars(select(Run).where(predicate).order_by(Run.created_at.desc(), Run.id).offset(offset).limit(limit))
            return {"items": [{**r.payload, "status": r.status} for r in rows], "total": total}

    def claim(self):
        with self.database.session_scope() as s:
            row = s.scalar(select(Run).where(Run.status == "queued").order_by(Run.created_at, Run.id).limit(1))
            if row is None:
                return None
            result = s.execute(update(Run).where(Run.id == row.id, Run.status == "queued").values(status="preparing"))
            return row.id if result.rowcount else None

    def interrupt_active(self):
        with self.database.session_scope() as s:
            s.execute(update(Run).where(Run.status.in_(ACTIVE)).values(status="interrupted"))

    def finish(self, identifier, result, candles, metadata):
        with self.database.session_scope() as s:
            row = s.scalar(select(Run).where(Run.id == identifier).with_for_update())
            if row.status not in ACTIVE:
                return False
            for kind, items in {**{k: v for k, v in result.items() if k not in {"report", "execution_detail"}}, "candles": candles}.items():
                for start in range(0, len(items), 1000):
                    batch = [{"run_id": identifier, "kind": kind, "sequence": start + j,
                              "timestamp": item.get("timestamp", item.get("entry_time", 0)), "payload": item}
                             for j, item in enumerate(items[start:start + 1000])]
                    if batch:
                        s.execute(insert(Record), batch)
            data = {**row.payload, "report": result["report"], "metadata": metadata, "progress": 1., "status": "completed"}
            changed = s.execute(update(Run).where(Run.id == identifier, Run.status.in_(ACTIVE)).values(status="completed", payload=data))
            if not changed.rowcount:
                s.rollback()
                return False
        return True

    def records(self, identifier, kind, offset=0, limit=500, start=None, end=None):
        filters = [Record.run_id == identifier, Record.kind == kind]
        if start is not None:
            filters.append(Record.timestamp >= start)
        if end is not None:
            filters.append(Record.timestamp <= end)
        with self.database.session_scope() as s:
            total = s.scalar(select(func.count()).select_from(Record).where(*filters))
            rows = s.scalars(select(Record).where(*filters).order_by(Record.sequence).offset(offset).limit(limit))
            return {"items": [r.payload for r in rows], "total": total, "offset": offset}
