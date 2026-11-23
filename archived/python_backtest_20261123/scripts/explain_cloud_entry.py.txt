"""Explain saved BTC v4 entries using project candles, strategy and trade records.

Run extract with the project Python; render with a Python that has Pillow.
This is a presentation artifact, not a strategy change or a new backtest.
"""
from pathlib import Path
import argparse
import json
import hashlib
from datetime import datetime, timezone, timedelta
from bisect import bisect_left, bisect_right

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/verification/cloud-entry-explanation-20260911'
SERVE = ROOT / 'docs/verification/eth-cloud-two-year-20260910'
KEY = 'c55_w50_t0p8_d1p5_a2_g50_s2'
TZ = timezone(timedelta(hours=8))


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def local(t):
    return datetime.fromtimestamp(t / 1000, TZ).strftime('%m-%d %H:%M')


def extract():
    from app.domain.local_backtest import Bar
    from strategies.trend_cloud_parameters_v4 import Calculation
    plan_file = ROOT / 'docs/verification/btc-cloud-parameters-20260911/plan.json'
    trace_file = ROOT / f'.opentrading_runtime/btc-cloud-parameters-20260911/traces/{KEY}-final.json'
    plan, trace = read(plan_file), read(trace_file)
    data_file = ROOT / plan['data']['path']
    strategy_file = ROOT / 'strategies/trend_cloud_parameters_v4.py'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(data_file) == plan['data']['data_hash']
    assert sha(strategy_file) == plan['source_hash']
    source = read(data_file)
    start = int(datetime.fromisoformat(trace['period'][0].replace('Z', '+00:00')).timestamp() * 1000)
    offset = bisect_left([r[0] for r in source], start)
    rows = source[offset - 650:offset + 4000]
    calc = Calculation({**trace['parameters'], 'record_indicators': True})
    observations = [calc.update(Bar(*r)) for r in rows]
    trades = {t['entry_time']: t for t in trace['trades']}
    entries = [t['entry_time'] for t in trace['trades']]
    signals = {s['timestamp']: s for s in trace['signals']}
    chosen = {}
    for i in range(650, len(rows) - 5):
        o = observations[i]
        up, down = o.checks['原做多信号'], o.checks['原做空信号']
        if not (up or down):
            continue
        side = 'long' if up else 'short'
        trade = trades.get(rows[i + 1][0])
        if o.checks['不追远处突破'] and trade and trade['side'] == side:
            chosen.setdefault(side, i)
        elif not o.checks['不追远处突破']:
            j = bisect_right(entries, rows[i][0]) - 1
            previous = trace['trades'][j] if j >= 0 else None
            # Pick a flat example, so the distance filter is the reason for no entry.
            if previous is None or previous['exit_time'] <= rows[i][0]:
                chosen.setdefault('skip', i)
        if len(chosen) == 3:
            break
    assert set(chosen) == {'long', 'short', 'skip'}
    examples = []
    for kind in ('long', 'short', 'skip'):
        i = chosen[kind]
        side = 'long' if observations[i].checks['原做多信号'] else 'short'
        bars = []
        for j in range(i - 18, i + 5):
            r, o = rows[j], observations[j]
            bars.append(dict(timestamp=r[0], time=local(r[0]), open=r[1], high=r[2], low=r[3], close=r[4],
                             **o.values, **o.checks))
        assert all(bars[j + 1]['timestamp'] - bars[j]['timestamp'] == 900000 for j in range(len(bars) - 1))
        b, prev = bars[18], bars[17]
        threshold = '做多门槛' if side == 'long' else '做空门槛'
        assert (prev['close'] <= prev[threshold] and b['close'] > b[threshold]) if side == 'long' else (prev['close'] >= prev[threshold] and b['close'] < b[threshold])
        trade = trades.get(rows[i + 1][0]) if kind != 'skip' else None
        if trade:
            assert signals[rows[i][0]]['status'] == 'executed'
            assert signals[rows[i][0]]['action'] == side
            assert trade['entry_price'] == bars[19]['open']
            assert trade['entry_time'] == signals[rows[i][0]]['decision_time']
            assert .8 < b['离中心距离 / W'] <= 1.5
        else:
            assert b['离中心距离 / W'] > 1.5
            assert rows[i][0] not in signals
            assert rows[i + 1][0] not in trades
        examples.append(dict(kind=kind, side=side, bars=bars, signal_index=18,
                             signal_candle=f"2024-{b['time']}—{local(b['timestamp'] + 900000)[6:]}",
                             signal_closed_at=local(b['timestamp'] + 900000),
                             trade=trade, previous=prev, signal=b))
    payload = dict(symbol='BTC/USDT', timeframe='15分钟', timezone='UTC+8', parameters=trace['parameters'],
                   examples=examples, selection='First executed long, first executed short, and first too-far raw crossing while flat, in chronological order from the saved final test. Not selected by profit.',
                   checks='Exact project source and data hashes; each displayed crossing and next-open fill checked against the saved final-test trace; skip occurred flat and no new trade exists; no gaps in displayed windows.',
                   provenance={str(p.relative_to(ROOT)): sha(p) for p in (plan_file, trace_file, data_file, strategy_file)})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'examples.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({e['kind']: dict(candle=e['signal_candle'], close=e['signal']['close'],
                                    center=e['signal']['中心线'], width=e['signal']['宽度基准'],
                                    entry=e['trade']['entry_price'] if e['trade'] else None) for e in examples}, ensure_ascii=False))


