"""Verify saved Pine source identity and shared Python execution fixtures.

Does not compile or execute Pine. JSON results state each evidence boundary.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from app.domain.local_backtest import Bar, BarResult, Intent, ProfitProtection, StopEntry, simulate

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT/'strategies/pine/eth_ema55_manual_chart_v7_2.manifest.json'


def verify():
    manifest = json.loads(MANIFEST.read_text(encoding='utf8'))
    source = ROOT/manifest['pine']['path']
    text = source.read_text(encoding='utf8')
    checks = []
    def check(name, passed):
        checks.append(dict(name=name, passed=bool(passed)))
    for item in [manifest['pine'], *manifest['sources']]:
        path = ROOT/item['path']
        check('source_hash:'+item['path'], path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'])
    check('current_chart_only', 'request.' not in '\n'.join(line.split('//')[0] for line in text.splitlines()))
    check('indicator_not_order_execution', 'indicator(' in text and 'strategy(' not in text)
    for label in manifest['labels']:
        check('label:'+label['text'], any('plotshape(' in line and f'text="{label["text"]}"' in line and label['color'] in line for line in text.splitlines()))
    # This checks source structure; compiler validity and actual Pine events are
    # deliberately distinct fields in the report.
    check('stop_before_close_protection', text.index('if side != 0 and (side == 1 ? currentLow') < text.index('float candidate ='))
    fixture_path = ROOT/manifest['fixtures']['path']
    check('fixtures_hash', hashlib.sha256(fixture_path.read_bytes()).hexdigest() == manifest['fixtures']['sha256'])
    fixture = json.loads(fixture_path.read_text(encoding='utf8'))
    results = []
    step = fixture['step_ms']
    for case in fixture['cases']:
        actions = {}
        for index, value in case['actions'].items():
            order = value.get('order')
            intent = Intent(value['intent']) if value.get('intent') else None
            entry = None
            if order:
                protection = ProfitProtection(*order['protection']) if order.get('protection') else None
                entry = StopEntry(Intent(order['side'], stop_loss_pct=order.get('stop_pct'), profit_protection=protection), order['trigger'], order.get('cap'))
            actions[int(index)] = BarResult(intent=intent, entry_order=entry)
        bars = [Bar(i*step,*row,1) for i,row in enumerate(case['bars'])]
        check('valid_ohlc:'+case['id'], all(0 < b.low <= min(b.open,b.close) <= max(b.open,b.close) <= b.high for b in bars))
        result = simulate(bars, SimpleNamespace(on_bar=lambda c: actions.get(len(c.history)-1)), {}, warmup=0, step_ms=step)
        actual = [[v['timestamp']//step, v['action'], v['phase'], round(v['price'],8)] for v in result['fills']]
        passed = actual == case['expected_fills']
        if case.get('exit_reason'):
            passed = passed and result['trades'][0]['exit_reason'] == case['exit_reason']
        if 'ambiguous' in case:
            passed = passed and result['trades'][0]['ambiguous'] == case['ambiguous']
        check('python_event:'+case['id'], passed)
        check('pine_rule_anchor:'+case['id'], case['pine_anchor'] in text)
        results.append(dict(id=case['id'], expected=case['expected_fills'], python_fills=actual,
                            python_passed=passed, pine_event_status='not_executed'))
    return dict(ok=all(v['passed'] for v in checks), manifest=str(MANIFEST), checks=checks, fixtures=results,
                pine_compilation='not_verified', pine_runtime_event_parity='not_verified',
                note='源码哈希、规则片段和 Python 事件样例通过，不表示 TradingView 编译或 Pine 逐笔事件已通过。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify()
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf8')
    print(text)
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
