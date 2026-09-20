"""Render equal-period comparisons for the frozen six-year joint study."""
from datetime import datetime, timezone
from html import escape
import argparse
import json

from scripts.cloud_joint_study import DOCS, RUNTIME, ROOT, LABELS
from scripts.profit_protection_study import read


def pct(v):
    return f'{v:+,.2f}%'


def description(p):
    return (f"EMA{p['center_length']} · 振幅{p['width_length']} · 突破{p['trigger_mult']:g}倍 · "
            f"最远{p['chase_mult']:g}倍 · 盈利{p['activation_pct']:g}%启动 · 回吐{p['giveback_pct']:g}% · "
            + (f"初始止损{p['initial_stop_pct']:g}%" if p['initial_stop_pct'] else '无初始止损'))


def mdtable(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |']
                     + ['| '+' | '.join(map(str, row))+' |' for row in rows])


def main(allow_pending=False):
    r = read(DOCS/'results.json')
    receipts = read(DOCS/'project-runs.json')
    assert r['status'] == 'completed'
    assert set(receipts['runs']) == set(r['chart_keys'])
    verified_runs = {k:v for k,v in receipts['runs'].items() if v['verified']}
    assert allow_pending or len(verified_runs) == len(receipts['runs'])
    pending_note = (f"128组、1152次计算已全部完成。重点版本的项目图表正在逐一复算核对，目前{len(verified_runs)}/{len(receipts['runs'])}个已核对；"
                    '下方只开放已核对的图表链接。') if len(verified_runs) < len(receipts['runs']) else ''
    plan, results = r['plan'], r['results']
    top, recent, selected = r['rankings']['full'][0], r['rankings']['recent'][0], r['selection']['selected']
    aliases = {}
    for k, n in [(top, '六年收益第一'), (recent, '近两年收益第一'), (selected, '只看前四年选出的版本'),
                 (plan['original'], '最初第一名'), (plan['previous_winner'], '上轮第一名（3%启动）'),
                 (plan['requested_example'], 'EMA65＋振幅40＋3%＋回吐40%'),
                 (plan['requested_example_stop'], '上述组合再加1%止损')]:
        aliases[k] = aliases.get(k, '') + ('；' if k in aliases else '') + n
    shortlist = list(aliases)
    names = {k: aliases.get(k, f"组合 {i+1:03d}") for i, k in enumerate(plan['variants'])}
    periods = {'full': '六年累计（2020/9—2026/9）', 'recent': '近两年累计（2024/9—2026/9）',
               **{f'y{i+1}': f'{2020+i}/9—{2021+i}/9' for i in range(6)},
               'selection': '前四年累计（2020/9—2024/9）'}
    scope = 'ETH/USDT，15分钟；2020年9月10日—2026年9月10日。沿用项目行情与成交规则，每笔使用当时全部资金，不加杠杆，不计手续费和滑点。下文总收益包含资金滚动，不是年化收益。'
    annual_note = '每个年度都是当年9月10日至次年9月10日，均为完整一年。年度分别从空仓开始、到期平仓；六年和两年总回测持续持仓，因此年度结果连乘不一定等于连续回测。只在相同日期范围内比较排名。'
    caveat = '这128组全部跑完了，但每个参数只选两个值，因此只能说是本轮范围内第一，不能说是长期最佳。参数范围参考过2024—2026年的旧结果，后两年已经被反复看过，不能称为完全独立的新行情验证。六年第一也是看完历史挑出的；逐年盈利并不保证以后盈利。'
    full = results[top]['full']
    years_positive = sum(results[top][f'y{i}']['return_pct'] > 0 for i in range(1, 7))
    headline = f"六年第一：{pct(full['return_pct'])}，六个年度中{years_positive}年盈利。"
    top_description = description(plan['variants'][top]['parameters'])
    recent_loss_years = sum(results[recent][f'y{i}']['return_pct'] < 0 for i in range(1, 7))
    interpretation = (f"只看近两年，第一名会换成另一组参数，近两年收益为{pct(results[recent]['recent']['return_pct'])}；"
                      f"但它在六个年度中有{recent_loss_years}年亏损。六年第一在近两年的排名是第{r['rankings']['recent'].index(top)+1}/128，"
                      f"近两年收益为{pct(results[top]['recent']['return_pct'])}。这次扩大年份确实改变了选择，不能用某一段的第一名代表长期最佳。")
    positive_full = sum(v['full']['return_pct'] > 0 for v in results.values())
    weak_losses = sum(v['y3']['return_pct'] < 0 for v in results.values())
    positive_each = sum(all(v[f'y{i}']['return_pct'] > 0 for i in range(1, 7)) for v in results.values())
    interpretation += (f"本轮{positive_full}/128组的六年累计收益为正，但2022/9—2023/9这一年有{weak_losses}组亏损；"
                       f"六个年度都盈利的有{positive_each}组。")
    factor_interpretation = (f"例如，把启动保护的浮盈从2%改为3%，近两年64组对照里有{r['interactions']['recent']['activation_pct']['better']}组收益提高，"
                            f"但放到六年里只有{r['interactions']['full']['activation_pct']['better']}组提高。"
                            f"增加1%初始止损，六年64组中有{r['interactions']['full']['initial_stop_pct']['better']}组收益提高；"
                            f"把最远入场距离从2倍放宽到2.5倍，则只有{r['interactions']['full']['chase_mult']['better']}组提高。"
                            '这些是本批固定参数和历史行情的对照结果，没有根据它们继续追加调参。')
    payload = dict(names=names, aliases=aliases, parameters={k:v['parameters'] for k,v in plan['variants'].items()},
                   results=results, rankings=r['rankings'], periods=periods, shortlist=shortlist, top=top,
                   original=plan['original'], selected=selected, neighbors=r['top_neighbors'],
                   interactions=r['interactions'], labels=LABELS,
                   runs={k:v['run_id'] for k,v in verified_runs.items()}, data_hash=plan['data_hash'])
    headers = ['版本', '六年累计', '近两年累计', '赚钱笔数', '亏钱笔数', '胜率']
    rows = [[names[k], pct(results[k]['full']['return_pct']), pct(results[k]['recent']['return_pct']),
             results[k]['full']['wins'], results[k]['full']['losses'], f"{results[k]['full']['win_rate']:.2f}%"] for k in shortlist]
    annual_headers = ['版本']+[periods[f'y{i}'] for i in range(1, 7)]
    annual_rows = [[names[k]]+[pct(results[k][f'y{i}']['return_pct']) for i in range(1, 7)] for k in shortlist]
    chart_url = lambda k: f"http://127.0.0.1:4173/research/backtests?run={receipts['runs'][k]['run_id']}&view=chart&theme=light&tz=8"
    missing = sum(g['missing_bars'] for g in plan['gaps'])
    gap_note = (f"原行情有{len(plan['gaps'])}段空档，共{missing}根15分钟K线（{missing/4:g}小时）；通过项目数据接口重查后仍无记录。"
                '没有补造K线。持仓和信号延续到下一条实际行情，空档内部是否触发退出无法确定。'
                '下面把直接跨空档的交易收益暂按零重算，只用于说明结果对这些交易有多敏感，不是另一套可执行策略；空档之后的指标也可能受影响。')
    gap_rows = [[names[k], results[k]['full']['gap_sensitivity']['affected_trades'],
                 pct(results[k]['full']['return_pct']), pct(results[k]['full']['gap_sensitivity']['return_with_affected_set_to_zero_pct'])] for k in shortlist]
    gap_table = '<div class="scroll"><table><thead><tr>'+''.join(f'<th>{x}</th>' for x in ['版本','跨空档交易','六年累计','这些交易按零计算'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in row)+'</tr>' for row in gap_rows)+'</tbody></table></div>'
    md = '\n\n'.join(['# 六年联合参数测试', headline, top_description, scope, interpretation, factor_interpretation, caveat,
        '## 重点版本', mdtable(headers, rows), '## 同样长度的年度对比', annual_note, mdtable(annual_headers, annual_rows),
        '## 每个版本的参数', '\n'.join(f'- {names[k]}：{description(plan["variants"][k]["parameters"])}。' for k in shortlist),
        '## 历史空档', gap_note, mdtable(['版本','跨空档交易','六年累计','这些交易按零计算'], gap_rows),
        '## 查看与恢复', pending_note, '\n'.join(f'- [{names[k]}，K线和实际成交]({chart_url(k)})' for k in shortlist if k in verified_runs),
        f'全部128个参数配置：`{RUNTIME}/variants`。策略副本：`{RUNTIME}/strategy.py`。每组9份逐笔记录：`{RUNTIME}/组合ID-期间.json`。',
        '完整排名、逐年结果、64组同条件参数对照、第一名附近7组结果见 report.html；原有报告和策略副本均保留。',
        f'固定试验计划：plan.json；数据来源与空档：data.json / gap-recheck.json；计算结果：results.json；项目回放核对：project-runs.json。数据SHA256：`{plan["data_hash"]}`。'])
    (DOCS/'REPORT.md').write_text(md+'\n', encoding='utf-8')
    html = TEMPLATE.replace('__HEADLINE__', escape(headline)).replace('__DESCRIPTION__', escape(top_description))
    html = html.replace('__SCOPE__', escape(scope)).replace('__CAVEAT__', escape(caveat)).replace('__ANNUAL_NOTE__', escape(annual_note))
    html = html.replace('__GAP_NOTE__', escape(gap_note)).replace('__GAP_TABLE__', gap_table)
    html = html.replace('__INTERPRETATION__', escape(interpretation)).replace('__FACTOR_INTERPRETATION__', escape(factor_interpretation))
    html = html.replace('__PENDING__', '<p class="notice">'+escape(pending_note)+'</p>' if pending_note else '')
    html = html.replace('__DATA__', json.dumps(payload, ensure_ascii=False).replace('</', '<\\/'))
    (DOCS/'report.html').write_text(html, encoding='utf-8')
    (ROOT/'docs/verification/eth-cloud-two-year-20260910/joint-six-year.html').write_text(html, encoding='utf-8')
    print(json.dumps(dict(report=str(DOCS/'REPORT.md'), top=top, full_return=full['return_pct'], published_runs=len(receipts['runs'])), ensure_ascii=False))


