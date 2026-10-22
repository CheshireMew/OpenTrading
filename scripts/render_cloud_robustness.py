"""Plain-language report, retaining every trial and the failed selection rule."""
from html import escape
import json

from scripts.cloud_robustness_study import DOCS, ROOT
from scripts.profit_protection_study import read


def pct(x):
    return f'{x:+.2f}%'


def main():
    data = read(DOCS/'results.json')
    assert data['status'] == 'completed'
    receipt = read(DOCS/'project-runs.json')
    plan, rr = data['plan'], data['rolling']['report']
    ef = data['fixed_quarters']['efficiency20']['report']
    ef_full = data['results']['efficiency20']['full']
    best = data['fixed_quarters'][data['retrospective_best']]['report']
    conclusion = ('本轮通过预先设定的继续研究门槛，但仍需新数据验证。' if data['decision']['continue_research'] else
                  '停止在这批历史数据上继续调参。原策略暂不作为稳定盈利方案；过滤震荡版保留为未验证候选。')
    rows = []
    for fold in plan['folds']:
        choice = data['choices'][fold['id']]['selected']
        result = data['results'][choice][fold['id']+'-test'] if choice else {'return_pct':0,'total_trades':0,'wins':0,'losses':0}
        rows.append(f"| {fold['test'][0][:10]} 至 {fold['test'][1][:10]} | {plan['variants'][choice]['name'] if choice else '空仓'} | {pct(result['return_pct'])} | {result['total_trades']} | {result['wins']} / {result['losses']} |")
    compare = []
    for key in ['anchor','no_protection','center55','center89','trend96','efficiency20','efficiency30','alternate']:
        r = data['fixed_quarters'][key]['report']
        qs = [data['results'][key][f'q{i}-test']['return_pct'] for i in range(1,5)]
        compare.append(f"| {plan['variants'][key]['name']} | {pct(r['return_pct'])} | {r['max_drawdown_pct']:.2f}% | {sum(x>0 for x in qs)} / 4 | {r['total_trades']} | {r['wins']} / {r['losses']} |")
    records = '\n'.join(f"| {v['name']} | `{key}` | {pct(data['results'][key]['full']['return_pct'])} | [{receipt['runs'][key]['run_id']}](http://127.0.0.1:4173/research/backtests?run={receipt['runs'][key]['run_id']}) |" for key,v in plan['variants'].items())
    notes = f'''# ETH 通道策略：这一轮稳健性检查

{conclusion}

本轮固定 20 个版本，共 148 次历史模拟：48 次用前一年选参数、80 次检查接下来三个月、20 次完整两年回放。随后将 20 个完整回放分别保存为项目正式记录，并核对逐笔交易。继续使用项目保存的 Binance ETH/USDT 15 分钟行情，2024-09-10 至 2026-09-10；不计算手续费和滑点，不加杠杆，每次使用账户资金的 100%。所有日期为 UTC，结束日期不含。

## 最重要的结果

每三个月，只用此前一年的成绩挑一个版本，再看接下来三个月。这样连续做四段，10,000 变成 {rr['final_equity']:,.2f}，赚 {rr['return_pct']:.2f}%；但途中从账户高点最多跌了 {rr['max_drawdown_pct']:.2f}%，四段中只有一段赚钱。共 {rr['total_trades']} 笔，赚 {rr['wins']} 笔、亏 {rr['losses']} 笔。总盈利金额 / 总亏损金额只有 {rr['profit_factor']:.3f}，盈利优势很薄。

| 接下来检查的三个月 | 只用过去选出的版本 | 该段收益 | 笔数 | 盈利 / 亏损 |
| --- | --- | ---: | ---: | ---: |
{chr(10).join(rows)}

这里暴露的是：过去表现好的设置，换一段行情不一定继续好。不能看完四段，再把当时选错的版本换掉，假装事先就选中了赢家。

## 有改善，但还不能宣布稳定盈利

所有固定版本都用相同的四段比较，范围是 2025-09-10 至 2026-09-10。每段边界都平仓，下一段沿用上段资金；即使固定参数也执行相同边界规则。这与前一份报告的日期分法、连续持仓方式不同，因此数字不能直接混用。

| 固定版本 | 后一年合计收益 | 从高点最大跌幅 | 赚钱的三个月段数 | 笔数 | 盈利 / 亏损 |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(compare)}

过滤震荡的 20% 版更值得保留：后一年收益 {pct(ef['return_pct'])}，最大跌幅 {ef['max_drawdown_pct']:.2f}%，四段均赚钱，共 {ef['total_trades']} 笔，赚 {ef['wins']} 笔、亏 {ef['losses']} 笔。完整两年则是 {ef_full['total_trades']} 笔，赚 {ef_full['wins']} 笔、亏 {ef_full['losses']} 笔，收益 {pct(ef_full['return_pct'])}、最大跌幅 {ef_full['max_drawdown_pct']:.2f}%。它降低了交易频率和跌幅，也放弃了一部分原策略在强趋势中赚到的钱。

它的意思是：最近八小时，如果价格来回折返很多、实际没走多远，就不开新单。用这八小时起点到终点的距离，除以中间每一步涨跌距离的总和，至少达到 20% 才准入场。例如累计走了 100 美元，最终离起点不到 20 美元，就暂不交易。开仓仍需突破通道且不能追得太远；盈利 2% 后允许回吐一半利润，或者出现反向信号，任何一个满足都平仓。过滤条件不阻拦反向信号平仓。

但 20% 是看完本轮才发现较平稳的候选，不能称为事先验证出的赢家。相邻的 30% 版后一年只有 93 笔，收益降到 18.53%，并有一个三个月亏损；需要更多新行情才能判断这个差异是否稳定。

如果只挑后一年收益最大的，会选到 EMA89 中心线版本（{pct(best['return_pct'])}）；它最后一个三个月却亏了 22.21%。如果只挑完整两年收益最大的，会选到 EMA55（+401.16%）；它也有一个三个月亏了 18.48%。这些好看的累计收益不能回答“以后能不能持续赚钱”。

## 为什么停止继续优化

测试前已写下继续研究的筛选标准：四段至少三段盈利、合计盈利、最大跌幅不超过 25%、最差一段不低于 -10%，以及按整周重抽行情后，盈利结论仍有足够余量。事先选参规则只通过“合计盈利”这一项，其余四项都没有通过。这是本轮的研究门槛，不是对稳定盈利的通用定义。

另按连续 7 天和 14 天重抽历史收益，各做 2,000 次，保留连续行情的影响，不把每笔交易当成互不相关。事先选参规则的 95% 年收益区间分别为 {pct(data['bootstrap']['7']['rolling_annual_return_interval_95'][0])} 至 {pct(data['bootstrap']['7']['rolling_annual_return_interval_95'][1])}、{pct(data['bootstrap']['14']['rolling_annual_return_interval_95'][0])} 至 {pct(data['bootstrap']['14']['rolling_annual_return_interval_95'][1])}，都跨过零。它们是依赖历史抽样假设的敏感性检查，不是未来收益预测。

同时考虑“20 个里面挑最好”之后，本轮使用的保守联合区间没有任何版本的盈利下限高于零，也没有任何版本能确认优于上轮利润保护基准。这个检验在不同波动大小的策略之间较保守；它表示证据不足，不能反过来说已经证明策略永远无效。

这两年行情此前已经被反复查看，以上也不是完全未见过的数据验证。继续在同一批数据上微调 19%、21%、22% 等数值，只会增加挑中偶然结果的机会。本轮到此停止，不再扩大参数表，也不因历史冠军好看就替换事先锁定的选择。保留震荡过滤版供以后真正新增的数据检查；没有安排自动测试或实际交易。这一结论只针对本次 ETH 15 分钟通道策略，不代表所有技术分析策略都不可能盈利。

## 版本和逐笔记录

旧策略均未覆盖。`versions/001-before-new-tests` 保存 32 份原策略、引擎、参数和报告文件；`versions/002-frozen-round-v1` 保存本轮测试前的程序和计划。每份副本有 SHA-256 校验清单，版本目录不复用，`versions/history.jsonl` 只追加。后续版本修改前运行 `python -m scripts.cloud_strategy_versions 新版本说明 文件路径…`，并另存新策略文件；不要覆盖旧策略。

本轮所有参数均在 `plan.json`，每段结果在 `results.json`，每次事先选择分别在 `q1-choice.json` 至 `q4-choice.json`，逐笔信号、交易和账户曲线在 `.opentrading_runtime/cloud-robustness-20260910/`。正式项目运行保存了独立策略副本、参数、行情快照和结果，可以从下表查看完整两年的买卖点。

| 版本 | 参数记录标识 | 连续两年收益 | 项目正式记录 |
| --- | --- | ---: | --- |
{records}

引擎仍为 v4，原来的三个基准版本均逐笔交易和账户曲线完全一致。利润保护仍每 15 分钟收盘更新，新线下一根生效；反向信号下一根开盘成交，开盘穿过保护价按实际开盘价平仓。没有新增固定止盈、固定止损或任何交易成本。

复现：`python -m scripts.cloud_robustness_study run`。程序会核对行情、策略、引擎、分析脚本和计划校验值；任何输入变化都会拒绝混入本轮。`python -m scripts.publish_cloud_robustness` 将本轮完整回放保存在项目，并核对所有交易和信号。
'''
    (DOCS/'REPORT.md').write_text(notes,encoding='utf-8')
    embedded = {'data':data,'runs':receipt['runs']}
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ETH 策略：稳健性检查与版本记录</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#1c2732;font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1400px;margin:36px auto;padding:0 26px 64px}h1{font-size:32px;letter-spacing:-1px;line-height:1.3}h2{font-size:22px;margin:0 0 14px}p{max-width:1080px}a{color:#245b9b}section{background:#fff;border:1px solid #dce1e7;border-radius:12px;padding:24px;margin:20px 0}.muted,small{color:#647284}.verdict{background:#fff4df;border-color:#dfbd77}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.card{background:white;border:1px solid #dce1e7;border-radius:12px;padding:18px}.card b{display:block;font-size:29px}.positive{color:#146a47}.negative{color:#b53e44}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:11px 12px;text-align:right;border-bottom:1px solid #e7ebef;white-space:nowrap}th{color:#546374;background:#f7f9fb;font-weight:600}td:first-child,th:first-child{text-align:left;white-space:normal;min-width:220px}tbody tr:hover{background:#f6f9fc}.scroll{overflow-x:auto}select,button{padding:9px 12px;border:1px solid #bdc7d0;background:#fff;border-radius:7px;color:inherit;font:inherit}.controls{display:flex;gap:16px;flex-wrap:wrap;margin:15px 0}.pill{font-size:12px;color:#607080}.legend{display:flex;gap:24px;flex-wrap:wrap;font-size:14px}.legend span:before{content:'●';margin-right:6px}svg{width:100%;height:auto;display:block}.foot{font-size:14px}.rules{font-size:15px}details{margin-top:16px}summary{cursor:pointer;color:#245b9b}@media(max-width:750px){main{padding:0 12px}.cards{grid-template-columns:repeat(2,1fr)}section{padding:16px}h1{font-size:25px}}
</style><main>
<div class="muted">ETH / USDT · 15 分钟 · 项目原有行情与回测引擎 · 不计手续费和滑点</div>
<h1>调出好成绩，和稳定赚钱，是两件需要分别检查的事</h1>
<section class="verdict"><h2 id="verdict"></h2><p>这轮固定测试了 20 个版本，共 148 次历史模拟，并把 20 个完整两年结果保存为项目记录。旧策略没有被覆盖。所有历史已经看过，这次只能检查稳健性，不能冒充全新数据验证。</p></section>
<h2>只用过去挑版本，接下来一年发生了什么</h2><p>每次用此前一年挑选一个版本，然后固定用三个月；连续做四次。期间不因后来的成绩难看而重选。</p>
<div class="cards" id="cards"></div>
<section><div class="scroll"><table><thead><tr><th>检查日期（UTC）</th><th>事先选出的版本</th><th>收益</th><th>笔数</th><th>盈利 / 亏损</th></tr></thead><tbody id="folds"></tbody></table></div><p id="rolling-summary"></p></section>
<section><h2>过滤震荡的版本更平稳，但还只是候选</h2><p id="candidate"></p><p>它先看最近八小时：如果价格来回折返很多、最后实际没走多远，就暂不开单。突破通道仍是入场条件；盈利 2% 后回吐一半利润，或出现反向信号，都能独立平仓。过滤条件不拦住反向平仓。</p><p>这是看完这轮比较才发现的候选。相邻的 30% 过滤版本交易明显减少，后一年仍有一段亏损。保留两个副本，到此停止在同一批历史上继续细调，等待真正新增的行情再判断。</p>
<div class="legend"><span style="color:#b45309">事先选参组合</span><span style="color:#526a87">上轮利润保护版</span><span style="color:#087f70">震荡过滤 20%</span></div><div id="chart"></div><small>10,000 USDT 起步，按日显示账户资金。比较范围均为 2025-09-10 至 2026-09-10；每三个月边界平仓，资金连续计算。</small></section>
<section><h2>全部 20 个版本，好的和差的都在</h2><div class="controls"><label>查看范围 <select id="period"><option value="quarters">后一年，按四段拼接</option><option value="full">完整两年，连续运行</option></select></label><label>版本类别 <select id="group"><option value="all">全部版本</option><option value="reference">旧基准对照</option><option value="neighbor">相邻参数</option><option value="methods">不同入场方法</option></select></label></div><p class="muted" id="table-note"></p><div class="scroll"><table><thead><tr><th>版本</th><th>收益</th><th>从高点最大跌幅</th><th>笔数</th><th>盈利 / 亏损</th><th>第一段收益</th><th>第二段收益</th><th>第三段收益</th><th>第四段收益</th><th>完整两年买卖点</th></tr></thead><tbody id="variants"></tbody></table></div><p class="foot">四段分别从 2025-09-10、2025-12-10、2026-03-10、2026-06-10 开始，每段三个月。后一年边界平仓的口径与上份报告不同，请不要混用数字。</p></section>
<section><h2>为什么现在停止</h2><p id="stop"></p><p>测试前约定：四段至少三段赚钱、合计赚钱、账户从高点最大跌幅不超过 25%、最差一段亏损不超过 10%，以及整周重抽行情后盈利仍有足够余量。事先选参只通过“合计赚钱”，其余四项没过。</p><details><summary>查看统计检查和它的局限</summary><p id="stats"></p><p>同时考虑从 20 个版本中挑选的影响后，本轮较保守的联合区间没有一个版本能确认盈利下限高于零，也没有确认哪个版本优于上轮基准。这表示证据不足，并不证明永远无效。统计依赖历史行情的抽样假设；不能消除我们已经反复查看这些数据带来的偏差。</p></details><p>结论只针对本次 ETH 15 分钟通道策略。旧版停止继续堆参数；震荡过滤版留下研究记录，还不能称为稳定盈利方案。</p></section>
<section><h2>每次修改都有副本</h2><p>旧文件保存在 <code>versions/001-before-new-tests</code>，本轮测试前程序和计划保存在 <code>versions/002-frozen-round-v1</code>。每份副本带文件校验值；版本历史只追加。20 个参数版本的完整两年正式记录可从上表直接打开。</p><p class="foot">记录目录：<code>D:\\Code\\OpenTrading\\docs\\verification\\eth-cloud-robustness-20260910</code><br>逐笔记录：<code>D:\\Code\\OpenTrading\\.opentrading_runtime\\cloud-robustness-20260910</code></p><p><a href="profit-protection.html">查看上一轮利润保护报告</a> · <a href="http://127.0.0.1:4173/research/backtests">打开项目回测记录</a></p></section>
</main><script>const payload=__DATA__;
const d=payload.data, plan=d.plan, variants=plan.variants, rr=d.rolling.report;
const pct=x=>(x>=0?'+':'')+x.toFixed(2)+'%', cls=x=>x>=0?'positive':'negative';
const cell=x=>`<td class="${cls(x)}">${pct(x)}</td>`;
document.querySelector('#verdict').textContent=__CONCLUSION__;
document.querySelector('#cards').innerHTML=[['后一年合计收益',pct(rr.return_pct)],['途中从高点最大跌幅',rr.max_drawdown_pct.toFixed(2)+'%'],['赚钱的三个月段数','1 / 4'],['总交易笔数',rr.total_trades]].map(([a,b])=>`<div class="card"><small>${a}</small><b>${b}</b></div>`).join('');
document.querySelector('#folds').innerHTML=plan.folds.map(f=>{const k=d.choices[f.id].selected,r=k?d.results[k][f.id+'-test']:{return_pct:0,total_trades:0,wins:0,losses:0};return `<tr><td>${f.test[0].slice(0,10)} 至 ${f.test[1].slice(0,10)}</td><td>${k?variants[k].name:'空仓'}</td>${cell(r.return_pct)}<td>${r.total_trades}</td><td>${r.wins} / ${r.losses}</td></tr>`}).join('');
document.querySelector('#rolling-summary').textContent=`10,000 最后变成 ${rr.final_equity.toFixed(2)}。共 ${rr.total_trades} 笔：赚 ${rr.wins} 笔，亏 ${rr.losses} 笔。此前一年更好看的版本，换到下一段行情，优势并没有稳定延续。`;
const ef=d.fixed_quarters.efficiency20.report, eff=d.results.efficiency20.full;
document.querySelector('#candidate').textContent=`过滤震荡 20% 版：后一年赚 ${ef.return_pct.toFixed(2)}%，途中最大跌幅 ${ef.max_drawdown_pct.toFixed(2)}%，四段都赚钱；共 ${ef.total_trades} 笔，赚 ${ef.wins} 笔、亏 ${ef.losses} 笔。完整两年是 ${eff.total_trades} 笔、收益 ${pct(eff.return_pct)}、最大跌幅 ${eff.max_drawdown_pct.toFixed(2)}%。收益和跌幅的取舍比原版更平稳。`;
function render(){const period=document.querySelector('#period').value,group=document.querySelector('#group').value;document.querySelector('#table-note').textContent=period==='full'?'主体指标：2024-09-10 至 2026-09-10 连续两年。右侧四段收益仍展示后一年各段，方便看稳定性。':'主体指标：2025-09-10 至 2026-09-10，四段资金连续计算。点击最右侧可查看该版本完整两年的逐笔交易。';document.querySelector('#variants').innerHTML=Object.entries(variants).filter(([k,v])=>group==='all'||group===v.family||(group==='methods'&&!['reference','neighbor'].includes(v.family))).map(([k,v])=>{const r=period==='full'?d.results[k].full:d.fixed_quarters[k].report,run=payload.runs[k];return `<tr><td>${v.name}<br><span class="pill">${k}</span></td>${cell(r.return_pct)}<td>${r.max_drawdown_pct.toFixed(2)}%</td><td>${r.total_trades}</td><td>${r.wins} / ${r.losses}</td>${[1,2,3,4].map(i=>cell(d.results[k]['q'+i+'-test'].return_pct)).join('')}<td><a href="http://127.0.0.1:4173/research/backtests?run=${run.run_id}">查看买卖记录</a></td></tr>`}).join('')}
document.querySelector('#period').addEventListener('change',render);document.querySelector('#group').addEventListener('change',render);render();
document.querySelector('#stop').textContent='只挑两年总收益，会喜欢 EMA55 的 +401.16%；只挑后一年收益，会喜欢 EMA89 的 +69.36%。但它们分别有一个三个月亏了 18.48% 和 22.21%。在同一批行情上再寻找更漂亮的参数，越来越容易选中偶然结果。';
document.querySelector('#stats').textContent=`按连续 7 天、14 天分别重抽 2,000 次。事先选参组合的 95% 年收益区间分别为 ${d.bootstrap['7'].rolling_annual_return_interval_95.map(pct).join(' 至 ')}、${d.bootstrap['14'].rolling_annual_return_interval_95.map(pct).join(' 至 ')}。区间包含亏损，不能据此确认稳定优势；这些也不是对未来收益的预测。`;
const curves=[{p:d.rolling.daily_equity,c:'#b45309'},{p:d.fixed_quarters.anchor.daily_equity,c:'#526a87'},{p:d.fixed_quarters.efficiency20.daily_equity,c:'#087f70'}];
const all=curves.flatMap(v=>v.p.map(p=>p.equity)),lo=Math.floor(Math.min(10000,...all)/1000)*1000,hi=Math.ceil(Math.max(...all)/1000)*1000;
const X=i=>70+i/365*1110,Y=v=>270-(v-lo)/(hi-lo)*240;
let svg='<svg viewBox="0 0 1220 320" role="img" aria-label="后一年三组账户资金曲线">';
for(let i=0;i<5;i++){const v=lo+(hi-lo)*i/4;svg+=`<line x1="70" x2="1180" y1="${Y(v)}" y2="${Y(v)}" stroke="#e6ebef"/><text x="61" y="${Y(v)+5}" text-anchor="end" font-size="13" fill="#697786">${Math.round(v)}</text>`}
curves.forEach(c=>{svg+=`<path d="M${X(0)},${Y(10000)} ${c.p.map((p,i)=>`L${X(i+1).toFixed(2)},${Y(p.equity).toFixed(2)}`).join(' ')}" fill="none" stroke="${c.c}" stroke-width="2.4"/>`});
svg+='<text x="70" y="305" font-size="13" fill="#697786">2025-09-10</text><text x="1180" y="305" text-anchor="end" font-size="13" fill="#697786">2026-09-10</text></svg>';document.querySelector('#chart').innerHTML=svg;
</script></html>'''
    html = html.replace('__DATA__',json.dumps(embedded,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')).replace('__CONCLUSION__',json.dumps(conclusion,ensure_ascii=False))
    (DOCS/'report.html').write_text(html,encoding='utf-8')
    (ROOT/'docs/verification/eth-cloud-two-year-20260910/robustness.html').write_text(html,encoding='utf-8')
    print('Wrote report and http://127.0.0.1:8787/robustness.html')


if __name__ == '__main__':
    main()
