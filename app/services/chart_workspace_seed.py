"""Build application defaults without putting transport or file loading in repositories."""
from app.domain.chart_workspace import WorkspaceWrite, WorkspaceDocument
from config.settings import BASE_DIR


def _defaults():
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
    return scripts, watchlist


def default_documents(kind):
    scripts, watchlist = _defaults()
    entries = scripts if kind == "scripts" else [("default", watchlist)] if kind == "watchlists" else []
    return [WorkspaceDocument(id=key, name=write.name, data=write.data, version=1, updated_at=0,
                              readonly=kind == "scripts") for key, write in entries]


def seed_workspace(store):
    scripts, watchlist = _defaults()
    store.ensure_defaults(scripts, watchlist, retired_scripts=("heimdall-v7-2",))
