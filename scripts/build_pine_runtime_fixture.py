"""Build a deterministic OHLC fixture and Python event oracle for manual Pine QA.

No market data is fetched. TradingView must separately execute the derived Pine
harness; this command does not constitute a Pine runtime verification.
"""
import hashlib
import json
import math
from pathlib import Path

from app.domain.local_backtest import Bar, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'docs/verification/pine-v7-2-contract'


def build():
    source = ROOT / 'strategies/pine/eth_ema55_manual_chart_v7_2.pine'
    strategy_path = ROOT / 'strategies/trend_cloud_intrabar_methods_v3.py'
    strategy, metadata = load_strategy(strategy_path)
    parameters = validate_parameters(metadata, {'confirmation_level': 3, 'max_wait_bars': 2})
    # Small oscillations exercise reversal exits; wider trends exercise profit
    # protection. Periodic wicks and gaps exercise adverse historical fills.
    rows = []
    previous = 100.0
    for i in range(240):
        amplitude = (0.8, 4.0, 1.2, 6.0)[i // 60]
        close = round(100 + amplitude * math.sin(i * math.pi / 12), 4)
        opening = round(previous + (1.8 if i % 37 == 0 else -1.8 if i % 41 == 0 else 0), 4)
        wick = 1.5 if i % 17 == 0 else 0.12
        rows.append([opening, round(max(opening, close) + wick, 4), round(min(opening, close) - wick, 4), close])
        previous = close
    warmup = 650
    step = 900000
    bars = [Bar(i * step, *row, 1) for i, row in enumerate([[100, 100.2, 99.8, 100]] * warmup + rows)]
    result = simulate(bars, strategy, parameters, warmup=warmup, step_ms=step)
    expected = [[f['timestamp'] // step, {'long': 1, 'short': 2, 'close': 3}[f['action']], round(f['price'], 8)]
                for f in result['fills'] if f['reason'] != 'end_of_backtest']
    payload = dict(schema_version=1, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   strategy=strategy_path.relative_to(ROOT).as_posix(),
                   strategy_sha256=hashlib.sha256(strategy_path.read_bytes()).hexdigest(),
                   parameters=parameters, warmup=warmup, step_ms=step,
                   warmup_ohlc=[100, 100.2, 99.8, 100], bars=rows, expected_fills=expected,
                   event_actions={'1': 'long', '2': 'short', '3': 'close'}, price_tolerance=1e-7,
                   exit_reasons={r: sum(t['exit_reason'] == r for t in result['trades'])
                                 for r in sorted({t['exit_reason'] for t in result['trades']})},
                   note='Full Python EMA signals and historical fills; end_of_backtest close excluded to match Pine indicator. No Pine execution occurs in this generator.')
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / 'runtime-fixture-20260920.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return payload


if __name__ == '__main__':
    fixture = build()
    print(json.dumps({'bars': len(fixture['bars']), 'fills': len(fixture['expected_fills']),
                      'exit_reasons': fixture['exit_reasons'], 'expected_fills': fixture['expected_fills']}))
