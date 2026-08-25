from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.application.persistence_ports import ResearchRepositoryPort, TradeSignalRepositoryPort
from app.application.research_report_ports import ResearchReportRepositoryPort
from app.contracts.research import (
    ResearchArchiveCommand,
    ResearchReportGenerateCommand,
    ResearchReportPageResponse,
    ResearchReportResponse,
)
from app.contracts.portfolios import PortfolioAnalyticsCommand
from app.infra.executor import run_database


class ResearchReportService:
    def __init__(
        self,
        *,
        repository: ResearchReportRepositoryPort,
        research_repository: ResearchRepositoryPort,
        signal_repository: TradeSignalRepositoryPort,
        portfolio_service,
        data_health_service,
        asset_research_service,
        portfolio_analytics_service=None,
    ) -> None:
        self._repository = repository
        self._research = research_repository
        self._signals = signal_repository
        self._portfolios = portfolio_service
        self._health = data_health_service
        self._assets = asset_research_service
        self._portfolio_analytics = portfolio_analytics_service

    async def generate(self, command: ResearchReportGenerateCommand) -> ResearchReportResponse:
        now = datetime.now(timezone.utc)
        period_days = 7 if command.reportType == "weekly_brief" else 1
        period_start = now - timedelta(days=period_days)
        workbench_task = run_database(lambda: self._research.get_workbench(event_limit=200, note_limit=200))
        events_task = run_database(
            lambda: self._research.list_events(
                kind=None,
                unacknowledged_only=False,
                since=period_start.replace(tzinfo=None),
                limit=5_000,
            )
        )
        stats_task = run_database(self._signals.get_stats)
        signals_task = run_database(
            lambda: self._signals.list_signals(
                symbol=command.symbol.upper() if command.symbol else None,
                outcome_status=None,
                source=None,
                include_archived=False,
                offset=0,
                limit=50,
            )
        )
        health_task = self._health.get_health()
        workbench, event_result, stats, signal_result, health = await asyncio.gather(
            workbench_task, events_task, stats_task, signals_task, health_task
        )
        period_events, _ = event_result
        signal_rows, _ = signal_result
        portfolio = None
        portfolio_analytics = None
        portfolio_id = command.portfolioId
        generation_issues: list[str] = []
        asset = None
        if not portfolio_id and command.reportType in {"daily_brief", "weekly_brief", "decision_review"} and hasattr(self._portfolios, "get_collection"):
            try:
                collection = await run_database(self._portfolios.get_collection)
                portfolio_id = collection.snapshot.activePortfolioId or None
            except Exception as exc:
                generation_issues.append(f"当前组合不可用：{exc}")
        if portfolio_id:
            try:
                portfolio = (await run_database(lambda: self._portfolios.get_ledger(portfolio_id))).model_dump(
                    mode="json"
                )
                if self._portfolio_analytics is not None:
                    portfolio_analytics = (
                        await self._portfolio_analytics.analyze(
                            portfolio_id,
                            PortfolioAnalyticsCommand(periodDays=365, benchmarkSymbol="BTC/USDT"),
                        )
                    ).model_dump(mode="json")
            except Exception as exc:
                generation_issues.append(f"组合分析不可用：{exc}")
        if command.symbol:
            asset = (await self._assets.get_asset(symbol=command.symbol, timeframe="1h", history_days=365)).model_dump(
                mode="json"
            )
        snapshot = {
            "generatedAt": now.isoformat(),
            "period": {"start": period_start.isoformat(), "end": now.isoformat(), "days": period_days},
            "scope": {"reportType": command.reportType, "symbol": command.symbol, "portfolioId": portfolio_id},
            "research": {
                "watchItems": [item for item in workbench["items"] if not item.get("archivedAt")],
                "recentNotes": [item for item in workbench["notes"] if not item.get("archivedAt")][:30],
                "recentEvents": workbench["events"][:50],
                "watchlistChanges": [
                    event for event in period_events
                    if event.get("entityType") in {"watchlist", "watch_item"}
                ],
                "triggeredAlerts": [event for event in period_events if event.get("kind") == "alert_triggered"],
            },
            "signals": {"stats": stats, "items": signal_rows},
            "dataHealth": health.model_dump(mode="json"),
            "portfolio": portfolio,
            "portfolioAnalytics": portfolio_analytics,
            "asset": asset,
            "generationIssues": generation_issues,
        }
        content = self._render(command, snapshot)
        row = await run_database(
            lambda: self._repository.create_report(
                {
                    "title": command.title.strip(),
                    "report_type": command.reportType,
                    "symbol": command.symbol.strip().upper() if command.symbol else None,
                    "portfolio_id": portfolio_id,
                    "content_markdown": content,
                    "data_snapshot": snapshot,
                }
            )
        )
        return ResearchReportResponse.model_validate(row)

    def list_reports(self, *, include_archived: bool, offset: int, limit: int) -> ResearchReportPageResponse:
        rows, total = self._repository.list_reports(include_archived=include_archived, offset=offset, limit=limit)
        return ResearchReportPageResponse(items=rows, total=total)

    def get_report(self, report_id: str) -> ResearchReportResponse:
        return ResearchReportResponse.model_validate(self._repository.get_report(report_id))

    def archive(self, report_id: str, command: ResearchArchiveCommand, *, archived: bool) -> ResearchReportResponse:
        return ResearchReportResponse.model_validate(
            self._repository.set_report_archived(report_id, command.expectedVersion, archived)
        )

    @classmethod
    def _render(cls, command, snapshot: dict[str, Any]) -> str:
        health = snapshot["dataHealth"]
        research = snapshot["research"]
        signal_stats = snapshot["signals"]["stats"]["overall"]
        lines = [
            f"# {command.title}",
            "",
            f"> 生成时间：{snapshot['generatedAt']}  ",
            f"> 报告类型：{command.reportType}",
            f"> 统计区间：{snapshot['period']['start']} 至 {snapshot['period']['end']}",
            "",
            "## 结论摘要",
            "",
            f"- 当前研究标的 {len(research['watchItems'])} 个，近期笔记 {len(research['recentNotes'])} 条。",
            f"- 已记录交易信号 {signal_stats['total']} 条；已明确结果 {signal_stats['resolved']} 条；目标命中率 {cls._percent(signal_stats.get('winRatePct'))}。",
            f"- 数据健康状态：{health['status']}；异常或过期数据源 {health['summary'].get('problemSourceCount', 0)} 个。",
            f"- 本期研究清单变更 {len(research['watchlistChanges'])} 次，提醒触发 {len(research['triggeredAlerts'])} 次。",
            "",
        ]
        if snapshot.get("asset"):
            asset = snapshot["asset"]
            lines.extend(
                [
                    f"## 资产：{asset['symbol']}",
                    "",
                    f"- 当前价格：{asset.get('currentPrice') if asset.get('currentPrice') is not None else '不可用'}",
                    f"- RSI：{(asset.get('indicators') or {}).get('rsi', '不可用')}",
                    f"- 关联研究判断：{len(asset.get('watchItems') or [])} 条；提醒：{len(asset.get('alerts') or [])} 条；信号：{len(asset.get('signals') or [])} 条。",
                    "",
                ]
            )
            for item in asset.get("watchItems") or []:
                lines.extend(
                    [
                        f"### 当前判断（{item['symbol']}）",
                        "",
                        item.get("thesis") or "尚未记录判断。",
                        "",
                        f"目标价：{item.get('targetPrice') or '未设'}；失效价：{item.get('invalidationPrice') or '未设'}。",
                        "",
                    ]
                )
        if snapshot.get("portfolio"):
            summary = snapshot["portfolio"]["summary"]
            lines.extend(
                [
                    "## 组合概览",
                    "",
                    f"- 总权益：{summary['totalEquity']:.2f}",
                    f"- 总损益：{summary['totalPnl']:.2f}；简单收益率：{cls._percent(summary.get('simpleReturnPct'))}；MWR/XIRR：{cls._percent(summary.get('moneyWeightedReturnPct'))}。",
                    f"- 已实现损益：{summary['realizedPnl']:.2f}；未实现损益：{summary['unrealizedPnl']:.2f}；费用：{summary['totalFees']:.2f}。",
                    "",
                ]
            )
        if snapshot.get("portfolioAnalytics"):
            analytics = snapshot["portfolioAnalytics"]
            lines.extend(
                [
                    "## 组合收益与风险",
                    "",
                    f"- TWR：{cls._percent(analytics.get('timeWeightedReturnPct'))}；MWR：{cls._percent(analytics.get('moneyWeightedReturnPct'))}；基准收益：{cls._percent(analytics.get('benchmarkReturnPct'))}；超额收益：{cls._percent(analytics.get('excessReturnPct'))}。",
                    f"- 年化波动：{cls._percent(analytics.get('annualizedVolatilityPct'))}；最大回撤：{cls._percent(analytics.get('maxDrawdownPct'))}；95% VaR：{analytics.get('valueAtRisk95') if analytics.get('valueAtRisk95') is not None else '--'}。",
                    f"- HHI：{analytics.get('concentrationHhi')}；最大单项权重：{cls._percent(analytics.get('topPositionWeightPct'))}；有效持仓数：{analytics.get('effectivePositionCount') or '--'}。",
                    "",
                    "### 压力情景",
                    "",
                    "| 情景 | 预计损益 | 预计收益率 | 预计权益 |",
                    "|---|---:|---:|---:|",
                ]
            )
            for scenario in analytics.get("scenarios") or []:
                lines.append(
                    f"| {scenario['name']} | {scenario['projectedPnl']:.2f} | {cls._percent(scenario.get('projectedReturnPct'))} | {scenario['projectedEquity']:.2f} |"
                )
            if analytics.get("issues"):
                lines.extend(["", "风险分析缺口：" + "；".join(analytics["issues"]), ""])
        lines.extend(
            [
                "## 交易信号校准",
                "",
                "| 来源 | 总数 | 已明确 | 目标命中率 | 平均 MFE | 平均 MAE |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in snapshot["signals"]["stats"].get("bySource", []):
            lines.append(
                f"| {row['key']} | {row['total']} | {row['resolved']} | {cls._percent(row.get('winRatePct'))} | {cls._percent(row.get('averageMfePct'))} | {cls._percent(row.get('averageMaePct'))} |"
            )
        lines.extend(
            [
                "",
                "### 置信度校准",
                "",
                "| 置信度 | 总数 | 已明确 | 期望胜率 | 实际胜率 | 校准差 |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in snapshot["signals"]["stats"].get("confidenceCalibration", []):
            lines.append(
                f"| {row['key']} | {row['total']} | {row['resolved']} | {cls._percent(row.get('expectedWinRatePct'))} | {cls._percent(row.get('winRatePct'))} | {cls._percent(row.get('calibrationGapPct'))} |"
            )
        lines.extend(["", "### 按策略", "", "| 策略 | 总数 | 已明确 | 目标命中率 |", "|---|---:|---:|---:|"])
        for row in snapshot["signals"]["stats"].get("byStrategy", []):
            lines.append(
                f"| {row['key']} | {row['total']} | {row['resolved']} | {cls._percent(row.get('winRatePct'))} |"
            )
        lines.extend(["", "## 本期研究清单变更", ""])
        if research["watchlistChanges"]:
            for event in research["watchlistChanges"]:
                lines.append(f"- {event['occurredAt']} · {event['title']}")
        else:
            lines.append("- 本期无变更。")
        lines.extend(["", "## 本期已触发提醒", ""])
        if research["triggeredAlerts"]:
            for event in research["triggeredAlerts"]:
                lines.append(f"- {event['occurredAt']} · {event['title']}：{event.get('body') or '--'}")
        else:
            lines.append("- 本期无提醒触发。")
        if snapshot.get("generationIssues"):
            lines.extend(["", "## 生成缺口", ""])
            lines.extend(f"- {issue}" for issue in snapshot["generationIssues"])
        lines.extend(["", "## 数据质量", "", "| 数据源 | 状态 | 记录数 | 说明 |", "|---|---|---:|---|"])
        for source in health["sources"]:
            lines.append(
                f"| {source['name']} | {source['status']} | {source['recordCount']} | {str(source.get('detail') or '').replace('|', '/')} |"
            )
        lines.extend(["", "## 最近研究笔记", ""])
        for note in research["recentNotes"][:15]:
            lines.extend(
                [
                    f"### {note['title']} · {note['symbol']}",
                    "",
                    note.get("content") or "（空）",
                    "",
                    f"记录时间：{note['occurredAt']}",
                    "",
                ]
            )
        lines.extend(
            [
                "## 口径说明",
                "",
                "本报告由 Heimdall 使用报告中保存的结构化数据快照确定性生成。市场价格和指标可能不完整；任何缺口都会保留在“数据质量”部分。报告用于研究复盘，不构成交易建议。",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _percent(value):
        return "--" if value is None else f"{float(value):.2f}%"
