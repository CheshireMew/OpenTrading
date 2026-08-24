from __future__ import annotations

from datetime import datetime
from typing import Any

from app.domain.market.dli_catalog import DLI_DISPLAY_DEFINITIONS, GROUP_DESCRIPTIONS


class DliPayloadBuilder:
    def indicator_payloads(
        self,
        history_map: dict[str, list[dict[str, Any]]],
        meta_map: dict[str, dict[str, Any]],
        display_cutoff: datetime,
        *,
        as_of: datetime,
    ) -> list[dict[str, Any]]:
        payloads = []
        for definition in DLI_DISPLAY_DEFINITIONS:
            rows = [
                item
                for item in history_map.get(definition.id, [])
                if item["timestamp"] >= display_cutoff
            ]
            meta = meta_map.get(definition.id, {})
            history = [{"date": item["date"], "value": item["value"]} for item in rows]
            last_timestamp = rows[-1]["timestamp"] if rows else None
            payloads.append(
                {
                    "indicator_id": definition.id,
                    "name": meta.get("name") or definition.label,
                    "category": meta.get("category") or "Macro",
                    "unit": meta.get("unit") or definition.unit,
                    "short_label": definition.short_label,
                    "group": definition.group,
                    "group_label": definition.group_label,
                    "group_description": GROUP_DESCRIPTIONS.get(definition.group),
                    "polarity": definition.polarity,
                    "description": definition.description,
                    "is_scored": definition.is_scored,
                    "current_value": history[-1]["value"] if history else None,
                    "last_updated": history[-1]["date"] if history else None,
                    "data_lag_days": None if last_timestamp is None else max(0, (as_of.date() - last_timestamp.date()).days),
                    "history": history,
                }
            )
        return payloads
