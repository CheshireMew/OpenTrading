from __future__ import annotations

from datetime import date
from typing import Any, Literal


from config.market_data import MarketDataConfig
from app.services.market.history.classifications import ClassificationService
from app.infra.persistence.market.history.contracts import content_hash
from app.domain.market.history.indicators import indicator_registry_hash
from app.services.market.history.indicators import PriceIndicatorService
from app.services.market.history.prices import PriceService
from app.infra.persistence.market.history.database import MarketHistoryDatabase


from app.infra.persistence.market.history.dataset_artifacts import DATASET_SCHEMA_VERSION, DatasetArtifactStore


class PriceDatasetService:
    """Build immutable partitioned datasets from formal price snapshots."""

    def __init__(self, database: MarketHistoryDatabase, config: MarketDataConfig, *,
                 prices: PriceService, indicators: PriceIndicatorService,
                 classifications: ClassificationService) -> None:
        self.root = database.root
        self.config = config
        self._database = database
        self._artifacts = DatasetArtifactStore(database, config)
        self.prices, self.indicators, self.classifications = prices, indicators, classifications

    def build(
        self,
        name: str,
        instruments: list[str],
        *,
        start: date,
        end: date,
        basis: Literal["raw", "adjusted"] = "adjusted",
        refresh: bool = False,
        cache_only: bool = False,
        provider: str | None = None,
        include_indicators: bool = True,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("dataset name is required")
        canonical_inputs = list(dict.fromkeys(instruments))
        if not canonical_inputs:
            raise ValueError("dataset requires at least one instrument")
        histories = [
            self.prices.history(
                instrument,
                start=start,
                end=end,
                basis=basis,
                refresh=refresh,
                cache_only=cache_only,
                provider=provider,
            )
            for instrument in canonical_inputs
        ]
        failed = [item for item in histories if item["status"] not in {"ok", "partial"}]
        if failed:
            reasons = [warning for item in failed for warning in item.get("warnings", [])]
            raise ValueError("dataset member failed: " + "; ".join(reasons))
        status = "ok" if all(item["status"] == "ok" for item in histories) else "partial"
        warnings = list(dict.fromkeys(
            warning for item in histories for warning in item.get("warnings", [])
        ))
        classifications = {
            item["instrument"]["canonical_code"]: self.classifications.memberships(
                item["instrument"]["canonical_code"], as_of=end,
            )
            for item in histories
        }
        registry_hash = indicator_registry_hash() if include_indicators else None
        component_identity = [
            {
                "canonical_code": item["instrument"]["canonical_code"],
                "snapshot_hash": item["artifact"]["snapshot_hash"],
                "coverage": item["coverage"],
                "classifications_as_of_end": classifications[
                    item["instrument"]["canonical_code"]
                ],
            }
            for item in histories
        ]
        dataset_hash = content_hash(
            {
                "schema_version": DATASET_SCHEMA_VERSION,
                "name": name,
                "timeframe": "1d",
                "basis": basis,
                "requested_start": start.isoformat(),
                "requested_end": end.isoformat(),
                "include_indicators": include_indicators,
                "indicator_registry_hash": registry_hash,
                "status": status,
                "warnings": warnings,
                "members": component_identity,
            }
        )
        indicator_artifacts = {
            item["instrument"]["canonical_code"]: self.indicators.materialize(
                item["instrument"]["canonical_code"], snapshot_hash=item["artifact"]["snapshot_hash"], basis=basis,
            ) for item in histories
        } if include_indicators else {}
        return self._artifacts.publish(
            dataset_hash, name=name, start=start, end=end, basis=basis,
            include_indicators=include_indicators, registry_hash=registry_hash, status=status,
            warnings=warnings, histories=histories, classifications=classifications,
            indicator_artifacts=indicator_artifacts,
        )