TEMPLATE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ETH 六年联合参数测试</title>
<style>
:root{font-family:Inter,"Microsoft YaHei",sans-serif;color:#233042;background:#f4f6f9;font-size:15px}*{box-sizing:border-box}body{margin:0}main{max-width:1500px;margin:auto;padding:40px 28px 70px}h1{font-size:32px;letter-spacing:-1px;margin:15px 0}h2{font-size:21px;margin:0 0 15px}h3{font-size:17px}p{line-height:1.8;max-width:1100px}a{color:#265db5}header{margin-bottom:28px}.eyebrow{font-size:13px;font-weight:700;color:#526880}.lead{font-size:22px;color:#15594b;font-weight:700}.muted,.note{color:#607086}.note{font-size:13px;line-height:1.7}.notice{background:#fff3dc;border-left:3px solid #d19b36;padding:14px 20px;border-radius:4px}section{background:white;border:1px solid #e1e5ec;border-radius:14px;margin:22px 0;padding:26px}.scroll{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}th,td{padding:13px 14px;border-bottom:1px solid #e8ecf1;text-align:right;white-space:nowrap}th{background:#f6f8fb;color:#5c6b80;font-size:12px}td:first-child,th:first-child{text-align:left}td small{display:block;color:#718198;max-width:430px;white-space:normal;margin-top:5px;line-height:1.6}tr.active{background:#edf7f4}.positive{color:#12775b}.negative{color:#c04646}.tools{display:flex;gap:16px;align-items:center;flex-wrap:wrap}select,button{border:1px solid #ccd5df;border-radius:7px;padding:9px 12px;background:white;color:#233042;font:inherit;max-width:100%}button{cursor:pointer}button:hover{background:#eef4fc}label{font-size:13px;display:flex;align-items:center;gap:8px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0}.card{border:1px solid #e4e9ee;border-radius:10px;padding:18px}.card strong{display:block;font-size:24px;margin-top:8px}.tag{background:#edf2f8;padding:4px 8px;border-radius:4px;font-size:12px}.param{display:flex;gap:10px;flex-wrap:wrap;line-height:2}.chart-link{display:inline-block;margin:10px 0}.topline{display:flex;justify-content:space-between;align-items:center;gap:20px}details{margin-top:20px}summary{cursor:pointer;font-weight:600}code{font-size:12px;overflow-wrap:anywhere}footer{color:#64758a;font-size:13px;line-height:1.8}@media(max-width:700px){main{padding:22px 12px}section{padding:18px}h1{font-size:27px}.cards{grid-template-columns:repeat(2,1fr)}td,th{padding:10px}.topline{display:block}}
</style><main><header><div class="eyebrow">ETH / USDT · 15 分钟 · 128 种组合 · 1,152 次计算</div><h1>把参数放到六年里比较</h1><p class="lead">__HEADLINE__</p><p>__DESCRIPTION__</p><p class="muted">__SCOPE__</p><p class="notice">__CAVEAT__</p></header>
__PENDING__<section><h2>每一年，到底赚了多少</h2><p>__INTERPRETATION__</p><p>这里直接对照六年第一、之前的版本，以及你提出的参数组合。每一列中的日期完全相同；红色代表该年亏损。</p><div id="annual"></div><p class="note">__ANNUAL_NOTE__</p></section>
<section><div class="topline"><h2>128 种组合，按收益率排名</h2><label>比较期间 <select id="period"></select></label></div><p class="note">切换到某个年度后，所有128组都会按该年度重新排名。胜率和交易次数仅展示，不参与排序。</p><div class="tools"><label>显示 <select id="limit"><option value="10">前10名</option><option value="128">全部128组</option></select></label></div><div id="ranking"></div></section>
<section><h2>检查某个组合</h2><label>选择版本 <select id="variant"></select></label><p class="param" id="params"></p><div class="cards" id="cards"></div><div id="variantYears"></div><div class="tools"><span id="chart"></span><button id="download">保存这组参数</button></div><p class="note">K线链接使用项目的正式回测记录，已与本轮逐笔结果核对一致。按照试验前保存的计划，重点版本提供正式图表；全部128组均已保存策略副本、参数和9个时间段的逐笔记录。</p></section>
<section><h2>只用前四年选出的版本，后两年如何</h2><p>先在2020/9—2024/9里选收益第一，保存选择后再计算剩余期间。下面只比较同样的2024/9—2026/9。后两年此前已经反复看过，所以这项检查不能冒充全新的独立验证。</p><div id="selection"></div></section>
<section><h2>改一个参数，效果是否经常更好</h2><p>每个参数有64组对照：其他六个参数完全一样，只改这一项。这样能看出一个改动是否只在少数组合里占便宜。</p><p>__FACTOR_INTERPRETATION__</p><label>比较期间 <select id="factorPeriod"><option value="full">六年</option><option value="recent">近两年</option><option value="selection">前四年</option></select></label><div id="factors"></div><h3>第一名附近的7组参数</h3><p class="note">每组只把第一名的一个参数换为本轮测试的另一个值。差一点点是否就差很多，可以直接看；这只能反映本次两个取值之间的变化。</p><div id="neighbors"></div></section>
<section><h2>原始行情的空档</h2><p>__GAP_NOTE__</p>__GAP_TABLE__</section>
<footer>旧的单参数报告、策略源码和记录均保留。<a href="parameters.html">查看上一轮40个版本</a>。本轮固定范围每个参数只有两个值，跑完即停止，没有根据结果追加搜索。<details><summary>交易规则和记录位置</summary><p>中心线使用高低价中点的EMA；W是每根最高价减最低价的EMA，不是ATR。收盘价从门槛内穿到中心线加突破倍数×W的上方，且离中心线没有超过最远距离，才发做多信号；向下穿过对应下门槛则做空。信号在收盘确认，下一条实际K线开盘成交。同向持仓不加仓；出现反向信号会退出，反向入场仍需满足距离限制。</p><p>达到设定浮盈后，按持仓期间最高浮盈的允许回吐比例设置保护线，每根收盘后更新、下一根生效。初始止损从实际开仓价计算，入场当根即可触发。反向信号、已经生效的保护线或初始止损都能平仓。没有固定止盈。</p><p>全部配置：<code>D:/Code/Heimdall/.heimdall_runtime/cloud-joint-six-year-20260911/variants</code><br>策略副本和各组逐笔记录：<code>D:/Code/Heimdall/.heimdall_runtime/cloud-joint-six-year-20260911</code><br>计划、结果、数据核对和正式回放记录：<code>D:/Code/Heimdall/docs/verification/eth-cloud-joint-six-year-20260911</code></p><p id="hash"></p></details></footer></main>
<script>
const D=__DATA__;const $=s=>document.getElementById(s);const fmt=v=>(v>=0?'+':'')+v.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+'%';
const pc=v=>'<span class="'+(v>=0?'positive':'negative')+'">'+fmt(v)+'</span>';
const desc=k=>{let p=D.parameters[k];return `EMA${p.center_length} / 振幅${p.width_length} / 突破${p.trigger_mult}倍 / 最远${p.chase_mult}倍 / ${p.activation_pct}%启动 / 回吐${p.giveback_pct}% / ${p.initial_stop_pct?'止损'+p.initial_stop_pct+'%':'无初始止损'}`};
const name=k=>D.names[k]+'<small>'+desc(k)+'</small>';
function table(h,r){return '<div class="scroll"><table><thead><tr>'+h.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+r.map(x=>'<tr>'+x.map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'}
function annual(keys){return table(['版本',...Array.from({length:6},(_,i)=>D.periods['y'+(i+1)])],keys.map(k=>[name(k),...Array.from({length:6},(_,i)=>pc(D.results[k]['y'+(i+1)].return_pct))]))}
$('annual').innerHTML=annual(D.shortlist);$('period').innerHTML=Object.entries(D.periods).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');
$('variant').innerHTML=D.rankings.full.map(k=>`<option value="${k}">${D.names[k]}：${desc(k)}</option>`).join('');
function rank(){let p=$('period').value;let keys=D.rankings[p].slice(0,Number($('limit').value));$('ranking').innerHTML=table(['排名 / 版本',D.periods[p]+'收益','胜率','赚钱 / 亏钱 / 持平','总笔数','查看参数'],keys.map((k,i)=>{let v=D.results[k][p];return [`${i+1}. ${name(k)}`,pc(v.return_pct),v.win_rate.toFixed(2)+'%',`${v.wins} / ${v.losses} / ${v.breakeven}`,v.total_trades,`<button data-key="${k}">检查</button>`]}));$('ranking').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('variant').value=b.dataset.key;inspect();$('variant').scrollIntoView({block:'center'})})}
function inspect(){let k=$('variant').value,p=D.parameters[k],v=D.results[k].full;$('params').innerHTML=Object.entries(D.labels).map(([f,n])=>'<span class="tag">'+n+'：'+p[f]+'</span>').join('');$('cards').innerHTML=[['六年累计',fmt(v.return_pct)],['近两年累计',fmt(D.results[k].recent.return_pct)],['六年胜率',v.win_rate.toFixed(2)+'%'],['赚钱 / 亏钱',v.wins+' / '+v.losses]].map(([a,b])=>'<div class="card">'+a+'<strong>'+b+'</strong></div>').join('');$('variantYears').innerHTML=annual([k]);$('chart').innerHTML=D.runs[k]?`<a class="chart-link" href="http://127.0.0.1:4173/research/backtests?run=${D.runs[k]}&view=chart&theme=light&tz=8" target="_blank" rel="noopener">打开K线、指标与实际成交 ↗</a>`:'这组逐笔记录已保存；本轮未为它另建正式图表。'}
$('download').onclick=()=>{let k=$('variant').value;let blob=new Blob([JSON.stringify({strategy:'trend_cloud_parameters_v4',parameters:D.parameters[k],data_hash:D.data_hash,version:k},null,2)],{type:'application/json'});let u=URL.createObjectURL(blob);let a=document.createElement('a');a.href=u;a.download=k+'.json';a.click();URL.revokeObjectURL(u)};
$('selection').innerHTML=table(['版本','相同后两年收益','后两年排名','2024/9—2025/9','2025/9—2026/9'],[...new Set([D.selected,D.original,D.top])].map(k=>[name(k),pc(D.results[k].recent.return_pct),(D.rankings.recent.indexOf(k)+1)+'/128',pc(D.results[k].y5.return_pct),pc(D.results[k].y6.return_pct)]));
function factors(){let p=$('factorPeriod').value;$('factors').innerHTML=table(['只改这一项','收益提高的组数','收益降低的组数'],Object.entries(D.interactions[p]).map(([f,v])=>[`${D.labels[f]}：${v.from_value} → ${v.to_value}`,v.better+' / '+v.comparisons,v.worse+' / '+v.comparisons]))}
$('neighbors').innerHTML=table(['版本 / 相对第一名的改动','六年累计','近两年累计'],[D.top,...D.neighbors].map(k=>[k===D.top?'六年第一':Object.keys(D.labels).filter(f=>D.parameters[k][f]!==D.parameters[D.top][f]).map(f=>D.labels[f]+'改为'+D.parameters[k][f]).join('、'),pc(D.results[k].full.return_pct),pc(D.results[k].recent.return_pct)]));
$('hash').textContent='行情 SHA256：'+D.data_hash;$('period').onchange=rank;$('limit').onchange=rank;$('variant').onchange=inspect;$('factorPeriod').onchange=factors;rank();inspect();factors();
</script></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-pending', action='store_true', help='Show completed calculations while formal charts are still being verified')
    main(parser.parse_args().allow_pending)
