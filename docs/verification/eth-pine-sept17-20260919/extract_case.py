"""Read saved project runs only; no new strategy or backtest implementation."""
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from config import settings

OUT = Path(__file__).resolve().parent
IDS = {"native": "13116fe281308330d7da0e4226f7f98f", "detail": "9cebde0a48c02fa60546d48263820a9c"}
TZ = timezone(timedelta(hours=8))


def stamp(value):
    return datetime.fromtimestamp(value / 1000, TZ).isoformat()


def millis(value):
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def main():
    db = build_database_runtime(settings)
    service = LocalBacktestService(db)
    start = millis("2026-09-17T01:15:00+08:00")
    end = millis("2026-09-17T08:00:00+08:00")
    try:
        result = {key: service.result(run) for key, run in IDS.items()}
        candles = service.records(IDS["native"], "candles", limit=5000)["items"]
        reference = next(row for row in candles if row["timestamp"] == start)
        assert [reference[k] for k in ("open", "high", "low", "close")] == [2391.01, 2394.02, 2386.93, 2389.06]
        trades = {}
        for key, data in result.items():
            trades[key] = [dict(row, entry_local=stamp(row["entry_time"]), exit_local=stamp(row["exit_time"]), signal_local=stamp(row["entry_order_signal_time"])) for row in data["trades"] if 56 <= row["trade_id"] <= 63]
        assert [(t["side"], t["entry_price"], t["exit_price"], t["return_pct"]) for t in trades["native"]] == [(t["side"], t["entry_price"], t["exit_price"], t["return_pct"]) for t in trades["detail"]]
        assert all(not row["ambiguous"] for row in trades["detail"])
        fine_path = service.data_path(IDS["detail"], "execution_data.json")
        fine = json.loads(fine_path.read_text(encoding="utf-8"))
        losses = trades["detail"][:6]
        recovery = trades["detail"][6]
        summary = {
            "six_losses_compounded_pct": (math.prod(1 + t["return_pct"] / 100 for t in losses) - 1) * 100,
            "following_long_pct": recovery["return_pct"],
            "seven_trades_compounded_pct": (math.prod(1 + t["return_pct"] / 100 for t in losses + [recovery]) - 1) * 100,
            "three_stops_compounded_pct": (0.99 ** 3 - 1) * 100,
            "execution_resolves_focal_ambiguities": True,
            "protection_update": "15-minute signal close in BOTH runs; 5-minute data resolves fills only",
        }
        output = {
            "symbol": "Binance ETH/USDT spot", "timezone": "+08:00", "run_ids": IDS,
            "scope": "Diagnose screenshot; no parameter changes. Timestamps identify candle starts, not exact ticks.",
            "reference_candle": reference, "summary": summary, "trades": trades,
            "candles_15m": [dict(row, local=stamp(row["timestamp"])) for row in candles if start <= row["timestamp"] < end],
            "candles_5m": [dict(zip(("timestamp", "open", "high", "low", "close", "volume"), row), local=stamp(row[0])) for row in fine if start <= row[0] < end],
            "indicators": [row for row in result["native"]["indicators"] if start <= row["timestamp"] < end],
            "artifacts": {key: service.artifacts(run) for key, run in IDS.items()},
            "limits": "Project companion strategy reproduced this case; not a TradingView compiler/runtime verification or evidence about live execution. Fine candles can still have internal ordering ambiguity in other trades.",
        }
        (OUT / "case-result.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(json.dumps([t for t in trades["detail"] if t["trade_id"] in (56, 62)], ensure_ascii=False, indent=2))
    finally:
        db.dispose()


if __name__ == "__main__":
    main()
