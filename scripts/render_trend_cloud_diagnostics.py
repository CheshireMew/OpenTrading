"""Plain-language diagnostic report from completed project experiments."""
from datetime import datetime, timezone, timedelta
from html import escape
import json
from pathlib import Path

from scripts.trend_cloud_diagnostics import DOCS, RUNTIME, read, save


def pct(x):
    return f'{x:+.2f}%'


def comparison_rows(data, keys):
    lines = ['| 改法 | 两年收益 | 途中最大跌幅 | 前一年收益 | 后续历史收益 | 最近18天收益 |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for key in keys:
        r = data['results'][key]
        lines.append(f"| {data['variants'][key]['name']} | {pct(r['full']['return_pct'])} | {r['full']['max_drawdown_pct']:.2f}% | {pct(r['selection']['return_pct'])} | {pct(r['validation']['return_pct'])} | {pct(r['recent']['return_pct'])} |")
    return '\n'.join(lines)


def main():
    data, diagnosis = read(DOCS/'experiments-results.json'), read(DOCS/'diagnostics.json')
    baseline = diagnosis['high_low_ema']['full']
    controls = {}
    for a, b in [('ema31_atr', 'ema31_range'), ('hl2_atr16', 'high_low_ema')]:
        one, two = (read(RUNTIME/f'experiment-{k}-full.json') for k in (a, b))
        sa, sb = ({(s['timestamp'], s['action']) for s in obj['signals']} for obj in (one, two))
        controls[f'{a} vs {b}'] = {'identical_completed_trades': one['trades'] == two['trades'],
                                  'signal_counts': [len(sa), len(sb)], 'different_signals_each_side': [len(sa-sb), len(sb-sa)]}
    originals = read(RUNTIME/'high_low_ema-full-diagnostics.json')['trades']
    target_trades = read(RUNTIME/'experiment-high_low_ema__target4-full.json')['trades']
    target_map = {(t['entry_time'], t['side']): t for t in target_trades}
    paired = [(t, target_map[(t['entry_time'], t['side'])]) for t in originals
              if t['profit'] > 0 and (t['entry_time'], t['side']) in target_map]
    controls['target4_matched_baseline_winners'] = {
        'matched_entries': len(paired), 'all_baseline_winners': baseline['wins'],
        'original_mean_return_pct': sum(t['return_pct'] for t, _ in paired)/len(paired),
        'target_mean_return_pct': sum(t['return_pct'] for _, t in paired)/len(paired),
        'lower_return_count': sum(b['return_pct'] < a['return_pct'] for a, b in paired),
        'note': 'Same entry time and direction; compares the first resulting trade only. Extra re-entries are included in the full strategy results, not in this pair subset.',
    }
    save(DOCS/'experiments-checks.json', controls)
    examples = [
        ('四小时内反向退出：该组单笔跌幅最大', min((t for t in originals if t['duration_minutes'] <= 240), key=lambda t: t['return_pct'])),
        ('曾浮盈超过1%却亏损：按时间顺序的第一笔', next(t for t in originals if t['mfe_pct'] >= 1 and t['profit'] < 0)),
        ('大趋势盈利：盈利交易按收益率排序的中间一笔', sorted((t for t in originals if t['profit'] > 0 and t['duration_minutes'] > 720), key=lambda t: t['return_pct'])[218]),
    ]
    example_rows = []
    for reason, t in examples:
        local = lambda x: datetime.fromtimestamp(x/1000, timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
        example_rows.append({'selection': reason, 'trade_id': t['trade_id'], 'side': '做多' if t['side'] == 'long' else '做空',
                             'entry': local(t['entry_time']), 'exit': local(t['exit_time']),
                             'entry_price': t['entry_price'], 'exit_price': t['exit_price'],
                             'mfe_pct': t['mfe_pct'], 'return_pct': t['return_pct']})
    save(DOCS/'diagnostic-examples.json', example_rows)
    quick = baseline['duration_groups']['up_to_1h']['losses']+baseline['duration_groups']['1h_to_4h']['losses']
    recent = diagnosis['high_low_ema']['recent']
    report = f'''# ETH 通道：ATR 是否有用，亏损从哪里来

这次已完成 8 组公式对照，以及对两个候选分别尝试 9 种改法，共 26 组方案、104 次分段模拟。全部使用项目已有的 Binance ETH/USDT 15 分钟行情快照和 Heimdall 引擎，不计算手续费和滑点。

目前结论是：通道宽度有过滤过密信号的作用，但这批行情没有显示 ATR 相比平滑高低差有独立优势。策略主要靠持续一段时间的趋势赚钱；短时间反向、追过远的价格以及利润回吐都在消耗收益。改进仍有取舍，没有找到可以声称稳定有效的新版本。

## ATR 的作用要分开看

原 EMA31＋ATR14 与“只把 ATR14 换成平滑高低差14”两年逐笔成交完全相同。两个版本各有 6,758 个信号，仅一对信号位置不同，未改变成交。把高低价通道换成相同中心线的 ATR16，连所有信号也一样。

因此，之前高低价通道的 190.05% 对 ATR14 候选的 174.27%，不能解释成“去掉 ATR 就变好”：原比较同时改了中心价格和宽度平滑周期。现在逐一控制这些变量后，ATR16 也能得到同样的 190.05%。这只回答当前 ETH 数据与规则，不能外推到所有市场。

把宽度整个去掉，交易从 1,919 笔增加到 7,887 笔，两年收益从 174.27% 降到 143.00%。固定比例宽度得到 139.93%。可见这批历史支持保留一定宽度，但不能证明 ATR 是唯一选择，且前一年单均线反而收益更高。

{comparison_rows(data, list(data['plan']['ablation']))}

固定比例宽度取前一年 ATR14／中心线比例的中位数 {data['fixed_width_pct_from_first_year']:.6f}%，再使用相同的 0.99 倍门槛；不根据收益选择该比例。

## 亏损原因：哪些已观察到，哪些不能提前知道

以高低价通道为例，两年 1,921 笔交易，605 笔盈利、1,316 笔亏损，最多连续亏 18 笔。

第一，{quick} 笔亏损发生在开仓四小时内又收到反向信号。这类交易一共 638 笔，只有 1 笔盈利，表现为刚跟上一个方向又被反打。按事后持仓长度分类，不能提前知道哪笔会持续四小时，更不能据此得出“强行拿够十二小时就能赚钱”。

第二，1,316 笔亏损中，335 笔盘中曾浮盈至少 1%，其中 221 笔在某次十五分钟收盘也仍浮盈至少 1%。当前规则一直等反向信号才退出，所以确实有利润回吐。但这些最高浮盈只是过程记录，不能事后假定全部能按最高点卖出。

第三，进场信号发生时，价格离中心线超过两倍宽度的 198 笔，平均单笔收益约 -0.16%；距离较近的 1,723 笔约 +0.11%。这为“少追过远的价格”提供了测试理由。它是历史相关性，所以我们又实际重跑了过滤后的整套交易，包含平仓、空仓和之后的入场。

第四，盈利集中在能走出较长趋势的交易。持仓超过十二小时的 501 笔中有 437 笔盈利，它们贡献约 91% 的全部盈利金额。加过早的止盈会伤到这些交易。同时，直接要求过去五小时走势更单向，或要求均线斜率同向，并没有解决问题，两年收益反而明显下降。

## “盈亏比不好”具体是什么

原高低价通道两年的平均盈利金额，是平均亏损金额的 2.31 倍；ATR14 候选也约 2.31 倍。页面上的 1.06 是“所有盈利金额加起来／所有亏损金额加起来”，不是每笔盈亏比。不能把这两个数混为一谈。

直观说，每亏一笔 100 元，赢一笔平均赚 231 元；但一百笔只赢约 31.5 笔、亏约 68.5 笔，所以大量盈利又被亏损抵掉。实际回测每次按当时资金开仓，单笔金额还会随资金变化，这个例子只帮助理解比例。

最近十八天问题更严重：55 笔只赢 14 笔、亏 41 笔。按各笔入场本金统一看，盈利单平均赚 {recent['avg_win_return_pct']:.2f}%，亏损单平均亏 {recent['avg_loss_return_pct']:.2f}%；赚一笔大约只能抵一笔亏损，赢的次数又明显更少。亏损不只是“没设一个好看的固定止盈止损比例”。

## 实际试过的改法

以下改法每次只加在对应原版本上，不混合挑选。固定止损、止盈、跟随止损距离使用信号收盘时已知的 ATR，换算为比例，再由原引擎相对于真实下一开盘价执行。

### 高低价通道

{comparison_rows(data, ['high_low_ema']+[k for k, v in data['variants'].items() if v.get('baseline') == 'high_low_ema'])}

### 原 EMA31＋ATR14 候选

{comparison_rows(data, ['ema31_atr']+[k for k, v in data['variants'].items() if v.get('baseline') == 'ema31_atr'])}

高低价通道里，“不追离中心线超过两倍宽度的突破”最值得继续检查：两年 10,000 变成约 34,865，途中最大跌幅 35.19%；原版是约 29,005 和 40.89%。后续历史从亏 8.37% 改善为赚 9.56%，但最近十八天仍亏 15.63%。它的盈利月份从 16／25 减到 14／25，并没有每个月都更稳；前一年也稍弱于原版。

这项过滤的规则是：向上突破上门槛、但离中心线已经超过两倍宽度，就不追多；向下同理。原有反向平仓照常，过滤不通过时先空仓，之后须再次出现新突破才考虑入场。比如中心线 2,500、宽度 10，上门槛约 2,509.90；若刚突破的收盘已到 2,525，就先不追。这个例子只解释规则。

三倍 ATR 固定止损也有降低两年最大跌幅的迹象，但后续历史仍亏 10.38%，比原版略差。三倍 ATR 跟随止损把跌幅降到 36.41%，两年收益也降到 90.81%。都存在明确取舍。

四倍 ATR 固定止盈把高低价通道胜率从 31.49% 提高到 37.11%，平均盈亏比却从 2.31 降到 1.69，两年收益变成 -8.44%。原因包括大盈利被提前结束，以及平仓后后续信号带来的额外入场；完整回测已经计入这两种变化。止盈不是加上去就会更好。

## 证据的边界与复查

完整两年为 2024-09-10 至 2026-09-10；前一年到 2025-09-10，后续历史为 2025-09-10 至 2026-08-18，最近观察为 2026-08-23 至 2026-09-10。均为 UTC 起止、结束不含；中间排除的五天包含截图拟合区间。各分段从 10,000 独立开始，不能直接拼接收益。最大跌幅按每根十五分钟收盘资金相对此前最高点计算。

本次是在已经看过历史的基础上提出改法。实验列表先保存，再按前一年检验，最后看后续区间。预设要求是“前一年收益提高且最大跌幅不增加”，两个原版本均没有改法通过。所以这里没有一个通过预定标准的优胜者；“不追过远价格”是查看全部结果后值得研究的线索，不能包装成未见行情验证成功。全部 26 组结果都保留，不只展示好的。

原版成交在新的实验实现中逐笔一致，资金曲线也完全一致。退出开盘所在 K 线的后续高低价不计入持仓浮盈亏；盘中退出无法知道退出前先走到哪一端，诊断器明确拒绝推算这类精确路径。所有改法仍由现有引擎执行，没有改变成交规则。

数据 SHA-256：`{data['data_hash']}`。实验源码 SHA-256：`{data['strategy_hash']}`。

项目入口：`python -m scripts.trend_cloud_diagnostics baseline` 重建逐笔诊断；`experiments` 按保存计划重跑；`publish` 创建或检查可在项目中打开的实验记录。报告生成：`python -m scripts.render_trend_cloud_diagnostics`。完整交易路径诊断保存在 `.heimdall_runtime/eth-cloud-two-year-20260910/*-diagnostics.json`，实验参数、逐笔交易和信号保存在同目录 `experiment-*.json`。

本次有针对性的 42 项测试通过，覆盖原版交易一致、退出开盘排除后续行情、多空浮盈亏手算、过滤不阻止平仓、两次收盘确认，以及原引擎成交与止损规则。
'''
    (DOCS/'DIAGNOSTICS.md').write_text(report, encoding='utf-8')
    receipt = read(DOCS/'experiments-project-run.json') if (DOCS/'experiments-project-run.json').exists() else None
    html_data = {'experiments': data, 'diagnosis': diagnosis, 'checks': controls, 'examples': example_rows, 'project_run': receipt}
    (DOCS/'diagnostics.html').write_text(HTML.replace('__DATA__', json.dumps(html_data, ensure_ascii=False).replace('<', '\\u003c')), encoding='utf-8')
    print(DOCS/'diagnostics.html')


HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATR 与亏损原因 · Heimdall</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#1a2934;font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1250px;margin:auto;padding:32px}h1{font-size:29px;line-height:1.4}h2{font-size:21px;line-height:1.5}p{margin:12px 0}a{color:#176b59}.panel{padding:24px;background:white;border:1px solid #dce3e7;border-radius:12px;margin:22px 0}.muted{color:#64747f;font-size:14px}.controls{display:flex;gap:16px;flex-wrap:wrap;align-items:center}select{font:inherit;padding:7px;border:1px solid #aab8c0;border-radius:6px;background:white}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;white-space:nowrap}td,th{padding:12px;border-bottom:1px solid #e5eaed;text-align:right}td:first-child,th:first-child{text-align:left}th{background:#f5f7f9}.positive{color:#167051}.negative{color:#b73b49}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{border-left:3px solid #3c7c67;padding-left:16px}.big{font-size:26px;font-weight:700}.warning{border-left:4px solid #b07c30}.tag{background:#e2ede7;color:#256046;display:inline-block;padding:3px 9px;border-radius:5px}summary{cursor:pointer;color:#176b59}nav{display:flex;gap:22px;flex-wrap:wrap}@media(max-width:700px){main{padding:16px}.panel{padding:16px}.cards{grid-template-columns:1fr}h1{font-size:24px}}
</style><main><nav><a href="comparison.html">← 原来的两年比较</a><a href="DIAGNOSTICS.md">完整分析与全部区间结果</a><a id="projectlink">在项目中看过滤后的实际交易</a></nav>
<p><span class="tag">26 组方案 · 104 次分段模拟 · 全部不计手续费和滑点</span></p>
<p><a href="profit-protection.html">查看最新测试：通道宽度参数＋利润保护或反向信号退出 →</a></p>
<h1>ATR 没有表现出不可替代的优势。<br>目前主要问题是反复亏损，以及大盈利不够多。</h1>
<p>比较的是高低价 EMA31 通道与此前 EMA31＋ATR14 候选。使用项目已有的 ETH/USDT 15 分钟行情，时间为 2024 年 9 月 10 日至 2026 年 9 月 10 日。</p>
<section class="panel"><h2>先把三个数说清楚</h2><div class="cards"><div class="card"><div class="big">约 31 笔 / 100 笔</div><p>高低价版本的盈利次数。其余大部分会亏。</p></div><div class="card"><div class="big">赚 231 / 亏 100</div><p>平均盈利金额约为平均亏损的 2.31 倍。</p></div><div class="card"><div class="big">只赢 14 笔 / 55 笔</div><p>最近十八天，赚一笔又只能抵约一笔亏损。</p></div></div><p class="muted">旧表里的“利润因子 1.06”指总盈利金额除以总亏损金额，不是平均一笔的盈亏比。</p></section>
<section class="panel"><h2>ATR 到底做了什么</h2><p>把 ATR14 换成平滑高低差14，两年实际交易完全一样；把高低价通道换成相同中心线的 ATR16，所有信号和实际交易也一样。之前两个版本的差别，不能简单归因于“用了 ATR”或“没用 ATR”。</p><p>但如果把通道宽度整个去掉，交易会从 1,919 笔增加到 7,887 笔，两年收益也会下降。当前证据支持保留宽度来减少过密信号，尚未显示必须使用 ATR。</p><details><summary>展开八组公式的两年对照</summary><div class="scroll"><table id="ablation"></table></div><p class="muted">固定宽度取前一年波动比例的中位数。其余对照每次只改变列明的因素。前一年单均线的收益反而更高，因此不能说带宽在所有时段都更好。</p></details></section>
<section class="panel"><h2>亏损具体集中在哪里</h2><p><strong>刚进场就被反打：</strong>1,316 笔亏损里，有 637 笔在开仓四小时内又出现反向信号。这是事后分类，不能提前知道哪笔会持续多久。</p><p><strong>到手的浮盈又回去：</strong>335 笔亏损交易曾经浮盈至少 1%；其中 221 笔在十五分钟收盘时也曾浮盈至少 1%。浮盈最高点不能事后当作可以成交的卖点。</p><p><strong>追过远的价格更吃亏：</strong>离中心线超过两倍宽度才进场的 198 笔，平均单笔约亏 0.16%；距离较近的交易平均约赚 0.11%。我们已实际测试过滤后的整套交易，结果如下。</p><p><strong>大盈利依赖较长趋势：</strong>持仓超过十二小时的交易贡献了约 91% 的全部盈利金额。太早止盈会削弱这部分收入。</p><details><summary>查看按固定规则选出的三笔过程示例</summary><p class="muted">示例用于解释过程，不代表全部交易；时间为北京时间。完整统计使用全部交易。</p><div class="scroll"><table id="examples"></table></div></details></section>
<section class="panel"><h2>真正改完再回测，有哪些改善</h2><p>以下每种改法单独试验。入场过滤不阻止原反向信号平仓；过滤不通过时先空仓。止盈止损用信号收盘时已知的波动幅度确定，随后交给原引擎执行。</p><div class="controls"><label>原版本 <select id="base"><option value="high_low_ema">高低价 EMA31 通道</option><option value="ema31_atr">原 EMA31＋ATR14 候选</option></select></label><label>看哪个时段 <select id="period"><option value="full">完整两年</option><option value="selection">前一年</option><option value="validation">后续历史</option><option value="recent">最近十八天</option></select></label></div><p class="muted" id="periodnote"></p><div class="scroll"><table id="changes"></table></div><p class="muted">“途中最大跌幅”指资金从此前最高点最多跌掉多少，按每根十五分钟收盘计算。“赢一笔抵几笔亏损”按各笔实际盈利、亏损金额平均计算。</p></section>
<section class="panel"><h2>目前会优先研究什么</h2><p><strong>少追离通道太远的价格。</strong>在高低价版本上，两年 10,000 变成约 34,865，原版约为 29,005；途中最大跌幅从 40.89% 降到 35.19%。但最近十八天仍亏 15.63%，盈利月份也从 16／25 减到 14／25，并没有每个月都改善。</p><p><strong>固定止盈暂时没有解决问题。</strong>四倍 ATR 止盈把胜率从 31.49% 提高到 37.11%，两年结果却由赚 190.05% 变为亏 8.44%。一部分原因是原本能赚很多的交易过早结束，随后再入场的交易也改变了结果。</p><p><strong>止损和保护利润都有取舍。</strong>三倍 ATR 固定止损降低了完整两年的最大跌幅，但后续历史表现稍差。跟随止损减少了跌幅，也削弱了总收益。只看胜率、某一个区间或最大跌幅，都可能选错。</p></section>
<section class="panel warning"><h2>还不能说已经找到稳定赚钱的版本</h2><p>实验名单先固定，再看前一年，然后检查后续历史。预先要求“前一年赚得更多，而且途中跌得不更多”，这次没有改法通过。少追过远价格是看完全部结果后值得进一步研究的线索，不是通过预设标准的优胜者。</p><p>这些历史之前已经看过，本轮属于有依据的改进实验，不能称为完全陌生行情验证。所有 26 组结果都已保留；本次没有继续调参数来凑好看的数字。</p></section><footer class="muted" id="provenance"></footer></main>
<script>const D=__DATA__,E=D.experiments,R=E.results,V=E.variants;
const f=(v,n=2)=>v==null?'—':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:n,maximumFractionDigits:n});const cls=v=>v>0?'positive':v<0?'negative':'';
function table(keys,period,id){document.getElementById(id).innerHTML='<thead><tr><th>规则</th><th>赚或亏 %</th><th>途中最大跌幅 %</th><th>交易笔数</th><th>100 笔里赢几笔</th><th>赢一笔抵几笔亏损</th><th>盈利月份</th></tr></thead><tbody>'+keys.map(k=>{let r=R[k][period];return `<tr><td>${V[k].name}</td><td class="${cls(r.return_pct)}">${f(r.return_pct)}</td><td>${f(r.max_drawdown_pct)}</td><td>${f(r.total_trades,0)}</td><td>${f(r.win_rate)}</td><td>${f(r.payoff_ratio)}</td><td>${r.positive_months} / ${r.month_count}</td></tr>`}).join('')+'</tbody>'}
const periods={full:'2024-09-10 至 2026-09-10，包含截图时段。',selection:'2024-09-10 至 2025-09-10。',validation:'2025-09-10 至 2026-08-18。',recent:'2026-08-23 至 2026-09-10，只有十八天。'};
function update(){let b=document.getElementById('base').value,p=document.getElementById('period').value;table([b,...Object.keys(V).filter(k=>V[k].baseline===b)],p,'changes');document.getElementById('periodnote').textContent=periods[p]+'日期为 UTC，各段从 10,000 独立开始，不计算手续费和滑点。'}
document.getElementById('base').onchange=update;document.getElementById('period').onchange=update;update();table(Object.keys(V).filter(k=>V[k].group==='ablation'),'full','ablation');
document.getElementById('examples').innerHTML='<thead><tr><th>选择方式</th><th>编号</th><th>方向</th><th>入场时间</th><th>退出时间</th><th>最高浮盈 %</th><th>最终盈亏 %</th></tr></thead><tbody>'+D.examples.map(t=>`<tr><td>${t.selection}</td><td>${t.trade_id}</td><td>${t.side}</td><td>${t.entry}</td><td>${t.exit}</td><td>${f(t.mfe_pct)}</td><td class="${cls(t.return_pct)}">${f(t.return_pct)}</td></tr>`).join('')+'</tbody>';
const link=document.getElementById('projectlink');if(D.project_run){link.href='http://127.0.0.1:4173/research/backtests?run='+D.project_run.run_id;link.target='_blank'}else{link.hidden=true}
document.getElementById('provenance').textContent='行情快照：'+E.data_hash+'。原版逐笔交易与资金曲线一致性检查通过；42 项相关测试通过。';
</script></html>'''


if __name__ == '__main__':
    main()
