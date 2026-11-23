from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import math
from pathlib import Path
from threading import Condition, Lock
from typing import Any, Callable, Protocol

from config.market_data import MarketDataConfig
from app.infra.market_data.fred_client import FredObservationClient
from app.infra.market_data.http import HttpPolicy, HttpTransport, UrllibJsonTransport
from app.infra.persistence.market.history.snapshots import RawSnapshotStore
from app.infra.persistence.market.history import MarketHistoryDatabase
from app.infra.persistence.market.history.macro_repository import IndicatorRepository
from app.infra.persistence.market.history.projections import DatabaseProjection


from app.domain.market.liquidity_definitions import (
    DISPLAY_DEFINITIONS,
    FRESHNESS_DAYS_BY_FREQUENCY,
    GROUP_DESCRIPTIONS,
    RAW_SOURCE_DEFINITIONS,
    SCORED_IDS as SCORED_IDS,
    SOURCE_DEFINITIONS,
    SOURCE_IDS,
    LiquidityIndicatorDefinition,
)
from app.domain.market.liquidity_scoring import LiquidityScoreEngine


_SYNC_LOCK = Lock()
_BUILD_CONDITION = Condition()
_BUILD_CACHE: dict[tuple[str, str, int, int, str], dict[str, Any]] = {}
_BUILD_INFLIGHT: set[tuple[str, str, int, int, str]] = set()


class LiquidityDataClient(Protocol):
    def fetch_fred(self, provider_series_id: str, start: date, end: date) -> list[dict[str, Any]]: ...

    def fetch_tga(self, start: date, end: date) -> list[dict[str, Any]]: ...


class PublicLiquidityClient:
    """Fetch latest-revised monitoring series from public official endpoints."""

    treasury_url = (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
        "accounting/dts/operating_cash_balance"
    )

    def __init__(self, transport: HttpTransport | None = None) -> None:
        self.transport = transport or UrllibJsonTransport(
            HttpPolicy(timeout_seconds=30.0),
        )
        self._fred = FredObservationClient(transport=self.transport)

    def fetch_fred(self, provider_series_id: str, start: date, end: date) -> list[dict[str, Any]]:
        payload, _transport_name = self._fred.fetch_latest(provider_series_id, start, end)
        rows = []
        for item in payload["observations"]:
            observation = item.get("date") or item.get("observation_date")
            raw = item.get("value")
            if not observation or raw in {None, "", "."}:
                continue
            value = float(str(raw))
            if math.isfinite(value):
                rows.append({"observation_date": date.fromisoformat(observation[:10]), "value": value})
        if not rows:
            raise ValueError(f"FRED public CSV returned no usable rows for {provider_series_id}")
        return rows

    def fetch_tga(self, start: date, end: date) -> list[dict[str, Any]]:
        points: dict[date, float] = {}
        account_types = (
            "Federal Reserve Account",
            "Treasury General Account (TGA) Closing Balance",
        )
        for account_type in account_types:
            page = 1
            total_pages = 1
            while page <= total_pages:
                params = {
                    "fields": "record_date,account_type,open_today_bal,close_today_bal",
                    "filter": (
                        f"record_date:gte:{start.isoformat()},record_date:lte:{end.isoformat()},"
                        f"account_type:eq:{account_type}"
                    ),
                    "sort": "record_date",
                    "page[number]": str(page),
                    "page[size]": "1000",
                }
                payload = self.transport.get_json(
                    self.treasury_url,
                    params,
                    {"Accept": "application/json"},
                )
                total_pages = int(payload.get("meta", {}).get("total-pages") or 1)
                for item in payload.get("data", []):
                    raw = item.get("close_today_bal")
                    if raw in {None, "", ".", "null"}:
                        raw = item.get("open_today_bal")
                    if raw in {None, "", ".", "null"}:
                        continue
                    points[date.fromisoformat(item["record_date"])] = float(raw)
                page += 1
        if not points:
            raise ValueError("Treasury Fiscal Data returned no usable TGA rows")
        return [
            {"observation_date": observation_date, "value": value}
            for observation_date, value in sorted(points.items())
        ]

def liquidity_definitions() -> list[dict[str, Any]]:
    output = []
    for definition in (*DISPLAY_DEFINITIONS, *RAW_SOURCE_DEFINITIONS):
        payload = asdict(definition)
        payload["category"] = "Macro"
        output.append(payload)
    return output


