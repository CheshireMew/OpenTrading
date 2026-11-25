from __future__ import annotations

from datetime import datetime

from typing import Any

from uuid import uuid4

from sqlalchemy import select

from app.domain.research import ResearchNotFoundError, ResearchRevisionConflictError
from app.domain.research_alerts import should_trigger

from app.infra.db.database import DatabaseRuntime

from app.infra.persistence.write_session import write_session

from app.infra.db.schema import ResearchAlertRule

from utils.time import utc_now_naive

from app.infra.persistence.research_rows import (
    require_row,
    validate_watch_item_link,
    touch,
    add_event,
    alert_payload,
    alert_runtime_payload,
)


class ResearchAlertRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def create_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            validate_watch_item_link(session, payload.get("watch_item_id"), payload["symbol"])
            now = utc_now_naive()
            row = ResearchAlertRule(id=uuid4().hex, version=1, created_at=now, updated_at=now, **payload)
            if row.configuration.get("chartSymbolId"):
                row.last_value = row.configuration.get("initialPrice")
            session.add(row)
            add_event(
                session,
                entity_type="alert",
                entity_id=row.id,
                symbol=row.symbol,
                kind="alert_created",
                title=f"创建提醒：{row.name}",
                payload={"metric": row.metric, "operator": row.operator, "threshold": row.threshold},
                occurred_at=now,
            )
            session.flush()
            return alert_payload(row)

    def update_alert(self, alert_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = require_row(session, ResearchAlertRule, alert_id, expected_version)
            validate_watch_item_link(session, payload.get("watch_item_id"), payload["symbol"])
            for key, value in payload.items():
                setattr(row, key, value)
            if row.configuration.get("chartSymbolId"):
                row.last_value = row.configuration.get("initialPrice")
            touch(row)
            add_event(
                session,
                entity_type="alert",
                entity_id=row.id,
                symbol=row.symbol,
                kind="alert_updated",
                title=f"更新提醒：{row.name}",
            )
            session.flush()
            return alert_payload(row)

    def delete_alert(self, alert_id: str, expected_version: int) -> None:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = require_row(session, ResearchAlertRule, alert_id, expected_version)
            session.delete(row)

    def list_enabled_alerts(self) -> list[dict[str, Any]]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            rows = list(
                session.scalars(
                    select(ResearchAlertRule)
                    .where(ResearchAlertRule.archived_at.is_(None), ResearchAlertRule.enabled == 1)
                    .order_by(ResearchAlertRule.symbol, ResearchAlertRule.created_at)
                )
            )
            return [alert_runtime_payload(row) for row in rows]

    def record_alert_evaluation(
        self, alert_id: str, *, value: float, evaluated_at: datetime, triggered: bool
    ) -> dict[str, Any] | None:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = session.scalar(select(ResearchAlertRule).where(ResearchAlertRule.id == alert_id).with_for_update())
            if row is None:
                # A subscription can have an in-flight tick when its rule is deleted.
                return None
            if row.archived_at is not None:
                raise ResearchNotFoundError("提醒规则不存在或已归档")
            if not row.enabled:
                return alert_payload(row)
            if row.configuration.get("chartSymbolId"):
                # Recheck the persisted rule inside the write transaction. An edit,
                # pause, or another evaluator must not deliver an obsolete trigger.
                triggered = should_trigger(alert_runtime_payload(row), value, evaluated_at)
            row.last_value = value
            row.last_evaluated_at = evaluated_at
            if triggered:
                row.last_triggered_at = evaluated_at
                add_event(
                    session,
                    entity_type="alert",
                    entity_id=row.id,
                    symbol=row.symbol,
                    kind="alert_triggered",
                    title=f"价格警报：{row.name}" if row.configuration.get("chartSymbolId") else f"提醒触发：{row.name}",
                    body=f"{row.symbol} 价格触及 {row.threshold:g}，当前价格 {value:g}" if row.configuration.get("chartSymbolId") else f"{row.symbol} 的 {row.metric} 当前值为 {value:g}",
                    payload={
                        "metric": row.metric,
                        "operator": row.operator,
                        "threshold": row.threshold,
                        "secondaryThreshold": row.secondary_threshold,
                        "value": value,
                        "notificationChannels": list(row.notification_channels or []),
                        "chartSymbolId": row.configuration.get("chartSymbolId"),
                    },
                    occurred_at=evaluated_at,
                )
                if row.configuration.get("once", bool(row.configuration.get("chartSymbolId"))):
                    row.enabled = 0
                    touch(row)
                    result = alert_payload(row)
                    session.delete(row)
                    session.flush()
                    return result
            session.flush()
            return alert_payload(row)
