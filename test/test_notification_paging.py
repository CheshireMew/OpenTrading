from datetime import datetime

from app.contracts.research import ResearchAlertCreateCommand, ResearchEventAcknowledgeCommand
from app.dependencies import get_research_service
from app.infra.persistence.research_repository import ResearchRepository
from app.main import app
from app.services.research_service import ResearchService


def test_event_api_pages_real_triggers_without_acknowledging_or_skipping_ties(
    api_harness, installed_database_runtime, monkeypatch,
):
    import app.infra.persistence.research_rows as producer

    fixed = datetime(2026, 11, 25, 0, 0)
    monkeypatch.setattr(producer, "utc_now_naive", lambda: fixed)
    repository = ResearchRepository(installed_database_runtime)
    service = ResearchService(repository)
    app.dependency_overrides[get_research_service] = lambda: service
    def trigger(value, at):
        alert = service.create_alert(ResearchAlertCreateCommand(
            symbol="BTC/USDT", name="Backlog", metric="price", operator="gt", threshold=100,
        ))
        repository.record_alert_evaluation(alert.id, value=value, evaluated_at=at, expected_version=alert.version)
    for _ in range(205):
        trigger(200, fixed)
    client = api_harness["client"]
    query = {"kind": "alert_triggered", "unacknowledged_only": True, "limit": 100}
    first = client.get("/api/v1/research/events", params=query).json()
    assert len(first["items"]) == 100
    assert first.get("nextCursor")
    # A new head item must not move the position of the already read page.
    trigger(201, datetime(2026, 11, 25, 1))
    seen = [row["id"] for row in first["items"]]
    cursor = first["nextCursor"]
    while cursor:
        page = client.get("/api/v1/research/events", params={**query, "cursor": cursor}).json()
        seen.extend(row["id"] for row in page["items"])
        cursor = page["nextCursor"]
    assert len(seen) == len(set(seen)) == 205
    assert service.list_events(kind="alert_triggered", unacknowledged_only=True, since=None, limit=1).total == 206
    service.acknowledge_event(seen[-1], ResearchEventAcknowledgeCommand(acknowledged=True))
    assert service.list_events(kind="alert_triggered", unacknowledged_only=True, since=None, limit=1).total == 205
    assert client.get("/api/v1/research/events", params={"cursor": "broken"}).status_code == 422