def sync_liquidity_data(
    root: Path,
    config: MarketDataConfig,
    client: LiquidityDataClient | None = None,
    *,
    start: date | None = None,
    end: date | None = None,
    retrieved_at: datetime | None = None,
) -> dict[str, Any]:
    if not _SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError("liquidity refresh is already in progress")
    try:
        return _sync_liquidity_data(
            root, config, client, start=start, end=end, retrieved_at=retrieved_at,
        )
    finally:
        _SYNC_LOCK.release()


def _sync_liquidity_data(
    root: Path,
    config: MarketDataConfig,
    client: LiquidityDataClient | None = None,
    *,
    start: date | None = None,
    end: date | None = None,
    retrieved_at: datetime | None = None,
) -> dict[str, Any]:
    client = client or PublicLiquidityClient()
    end = end or date.today()
    start = start or date(end.year - 10, end.month, min(end.day, 28))
    retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    database = MarketHistoryDatabase(root)
    indicators = IndicatorRepository(database)
    indicators.upsert_indicator_series(liquidity_definitions())
    snapshots = RawSnapshotStore(root, config)
    def fetch(definition: LiquidityIndicatorDefinition) -> tuple[Any, ...] | None:
        if definition.provider == "treasury":
            rows = client.fetch_tga(start, end)
            resource = "treasury-tga"
            provider = "treasury-fiscal-data"
        else:
            if definition.provider_series_id is None:
                return None
            rows = client.fetch_fred(definition.provider_series_id, start, end)
            resource = f"fredgraph-{definition.provider_series_id}"
            provider = "fred-public"
        raw_payload = {
            "indicator_id": definition.indicator_id,
            "provider_series_id": definition.provider_series_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "observations": [
                {"date": item["observation_date"].isoformat(), "value": item["value"]}
                for item in rows
            ],
        }
        return definition, provider, resource, rows, raw_payload

    with ThreadPoolExecutor(max_workers=min(4, len(SOURCE_DEFINITIONS))) as executor:
        fetched = [item for item in executor.map(fetch, SOURCE_DEFINITIONS) if item is not None]

    results = []
    for definition, provider, resource, rows, raw_payload in fetched:
        snapshot = snapshots.save(provider, resource, raw_payload, retrieved_at)
        count = indicators.upsert_indicator_observations(
            definition.indicator_id,
            rows,
            source=provider,
            retrieved_at=retrieved_at,
            snapshot_hash=snapshot.snapshot_hash,
        )
        results.append(
            {
                "indicator_id": definition.indicator_id,
                "provider": provider,
                "row_count": count,
                "start": rows[0]["observation_date"].isoformat(),
                "end": rows[-1]["observation_date"].isoformat(),
                "snapshot_hash": snapshot.snapshot_hash,
            }
        )
    return {
        "retrieved_at": retrieved_at.isoformat(),
        "series_count": len(results),
        "row_count": sum(item["row_count"] for item in results),
        "series": results,
    }


