from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from app.domain.research import ResearchNotFoundError, ResearchRevisionConflictError
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import ResearchEvent, TradeSignalRecord
from utils.time import utc_now_naive


class TradeSignalRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def create_signal(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            now = utc_now_naive()
            row = TradeSignalRecord(
                id=uuid4().hex,
                version=1,
                created_at=now,
                updated_at=now,
                **payload,
            )
            session.add(row)
            session.add(
                ResearchEvent(
                    id=uuid4().hex,
                    entity_type="trade_signal",
                    entity_id=row.id,
                    symbol=row.symbol,
                    kind="trade_signal_recorded",
                    title=f"交易信号已留档：{row.symbol}",
                    body=row.reason,
                    payload={"source": row.source, "status": row.signal_status, "side": row.side},
                    occurred_at=now,
                    created_at=now,
                )
            )
            session.flush()
            return self._payload(row)

    def list_signals(
        self,
        *,
        symbol: str | None,
        outcome_status: str | None,
        source: str | None,
        include_archived: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._database_runtime.session_scope() as session:
            filters = []
            if symbol:
                filters.append(TradeSignalRecord.symbol == symbol.upper())
            if outcome_status:
                filters.append(TradeSignalRecord.outcome_status == outcome_status)
            if source:
                filters.append(TradeSignalRecord.source == source)
            if not include_archived:
                filters.append(TradeSignalRecord.archived_at.is_(None))
            total = int(session.scalar(select(func.count()).select_from(TradeSignalRecord).where(*filters)) or 0)
            rows = list(
                session.scalars(
                    select(TradeSignalRecord)
                    .where(*filters)
                    .order_by(TradeSignalRecord.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            return [self._payload(row) for row in rows], total

    def get_signal(self, signal_id: str) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            return self._payload(self._require(session, signal_id))

    def list_evaluation_candidates(self, signal_id: str | None = None) -> list[dict[str, Any]]:
        with self._database_runtime.session_scope() as session:
            statement = select(TradeSignalRecord).where(TradeSignalRecord.archived_at.is_(None))
            if signal_id:
                statement = statement.where(TradeSignalRecord.id == signal_id)
            else:
                statement = statement.where(TradeSignalRecord.outcome_status.in_(("pending", "unavailable")))
            rows = list(session.scalars(statement.order_by(TradeSignalRecord.created_at)))
            return [self._payload(row) for row in rows]

    def record_evaluation(self, signal_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require(session, signal_id)
            previous = row.outcome_status
            mapping = {
                "outcomeStatus": "outcome_status",
                "outcomePrice": "outcome_price",
                "targetHitAt": "target_hit_at",
                "stopHitAt": "stop_hit_at",
                "mfePct": "mfe_pct",
                "maePct": "mae_pct",
                "forwardReturns": "forward_returns",
                "evaluatedAt": "evaluated_at",
            }
            for source_key, target_key in mapping.items():
                if source_key in payload:
                    setattr(row, target_key, payload[source_key])
            row.updated_at = utc_now_naive()
            if row.outcome_status != previous and row.outcome_status not in {"pending", "unavailable"}:
                now = row.evaluated_at or utc_now_naive()
                session.add(
                    ResearchEvent(
                        id=uuid4().hex,
                        entity_type="trade_signal",
                        entity_id=row.id,
                        symbol=row.symbol,
                        kind=f"trade_signal_{row.outcome_status}",
                        title=f"信号结果：{row.symbol} · {row.outcome_status}",
                        body=f"MFE {row.mfe_pct or 0:.2f}% / MAE {row.mae_pct or 0:.2f}%",
                        payload={"source": row.source, "strategy": row.strategy},
                        occurred_at=now,
                        created_at=utc_now_naive(),
                    )
                )
            session.flush()
            return self._payload(row)

    def set_signal_archived(
        self,
        signal_id: str,
        expected_version: int,
        archived: bool,
    ) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require(session, signal_id)
            if row.version != expected_version:
                raise ResearchRevisionConflictError("交易信号已在其它窗口更新，请重新载入")
            now = utc_now_naive()
            row.archived_at = now if archived else None
            row.version += 1
            row.updated_at = now
            session.add(
                ResearchEvent(
                    id=uuid4().hex,
                    entity_type="trade_signal",
                    entity_id=row.id,
                    symbol=row.symbol,
                    kind="trade_signal_archived" if archived else "trade_signal_restored",
                    title=f"{'归档' if archived else '恢复'}交易信号：{row.symbol}",
                    body="",
                    payload={},
                    occurred_at=now,
                    created_at=now,
                )
            )
            session.flush()
            return self._payload(row)

    def get_stats(self) -> dict[str, Any]:
        rows, _ = self.list_signals(
            symbol=None,
            outcome_status=None,
            source=None,
            include_archived=False,
            offset=0,
            limit=100_000,
        )
        return {
            "overall": self._stat_group("all", rows),
            "bySource": self._group_stats(rows, "source"),
            "byStrategy": self._group_stats(rows, "strategy"),
            "confidenceCalibration": self._confidence_calibration(rows),
        }

    @staticmethod
    def _confidence_calibration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets = ((0, 39), (40, 59), (60, 79), (80, 100))
        result: list[dict[str, Any]] = []
        for minimum, maximum in buckets:
            values = [
                row for row in rows
                if row.get("confidence") is not None and minimum <= int(row["confidence"]) <= maximum
            ]
            target_hits = sum(row["outcomeStatus"] == "target_hit" for row in values)
            stop_hits = sum(row["outcomeStatus"] == "stop_hit" for row in values)
            resolved = target_hits + stop_hits
            actual = round(target_hits / resolved * 100, 2) if resolved else None
            resolved_values = [
                row for row in values if row["outcomeStatus"] in {"target_hit", "stop_hit"}
            ]
            expected = (
                round(sum(float(row["confidence"]) for row in resolved_values) / len(resolved_values), 2)
                if resolved_values
                else None
            )
            result.append({
                "key": f"{minimum}-{maximum}",
                "minConfidence": minimum,
                "maxConfidence": maximum,
                "total": len(values),
                "resolved": resolved,
                "targetHits": target_hits,
                "stopHits": stop_hits,
                "winRatePct": actual,
                "expectedWinRatePct": expected,
                "calibrationGapPct": round(actual - expected, 2)
                if actual is not None and expected is not None
                else None,
            })
        return result

    @classmethod
    def _group_stats(cls, rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row.get(field) or "未指定")].append(row)
        return [cls._stat_group(key, values) for key, values in sorted(groups.items())]

    @staticmethod
    def _stat_group(key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        target_hits = sum(row["outcomeStatus"] == "target_hit" for row in rows)
        stop_hits = sum(row["outcomeStatus"] == "stop_hit" for row in rows)
        ambiguous = sum(row["outcomeStatus"] == "ambiguous" for row in rows)
        expired = sum(row["outcomeStatus"] == "expired" for row in rows)
        resolved = target_hits + stop_hits

        def average(field: str) -> float | None:
            values = [float(row[field]) for row in rows if row.get(field) is not None]
            return round(sum(values) / len(values), 4) if values else None

        return {
            "key": key,
            "total": len(rows),
            "resolved": resolved,
            "targetHits": target_hits,
            "stopHits": stop_hits,
            "ambiguous": ambiguous,
            "expired": expired,
            "winRatePct": round(target_hits / resolved * 100, 2) if resolved else None,
            "averageConfidence": average("confidence"),
            "averageMfePct": average("mfePct"),
            "averageMaePct": average("maePct"),
        }

    @staticmethod
    def _require(session, signal_id: str) -> TradeSignalRecord:
        row = session.get(TradeSignalRecord, signal_id)
        if row is None:
            raise ResearchNotFoundError("交易信号不存在")
        return row

    @staticmethod
    def _payload(row: TradeSignalRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "source": row.source,
            "mode": row.mode,
            "signalStatus": row.signal_status,
            "side": row.side,
            "entry": row.entry,
            "target": row.target,
            "stop": row.stop,
            "riskReward": row.risk_reward,
            "confidence": row.confidence,
            "riskAmount": row.risk_amount,
            "style": row.style,
            "strategy": row.strategy,
            "reason": row.reason,
            "errorCode": row.error_code,
            "currentPrice": row.current_price,
            "entryTime": row.entry_time,
            "marketSnapshot": dict(row.market_snapshot or {}),
            "outcomeStatus": row.outcome_status,
            "outcomePrice": row.outcome_price,
            "targetHitAt": row.target_hit_at,
            "stopHitAt": row.stop_hit_at,
            "mfePct": row.mfe_pct,
            "maePct": row.mae_pct,
            "forwardReturns": dict(row.forward_returns or {}),
            "evaluatedAt": row.evaluated_at,
            "expiresAt": row.expires_at,
            "version": row.version,
            "archivedAt": row.archived_at,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }
