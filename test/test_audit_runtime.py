import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config.settings import AppSettings, BASE_DIR
from app.services.chart_workspace_store import ChartWorkspaceStore
from app.services.chart_workspace_records import PineRecordStore
from app.services.tools.dca_calculator import prepare_dca_dataset, simulate_dca_schedule
from app.services.tools.pair_compare_service import PairCompareService


def test_runtime_root_derives_children_and_preserves_explicit_override(tmp_path, monkeypatch):
    root, logs = tmp_path / "runtime", tmp_path / "own-logs"
    settings = AppSettings(_env_file=None, RUNTIME_ROOT_DIR=root, LOG_DIR=logs)
    assert settings.LOG_DIR == logs
    assert settings.TEMP_DIR == root / "tmp"
    assert settings.LLM_CONFIG_PATH == root / "config/llm_provider_config.json"
    assert settings.BACKGROUND_RUNTIME_LOCK_PATH == root / "runtime/background.lock"
    import config
    monkeypatch.setattr(config, "settings", settings)
    assert ChartWorkspaceStore().root == root / "chart_workspace"
    assert AppSettings(_env_file=None).CHART_WORKSPACE_DIR == BASE_DIR / ".opentrading_runtime/chart_workspace"


@pytest.mark.parametrize("strategy", ["ema_deviation", "rsi_dynamic", "ahr999", "fear_greed", "value_averaging"])
def test_dca_future_changes_do_not_change_prior_decisions_in_utc8(strategy):
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [[start + hour * 3600000, 100 + hour % 71, 250, 50, 101 + hour % 71, 10] for hour in range(225 * 24)]
    decision = int(datetime(2025, 8, 3, 15, tzinfo=timezone.utc).timestamp() * 1000)
    changed = [row[:] if row[0] < decision else [row[0], row[1], 9000, 1, 8000, 10] for row in rows]
    results = []
    for data in (rows, changed):
        frame = prepare_dca_dataset(data, timezone="Asia/Shanghai", start_dt_local=datetime(2025, 8, 1), target_hour=23)
        frame = frame[frame.timestamp <= decision]
        assert frame.iloc[-1].datetime.hour == 15
        history, _, _ = simulate_dca_schedule(frame, daily_investment=100, strategy=strategy,
                                              strategy_params={"fee_rate": 0}, sentiment_map={"2025-08-02": 20})
        results.append(history)
    assert results[0] == results[1]
    assert len(results[0]) == 3


def test_close_ratio_never_claims_independent_extremes():
    service = PairCompareService(object(), object())
    point = service._calculate_ratio_ohlc([[0, 100, 120, 80, 110, 1]], [[0, 10, 100, 5, 20, 1]])[0]
    assert point["open"] == point["high"] == point["low"] == point["close"] == 5.5


def test_pages_retain_all_records_without_reopening_large_snapshots(tmp_path, monkeypatch):
    equity = [{"time": index, "equity": 100 + index} for index in range(20201)]
    (tmp_path / "input.json").write_text(json.dumps({"bars": [{"time": 1}]}), encoding="utf-8")
    (tmp_path / "result.json").write_text(json.dumps({"equity": equity, "trades": [{"id": 1}]}), encoding="utf-8")
    store = PineRecordStore(tmp_path)
    assert store.page("equity", 0, 10000)["items"] == equity[:10000]
    original = Path.read_text

    def no_snapshot_read(path, *args, **kwargs):
        assert path.suffix != ".json", "page query reopened the complete snapshot"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", no_snapshot_read)
    assert store.page("equity", 10000, 10000)["items"] == equity[10000:20000]
    assert store.page("equity", 20000, 10000)["items"] == equity[20000:]
    assert store.page("bars", 0, 1)["items"] == [{"time": 1}]
    assert store.page("trades", 0, 1)["items"] == [{"id": 1}]


def test_all_generator_outputs_have_a_drift_gate(tmp_path):
    from scripts.generate_frontend_contracts import render_outputs, stale_outputs
    generated = render_outputs()
    assert len(generated) == 8
    outputs = {tmp_path / str(index): content for index, content in enumerate(generated.values())}
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")
    assert not stale_outputs(outputs)
    for path, content in outputs.items():
        path.write_text(content + "// drift", encoding="utf-8")
        assert stale_outputs(outputs) == [path]
        path.write_text(content, encoding="utf-8")


def test_prepare_db_never_logs_connection_credentials(tmp_path, caplog):
    from app.infra.db.database import DatabaseRuntime
    from app.infra.db.schema_runtime import prepare_db
    sentinel = "synthetic-password-never-log"
    url = f"sqlite:///{(tmp_path / 'logs.db').as_posix()}?password={sentinel}"
    runtime = DatabaseRuntime(database_url=url, source="test")
    try:
        with caplog.at_level("INFO"):
            prepare_db(runtime)
        assert "dialect=sqlite" in caplog.text
        assert sentinel not in caplog.text and url not in caplog.text
    finally:
        runtime.dispose()


@pytest.mark.parametrize("valid", [True, False])
def test_prepare_db_launch_output_is_safe_and_keeps_failure_exit(tmp_path, valid):
    sentinel = "synthetic-launch-password-never-log"
    url = f"sqlite:///{(tmp_path / 'launch.db').as_posix()}?password={sentinel}" if valid else f"sqlite://user:{sentinel}@invalid/database"
    environment = {**os.environ, "DATABASE_URL": url, "RUNTIME_ROOT_DIR": str(tmp_path / "runtime"), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", "-m", "scripts.prepare_db"], cwd=BASE_DIR,
                            env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == (0 if valid else 1)
    assert sentinel not in output and url not in output
    assert ("dialect=sqlite" if valid else "ArgumentError") in output
