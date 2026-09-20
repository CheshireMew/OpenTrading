"""Readable parameter comparison backed by the frozen project study."""
from html import escape
import json
from scripts.cloud_parameter_study import DOCS, ROOT, GROUPS
from scripts.profit_protection_study import read


def pct(v, signed=False):
    return '—' if v is None else f'{v:+.2f}%' if signed else f'{v:.2f}%'


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def mdtable(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str, row))+' |' for row in rows])


def main():
    r = read(DOCS/'results.json')
    receipts = read(DOCS/'project-runs.json')
    assert r['status'] == 'completed' and all(x['verified'] for x in receipts['runs'].values())
    v, y = r['variants'], r['following_year']
    full = lambda k: r['results'][k]['full']
    train = lambda k: r['results'][k]['selection']
    name = lambda k: v[k]['name']
    url = lambda k: 'http://127.0.0.1:4173/research/backtests?run='+receipts['runs'][k]['run_id']+'&view=chart&theme=light&tz=8'
    b = full('baseline')
    top = r['rankings']['full'][0]
    selected = r['selection']['selected']
    scope = '同一批项目缓存行情：2024/9/10—2026/9/10，ETH/USDT 十五分钟；每笔使用当时全部资金，不加杠杆，不计手续费和滑点。收益是资金滚动后的累计收益，不是年化收益。'
    caveat = '这两年行情此前已经反复看过。本轮先根据前一年选参数、再查看后一年，只能检查参数换个时间段是否还有效，不能当成全新行情上的独立验证，也不能证明某个周期长期最佳。'
    factor_rows, details = [], {}
    for group, (title, fields) in GROUPS.items():
        keys = ['baseline']+[k for k, x in v.items() if x['group'] == group]
        best = max(keys, key=lambda k: full(k)['return_pct'])
        following_best = max(keys, key=lambda k: y[k]['return_pct'])
        def value(k):
            p = v[k]['parameters']
            if group == 'stop':
                return f"{p['initial_stop_pct']:g}%" if p['initial_stop_pct'] else f"{p['initial_stop_width']:g}W" if p['initial_stop_width'] else '无初始止损'
            n = p[fields[0]]
            if group == 'activation' and n == 0:
                return '关闭保护'
            if group == 'chase' and n == 0:
                return '不限制'
            return f'{n:g}'+(' 根' if group in ('center', 'width') else 'W' if group in ('trigger', 'chase') else '%')
        factor_rows.append([title, value('baseline'), value(best), pct(full(best)['return_pct'], True),
                            value(following_best), pct(y[following_best]['return_pct'], True)])
        details[group] = dict(title=title, keys=keys, labels={k: value(k) for k in keys})
    summary = [
        f'原第一名完整两年收益 {pct(b["return_pct"], True)}。这轮完整两年收益最高的是“{name(top)}”：{pct(full(top)["return_pct"], True)}，共 {full(top)["total_trades"]} 笔，赚 {full(top)["wins"]} 笔、亏 {full(top)["losses"]} 笔，胜率 {pct(full(top)["win_rate"])}。这是看完整两年后排出的第一名。',
        f'只根据前一年选，锁定的是“{name(selected)}”：前一年 {pct(train(selected)["return_pct"], True)}，后一年 {pct(y[selected]["return_pct"], True)}；原版后一年是 {pct(y["baseline"]["return_pct"], True)}。选定后没有根据后来结果改选。',
        '共测试 37 个逐项对照版本和 3 个按前一年结果组成的版本，每版跑前一年、后四个季度及完整两年，共 240 次。另有 40 条带 K 线的项目记录，逐笔成交与研究结果核对一致。旧策略、冻结参数表和每个版本的结果都已保留。'
    ]
    rules = [
        ('中心线周期', '55 是价格平滑的快慢，不是已经证实的最佳数字。周期越长，通常越迟钝，穿越信号也会变化。本轮比较 21、31、45、55、65、89；其他条件先保持原样。'),
        ('通道振幅与突破门槛', 'W 是近期每根十五分钟 K 线“最高价减最低价”的平滑平均，不是 ATR。振幅平均周期测 14、21、31、40、55；入场门槛测离中心 0.4、0.6、0.8、1、1.2 倍 W。两项分别改变。图上浅色云带的边缘是 0.45W，实际入场门槛另算。'),
        ('算多远才不追', '原版要求信号收盘价离中心不超过 2W。假设中心是 3000，W 是 12，做多信号既要向上突破 3009.6，又不能收得高于 3024。本轮测 1.25、1.5、2、2.5、3W，以及不限制。判断用信号收盘价，下一根开盘成交。'),
        ('浮盈达到多少才保护', '关闭保护，或浮盈达到 0.5%、1%、1.5%、2%、2.5%、3% 才启动。这里先固定回吐 50%。达到门槛用持仓后的有利最高／最低价判断，收盘后更新保护线，下一根才生效。'),
        ('回吐多少就平仓', '分别允许最高浮盈回吐 25%、40%、50%、60%、75%，启动点先固定 2%。例如最多浮盈 6%，允许回吐 50%，就是退回盈利约 3% 的保护价时退出，不是允许价格下跌 50%。'),
        ('初始止损', '原版没有。新增固定亏损 0.5%、1%、1.5%、2%、3% 的版本，以及按 2、3、4W 决定初始距离的版本。振幅版先用信号时 W 换成价格百分比，再从实际成交价算止损；开仓后不会因为振幅变大而放宽。'),
        ('三个退出条件如何配合', '加止损后，初始止损、利润回吐保护、反向信号都可以平仓，哪个先触发就按哪个退出。利润保护只能把初始止损向盈利方向推进。初始止损开仓即生效；跳过止损价的开盘按实际开盘价成交，不能保证亏损正好等于设置值。'),
    ]
    findings = [
        f'EMA55 不是本轮测试里收益最高的周期。只改成 EMA65，两年收益是 {pct(full("center65")["return_pct"], True)}，后一年 {pct(y["center65"]["return_pct"], True)}，都超过 EMA55。但更慢的 EMA89 两年只有 {pct(full("center89")["return_pct"], True)}，不是越慢越好；六个周期的历史比较不能证明 65 长期最佳。',
        f'振幅平均周期有影响。保留中心 EMA55，把振幅平均从 EMA31 改为 EMA40，两年收益 {pct(full("width40")["return_pct"], True)}；改成 EMA55 是 {pct(full("width55")["return_pct"], True)}。相邻两个较慢的设定都高于原版，但这里还没有证明它们与其他新参数组合后也更好。',
        f'入场距离不宜卡得过近。2W 与 2.5W 两年收益分别为 {pct(b["return_pct"], True)}、{pct(full("chase250")["return_pct"], True)}，差别很小；收紧到 1.25W 只剩 {pct(full("chase125")["return_pct"], True)}，完全不限制则为 {pct(full("chase0")["return_pct"], True)}。这批数据支持保留距离限制，但没有显示 2.5 比 2 有明显优势。',
        f'启动点改到 3% 后，平均赚钱一笔从 {pct(b["average_win_return_pct"])} 增至 {pct(full("activate300")["average_win_return_pct"])}，胜率从 {pct(b["win_rate"])} 降到 {pct(full("activate300")["win_rate"])}。它容许更多小盈利回落，留下来的赢家平均赚得更多。改成 0.5% 启动，胜率虽升至 {pct(full("activate50")["win_rate"])}, 后一年收益却只有 {pct(y["activate50"]["return_pct"], True)}。',
        f'回吐比例改为 40%，两年收益 {pct(full("giveback40")["return_pct"], True)}，后一年 {pct(y["giveback40"]["return_pct"], True)}，高于原来 50%。但前一年它低于原版，所以“回吐多少最好”也随时间段变化。这一项始终以 2% 启动保护为前提，没有测完所有启动点与回吐比例的交叉组合。',
        f'1% 初始止损让两年收益从 {pct(b["return_pct"], True)} 变成 {pct(full("stop100")["return_pct"], True)}，平均亏一笔从 {pct(b["average_loss_return_pct"])} 缩小到 {pct(full("stop100")["average_loss_return_pct"])}。但后一年 {pct(y["stop100"]["return_pct"], True)} 仍略低于原版，不能说它总能提高收益。0.5% 止损虽然每次亏得更少，两年却出现 {full("stop50")["losses"]} 次亏损，收益降至 {pct(full("stop50")["return_pct"], True)}。',
    ]
    fh = ['因素', '原版数值', '完整两年收益最高的数值', '该版两年收益', '后一年收益最高的数值', '该版后一年收益']
    th = ['版本', '完整两年收益', '前一年收益', '后一年收益', '胜率（两年）', '赚钱 / 亏钱', '平均赚一笔', '平均亏一笔']
    rows = lambda keys: [[name(k), pct(full(k)['return_pct'], True), pct(train(k)['return_pct'], True), pct(y[k]['return_pct'], True),
                          pct(full(k)['win_rate']), f'{full(k)["wins"]} / {full(k)["losses"]}',
                          pct(full(k)['average_win_return_pct']), pct(full(k)['average_loss_return_pct'])] for k in keys]
    stopkeys = ['baseline']+[k for k, x in v.items() if x['group'] == 'stop']
    sh = ['初始止损', '两年收益', '后一年收益', '触发初始止损次数', '最大账户回撤', '平均亏一笔']
    sr = [[details['stop']['labels'][k], pct(full(k)['return_pct'], True), pct(y[k]['return_pct'], True),
           full(k)['exit_reasons'].get('stop_loss', {}).get('count', 0), pct(full(k)['max_drawdown_pct']), pct(full(k)['average_loss_return_pct'])] for k in stopkeys]
    ph = ['止损版本', '可对应的相同入场', '原亏损中亏得更少', '原盈利中赚得更少', '原盈利中赚得更多', '新增加的入场']
    pr = [[name(k), x['matched'], x['losses_reduced'], x['winners_reduced'], x['winners_improved'], x['additional_entries']]
          for k, x in r['paired_stops']['full'].items()]
    pairing_note = '只比较入场时间与方向完全一致的交易，看单笔价格收益变化，避免资金滚动造成金额不可比。止损后还可能出现新的入场，所以这张表只解释变化，完整收益必须看实际重新回测。不能把“亏得更少”和“少赚”的笔数直接相减当收益。'
    combo_keys = ['baseline', 'entry_combo', 'exit_combo', 'all_combo']
    combo_text = '三个组合都是用前一年各因素的收益第一名拼成，包含保留原参数的选择。入场组合只换入场因素，退出组合只换利润保护和初始止损，全组合同时换。它们不是在完整两年上穷举所有数字后拼出的组合；单项好，组合未必好。'
    qh = ['版本', '前一年', '后一年第1季', '第2季', '第3季', '第4季', '后一年合计']
    qrows = [[name(k), pct(train(k)['return_pct'], True), *[pct(r['results'][k][f'q{i}']['return_pct'], True) for i in range(1, 5)], pct(y[k]['return_pct'], True)] for k in dict.fromkeys(['baseline', selected, top])]
    notes = ['前一年是 2024/9/10—2025/9/10。后一年四个季度分别为 2025/9/10—12/10、2025/12/10—2026/3/10、2026/3/10—6/10、2026/6/10—9/10。日期边界按 UTC。后一年合计把四个季度的资金接起来，每个季度开始、结束都空仓；完整两年则连续持仓，因此不是简单加减关系。', caveat,
             '3% 是本轮利润保护启动点的测试上限；它排第一，只说明在本轮列出的数值里两年收益最高，没有证明更高或更细的数字都不如它。本轮按事先确定的范围结束，没有看到结果后继续加数字。',
             '本页始终按收益排序，胜率、亏损次数和回撤只用于说明变化，不作为排除高收益版本的门槛。单项表是在其余条件保持原版时的结果，并非所有组合中的最优值。']
    md = '# EMA55 第一名策略：逐项参数测试\n\n'+'\n\n'.join(summary+[scope, caveat])+'\n\n'
    md += '## 哪些数字有影响\n\n'+mdtable(fh, factor_rows)+'\n\n'
    md += '## 用人话解释结果\n\n'+'\n\n'.join(findings)+'\n\n'
    for group, d in details.items():
        md += '## '+d['title']+'\n\n'+mdtable(th, rows(d['keys']))+'\n\n'
    md += '## 加初始止损的变化\n\n'+mdtable(sh, sr)+'\n\n'+mdtable(ph, pr)+'\n\n'+pairing_note+'\n\n'
    md += '## 前一年选定的组合\n\n'+combo_text+'\n\n'+mdtable(th, rows(combo_keys))+'\n\n'
    md += '## 换时间段是否仍然好\n\n'+mdtable(qh, qrows)+'\n\n'+'\n\n'.join(notes)+'\n\n'
    md += '## 各项怎么执行\n\n'+'\n\n'.join('### '+a+'\n\n'+b for a, b in rules)+'\n\n'
    md += '## 全部版本与 K 线\n\n'+'\n'.join(f'- [{name(k)}]({url(k)})' for k in r['rankings']['full'])+'\n'
    (DOCS/'REPORT.md').write_text(md, encoding='utf-8')
    css = '''body{margin:0;background:#f5f6f8;color:#26343e;font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1280px;margin:28px auto;padding:0 22px 55px}section{background:white;border:1px solid #dce3e8;border-radius:12px;padding:24px;margin:20px 0}h1{font-size:30px;line-height:1.5}h2{font-size:23px;margin:0 0 14px}h3{font-size:18px}.muted{font-size:14px;color:#637580}.notice{background:#fff9e9;border-color:#dbc998}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}.card{background:#fff;border:1px solid #dce3e8;border-radius:9px;padding:16px}.card strong{font-size:30px;display:block}.card span{font-size:14px}a,summary{color:#24618e}summary{cursor:pointer}details{margin:16px 0}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;border-bottom:1px solid #e4e9ec;text-align:right;white-space:nowrap}td:first-child,th:first-child{text-align:left}th{background:#f5f7f9}select{font:inherit;padding:6px;border:1px solid #9aaab7;border-radius:6px;background:white;margin:0 15px 14px 5px}p{max-width:1160px}.positive{color:#14694a}.negative{color:#b34848}tr.baseline{background:#eef5fb}tr.baseline td:first-child:before{content:"原版 · ";font-weight:600}code{background:#eef1f5;padding:2px 4px}'''
    paras = lambda texts: ''.join('<p>'+escape(t)+'</p>' for t in texts)
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EMA55 第一名策略 · 参数测试</title><style>'+css+'</style><main><a href="context-signals.html">← 之前的研究</a><p class="muted">ETH / USDT · 十五分钟 · 不计手续费和滑点 · 按收益排序</p><h1>EMA55、入场距离、利润保护和止损，分别测过以后</h1>'
    html += '<section class="notice"><h2>这次测到了什么</h2>'+paras(summary)+'<div class="cards">'
    for k, title in [('baseline', '原第一名'), (top, '本轮完整两年收益第一'), (selected, '只按前一年选出的版本')]:
        html += '<div class="card">'+title+'<strong>'+pct(full(k)['return_pct'], True)+'</strong><span>'+escape(name(k))+'<br>后一年 '+pct(y[k]['return_pct'], True)+'</span><br><a href="'+url(k)+'">查看 K 线和逐笔成交</a></div>'
    html += '</div><p class="muted">'+scope+'</p></section>'
    html += '<section><h2>各因素单独改，哪个数值的收益高？</h2>'+table(fh, factor_rows)+'<p class="muted">“完整两年最高”与“后一年最高”都是事后排名。每行只改该因素，其余仍用原第一名的参数；不代表长期最佳。</p></section>'
    html += '<section><h2>这些结果说明了什么</h2>'+paras(findings)+'</section>'
    html += '<section><h2>全部 40 个版本，按收益从高到低看</h2><label for="period">时间段</label><select id="period"><option value="full">完整两年</option><option value="selection">前一年</option><option value="following_year">后一年（四季度接续）</option>'+''.join(f'<option value="q{i}">后一年第 {i} 季</option>' for i in range(1, 5))+'</select><label for="factor">只看某项</label><select id="factor"><option value="all">全部版本</option>'+''.join('<option value="'+g+'">'+d['title']+'</option>' for g, d in details.items())+'<option value="combined">三个组合</option></select><div id="ranking"></div><p class="muted">点击版本可查看真实回测 K 线。只看某项时，原版始终保留作对照；表格会按所选时间段的收益重新排序。</p></section>'
    html += '<section><h2>浮盈达到 2% 才启动，是否合适？</h2>'+paras([rules[3][1]])+table(th, rows(details['activation']['keys']))+'<p class="muted">这里改变启动点，回吐比例都为 50%，没有同时改其他数字。</p><details><summary>允许回吐比例也单独测试了</summary>'+paras([rules[4][1]])+table(th, rows(details['giveback']['keys']))+'</details></section>'
    html += '<section><h2>止损能少亏多少，又会不会少赚？</h2>'+table(sh, sr)+paras([rules[5][1], rules[6][1]])+'<details><summary>查看相同入场的逐笔对照</summary>'+table(ph, pr)+paras([pairing_note])+'</details></section>'
    html += '<section><h2>单项较好的数字，拼起来还好吗？</h2>'+paras([combo_text])+table(th, rows(combo_keys))+'<details><summary>查看三个组合的确切参数</summary><ul>'+''.join('<li>'+escape(name(k))+': <code>'+escape(json.dumps({f: x for f, x in v[k]['parameters'].items() if f != 'record_indicators'}, ensure_ascii=False))+'</code></li>' for k in combo_keys[1:])+'</ul></details></section>'
    html += '<section><h2>换个时间段，结果是否重复？</h2>'+table(qh, qrows)+paras(notes)+'</section>'
    html += '<section><h2>每个参数说的是哪件事</h2>'+''.join('<h3>'+a+'</h3><p>'+b+'</p>' for a, b in rules)+'</section>'
    html += '<section><h2>每个版本都可以回来继续查</h2><p>原第一名没有修改。新版本使用独立策略 <code>trend_cloud_parameters_v4</code>，保留了 240 次分段结果与 40 条正式项目记录。原版六个时间段的成交和账户曲线均与旧记录完全一致。</p><p class="muted">D:\\Code\\Heimdall\\docs\\verification\\eth-cloud-parameters-20260910：plan.json 是事先冻结的范围，factor-selection.json 和 selection.json 是前一年选择记录，results.json 是全部结果，project-runs.json 是逐笔核对记录；源码副本从 021 开始。</p></section></main>'
    dataset = {k: dict(name=name(k), group=v[k]['group'], url=url(k), periods={**{p: {f: x.get(f) for f in ['return_pct', 'win_rate', 'total_trades', 'wins', 'losses', 'max_drawdown_pct', 'average_win_return_pct', 'average_loss_return_pct']} for p, x in r['results'][k].items()},
                'following_year': {f: y[k].get(f) for f in ['return_pct', 'win_rate', 'total_trades', 'wins', 'losses', 'max_drawdown_pct', 'average_win_return_pct', 'average_loss_return_pct']}}) for k in v}
    html += '<script>const data='+json.dumps(dataset, ensure_ascii=False).replace('<', '\\u003c')+''';
const fmt=(v,s=false)=>v==null?'—':(s&&v>=0?'+':'')+v.toFixed(2)+'%';
function render(){const period=document.querySelector('#period').value,group=document.querySelector('#factor').value;
const rows=Object.entries(data).filter(([k,v])=>group==='all'||k==='baseline'||v.group===group).sort((a,b)=>b[1].periods[period].return_pct-a[1].periods[period].return_pct);
const root=document.querySelector('#ranking');root.replaceChildren();const scroll=document.createElement('div');scroll.className='scroll';const table=document.createElement('table');
const head=document.createElement('thead'),hr=document.createElement('tr');['名次','版本','总收益','胜率','赚钱次数','亏钱次数','总笔数','平均赚一笔','平均亏一笔','最大账户回撤'].forEach(s=>{const th=document.createElement('th');th.textContent=s;hr.append(th)});head.append(hr);table.append(head);
const body=document.createElement('tbody');rows.forEach(([key,v],i)=>{const m=v.periods[period],tr=document.createElement('tr');if(key==='baseline')tr.className='baseline';
const vals=[i+1,v.name,fmt(m.return_pct,true),fmt(m.win_rate),m.wins,m.losses,m.total_trades,fmt(m.average_win_return_pct),fmt(m.average_loss_return_pct),fmt(m.max_drawdown_pct)];
vals.forEach((val,j)=>{const td=document.createElement('td');if(j===1){const a=document.createElement('a');a.href=v.url;a.textContent=val;td.append(a)}else td.textContent=String(val);if(j===2)td.className=m.return_pct>=0?'positive':'negative';tr.append(td)});body.append(tr)});table.append(body);scroll.append(table);root.append(scroll)}
document.querySelector('#period').addEventListener('change',render);document.querySelector('#factor').addEventListener('change',render);render();
</script></html>'''
    (DOCS/'report.html').write_text(html, encoding='utf-8')
    (ROOT/'docs/verification/eth-cloud-two-year-20260910/parameters.html').write_text(html, encoding='utf-8')
    print('http://127.0.0.1:8787/parameters.html')


if __name__ == '__main__':
    main()
