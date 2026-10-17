from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.application.data_health_ports import DataHealthRepositoryPort
from app.application.errors import InvalidRequestError
from app.contracts.data_health import (
    DataHealthResponse,
    DataRepairCommand,
    DataRepairResponse,
    DataSourceHealthResponse,
)
from app.infra.executor import run_database
from app.domain.market.constants import timeframe_to_milliseconds
from app.services.market.symbol_catalog import resolve_market_asset


class DataHealthService:
    def __init__(
        self,
        *,
        repository: DataHealthRepositoryPort,
        database_verifier: Callable[[], None],
        market_query_service,
        index_data_service,
        binance_market_service,
        research_alert_runtime,
        trade_signal_runtime,
        cache_service=None,
    ) -> None:
        self._repository = repository
        self._database_verifier = database_verifier
        self._market_query = market_query_service
        self._indexes = index_data_service
        self._binance = binance_market_service
        self._alerts = research_alert_runtime
        self._signals = trade_signal_runtime
        self._cache = cache_service

    async def get_health(self) -> DataHealthResponse:
        checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        snapshot = await run_database(self._repository.snapshot)
        sources = [
            self._database_source(snapshot),
            self._kline_source(snapshot, checked_at),
            self._indicator_source(snapshot, checked_at),
            self._research_series_source(snapshot, checked_at),
        ]
        sources.extend(self._runtime_sources(snapshot, checked_at))
        if self._cache is not None:
            sources.append(self._cache_source())
        sources.append(await self._binance_source(checked_at))
        meaningful = [source for source in sources if source.id != "database"]
        if meaningful and all(source.status == "empty" for source in meaningful):
            status = "empty"
        elif any(source.status in {"stale", "failed", "stopped"} for source in sources):
            status = "degraded"
        else:
            status = "healthy"
        return DataHealthResponse(
            status=status,
            checkedAt=checked_at,
            databaseRevision=snapshot.get("databaseRevision"),
            sources=sources,
            summary={
                **snapshot["counts"],
                "sourceCount": len(sources),
                "problemSourceCount": sum(source.status not in {"ready", "starting", "empty"} for source in sources),
            },
        )

    async def repair(self, command: DataRepairCommand) -> DataRepairResponse:
        started = datetime.now(timezone.utc).replace(tzinfo=None)
        result: dict[str, Any] = {}
        if command.action == "verify_database":
            await run_database(self._database_verifier)
            detail = "数据库迁移版本、表和模型结构一致"
        elif command.action == "refresh_binance_snapshot":
            await self._binance.snapshot_service.seed(
                spot_ticker_loader=self._binance.spot.get_ticker_24hr,
                usdm_ticker_loader=self._binance.usdm.get_ticker_24hr,
                usdm_mark_loader=self._binance.usdm.get_mark_price,
                force=True,
            )
            result = self._binance.snapshot_service.health_snapshot()
            detail = "币安现货、合约与标记价格快照已重新拉取"
        elif command.action == "hydrate_symbol_history":
            if not command.symbol:
                raise InvalidRequestError("补齐历史数据必须指定标的")
            resolved = resolve_market_asset(command.symbol)
            if resolved is None or resolved["asset_class"] == "cash":
                raise InvalidRequestError("该标的不支持历史数据补齐")
            start = (datetime.now(timezone.utc).date() - timedelta(days=command.days)).isoformat()
            if resolved["asset_class"] == "index":
                response = await self._indexes.get_pricing_history_async(
                    symbol=resolved["symbol"], timeframe="1d", start_date=start
                )
                result = {"symbol": resolved["symbol"], "pointCount": len(response.data), "source": response.source}
            else:
                response = await self._market_query.get_full_history(
                    symbol=resolved["symbol"], timeframe=command.timeframe, start_date=start, fetch_policy="hydrate"
                )
                result = {
                    "symbol": resolved["symbol"],
                    "pointCount": len(response.items),
                    "coverageComplete": response.coverage.complete,
                }
            detail = f"{resolved['symbol']} 的历史数据已检查并补齐可获取区间"
        elif command.action == "evaluate_research_alerts":
            response = await self._alerts.evaluate_once()
            result = response.model_dump(mode="json")
            detail = f"已检查 {response.evaluatedCount} 条提醒"
        else:
            response = await self._signals.evaluate_once(force=True)
            result = response.model_dump(mode="json")
            detail = f"已评估 {response.evaluatedCount} 条交易信号"
        completed = datetime.now(timezone.utc).replace(tzinfo=None)
        return DataRepairResponse(
            action=command.action,
            status="completed",
            startedAt=started,
            completedAt=completed,
            detail=detail,
            result=result,
        )

    @staticmethod
    def _database_source(snapshot) -> DataSourceHealthResponse:
        return DataSourceHealthResponse(
            id="database",
            name="数据库结构",
            status="ready",
            recordCount=sum(snapshot["counts"].values()),
            detail=f"Alembic {snapshot.get('databaseRevision') or 'unknown'}",
            metadata=snapshot["counts"],
            repairActions=["verify_database"],
        )

    @classmethod
    def _kline_source(cls, snapshot, now) -> DataSourceHealthResponse:
        rows = snapshot["klines"]
        count = sum(row["count"] for row in rows)
        latest = max((row["last"] for row in rows if row["last"]), default=None)
        first = min((row["first"] for row in rows if row["first"]), default=None)
        end = cls._from_ms(latest)
        age = (now - end).total_seconds() if end else None
        series = []
        total_gaps = 0
        for row in rows:
            interval_ms = timeframe_to_milliseconds(row["timeframe"])
            expected = (
                int((row["last"] - row["first"]) // interval_ms) + 1
                if interval_ms > 0 and row["first"] is not None and row["last"] is not None
                else row["count"]
            )
            gaps = max(expected - row["count"], 0)
            total_gaps += gaps
            series.append({
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "count": row["count"],
                "expectedCount": expected,
                "gapCount": gaps,
            })
        status = "empty" if not rows else "stale" if total_gaps > 0 or (age is not None and age > 7 * 86400) else "ready"
        return DataSourceHealthResponse(
            id="klines",
            name="K 线缓存",
            status=status,
            recordCount=count,
            coverageStart=cls._from_ms(first),
            coverageEnd=end,
            ageSeconds=max(age, 0) if age is not None else None,
            gapCount=total_gaps,
            detail=f"{len(rows)} 个标的/周期序列，{total_gaps} 个缺口",
            metadata={"seriesCount": len(rows), "series": series},
            repairActions=["hydrate_symbol_history"],
        )

    @staticmethod
    def _indicator_source(snapshot, now) -> DataSourceHealthResponse:
        rows = snapshot["indicators"]
        count = sum(row["count"] for row in rows)
        latest = max((row["last"] for row in rows if row["last"]), default=None)
        first = min((row["first"] for row in rows if row["first"]), default=None)
        age = (now - latest).total_seconds() if latest else None
        status = "empty" if not rows else "stale" if age is not None and age > 48 * 3600 else "ready"
        return DataSourceHealthResponse(
            id="market_indicators",
            name="市场信号指标",
            status=status,
            recordCount=count,
            coverageStart=first,
            coverageEnd=latest,
            ageSeconds=max(age, 0) if age is not None else None,
            detail=f"{len(rows)} 个指标",
            metadata={"indicatorCount": len(rows)},
            repairActions=[],
        )

    @classmethod
    def _research_series_source(cls, snapshot, now) -> DataSourceHealthResponse:
        rows = snapshot["researchSeries"]
        count = sum(row["count"] for row in rows)
        latest = max((row["last"] for row in rows if row["last"]), default=None)
        first = min((row["first"] for row in rows if row["first"]), default=None)
        end = cls._from_ms(latest)
        age = (now - end).total_seconds() if end else None
        series = []
        computable = 0
        total_gaps = 0
        for row in rows:
            interval_ms = timeframe_to_milliseconds(row.get("period") or "")
            gaps = None
            expected = None
            if interval_ms > 0 and row["first"] is not None and row["last"] is not None:
                expected = int((row["last"] - row["first"]) // interval_ms) + 1
                gaps = max(expected - row["count"], 0)
                computable += 1
                total_gaps += gaps
            series.append({**row, "expectedCount": expected, "gapCount": gaps})
        status = "empty" if not rows else "stale" if total_gaps > 0 or (age is not None and age > 7 * 86400) else "ready"
        return DataSourceHealthResponse(
            id="binance_research_series",
            name="币安研究序列",
            status=status,
            recordCount=count,
            coverageStart=cls._from_ms(first),
            coverageEnd=end,
            ageSeconds=max(age, 0) if age is not None else None,
            gapCount=total_gaps if computable else None,
            detail=f"{len(rows)} 组持久化序列，{computable} 组可计算缺口",
            metadata={"seriesCount": len(rows), "gapComputableSeriesCount": computable, "series": series},
            repairActions=["refresh_binance_snapshot"],
        )

    @staticmethod
    def _runtime_sources(snapshot, now):
        result = []
        for row in snapshot["runtime"]:
            age = max((now - row["heartbeatAt"]).total_seconds(), 0)
            status = row["status"] if row["status"] in {"ready", "failed", "stopped", "starting"} else "ready"
            status = "stale" if age > 120 and status == "ready" else status
            result.append(
                DataSourceHealthResponse(
                    id=f"runtime:{row['component']}",
                    name=f"运行组件：{row['component']}",
                    status=status,
                    recordCount=0,
                    coverageEnd=row["lastSuccessAt"],
                    ageSeconds=age,
                    lastSuccessAt=row["lastSuccessAt"],
                    lastFailureAt=row["lastFailureAt"],
                    nextRunAt=row["nextRunAt"],
                    detail=row["errorDetail"] or row["errorCode"] or "心跳正常",
                    metadata={},
                    repairActions=[],
                )
            )
        return result

    def _cache_source(self) -> DataSourceHealthResponse:
        backend = self._cache.runtime_backend
        fallback = backend == "memory_fallback"
        return DataSourceHealthResponse(
            id="runtime_cache",
            name="运行缓存",
            status="ready",
            recordCount=int(self._cache.local_entry_count),
            detail="本地内存回退可用（Redis 未连接）" if fallback else "Redis 与本地二级缓存可用",
            metadata={
                "backend": backend,
                "localEntryCount": int(self._cache.local_entry_count),
                "localByteSize": int(self._cache.local_byte_size),
                "redisOptional": True,
            },
            repairActions=[],
        )

    async def _binance_source(self, now):
        health = self._binance.snapshot_service.health_snapshot()
        data = await self._binance.snapshot_service.get_market_page_snapshot_data()
        count = sum(len(data.get(key, {}).get("items", [])) for key in ("spot_ticker", "usdm_ticker", "usdm_mark"))
        updated = data.get("updated_at")
        end = self._from_ms(updated)
        age = (now - end).total_seconds() if end else None
        raw = health.get("status")
        status = raw if raw in {"ready", "failed", "stopped", "starting"} else "failed"
        return DataSourceHealthResponse(
            id="binance_live_snapshot",
            name="币安实时市场快照",
            status=status,
            recordCount=count,
            coverageEnd=end,
            ageSeconds=max(age, 0) if age is not None else None,
            detail=health.get("error") or f"{health.get('activeStreams', 0)} 条活动流",
            metadata={
                "activeStreams": health.get("activeStreams", 0),
                "seedSuccessCount": health.get("seedSuccessCount", 0),
            },
            repairActions=["refresh_binance_snapshot"],
        )

    @staticmethod
    def _from_ms(value):
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None) if value else None
