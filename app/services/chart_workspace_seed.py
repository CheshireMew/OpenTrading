"""Build application defaults without putting transport or file loading in repositories."""
from app.domain.chart_workspace import WorkspaceWrite
from config.settings import BASE_DIR


def seed_workspace(store):
    scripts = [
        ("opentrading-v7-2", WorkspaceWrite(
            name="OpenTrading ETH · EMA55 · v7.2",
            data={"source": (BASE_DIR / "strategies/pine/eth_ema55_manual_chart_v7_2.pine").read_text(encoding="utf-8"),
                  "language": "pine", "kind": "indicator"},
        )),
        ("ema-zigzag-glow", WorkspaceWrite(
            name="EMA + ZigZag++（发光特效版）",
            data={"source": (BASE_DIR / "strategies/pine/ema_zigzag_glow.pine").read_text(encoding="utf-8"),
                  "language": "pine", "kind": "indicator", "libraries": ["DevLucem/ZigLib/1"]},
        )),
    ]
    watchlist = WorkspaceWrite(name="我的自选", data={"symbols": [
        "binance:spot:BTCUSDT", "binance:spot:ETHUSDT", "binance:spot:SOLUSDT",
    ]})
    store.ensure_defaults(scripts, watchlist, retired_scripts=("heimdall-v7-2",))
