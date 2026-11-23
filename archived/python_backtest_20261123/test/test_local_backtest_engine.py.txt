from types import SimpleNamespace
import pytest
from app.domain.local_backtest import Bar, Intent, simulate, validate_bars


def run(prices, actions, **kwargs):
    bars = [Bar(i * 60000, *values, 1) for i, values in enumerate(prices)]
    strategy = SimpleNamespace(on_bar=lambda c: actions.get(len(c.history) - 1))
    return simulate(bars, strategy, {}, warmup=0, step_ms=60000, **kwargs)


def test_signal_executes_next_open_and_marks_unrealized_drawdown():
    r = run([(100, 100, 100, 100), (100, 100, 70, 80), (80, 120, 80, 120)], {0: Intent("long")})
    assert r["trades"][0]["entry_time"] == 60000
    assert r["report"]["profit"] == 2000
    assert r["report"]["max_drawdown_pct"] == 20
    assert r["equity"][2]["unrealized"] == -2000
    assert r["trades"][0]["exit_reason"] == "end_of_backtest"
    assert r["equity"][-1]["cash"] == 12000


def test_reversal_compounds_and_records_two_fills():
    r = run([(100, 100, 100, 100), (100, 110, 100, 110), (120, 120, 100, 100)], {0: Intent("long"), 1: Intent("short")})
    assert r["report"]["profit"] == pytest.approx(4000)
    assert [f["action"] for f in r["fills"]] == ["long", "close", "short", "close"]
    assert r["trades"][1]["principal"] == 12000


@pytest.mark.parametrize("side,ohlc,expected", [("long", (100, 115, 85, 100), 90), ("short", (100, 115, 85, 100), 110)])
def test_both_levels_hit_stop_first(side, ohlc, expected):
    r = run([(100,100,100,100), ohlc], {0: Intent(side, 10, 10)})
    assert r["trades"][0]["exit_price"] == pytest.approx(expected)
    assert r["trades"][0]["ambiguous"]
    assert r["report"]["profit"] == pytest.approx(-1000)


def test_gap_uses_open_and_ignores_redundant_close():
    r = run([(100,100,100,100), (100,105,95,100), (70,80,65,75)], {0: Intent("long", 10, 20), 1: Intent("close")})
    assert r["trades"][0]["exit_price"] == 70
    assert r["trades"][0]["exit_phase"] == "open"
    assert r["signals"][1]["status"] == "ignored_flat"


def test_trailing_does_not_retroactively_hit_current_low():
    r = run([(100,100,100,100), (100,120,95,115), (115,118,105,110)], {0: Intent("long", trailing_stop_pct=10)})
    assert r["trades"][0]["exit_time"] == 120000
    assert r["trades"][0]["exit_price"] == pytest.approx(110)
    assert r["levels"][0]["stop"] == 90


def test_short_trailing_and_fixed_stop():
    r = run([(100,100,100,100), (100,104,80,85), (85,90,82,86)], {0: Intent("short", 5, trailing_stop_pct=10)})
    assert r["trades"][0]["exit_price"] == pytest.approx(90)
    assert r["levels"][0]["stop"] == 105


def test_partial_allocation_does_not_credit_short_proceeds():
    r = run([(100,100,100,100), (100,100,80,80)], {0: Intent("short")}, position_pct=50)
    assert r["report"]["profit"] == 1000
    assert r["trades"][0]["quantity"] == 50


def test_negative_equity_no_forced_liquidation_and_no_reentry():
    r = run([(100,100,100,100), (100,300,100,300), (300,300,300,300)], {0: Intent("short"), 1: Intent("long")})
    assert r["report"]["final_equity"] == -10000
    assert r["signals"][1]["status"] == "ignored_nonpositive_equity"
    assert r["trades"][0]["exit_reason"] == "reversal"


def test_flat_breakeven_and_last_signal():
    r = run([(100,100,100,100)] * 3, {0: Intent("long"), 1: Intent("long"), 2: Intent("short")})
    assert r["signals"][1]["status"] == "ignored_same_side"
    assert r["signals"][-1]["status"] == "unexecuted_end"
    assert r["report"]["breakeven"] == 1
    assert r["report"]["profit_factor"] is None
    empty = run([(100,100,100,100)], {})
    assert empty["report"]["win_rate"] is None


def test_warmup_and_future_data_not_visible():
    seen = []
    def on_bar(c):
        seen.append(tuple(b.close for b in c.history))
        with pytest.raises(IndexError):
            _ = c.history[len(c.history)]
        return Intent("long") if len(c.history) == 3 else None
    bars = [Bar(i * 60000, 100, 100, 100, 100, 1) for i in range(5)]
    r = simulate(bars, SimpleNamespace(on_bar=on_bar), {}, warmup=2)
    assert len(seen) == 3 and len(seen[0]) == 3
    assert r["trades"][0]["entry_time"] == 180000


