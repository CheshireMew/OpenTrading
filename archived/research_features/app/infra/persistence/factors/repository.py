from __future__ import annotations

from typing import Any

from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import FactorDataset, FactorDatasetRow, FactorResearchRun


class FactorResearchRepository:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def get_dataset_by_signature(self, signature: str) -> dict[str, Any] | None:
        with self.database_runtime.session_scope() as session:
            dataset = session.query(FactorDataset).filter(FactorDataset.signature == signature).first()
            if not dataset:
                return None
            return self._serialize_dataset(dataset)

    def get_dataset_rows(self, dataset_id: int) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            rows = (
                session.query(FactorDatasetRow)
                .filter(FactorDatasetRow.dataset_id == dataset_id)
                .order_by(FactorDatasetRow.timestamp.asc())
                .all()
            )
            return [
                {
                    "timestamp": row.timestamp,
                    "close": row.close,
                    "volume": row.volume,
                    "raw_values": dict(row.raw_values or {}),
                    "feature_values": dict(row.feature_values or {}),
                    "labels": dict(row.labels or {}),
                }
                for row in rows
            ]

    def create_dataset(
        self,
        *,
        signature: str,
        symbol: str,
        timeframe: str,
        start_date,
        end_date,
        primary_horizon: int,
        forward_horizons: list[int],
        factor_ids: list[str],
        categories: list[str],
        cleaning: dict[str, Any],
        row_count: int,
        dataset_info: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with self.database_runtime.session_scope() as session:
            dataset = session.query(FactorDataset).filter(FactorDataset.signature == signature).first()
            if dataset:
                return self._serialize_dataset(dataset)

            dataset = FactorDataset(
                signature=signature,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                primary_horizon=primary_horizon,
                forward_horizons=list(forward_horizons),
                factor_ids=list(factor_ids),
                categories=list(categories),
                cleaning=dict(cleaning),
                row_count=row_count,
                dataset_info=dict(dataset_info),
            )
            session.add(dataset)
            session.flush()
            if rows:
                session.bulk_save_objects(
                    [
                        FactorDatasetRow(
                            dataset_id=dataset.id,
                            timestamp=row["timestamp"],
                            close=row["close"],
                            volume=row["volume"],
                            raw_values=row["raw_values"],
                            feature_values=row["feature_values"],
                            labels=row["labels"],
                        )
                        for row in rows
                    ]
                )
                session.flush()
            return self._serialize_dataset(dataset)

    def create_research_run(
        self,
        *,
        dataset_id: int,
        request_payload: dict[str, Any],
        summary: dict[str, Any],
        ranking: list[dict[str, Any]],
        details: list[dict[str, Any]],
        blend: dict[str, Any],
        status: str = "completed",
        error: str | None = None,
    ) -> dict[str, Any]:
        with self.database_runtime.session_scope() as session:
            run = FactorResearchRun(
                dataset_id=dataset_id,
                status=status,
                request_payload=dict(request_payload),
                summary=dict(summary),
                ranking=list(ranking),
                details=list(details),
                blend=dict(blend),
                error=error,
            )
            session.add(run)
            session.flush()
            return self._serialize_research_run(run)

    def list_research_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            rows = (
                session.query(FactorResearchRun)
                .order_by(FactorResearchRun.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._serialize_research_run(row, include_details=False) for row in rows]

    def get_research_run(self, run_id: int) -> dict[str, Any] | None:
        with self.database_runtime.session_scope() as session:
            row = session.query(FactorResearchRun).filter(FactorResearchRun.id == run_id).first()
            if not row:
                return None
            return self._serialize_research_run(row, include_details=True)

    def _serialize_dataset(self, dataset: FactorDataset) -> dict[str, Any]:
        return {
            "id": dataset.id,
            "signature": dataset.signature,
            "symbol": dataset.symbol,
            "timeframe": dataset.timeframe,
            "start_date": dataset.start_date,
            "end_date": dataset.end_date,
            "primary_horizon": dataset.primary_horizon,
            "forward_horizons": list(dataset.forward_horizons or []),
            "factor_ids": list(dataset.factor_ids or []),
            "categories": list(dataset.categories or []),
            "cleaning": dict(dataset.cleaning or {}),
            "row_count": dataset.row_count,
            "dataset_info": dict(dataset.dataset_info or {}),
            "created_at": dataset.created_at,
        }

    def _serialize_research_run(self, run: FactorResearchRun, *, include_details: bool = True) -> dict[str, Any]:
        payload = {
            "id": run.id,
            "dataset_id": run.dataset_id,
            "status": run.status,
            "request": dict(run.request_payload or {}),
            "summary": dict(run.summary or {}),
            "ranking": list(run.ranking or []),
            "blend": dict(run.blend or {}),
            "error": run.error,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
        if include_details:
            payload["details"] = list(run.details or [])
        return payload
