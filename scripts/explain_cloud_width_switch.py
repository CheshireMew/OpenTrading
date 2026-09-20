"""Extract and plot saved trades; no new backtests or strategy edits."""
import argparse
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/verification/cloud-width-examples-20260913'
RUNS = {'baseline': '4e65bfb4229646299932d76515ec0ac0',
        'cloud': 'f61211db66385697e90d92041a56d183',
        'bb': '0feca3b83805ac91d65b80ed1b5e91d4'}
TZ = timezone(timedelta(hours=8))
STEP = 900000
CASES = [
    ('avoided_flips', '① 避开四次反复换仓，再接上涨', '2026-09-03T09:00', '2026-09-03T23:00'),
    ('missed_short', '② 原版空单盈利，布林切换版没有跟进', '2026-08-28T21:00', '2026-08-29T03:00'),
    ('outer_stop', '③ 突破外线入场，也会马上止损', '2026-09-07T19:30', '2026-09-08T03:00'),
]
NAMES = {'baseline': '原版：始终按内线突破', 'cloud': '按原通道宽度切换', 'bb': '按布林宽度切换'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def stamp(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=TZ).timestamp()*1000)


def local(t):
    return datetime.fromtimestamp(t/1000, TZ).strftime('%m-%d %H:%M')


def load():
    runs = {}
    for key, rid in RUNS.items():
        p = ROOT/'.heimdall_runtime/local_backtests'/rid/'result.json'
        r = read(p)
        cutoff = stamp('2026-08-01')
        runs[key] = {k: [x for x in r[k] if x.get('timestamp', x.get('exit_time', 0)) >= cutoff]
                     for k in ('trades', 'fills', 'signals', 'indicators')}
        runs[key]['obs'] = {x['timestamp']: x for x in runs[key]['indicators']}
    rows = read(ROOT/'.heimdall_runtime/local_backtests'/RUNS['baseline']/'data.json')
    return rows, runs


def scan():
    rows, runs = load()
    for key, r in runs.items():
        print(key, 'Sep03')
        for t in r['trades']:
            if stamp('2026-09-03T08:00') <= t['entry_time'] <= stamp('2026-09-03T23:00'):
                o = r['obs'].get(t['entry_time']-STEP, {})
                print(t['trade_id'], local(t['entry_time']), local(t['exit_time']), t['side'], round(t['return_pct'], 3),
                      t['exit_reason'], o.get('checks', {}).get('外线入场模式'))
        if key == 'baseline':
            continue
        print('recent outer wins/losses, <=12h')
        outer = [t for t in r['trades'] if t['duration_minutes'] <= 720 and
                 r['obs'].get(t['entry_time']-STEP, {}).get('checks', {}).get('外线入场模式')]
        for win in (True, False):
            candidates = [t for t in outer if (t['return_pct'] > 1) if win] if win else [t for t in outer if t['return_pct'] < 0]
            for t in candidates[-5:]:
                o = r['obs'][t['entry_time']-STEP]
                print(t['trade_id'],local(t['entry_time']),local(t['exit_time']),t['side'],round(t['return_pct'],3),
                      t['exit_reason'], round(o['values']['通道相对宽度'],3), round(o['values']['切换参照相对宽度'],3))
    print('missed profitable move candidates (no overlapping same-side position)')
    for t in runs['baseline']['trades']:
        if t['return_pct'] < 2 or t['duration_minutes'] > 720:
            continue
        missing = []
        for key in ('cloud', 'bb'):
            overlaps = [x for x in runs[key]['trades'] if x['side'] == t['side'] and
                        x['entry_time'] < t['exit_time'] and x['exit_time'] > t['entry_time']]
            if not overlaps:
                missing.append(key)
        if missing:
            print(t['trade_id'], local(t['entry_time']), local(t['exit_time']), t['side'], round(t['return_pct'],3), missing)