def render():
    from PIL import Image, ImageDraw, ImageFont
    p = read(OUT / 'examples.json')
    bg, ink, muted = '#f5f7fb', '#18243a', '#607088'
    blue, green, red, gray = '#346bd5', '#008d72', '#c24b38', '#8995a8'
    image = Image.new('RGB', (1800, 1260), bg)
    d = ImageDraw.Draw(image)
    def font(n, bold=False):
        return ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc' if bold else 'C:/Windows/Fonts/msyh.ttc', n)
    def text(x, y, t, size=25, color=ink, bold=False):
        d.text((x, y), t, font=font(size, bold), fill=color)
    text(55, 30, '收盘越过门槛，下一根才成交', 43, bold=True)
    text(57, 96, 'BTC 实际 15 分钟 K 线  ·  EMA55 / 振幅50 / 门槛0.8 / 最远1.5  ·  北京时间', 25, muted)
    for x, c, label in [(60, blue, '中心线 EMA55'), (425, green, '做多门槛：中心 + 0.8倍振幅'), (1020, red, '做空门槛：中心 − 0.8倍振幅')]:
        d.line((x, 155, x + 44, 155), fill=c, width=5)
        text(x + 55, 135, label, 25, c)
    for panel, e in enumerate(p['examples'][:2]):
        top = 201 + panel * 498
        d.rounded_rectangle((40, top, 1760, top + 473), 23, fill='white')
        side, bars, sig = e['side'], e['bars'], e['signal']
        color = green if side == 'long' else red
        title = '① 做多：刚刚向上越过绿线' if side == 'long' else '② 做空：刚刚向下越过红线'
        text(66, top + 17, title, 29, color, True)
        text(920, top + 23, e['signal_candle'], 23, muted)
        x0, x1, y0, y1 = 140, 1295, top + 85, top + 368
        lo = min(min(b['low'], b['最远做空价']) for b in bars)
        hi = max(max(b['high'], b['最远做多价']) for b in bars)
        lo, hi = lo - (hi-lo)*.07, hi + (hi-lo)*.07
        X = lambda i: x0 + i * (x1-x0)/(len(bars)-1)
        Y = lambda v: y1 - (v-lo)/(hi-lo)*(y1-y0)
        for z in range(5):
            v = lo + (hi-lo)*z/4; yy = Y(v)
            d.line((x0, yy, x1, yy), fill='#e9edf4', width=1)
            text(63, yy-12, f'{v:,.0f}', 17, muted)
        for field, c, w in [('最远做多价', gray, 2), ('最远做空价', gray, 2), ('中心线', blue, 4), ('做多门槛', green, 4), ('做空门槛', red, 4)]:
            pts = [(X(i), Y(b[field])) for i, b in enumerate(bars)]
            if field.startswith('最远'):
                for i in range(len(pts)-1):
                    for a,b in [(0,.35),(.6,.9)]:
                        p0,p1=pts[i],pts[i+1]
                        d.line((p0[0]+a*(p1[0]-p0[0]),p0[1]+a*(p1[1]-p0[1]),p0[0]+b*(p1[0]-p0[0]),p0[1]+b*(p1[1]-p0[1])), fill=c, width=w)
            else:
                d.line(pts, fill=c, width=w)
        for i,b in enumerate(bars):
            xx=X(i);cc=green if b['close']>=b['open'] else red
            d.line((xx,Y(b['high']),xx,Y(b['low'])), fill=cc, width=2)
            ya,yb=sorted([Y(b['open']),Y(b['close'])]);yb=max(yb,ya+2)
            d.rectangle((xx-9,ya,xx+9,yb), fill=cc)
        sx, sy = X(18), Y(sig['close'])
        d.ellipse((sx-10,sy-10,sx+10,sy+10), fill='white', outline=color, width=5)
        tx, ty = X(19), Y(e['trade']['entry_price'])
        d.rectangle((tx-8,ty-8,tx+8,ty+8), fill='#142c50', outline='white', width=2)
        # Fixed annotation area keeps labels clear of the actual candles.
        text(1330, top+94, '空心圆：确认信号', 23, color, True)
        text(1330, top+137, f"收盘 {sig['close']:,.2f}", 23)
        text(1330, top+188, '深色方块：实际成交', 23, ink, True)
        text(1330, top+231, f"下一根开盘", 23, muted)
        text(1330, top+267, f"{e['trade']['entry_price']:,.2f}", 26, ink, True)
        text(1330, top+318, '灰虚线：太远就不追', 22, gray)
        for i in [0,4,8,12,16,20,22]:
            text(X(i)-27, y1+12, bars[i]['time'][6:], 18, muted)
        threshold = sig['做多门槛' if side=='long' else '做空门槛']
        limit = sig['最远做多价' if side=='long' else '最远做空价']
        sign = '高于' if side=='long' else '低于'
        text(67, top+416, f"收盘 {sig['close']:,.2f} {sign}门槛 {threshold:,.2f}，且未越过不追价界限 {limit:,.2f}。", 24)
    text(57, 1211, '这些位置来自保存的回测成交。越过门槛只是进场规则，不代表这笔一定赚钱；不因后续盈亏挑选例子。', 23, muted)
    image.save(OUT / 'entry-explained.png')
    html = (ROOT / 'scripts/cloud_entry_explanation.html').read_text(encoding='utf-8')
    html = html.replace('__DATA__', json.dumps(p, ensure_ascii=False).replace('</', '<\\/'))
    (OUT / 'index.html').write_text(html, encoding='utf-8')
    (SERVE / 'entry-explained.html').write_text(html, encoding='utf-8')
    (OUT / 'README.md').write_text('# 用实际 K 线解释买卖门槛\n\n'
        '展示 BTC 当前较好版本；不是原截图指标源码的确认。取已有回测最早一笔做多、最早一笔做空，以及最早一次空仓时因太远而放弃的突破。没有根据盈亏挑选。\n\n'
        '数据、算法与成交核对记录：examples.json。交互页面：index.html。图：entry-explained.png。\n\n'
        '复现：项目 Python 运行 `-m scripts.explain_cloud_entry extract`；安装有 Pillow 的 Python 运行 `scripts/explain_cloud_entry.py render`。原策略和回测结果未改。\n', encoding='utf-8')
    print(OUT / 'entry-explained.png')


if __name__ == '__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['extract','render']);args=ap.parse_args()
    extract() if args.mode=='extract' else render()