class LiquidityService:
    def __init__(self, root: Path) -> None:
        self._database = MarketHistoryDatabase(root)
        self._indicators = IndicatorRepository(self._database)
        self._projection = DatabaseProjection(self._database)
        self.series_builder = LiquiditySeriesBuilder()
        self.score_engine = LiquidityScoreEngine()

    def build(
        self,
        *,
        days: int = 365,
        change_days: int = 30,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        display_days = max(30, min(days, 3650))
        change_window_days = max(1, min(change_days, 365))
        now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        revision = self._projection.indicator_revision(SOURCE_IDS)
        key = (
            self._database.cache_key, revision, display_days, change_window_days,
            now.isoformat() if as_of is not None else now.date().isoformat(),
        )
        return _cached_liquidity_build(
            key,
            lambda: self._build_uncached(display_days, change_window_days, now),
        )

    def _build_uncached(
        self,
        display_days: int,
        change_window_days: int,
        now: datetime,
    ) -> dict[str, Any]:
        display_cutoff = now - timedelta(days=display_days)
        model_cutoff = now - timedelta(days=3650)
        source_history = self._indicators.indicator_history(SOURCE_IDS, start_at=model_cutoff)
        history_map = self.series_builder.with_derived_indicators(source_history)
        points_map = self.series_builder.points_map(history_map)
        current, raw_history = self.score_engine.composite_snapshot_and_history(
            points_map,
            as_of=now,
            history_start=now - timedelta(days=1825),
            change_days=change_window_days,
        )
        raw_values = sorted(
            item["score"] for item in raw_history if item.get("score") is not None
        )
        thresholds = self.score_engine.thresholds(raw_history)
        raw_score = current["score"]
        score_percentile = self.score_engine.score_percentile_sorted(raw_score, raw_values)
        state, tone = self.score_engine.state(score_percentile)
        display_history = []
        for item in raw_history:
            if item["date"] < display_cutoff:
                continue
            percentile = self.score_engine.score_percentile_sorted(item["score"], raw_values)
            if percentile is None:
                continue
            display_history.append(
                {
                    "date": item["date"].isoformat(),
                    "score": round(percentile, 2),
                    "state": self.score_engine.state(percentile)[0],
                }
            )
        return {
            "schema_version": "signal-lab.liquidity.v1",
            "score": None if score_percentile is None else round(score_percentile),
            "raw_score": None if raw_score is None else round(raw_score, 4),
            "score_percentile": None if score_percentile is None else round(score_percentile, 2),
            "state": state,
            "tone": tone,
            "updated_at": self.series_builder.latest_update(history_map),
            "coverage": current["coverage"],
            "methodology": "pressure_z_composite_percentile_v3",
            "data_scope": "latest_revised_monitoring",
            "data_scope_note": "历史曲线使用当前可获得的最新修订值，只用于状态监控，不得直接作为点时回测输入。",
            "thresholds": thresholds,
            "components": current["components"],
            "history": display_history,
            "indicators": self._indicator_payloads(history_map, display_cutoff, now),
            "alerts": self.score_engine.alerts(current["components"], change_days=change_window_days),
        }

    @staticmethod
    def _indicator_payloads(
        history_map: dict[str, list[dict[str, Any]]],
        display_cutoff: datetime,
        as_of: datetime,
    ) -> list[dict[str, Any]]:
        output = []
        for definition in DISPLAY_DEFINITIONS:
            rows = [
                item for item in history_map.get(definition.indicator_id, [])
                if item["timestamp"] >= display_cutoff
            ][-50:]
            history = [{"date": item["date"], "value": item["value"]} for item in rows]
            last_timestamp = rows[-1]["timestamp"] if rows else None
            data_lag_days = (
                None
                if last_timestamp is None
                else max(0, (as_of.date() - last_timestamp.date()).days)
            )
            freshness_days = FRESHNESS_DAYS_BY_FREQUENCY[definition.frequency]
            output.append(
                {
                    "indicator_id": definition.indicator_id,
                    "name": definition.name,
                    "short_label": definition.short_label,
                    "category": "Macro",
                    "unit": definition.unit,
                    "group": definition.group_id,
                    "group_label": definition.group_label,
                    "group_description": GROUP_DESCRIPTIONS.get(definition.group_id, "补充监控指标。"),
                    "polarity": definition.polarity,
                    "description": definition.description,
                    "is_scored": definition.is_scored,
                    "frequency": definition.frequency,
                    "freshness_days": freshness_days,
                    "current_value": history[-1]["value"] if history else None,
                    "last_updated": history[-1]["date"] if history else None,
                    "data_lag_days": data_lag_days,
                    "is_stale": (
                        data_lag_days is not None and data_lag_days > freshness_days
                    ),
                    "history": history,
                }
            )
        return output


def _cached_liquidity_build(
    key: tuple[str, str, int, int, str],
    factory: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    while True:
        with _BUILD_CONDITION:
            cached = _BUILD_CACHE.get(key)
            if cached is not None:
                return cached
            if key not in _BUILD_INFLIGHT:
                _BUILD_INFLIGHT.add(key)
                break
            _BUILD_CONDITION.wait()
    try:
        result = factory()
    except BaseException:
        with _BUILD_CONDITION:
            _BUILD_INFLIGHT.discard(key)
            _BUILD_CONDITION.notify_all()
        raise
    with _BUILD_CONDITION:
        _BUILD_CACHE[key] = result
        while len(_BUILD_CACHE) > 24:
            oldest = next(iter(_BUILD_CACHE))
            _BUILD_CACHE.pop(oldest, None)
        _BUILD_INFLIGHT.discard(key)
        _BUILD_CONDITION.notify_all()
    return result


class LiquiditySeriesBuilder:
    def with_derived_indicators(
        self,
        history_map: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        result = {key: list(value) for key, value in history_map.items()}
        result["SOFR_IORB"] = self._derive_pair_spread(result.get("SOFR", []), result.get("IORB", []), scale=100.0)
        result["SRF_USAGE"] = list(result.get("RPONTSYD", []))
        result["BANK_CASH_BUFFER"] = self._derive_ratio_percent(
            result.get("CASACBW027SBOG", []),
            result.get("TLAACBW027SBOG", []),
        )
        result["US10Y_REAL"] = list(result.get("DFII10", []))
        result["NET_LIQUIDITY"] = self._derive_net_liquidity(
            result.get("FED_BALANCE", []),
            result.get("TGA", []),
            result.get("ONRRP", []),
        )
        return result

    @staticmethod
    def points_map(history_map: dict[str, list[dict[str, Any]]]) -> dict[str, list[tuple[datetime, float]]]:
        output: dict[str, list[tuple[datetime, float]]] = {}
        for indicator_id, rows in history_map.items():
            output[indicator_id] = sorted(
                (
                    (item["timestamp"], float(item["value"]))
                    for item in rows
                    if item.get("timestamp") is not None
                    and item.get("value") is not None
                    and math.isfinite(float(item["value"]))
                ),
                key=lambda item: item[0],
            )
        return output

    @staticmethod
    def latest_update(history_map: dict[str, list[dict[str, Any]]]) -> str | None:
        values = [
            item["timestamp"]
            for rows in history_map.values()
            for item in rows
            if item.get("timestamp") is not None
        ]
        return max(values).isoformat() if values else None

    def _derive_pair_spread(self, left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]], *, scale: float) -> list[dict[str, Any]]:
        left_raw = self._values_by_date(left_rows)
        right_raw = self._values_by_date(right_rows)
        dates = sorted(set(left_raw) | set(right_raw))
        left = self._carry_forward(left_raw, dates)
        right = self._carry_forward(right_raw, dates)
        return [self._derived_row(item, (left[item] - right[item]) * scale) for item in dates if item in left and item in right]

    def _derive_ratio_percent(self, numerator_rows: list[dict[str, Any]], denominator_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        numerator_raw = self._values_by_date(numerator_rows)
        denominator_raw = self._values_by_date(denominator_rows)
        dates = sorted(set(numerator_raw) | set(denominator_raw))
        numerator = self._carry_forward(numerator_raw, dates)
        denominator = self._carry_forward(denominator_raw, dates)
        return [
            self._derived_row(item, numerator[item] / denominator[item] * 100.0)
            for item in dates
            if item in numerator and item in denominator and denominator[item] != 0
        ]

    def _derive_net_liquidity(self, fed_rows: list[dict[str, Any]], tga_rows: list[dict[str, Any]], onrrp_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fed_raw = self._values_by_date(fed_rows)
        tga_raw = self._values_by_date(tga_rows)
        onrrp_raw = self._values_by_date(onrrp_rows)
        dates = sorted(set(fed_raw) | set(tga_raw) | set(onrrp_raw))
        fed = self._carry_forward(fed_raw, dates)
        tga = self._carry_forward(tga_raw, dates)
        onrrp = self._carry_forward(onrrp_raw, dates)
        return [
            self._derived_row(item, fed[item] - tga[item] - onrrp[item] * 1000.0)
            for item in dates
            if item in fed and item in tga and item in onrrp
        ]

    @staticmethod
    def _values_by_date(rows: list[dict[str, Any]]) -> dict[datetime, float]:
        return {
            item["timestamp"]: float(item["value"])
            for item in rows
            if isinstance(item.get("timestamp"), datetime) and item.get("value") is not None
        }

    @staticmethod
    def _carry_forward(values: dict[datetime, float], dates: list[datetime]) -> dict[datetime, float]:
        output: dict[datetime, float] = {}
        latest = None
        for item in dates:
            if item in values:
                latest = values[item]
            if latest is not None:
                output[item] = latest
        return output

    @staticmethod
    def _derived_row(timestamp: datetime, value: float) -> dict[str, Any]:
        return {"date": timestamp.date().isoformat(), "timestamp": timestamp, "value": value}