def extract():
    rows, runs = load()
    times = [int(r[0]) for r in rows]
    examples = []
    for key, title, first, last in CASES:
        start, end = stamp(first), stamp(last)
        selected_rows = rows[bisect_left(times, start):bisect_right(times, end)]
        assert all(b[0]-a[0] == STEP for a, b in zip(selected_rows, selected_rows[1:]))
        example = dict(id=key, title=title, start=start, end=end, rows=selected_rows, versions={})
        for version, r in runs.items():
            obs = [r['obs'][int(row[0])] for row in selected_rows]
            trades = [t for t in r['trades'] if t['entry_time'] <= end and t['exit_time'] >= start]
            fills = [f for f in r['fills'] if start <= f['timestamp'] <= end]
            events = []
            for t in trades:
                signal_time = times[bisect_left(times, t['entry_time'])-1]
                signal = r['obs'].get(signal_time)
                if signal is None:
                    continue
                srow = rows[bisect_left(times, signal_time)]
                pi = r['obs'].get(signal_time-STEP)
                is_outer = signal['checks'].get('外线入场模式', False)
                mult = 2 if is_outer else .4
                v = signal['values']
                d = 1 if t['side'] == 'long' else -1
                threshold = v['中心线']+d*mult*v['宽度基准']
                previous_threshold = pi['values']['中心线']+d*mult*pi['values']['宽度基准'] if pi else None
                prow = rows[bisect_left(times, signal_time)-1]
                assert d*(srow[4]-threshold) > 0
                assert d*(prow[4]-previous_threshold) <= 1e-10
                assert t['entry_price'] == rows[bisect_left(times, t['entry_time'])][1]
                events.append(dict(trade=t, signal_time=signal_time, signal_close=srow[4], threshold=threshold,
                    mode='outer' if is_outer else 'inner', reference_ratio_previous_close=pi['values'].get('切换参照相对宽度') if pi else None,
                    signal_ratio=v.get('切换参照相对宽度'), checks_passed=True))
            example['versions'][version] = dict(name=NAMES[version], run_id=RUNS[version], observations=obs,
                trades=trades, fills=fills, entries=events)
        examples.append(example)
    provenance = {}
    for key, rid in RUNS.items():
        folder = ROOT/'.heimdall_runtime/local_backtests'/rid
        metadata = read(folder/'metadata.json')
        actual_hash = hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()
        if metadata.get('result_hash'):
            assert metadata['result_hash'] == actual_hash
        provenance[key] = dict(run=rid, result_hash=actual_hash, data_hash=metadata['data_hash'])
    payload = dict(symbol='Binance 现货 ETH/USDT', timeframe='15 分钟', timezone='UTC+8', examples=examples,
        provenance=provenance,
        selection='三种机制的说明性实例：用户此前截图中的反复换仓段；2026 年 8 月以来原版 0.5%～2% 盈利、持仓不超过 12 小时而切换版完全没有同向重叠持仓的实例；最近一次两种切换版共同外线入场后止损的清晰实例。不是随机抽样，也不用于估计发生频率。',
        note='只读取已完成回测；不重算策略、不挑新参数。买卖标记为实际成交；K线横轴为开盘时间，收盘确认后下一根开盘成交。')
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT/'examples.json').open('x', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    for example in examples:
        print(example['id'])
        for k, v in example['versions'].items():
            print(k, [(e['trade']['trade_id'], local(e['trade']['entry_time']), e['trade']['side'], round(e['trade']['return_pct'], 3),
                       e['mode'], round(e['signal_close'],2), round(e['threshold'],2), e['trade']['exit_reason']) for e in v['entries']])


def render():
    # Dedicated plotting dependencies are installed on D:, not into the project.
    import os
    os.environ.setdefault('MPLCONFIGDIR', 'D:/Tools/heimdall-chart-deps/mpl-config')
    import sys
    sys.path.insert(0, 'D:/Tools/heimdall-chart-deps')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Rectangle, Patch
    from matplotlib.lines import Line2D
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'axes.unicode_minus': False, 'font.size': 11})
    payload = read(OUT/'examples.json')
    explanations = read(OUT/'captions.json')
    for ex in payload['examples']:
        rows = ex['rows']; n = len(rows)
        ylow = min(r[3] for r in rows); yhigh = max(r[2] for r in rows)
        span = yhigh-ylow
        fig, axes = plt.subplots(3, 1, figsize=(16, 11), dpi=140, sharex=True, sharey=True)
        fig.patch.set_facecolor('#f7f9fc')
        fig.suptitle(ex['title'], fontsize=21, x=.055, ha='left', y=.985, weight='bold')
        fig.text(.055,.94, 'ETH/USDT 15 分钟 · Binance 现货 · 北京时间 · 三行是完全相同的 K 线', color='#536277', fontsize=11)
        handles = [Line2D([0],[0],color='#9ca8b8',label='中心线'), Line2D([0],[0],color='#899bae',ls=':',label='内线 ±0.4W'),
                   Line2D([0],[0],color='#a58bbc',ls='--',label='外线 ±2W'), Patch(facecolor='#eee5fb',label='紫底：这一根用外线规则'),
                   Line2D([0],[0],color='#237da9',lw=2,label='蓝线：当时实际买卖门槛')]
        fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.05,.928), ncol=5, frameon=False, fontsize=10)
        for ax, (key, v) in zip(axes, ex['versions'].items()):
            obs = v['observations']; xs = list(range(n))
            vals = [o['values'] for o in obs]
            base = [o['中心线'] for o in vals]; widths = [o['宽度基准'] for o in vals]
            for i, o in enumerate(obs):
                if o['checks'].get('外线入场模式', False):
                    ax.axvspan(i-.5, i+.5, color='#eee5fb', zorder=0, lw=0)
            for d in (1,-1):
                ax.plot(xs, [b+d*.4*w for b,w in zip(base,widths)], color='#899bae', ls=':', lw=.8, zorder=1)
                ax.plot(xs, [b+d*2*w for b,w in zip(base,widths)], color='#a58bbc', ls='--', lw=.9, zorder=1)
                ax.plot(xs, [o['做多门槛' if d==1 else '做空门槛'] for o in vals], color='#237da9', lw=1.6, zorder=2)
            ax.plot(xs, base, color='#9ca8b8', lw=.8, zorder=1)
            for i, row in enumerate(rows):
                _, op, hi, lo, cl, _ = row
                color = '#089981' if cl >= op else '#ef4356'
                ax.vlines(i, lo, hi, color=color, lw=1.1, zorder=3)
                ax.add_patch(Rectangle((i-.3,min(op,cl)),.6,max(abs(cl-op),span*.001),facecolor=color,edgecolor=color,lw=.6,zorder=4))
            grouped = {}
            for f in v['fills']:
                grouped.setdefault(f['timestamp'], []).append(f)
            trade_map = {t['trade_id']:t for t in v['trades']}
            prior_label = {True: (-100, 0), False: (-100, 0)}
            for j,(timestamp, fills) in enumerate(sorted(grouped.items())):
                i = (timestamp-ex['start'])/STEP
                entries = [f for f in fills if f['action'] in ('long','short')]
                exits = [f for f in fills if f['action']=='close']
                # One clear merged label per actual reversal, no duplicate tags.
                if entries:
                    f=entries[-1]; side=f['action']; text=('平仓做多' if side=='long' else '平仓做空') if exits else ('做多' if side=='long' else '做空')
                    color='#3164d9' if exits else '#ed3c51' if side=='long' else '#16986d'
                    below=side=='long'
                    if exits:
                        old=trade_map[exits[-1]['trade_id']]
                        text += f'\n上一笔 {old["return_pct"]:+.2f}%'
                else:
                    f=exits[-1]; t=trade_map[f['trade_id']]
                    text=('止损' if t['exit_reason']=='stop_loss' else '利润保护' if t['exit_reason']=='profit_protection' else '平仓')+f'\n{t["return_pct"]:+.2f}%'
                    color='#cc7909'; below=t['side']=='short'
                row=rows[int(i)]; anchor=row[3] if below else row[2]
                # Keep all labels inside their panel; nearby labels use another
                # lane so neither captions nor time ticks can be covered.
                previous_i, lane = prior_label[below]
                lane = 1-lane if i-previous_i < n*.08 else 0
                prior_label[below] = (i,lane)
                label_y = (.12 if lane==0 else .29) if below else (.88 if lane==0 else .71)
                if entries and exits and any(a['trade_id']==entries[-1]['trade_id'] for a in exits):
                    text += '\n当根止损'
                ax.scatter([i],[f['price']],s=22,color=color,zorder=6)
                ax.annotate(text,(i,anchor),xytext=(i,label_y),textcoords=ax.get_xaxis_transform(),ha='center',va='center',fontsize=9,
                    color='white',bbox=dict(boxstyle='round,pad=.35',facecolor=color,edgecolor='none'),
                    arrowprops=dict(arrowstyle='-',color=color,lw=.8),zorder=7)
            ax.set_title(v['name']+'  |  '+explanations[ex['id']][key],loc='left',fontsize=12,pad=10,weight='bold')
            ax.set_ylim(ylow-span*.65,yhigh+span*.65)
            ax.set_xlim(-1.5,n+.5); ax.grid(axis='y',alpha=.18); ax.set_axisbelow(True)
            ax.spines[['top','right']].set_visible(False)
            ax.tick_params(axis='x',labelbottom=True)
            step=max(1,round(n/8)); ticks=list(range(0,n,step))
            ax.set_xticks(ticks,[local(rows[i][0]) for i in ticks],fontsize=9)
        fig.text(.055,.025,'收盘确认后，下一根开盘成交。标签标成交；紫底是当时使用的规则，不是在事后给行情分类。',fontsize=11,color='#536277')
        fig.subplots_adjust(top=.865,bottom=.075,left=.06,right=.975,hspace=.42)
        path=OUT/(ex['id']+'-v2.png')
        if path.exists():
            raise ValueError('已有图不可覆盖，请另存修订')
        fig.savefig(path, facecolor=fig.get_facecolor())
        plt.close(fig)
    print('已保存三张真实 K 线对照图')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['scan','extract','render'],default='scan',nargs='?')
    args=parser.parse_args()
    {'scan':scan,'extract':extract,'render':render}[args.action]()