@pytest.mark.parametrize("rows", [[], [[0,100,90,95,100,1]], [[0,100,100,100,100,float('nan')]], [[60000,100,100,100,100,1]]])
def test_invalid_data(rows):
    with pytest.raises(ValueError):
        validate_bars(rows, 0, 60000, 60000, 0, 120000)


def test_unclosed_and_misaligned_data():
    with pytest.raises(ValueError):
        validate_bars([[0,100,100,100,100,1]], 0, 60000, 60000, 0, 59999)
    with pytest.raises(ValueError):
        validate_bars([], 1, 60000, 60000, 0, 120000)


def test_strategy_exception_context():
    def broken(c):
        raise ValueError("broken")
    with pytest.raises(ValueError, match="K 线 0.*broken"):
        simulate([Bar(0,100,100,100,100,1)], SimpleNamespace(on_bar=broken), {}, warmup=0)


def test_changing_future_does_not_change_past_decisions_or_fills():
    prefix = [(100,100,100,100), (100,105,99,104), (104,108,103,107)]
    actions = {0: Intent("long"), 1: Intent("short"), 2: Intent("close")}
    first = run(prefix + [(107,110,105,108)], actions)
    changed = run(prefix + [(200,220,190,210)], actions)
    assert first["signals"] == changed["signals"]
    assert [f for f in first["fills"] if f["timestamp"] < 180000] == [f for f in changed["fills"] if f["timestamp"] < 180000]
    assert first["equity"][:-1] == changed["equity"][:-1]


def test_zero_equity_and_flat_close_have_defined_results():
    r = run([(100,100,100,100), (100,200,100,200), (200,200,200,200)], {0: Intent("short"), 1: Intent("long")})
    assert r["report"]["final_equity"] == 0
    assert r["report"]["max_drawdown_pct"] == 100
    assert r["signals"][1]["status"] == "ignored_nonpositive_equity"
    assert run([(100,100,100,100)] * 2, {0: Intent("close")})["signals"][0]["status"] == "ignored_flat"


@pytest.mark.parametrize("intent", [Intent("invalid"), Intent("long", -1), Intent("short", trailing_stop_pct=float("nan")), {"action": "long"}])
def test_invalid_intent_stops_at_the_specific_bar(intent):
    with pytest.raises(ValueError, match="K 线 0"):
        run([(100,100,100,100)], {0: intent})


@pytest.mark.parametrize("side,price", [("long", 125), ("short", 75)])
def test_gap_target_fills_at_open(side, price):
    r = run([(100,100,100,100)] * 2 + [(price,price,price,price)], {0: Intent(side, take_profit_pct=20)})
    assert r["trades"][0]["exit_price"] == price
    assert r["trades"][0]["exit_reason"] == "take_profit"
    assert r["trades"][0]["exit_phase"] == "open"


@pytest.mark.parametrize("side,prices,stop", [
    ("long", [(100,100,100,100), (100,120,95,115), (115,116,109,115)], 110),
    ("short", [(100,100,100,100), (100,105,80,85), (85,91,84,85)], 90),
])
def test_trailing_distance_is_based_on_entry_price(side, prices, stop):
    result = run(prices, {0: Intent(side, trailing_stop_pct=10)})
    assert result["trades"][0]["exit_reason"] == "stop_loss"
    assert result["trades"][0]["exit_price"] == stop
    assert result["trades"][0]["exit_time"] == 120000


@pytest.mark.parametrize("side,prices,stop", [
    ("long", [(100,100,100,100), (100,120,95,115), (105,106,100,104)], 110),
    ("short", [(100,100,100,100), (100,105,80,85), (95,100,94,96)], 90),
])
def test_gap_exit_keeps_effective_protection_level(side, prices, stop):
    result = run(prices, {0: Intent(side, trailing_stop_pct=10)})
    trade = result["trades"][0]
    assert trade["exit_phase"] == "open"
    assert result["levels"][-1] == {"timestamp": trade["exit_time"], "trade_id": 1, "stop": stop, "target": None}


def test_reversal_keeps_both_positions_levels_without_duplicates():
    result = run([(100,100,100,100)] * 4,
                 {0: Intent("long", 10, 20), 1: Intent("short", 5, 10)})
    same_bar = [v for v in result["levels"] if v["timestamp"] == 120000]
    assert [v["trade_id"] for v in same_bar] == [1, 2]
    assert [v["stop"] for v in same_bar] == [90, 105]
    assert len({(v["timestamp"], v["trade_id"]) for v in result["levels"]}) == len(result["levels"])


def test_trailing_stop_never_moves_backwards():
    result = run([(100,100,100,100), (100,120,95,115), (115,118,111,114), (114,119,112,118)],
                 {0: Intent("long", trailing_stop_pct=10)})
    assert [v["stop"] for v in result["levels"]] == [90, 110, 110]
