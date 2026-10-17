"""Present the frozen parameter study, including unsuccessful selected rules."""
from pathlib import Path
import json

from scripts.profit_protection_study import DOCS, RUNTIME, ROOT, read, save

OLD_DOCS = ROOT/'docs/verification/eth-cloud-two-year-20260910'


def name(key, data):
    p = data['variants'][key]['parameters']
    return f"宽度EMA{p['width_length']}／门槛{p['trigger_mult']:g}"+(
        f"／盈利{p['activation_pct']}%启动、回吐{p['giveback_pct']}%退出" if p['activation_pct'] else '／无利润保护')


def table(data, keys):
    rows = ['| 设置 | 两年收益 | 最大跌幅 | 交易笔数 | 前一年收益 | 后续历史收益 | 最近18天收益 |',
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for k in keys:
        r = data['results'][k]
        rows.append(f"| {name(k,data)} | {r['full']['return_pct']:+.2f}% | {r['full']['max_drawdown_pct']:.2f}% | {r['full']['total_trades']} | {r['selection']['return_pct']:+.2f}% | {r['validation']['return_pct']:+.2f}% | {r['recent']['return_pct']:+.2f}% |")
    return '\n'.join(rows)


def main():
    data = read(DOCS/'results.json')
    assert data['status'] == 'completed'
    runs = read(DOCS/'project-runs.json') if (DOCS/'project-runs.json').exists() else {'runs': {}}
    widths = [k for k, v in data['variants'].items() if v['group'] == 'width']
    protections = [k for k, v in data['variants'].items() if v['group'] == 'protection']
    combos = [k for k, v in data['variants'].items() if v['group'] == 'combination']
    focus = ['w31_m99', 'w31_m80', 'w31_m99_a1_g50', 'w31_m80_a2_g50']
    p = data['entry_comparisons']['w31_m80_a2_g50']['full']
    selected_p = data['entry_comparisons']['w31_m99_a1_g50']['full']
    report = f'''# ETH 通道参数与利润保护：已完成测试

使用项目原有 Binance ETH/USDT 15 分钟数据和 Heimdall 回测引擎，共 21 组参数、84 次分段模拟。另做 12 次固定原入场时刻的对照，检查保护本身的影响。所有结果不计算手续费和滑点；初始 10,000 USDT，每次使用当前账户资金的 100%，不加杠杆。

当前结论：利润保护与反向信号已按“任一条件成立都可平仓”实现。保护确实能救回由盈转亏的交易，但也截短部分大盈利，不能只看胜率。通道门槛 0.8 是只看前一年选出的设置；盈利 2% 后允许回吐一半，是看完各段后值得观察的收益／跌幅取舍，不能冒充前一年选出的赢家。最近十八天全部 21 组都亏损。

## 当前最有用的四组对照

{table(data,focus)}

前两行都保留“不追离中心线超过两倍宽度的价格”，也都不是最初没有入场过滤的截图候选。

门槛从 0.99 改为 0.8，使信号更早、更频繁。完整两年收益略提高，最大跌幅略降低，但交易由 1,864 增至 2,252，最长连续亏损由 17 笔增至 31 笔，盈利月份从 14／25 变为 13／25。所以不能简单称为全面改善。

门槛 0.8 再加“盈利 2% 后允许回吐 50%”，两年 10,000 变为约 36,425，相同通道不保护约为 37,350。最大跌幅从 34.47% 降至 31.96%，最长连续亏损从 31 笔降至 24 笔；最近十八天仍亏 13.08%。它改善了部分波动指标，同时少赚了一些，尚未解决近期亏损。

## 两种退出条件如何同时工作

反向信号不要求当前仓位盈利，也不要求利润保护先启动。反向信号在十五分钟收盘确认，下一根开盘平掉旧仓；反向开仓也满足不追单条件才开新仓，否则空仓。利润保护退出后也先空仓，之后出现新的合格突破信号才再入场。重复同方向信号不会叠加仓位。

保护使用最大浮盈的回吐比例，而不是最高价格的跌幅。比如 100 做多，盈利达到 2% 后启动；若最高到 110，允许回吐一半利润，保护线在 105。最高再上升到 112，保护线到 106，之后不能向下放宽。做空对称：100 做空，最低到 90，保护线是 95。

行情只有十五分钟 OHLC，所以本轮严格按“每根收盘更新保护线，新线从下一根生效”。已经生效的线可以在下一根盘中触发；开盘越过时按实际开盘价成交。不能用同一根后来的最高点抬线，又回到该根更早的最低点退出。若刚创高后同根回落，可能要到下一开盘才退出，因此这是十五分钟更新的保护，不是逐笔行情的实时保护。表里的保留利润是触发规则，不保证每笔精确按该比例成交。

保护线和已确认反向信号同时能在开盘退出时，旧保护线先检查，旧仓只平一次；合格的反向新仓仍可开。新仓不继承旧仓的浮盈最高点。最后一根强制平仓仅用于结算回测。

## 利润保护究竟救了什么，又损失了什么

以“门槛 0.8、盈利 2% 启动、回吐 50%”和相同通道不保护比较：全部 {p['baseline_trades']} 个原入场时刻都能一一对应。

- 原本亏损的 {p['matched_baseline_losses']} 笔中，{p['losses_turned_into_wins']} 笔被变成盈利。
- 原本盈利的 {p['matched_baseline_winners']} 笔中，{p['winners_reduced']} 笔赚得更少，{p['winners_improved']} 笔赚得更多；其余基本相同。
- 原盈利交易平均赚 {p['winners_baseline_average_return_pct']:.2f}%，加保护后这些同入场交易平均赚 {p['winners_protected_average_return_pct']:.2f}%。单纯数“救了多少笔”会漏掉大盈利减少的影响。
- 提前退出又允许后续新信号入场，额外产生 {p['additional_entries']} 笔交易，完整回测已计算这部分。另做固定原入场时刻的对照，排除额外入场后，两年收益为 {data['entry_comparisons']['w31_m80_a2_g50']['fixed_baseline_entries_full']['report']['return_pct']:.2f}%，也低于原来的 273.50%。不能把最终收益变化全部归因于止盈线本身。

该保护组合共 2,601 笔交易，盈利 883 笔、亏损 1,718 笔。按退出原因分：581 笔由利润保护退出，全部盈利；1,889 笔反向信号直接换仓；130 笔反向信号平仓后因追单限制没有立刻反向开仓；1 笔到回测结束结算。后三类同样保留在总结果中，不只统计保护成功的交易。

更早启动也不是越早越好。在旧门槛 0.99 上，“盈利 1% 就启动、回吐一半”救回 {selected_p['losses_turned_into_wins']} 笔原亏损，但 {selected_p['winners_reduced']} 笔原盈利赚得更少，原盈利单的平均收益从 2.17% 降到 1.28%。整体胜率提高到 49.45%，两年收益却降至 139.49%，最大跌幅增至 49.41%。有 18 笔保护退出最终仍亏损，这是十五分钟更新与实际开盘越过保护线的结果。

## 九组通道参数：其他规则保持一致

中心线固定 EMA31（高低价中点），只改变高低差的 EMA 周期与触发倍数，不追单限制固定为两倍宽度。图上颜色带仍用 0.45 倍，仅影响外观。

{table(data,widths)}

宽度周期 31 的 0.8、0.99、1.2 在完整两年都盈利较多，但换到周期 20 或 40，后续历史大多亏损。首年选出的 31／0.8 后续赚 5.66%，31／1.2 后续赚 29.59%，后者首年又更弱。这说明参数对时段仍敏感，不能声称 31／0.8 是通用最佳参数。

## 原通道上的六组利润保护

{table(data,['w31_m99']+protections)}

## 首年选出通道上的六组利润保护

{table(data,['w31_m80']+combos)}

## 选择过程与限制

计划先保存在 `plan.json`。先看前一年，要求收益为正、所有盈利金额合计超过所有亏损金额合计、至少 50 笔交易，再按收益／最大跌幅排序。宽度选择为 **31／0.8**。原 31／0.99 通道的保护选择为 **1% 启动、回吐 50%**，它后来表现变差，这个失败结果仍完整展示。31／0.8 的组合排名选择为 **不加利润保护**。

“2% 启动、回吐 50%”在完整结果里体现了收益与跌幅的取舍，所以保留为探索候选，不改写成首年选中的方案，也不继续缩小步长搜参数。本轮历史之前已被看过，所谓后续历史区间并非完全陌生的数据，未来仍需新行情检查。

完整两年：2024-09-10 至 2026-09-10；前一年：2024-09-10 至 2025-09-10；后续历史：2025-09-10 至 2026-08-18；最近十八天：2026-08-23 至 2026-09-10。全部 UTC、结束不含。中间排除五天包含截图拟合区间。分段各从 10,000 开始，不能直接相加或拼接；最大跌幅按全部十五分钟收盘资金计算。月份首尾可能为部分月份。

## 项目与复现

已新增单文件策略 `strategies/trend_cloud_profit_protection.py`，通道周期、门槛、启动盈利和回吐比例都能从项目参数设置。引擎增加 `ProfitProtection`，版本为 4，关闭新功能后逐笔交易和资金曲线与旧基准完全相同；原有记录保留。项目页面的退出原因显示为“利润回吐保护”，保护线沿用原止损轨迹显示。

68 项相关测试通过，覆盖多空手算、两种独立退出、启动边界、保护线不放宽、开盘越线、重新入场重置、无未来数据影响、原规则一致、服务快照与已有引擎规则。前端类型检查通过。

命令：`python -m scripts.profit_protection_study run`；项目运行创建与核对：`python -m scripts.profit_protection_study publish`；生成报告：`python -m scripts.render_profit_protection_study`。完整参数、选择记录和所有指标在本目录；各组信号和逐笔交易、固定入场对照以及源码/引擎副本保存在 `.heimdall_runtime/profit-protection-study-20260910`。

数据 SHA-256：`{data['provenance']['data_hash']}`；策略 SHA-256：`{data['provenance']['strategy_hash']}`；引擎 SHA-256：`{data['provenance']['engine_hash']}`。
'''
    (DOCS/'REPORT.md').write_text(report, encoding='utf-8')
    payload = {'data': data, 'project_runs': runs['runs']}
    page = HTML.replace('__DATA__', json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c'))
    (DOCS/'report.html').write_text(page, encoding='utf-8')
    (OLD_DOCS/'profit-protection.html').write_text(page, encoding='utf-8')
    print(DOCS/'report.html')


HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>通道与利润保护测试 · Heimdall</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#1a2934;font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1350px;margin:auto;padding:32px}h1{font-size:29px;line-height:1.45}h2{font-size:21px}a{color:#176b59}.muted{color:#64747f;font-size:14px}.panel{background:white;border:1px solid #dce3e7;border-radius:12px;margin:22px 0;padding:24px}.warning{border-left:4px solid #ba8746}.tag{display:inline-block;background:#e2ede7;color:#256046;padding:3px 10px;border-radius:5px}.controls,nav{display:flex;align-items:center;gap:18px;flex-wrap:wrap}select{font:inherit;border:1px solid #aab8c0;border-radius:5px;background:white;padding:7px}table{border-collapse:collapse;width:100%;font-size:14px;white-space:nowrap}th,td{border-bottom:1px solid #e5eaed;padding:10px;text-align:right}th{background:#f5f7f9}th:first-child,td:first-child{text-align:left}.scroll{overflow:auto}.positive{color:#167051}.negative{color:#b73b49}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}.card{border-left:3px solid #3c7c67;padding-left:16px}.big{font-size:25px;font-weight:bold}svg{width:100%;display:block}summary{cursor:pointer;color:#176b59}@media(max-width:750px){main{padding:16px}.panel{padding:16px}.cards{grid-template-columns:1fr}h1{font-size:23px}}</style>
<main><nav><a href="diagnostics.html">← 上一轮亏损诊断</a><a href="comparison.html">最初两年比较</a><a id="candidate">在项目中看利润保护逐笔交易</a></nav>
<p><span class="tag">21 组参数 · 84 次分段模拟 · 12 次固定入场对照 · 不计手续费和滑点</span></p>
<h1>利润保护与反向信号，任一条件都能平仓。<br>测试已完成，收益和保护利润之间存在取舍。</h1>
<p>ETH/USDT 15 分钟，2024-09-10 至 2026-09-10；使用项目已有行情。初始 10,000 USDT，每次按当前账户全部资金开仓，不加杠杆。</p>
<section class="panel"><h2>目前看到了什么</h2><div class="cards"><div class="card"><div class="big">1 万 → 37,350</div><p>门槛改为 0.8、不加利润保护。两年最多从资金高点跌 34.47%，最长连续亏 31 笔。</p></div><div class="card"><div class="big">1 万 → 36,425</div><p>同样通道，盈利 2% 后启动，回吐一半就退出。最大跌幅 31.96%，最长连续亏 24 笔。</p></div><div class="card"><div class="big">最近仍亏 13.08%</div><p>上述保护版最近十八天做了 66 笔，赢 17 笔、亏 49 笔。问题尚未解决。</p></div></div></section>
<section class="panel"><h2>两种平仓条件的具体规则</h2><p><strong>利润保护：</strong>比如 100 做多，最高涨到 110，浮盈是 10；允许回吐一半，就把保护线放在 105。涨到 112，保护线再抬到 106，不能跟着回落放宽。做空方向相反。</p><p><strong>反向信号：</strong>无论当前是否盈利、保护是否启动，反向信号都可以平仓。满足新方向入场条件就换方向，不满足就先空仓。利润保护退出后，须等新的合格突破信号才再开仓。</p><p class="muted">本轮每根十五分钟收盘更新保护线，新线下一根才生效，已生效的线可盘中触发。反向信号收盘确认、下一开盘成交。跳空越线按真实开盘价，不能回头用同一根后来出现的最高点改善成交。这是十五分钟更新的测试，不是逐笔行情实时移动。</p></section>
<section class="panel"><h2>四组重点对照</h2><div class="controls"><label>时段 <select id="period"><option value="full">完整两年</option><option value="selection">前一年</option><option value="validation">后续历史</option><option value="recent">最近十八天</option></select></label></div><p class="muted" id="periodnote"></p><div class="scroll"><table id="focus"></table></div><svg id="chart" viewBox="0 0 1200 340" aria-label="四组候选每日收盘资金比较" role="img"></svg><p id="legend" class="muted"></p><p class="muted">曲线按每日收盘显示，最大跌幅使用每根十五分钟收盘资金计算。各分段独立从 10,000 开始。</p></section>
<section class="panel"><h2>它救回了亏损，也提前结束了部分大盈利</h2><p>对比相同 0.8 通道，加“盈利 2% 启动、回吐 50%”后，2,252 个原入场时刻全部能一一对应。原来亏损的交易中，<strong>73 笔变成盈利</strong>；原来盈利的交易中，<strong>146 笔赚得更少，248 笔赚得更多</strong>。原盈利交易平均赚 2.04%，保护后这些交易平均赚 1.77%，说明大盈利被截短的影响不能忽略。</p><p>提前退出后又产生了 <strong>349 笔额外入场</strong>，因此完整结果变成 2,601 笔。把原入场时刻固定住、不增加额外入场，另测得到两年收益 172.39%；不能把整套策略的 264.25% 全部归因于保护线。</p><div class="scroll"><table id="exits"></table></div><p class="muted">本表对应 0.8 通道、2% 启动、回吐 50% 的完整两年，共 2,601 笔，赢 883 笔、亏 1,718 笔。反向信号换仓与反向信号平仓后空仓，都是用户要求的反向退出。</p></section>
<section class="panel"><h2>全部参数结果</h2><div class="controls"><label>比较什么 <select id="group"><option value="width">九组通道宽度</option><option value="protection">原 0.99 通道＋六组利润保护</option><option value="combination">0.8 通道＋六组利润保护</option></select></label></div><p class="muted">沿用上方时段选择。中心线始终 EMA31，不追单上限始终为两倍宽度，彩色云带粗细不影响交易。</p><div class="scroll"><table id="allresults"></table></div></section>
<section class="panel warning"><h2>哪些是提前选出的，哪些只是新的研究线索</h2><p>只看前一年，按收益／最大跌幅挑出的通道是 <strong>31／0.8</strong>。旧 31／0.99 通道挑出的保护是 <strong>1% 启动、回吐 50%</strong>；它后续亏 20.99%，两年最大跌幅变成 49.41%。这个失败结果没有被换掉。</p><p>在 31／0.8 上，前一年排名仍然选择<strong>不加保护</strong>。2% 启动、回吐 50% 是看完各段结果后发现的取舍：总收益略少，最大跌幅较小，后续历史有所改善。它没有赢得预先规定的筛选。</p><p>相邻参数也并非都好：宽度周期换成 20 或 40 后，后续历史多数亏损。最近十八天全部 21 组都亏损。目前无法宣布某组是稳定最佳参数，仍需之后新增行情检验。</p></section><footer class="muted" id="provenance"></footer></main>
<script>const X=__DATA__,D=X.data,R=D.results,V=D.variants,focus=['w31_m99','w31_m80','w31_m99_a1_g50','w31_m80_a2_g50'];let period='full',group='width';const colors=['#657b89','#16795a','#b3753b','#456cca'];const f=(v,n=2)=>v==null?'—':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:n,maximumFractionDigits:n}),cls=v=>v>0?'positive':v<0?'negative':'';
const shortnames={'w31_m99':'原 0.99 门槛，无利润保护','w31_m80':'0.8 门槛，无利润保护（首年选出）','w31_m99_a1_g50':'0.99 门槛，1% 启动／回吐 50%（首年选出）','w31_m80_a2_g50':'0.8 门槛，2% 启动／回吐 50%（探索取舍）'};
function label(k){let p=V[k].parameters;return shortnames[k]||`宽度EMA${p.width_length}／门槛${p.trigger_mult}`+(p.activation_pct?`／盈利${p.activation_pct}%启动、回吐${p.giveback_pct}%`:'／无利润保护')}
function table(keys,id){document.getElementById(id).innerHTML='<thead><tr><th>设置</th><th>收益 %</th><th>最大跌幅 %</th><th>交易笔数</th><th>盈利 / 亏损</th><th>胜率 %</th><th>平均赢一笔抵几笔亏损</th><th>最长连续亏损</th></tr></thead><tbody>'+keys.map(k=>{let r=R[k][period],run=X.project_runs[k];return `<tr><td>${run?`<a target="_blank" href="http://127.0.0.1:4173/research/backtests?run=${run.run_id}">${label(k)}</a>`:label(k)}</td><td class="${cls(r.return_pct)}">${f(r.return_pct)}</td><td>${f(r.max_drawdown_pct)}</td><td>${r.total_trades}</td><td>${r.wins} / ${r.losses}</td><td>${f(r.win_rate)}</td><td>${f(r.payoff_ratio)}</td><td>${r.max_consecutive_losses}</td></tr>`}).join('')+'</tbody>'}
function chart(){let arrays=focus.map(k=>R[k][period].daily_equity),values=arrays.flatMap(a=>a.map(p=>p.equity)),lo=Math.min(10000,...values),hi=Math.max(10000,...values),pad=(hi-lo)*.06;lo-=pad;hi+=pad;const x=i=>80+i/Math.max(1,arrays[0].length-1)*1090,y=v=>290-(v-lo)/(hi-lo)*250;let s='';for(let j=0;j<5;j++){let v=lo+(hi-lo)*j/4;s+=`<line x1="80" x2="1170" y1="${y(v)}" y2="${y(v)}" stroke="#e4eaed"/><text x="70" y="${y(v)+4}" text-anchor="end" font-size="12" fill="#64747f">${f(v,0)}</text>`}s+=`<line x1="80" x2="1170" y1="${y(10000)}" y2="${y(10000)}" stroke="#91a2ad" stroke-dasharray="5 5"/>`;arrays.forEach((a,j)=>s+=`<path d="${a.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(p.equity).toFixed(1)).join(' ')}" fill="none" stroke="${colors[j]}" stroke-width="2"/>`);[0,Math.floor((arrays[0].length-1)/2),arrays[0].length-1].forEach(i=>s+=`<text x="${x(i)}" y="324" text-anchor="${i===0?'start':i===arrays[0].length-1?'end':'middle'}" font-size="12" fill="#64747f">${arrays[0][i].date}</text>`);document.getElementById('chart').innerHTML=s;document.getElementById('legend').innerHTML=focus.map((k,i)=>`<span style="color:${colors[i]};margin-right:16px">● ${label(k)}</span>`).join(' ')}
function update(){table(focus,'focus');let keys=Object.keys(V).filter(k=>V[k].group===group);if(group==='protection')keys.unshift('w31_m99');if(group==='combination')keys.unshift('w31_m80');table(keys,'allresults');chart();let dates=D.plan.periods[period];document.getElementById('periodnote').textContent=dates[0].slice(0,10)+' 至 '+dates[1].slice(0,10)+'（UTC，结束不含）。'}
document.getElementById('period').onchange=e=>{period=e.target.value;update()};document.getElementById('group').onchange=e=>{group=e.target.value;update()};update();
const reasons={profit_protection:'利润回吐触及保护线',reversal:'反向信号平仓并换方向',signal:'反向信号平仓，过滤后先空仓',end_of_backtest:'回测结束结算'};document.getElementById('exits').innerHTML='<thead><tr><th>退出原因</th><th>交易笔数</th><th>盈利笔数</th><th>亏损笔数</th></tr></thead><tbody>'+Object.entries(R.w31_m80_a2_g50.full.exit_reasons).map(([k,r])=>`<tr><td>${reasons[k]||k}</td><td>${r.count}</td><td>${r.wins}</td><td>${r.losses}</td></tr>`).join('')+'</tbody>';
let candidate=X.project_runs.w31_m80_a2_g50;document.getElementById('candidate').href=candidate?'http://127.0.0.1:4173/research/backtests?run='+candidate.run_id:'#';document.getElementById('candidate').target='_blank';document.getElementById('provenance').textContent='关闭新保护后，原基准的逐笔交易和资金曲线完全相同。68 项相关测试通过，前端类型检查通过。行情 SHA-256：'+D.provenance.data_hash+'。引擎版本 '+D.provenance.environment.engine+'。';
</script></html>'''


if __name__ == '__main__':
    main()
