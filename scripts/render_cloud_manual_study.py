"""Human-readable manual-trading study, using only recorded project runs."""
from datetime import datetime, timezone, timedelta
from html import escape
import json

from app.domain.backtest_diagnostics import summarize
from scripts.cloud_manual_study import DOCS, RUNTIME, ROOT
from scripts.profit_protection_study import read, save, paired_entries


NAMES={
    'baseline':'原版：浮盈 2%，回吐 50%',
    'confirm2':'连续两根确认后入场',
    'confirm3':'连续三根确认后入场',
    'retest4':'等回踩，最多一小时',
    'retest8':'等回踩，最多两小时',
    'efficiency40':'震荡过滤从 20% 提高到 40%',
    'protect05':'浮盈 0.5%，回吐 40%',
    'protect10':'浮盈 1%，回吐 40%',
    'giveback30':'浮盈 2%，回吐 30%',
    'runner3':'浮盈 3%，回吐 60%',
    'confirm2protect05':'两根确认＋浮盈 0.5% 保护',
    'retest8protect10':'回踩确认＋浮盈 1% 保护',
}


def pct(n):
    return f'{n:+.2f}%'


def mdtable(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+
                     ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])


def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join(f'<th>{escape(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def main():
    data=read(DOCS/'results.json')
    assert data['status']=='completed' and data['baseline_exact']
    assert data['accepted_selected_candidate'] is None, 'Review narrative if conclusions change'
    assert data['selection']['selected']=='protect10'
    receipts=read(DOCS/'project-runs.json')
    baseline=read(RUNTIME/'baseline-full.json')
    pairs={k:paired_entries(baseline,read(RUNTIME/f'{k}-full.json')) for k in ('protect05','protect10','giveback30','runner3')}
    sides={}
    exits={}
    for key in NAMES:
        t=read(RUNTIME/f'{key}-following-year.json')['trades']
        sides[key]={side:summarize([v for v in t if v['side']==side]) for side in ('long','short')}
        exits[key]={reason:summarize([v for v in t if v['exit_reason']==reason]) for reason in sorted({v['exit_reason'] for v in t})}
    save(DOCS/'diagnostics.json',dict(matched_entries=pairs,following_year_sides=sides,following_year_exits=exits))
    headers=['版本','交易','赚 / 亏 / 持平','赚钱比例','平均赚一笔','平均亏一笔','总收益','最长连亏','最大跌幅']

    def rows(period):
        out=[]
        for k in NAMES:
            m=data['following_year'][k] if period=='year' else data['results'][k][period]
            win=m.get('average_win_return_pct',m.get('avg_win_return_pct'))
            loss=m.get('average_loss_return_pct',m.get('avg_loss_return_pct'))
            flat=m['total_trades']-m['wins']-m['losses']
            out.append([NAMES[k],m['total_trades'],f"{m['wins']} / {m['losses']} / {flat}",f"{m['win_rate']:.1f}%",f'{win:.2f}%',f'{loss:.2f}%',pct(m['return_pct']),m['max_consecutive_losses'],f"{m['max_drawdown_pct']:.2f}%"])
        return out

    yearrows,fullrows=rows('year'),rows('full')
    qheaders=['版本','2025/9/10—12/10','2025/12/10—2026/3/10','2026/3/10—6/10','2026/6/10—9/10']
    qrows=[[NAMES[k]]+[f"{pct(data['results'][k][f'q{i}']['return_pct'])}；赚 {data['results'][k][f'q{i}']['wins']} / 亏 {data['results'][k][f'q{i}']['losses']}" for i in range(1,5)] for k in NAMES]
    base=data['following_year']['baseline']
    early=data['following_year']['protect05']
    selected=data['following_year']['protect10']
    late=data['following_year']['runner3']
    tight=data['following_year']['giveback30']
    p=pairs['protect05']
    top=max(baseline['trades'],key=lambda t:t['return_pct'])
    earlytop=next(t for t in read(RUNTIME/'protect05-full.json')['trades'] if t['entry_time']==top['entry_time'] and t['side']==top['side'])
    local=lambda t:datetime.fromtimestamp(t/1000,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')

    lead='这轮没有找到同时满足“赚钱次数多于亏钱次数”和“后续表现仍可靠”的版本。提前保护利润能提高胜率，却削弱了用大赚弥补小亏的能力；加强入场确认也没有解决这个问题。按你提出的手工操作要求，这一套暂时不采用。'
    scope='沿用项目里的 ETH/USDT 十五分钟行情与回测引擎。完整两年为 2024-09-10 至 2026-09-10，后一年为 2025-09-10 至 2026-09-10，日期均为 UTC、结束不含。不计算手续费和滑点，不加杠杆，每次使用当时账户全部资金。完整两年连续运行；后一年沿用原研究分成四段、每三个月末平仓并连续计算资金的规则，所以两者交易数不一定能直接相减。'
    losses='原过滤震荡版两年亏损 525 笔。其中 290 笔在持仓过程中最高浮盈也没到 0.5%，说明进场后没有走出足够的有利行情；另外 235 笔曾浮盈至少 0.5%，但都没到原来 2% 的保护启动线，后来被反向信号平掉。前者主要是入场后走势未能延续，后者还包括已有利润没有保护住。这是交易结束后的分类，不是开仓时能预知的名单。'
    direction='“方向不一致”没有得到这批交易的支持：逆着过去八小时净方向开的仅 15 笔，合计还贡献正利润。不能因为这个猜想听起来合理，就直接增加一条过滤规则。'
    filtering='测试了突破后连续两根或三根收在门槛外再入场，以及突破后等一小时或两小时内回踩确认。它们减少了总交易数，却也减少了盈利交易；后一年赚钱比例只有约 26%—31%，比原来的 34% 还低。等确认没有让这些入场更可靠，不能把“交易变少”说成“亏损被有效过滤”。'
    er='当前用过去 32 根十五分钟 K 线，也就是八小时，判断价格是否一直来回折返。把这八小时每次收盘涨跌的距离全部加起来，再看起点到终点实际走了多远。例如来回一共走了 100 美元，最后只离起点 10 美元，比例就是 10%，不新开仓；至少达到 20% 才允许开仓。这个比例只衡量过去走得顺不顺，不能保证下一段继续走趋势。提高到 40% 后，两年只剩 25 笔、11 赚 14 亏；过滤太严会把大量机会一起挡掉，也没有足够交易支撑结论。'
    earlytext=f'浮盈达到 0.5% 就启动保护，允许最高浮盈回吐 40%。后一年共 {early["total_trades"]} 笔，赚 {early["wins"]} 笔、亏 {early["losses"]} 笔，赚钱比例 {early["win_rate"]:.1f}%，但平均赚一笔只有 {early["avg_win_return_pct"]:.2f}%，平均亏一笔 {early["avg_loss_return_pct"]:.2f}%，最后总收益 {pct(early["return_pct"])}。赢得更多次，仍然会亏钱。两年合计则是 605 赚、376 亏，赚 10.06%；不能用两年合计掩盖后一年的退步。'
    paired=f'对齐完全相同的进场时刻和方向后，提前保护把原来的 {p["losses_turned_into_wins"]} 笔亏损变成了盈利；代价是原来 {p["winners_reduced"]} 笔盈利交易赚得更少。原来 285 笔赢家的平均单笔收益，从 {p["winners_baseline_average_return_pct"]:.2f}% 降到 {p["winners_protected_average_return_pct"]:.2f}%。此外多出了 {p["additional_entries"]} 笔提前退出后的再入场，已算在整体回测里，不能只统计被救回来的亏损。'
    example=f'原截图那一段也能说明代价：北京时间 {local(top["entry_time"])} 的同一笔做多，原版持有到 {local(top["exit_time"])}，单笔赚 {top["return_pct"]:.2f}%；提前保护版在 {local(earlytop["exit_time"])} 就退出，同一笔只赚 {earlytop["return_pct"]:.2f}%。这是一个已知案例，不是未来一定会重复的证明；完整结果已包括之后所有再入场。'
    more=f'如果把保护放宽到浮盈 3% 才启动、允许回吐 60%，后一年盈利单平均从 {base["avg_win_return_pct"]:.2f}% 提高到 {late["avg_win_return_pct"]:.2f}%，总收益 {pct(late["return_pct"])}，但赚钱比例降到 {late["win_rate"]:.1f}%，最长连续亏损 {late["max_consecutive_losses"]} 笔。若仍浮盈 2% 启动、只允许回吐 30%，后一年总收益 {pct(tight["return_pct"])}，仍然是 {tight["wins"]} 赚、{tight["losses"]} 亏。这两个版本历史收益更高，却都不符合你不能接受亏损次数更多的要求。'
    choice=f'开始计算前固定了 12 个版本，先用前一年筛掉“亏的次数更多、总收益负、交易不足 50 笔”的版本，再按收益相对于最大跌幅排序。选中的是“浮盈 1%、回吐 40%”：前一年 246 赚、233 亏；后一年却变成 {selected["wins"]} 赚、{selected["losses"]} 亏，虽然总收益 {pct(selected["return_pct"])}，仍不符合要求。不能看到后一年的结果以后，再换成别的版本宣布成功。'
    control='额外检查后一年至少三个季度赚钱、至少三个季度赚的次数多于亏的次数，以及交易数和跌幅。这些是本轮事先写下的研究筛选条件，不代表用户承诺接受某个跌幅。结果不仅预先选中的版本失败，全部 12 个版本也没有一个通过全部条件。此轮共完成 72 次分段或全期回测，参数范围到此停止，不把数字继续调细来迎合已知历史。'
    burden=f'手工执行的负担也没有消失：浮盈 0.5% 版后一年平均每天新开 {early["average_trades_per_day"]:.2f} 笔，最忙一天 {early["max_trades_per_day"]} 笔，最长仍连亏 {early["max_consecutive_losses"]} 笔，平均持仓约 {early["average_duration_minutes"]/60:.1f} 小时。这是全天候执行的模拟，可能夜里进出场，没有假设人工能守住所有信号。不能只看平均一天一笔就说适合手工。'
    rules='这一轮中心线为高低价中点的 EMA31，宽度为每根最高价减最低价的 EMA31。收盘向上穿过“中心＋0.8 倍宽度”考虑做多，向下穿过“中心－0.8 倍宽度”考虑做空；离中心超过 2 倍宽度不追单，还必须满足震荡过滤。新版本只改表中明确写出的入场确认或利润保护参数。反向信号和平仓保护仍分别可以触发退出；入场过滤不会拦住反向平仓。没有额外固定止盈或初始固定止损，尚未盈利时主要靠反向信号退出。'
    execution='收盘确认信号，下一根开盘成交。利润保护根据持仓时已经发生的最高浮盈计算，每十五分钟收盘更新，下一根才生效。例如做多开在 100，最高涨到 100.5，回吐 40% 对应保护价约 100.3；并不代表任意时刻都一定成交在 100.3，价格跳过保护线时按实际开盘处理。这一轮没有按逐笔价格实时移动保护线。'
    caveat='这两年行情此前已经用于反推指标和比较参数，因此“前一年选、后一年检查”仍然是重复使用历史，不能当作从未见过的新行情验证。现在可以据此拒绝一个不符合要求的候选，不能据此保证未来稳赚，也不能推出所有技术策略都无效。'

    sections=[('结论',[lead,scope]),('亏损原因与过滤入场',[losses,direction,filtering]),('提前保护利润的收益和代价',[earlytext,paired,example]),('盈利的时候多赚一点',[more]),('怎么过滤震荡',[er]),('防止看完结果再选规则',[choice,control]),('手工负担和具体买卖规则',[burden,rules,execution]),('证据边界',[caveat])]
    md='# 手工交易要求：多赚几次，能否仍然赚钱\n\n'
    for title,paragraphs in sections:
        md+='## '+title+'\n\n'+'\n\n'.join(paragraphs)+'\n\n'
    md+='## 后一年全部结果\n\n'+mdtable(headers,yearrows)+'\n\n## 完整两年全部结果\n\n'+mdtable(headers,fullrows)+'\n\n## 后一年四个季度\n\n'+mdtable(qheaders,qrows)+'\n\n'
    md+='平均赚亏是每笔相对于进场资金的百分比；总收益按账户实际资金复利计算，不能简单相加。最大跌幅指资金从之前最高点向下跌了多少，按每根收盘权益计算。个别版本存在持平交易，已单列。\n\n'
    md+='## 保存记录\n\n旧策略和报告均保留。本轮独立策略为 `strategies/trend_cloud_manual_v1.py`。`plan.json` 保存事先固定规则，`selection.json` 保存前一年选中的版本，`results.json` 为完整结果，`diagnostics.json` 为逐笔对齐及多空分类，`project-runs.json` 对应项目正式逐笔记录。副本由 `cloud_strategy_versions.py` 保存。\n'
    (DOCS/'REPORT.md').write_text(md,encoding='utf-8')

    links=''.join(f'<li><a href="http://127.0.0.1:4173/research/backtests?run={v["run_id"]}">{escape(NAMES[k])}：查看完整两年逐笔记录</a></li>' for k,v in receipts['runs'].items())
    intro=f'<section class="notice"><p>{lead}</p><p>12 个版本 · 72 次回测 · 未找到符合本轮要求的版本</p></section>'
    prose=''
    for title,paragraphs in sections[1:]:
        prose+=f'<section><h2>{title}</h2>'+''.join(f'<p>{escape(p)}</p>' for p in paragraphs)+'</section>'
    byrange={'year':yearrows,'full':fullrows}
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>手工交易检查 · 胜率和赚亏金额</title>
<style>body{margin:0;background:#f3f5f7;color:#263743;font:16px/1.85 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1180px;margin:30px auto;padding:0 22px 48px}h1{font-size:30px;line-height:1.45}h2{font-size:22px;margin-top:0}section{background:white;border:1px solid #d8e1e6;border-radius:12px;padding:22px;margin:20px 0}.notice{background:#fff5df;border-color:#d7b979}.muted{font-size:14px;color:#647785}a{color:#23628c}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:10px;border-bottom:1px solid #e1e7ec;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{background:#f5f8fa}.scroll{overflow-x:auto}select{padding:9px 12px;font:inherit;margin:0 0 16px 8px;border:1px solid #97a8b3;border-radius:6px;background:white}summary{cursor:pointer;color:#23628c}p{max-width:1050px}li{margin:5px 0}.result-note{margin-top:10px}#results td:nth-child(7){font-weight:650}</style>
<main><a href="profit-audit.html">← 上次的盈利来源检查</a><p class="muted">ETH / USDT · 十五分钟 · 不计算手续费和滑点 · 保留全部旧版</p><h1>赚的次数更多了，为什么总账反而亏了？</h1>'''+intro+f'''<section><h2>把次数和金额放在一起看</h2><label for="period">查看范围</label><select id="period"><option value="year">后一年：2025/9/10—2026/9/10</option><option value="full">完整两年：2024/9/10—2026/9/10</option></select><div id="results">{table(headers,yearrows)}</div><p class="muted">平均赚、亏都是相对于该笔进场资金的百分比。最大跌幅是账户从之前高点跌下来多少。收益使用同一账户复利计算。</p><p class="muted">{scope}</p><details><summary>查看后一年四个季度，是否只是合计好看</summary>{table(qheaders,qrows)}</details></section>'''+prose+f'''<section><h2>版本和逐笔记录均已保存</h2><p>每个版本都能在项目内查看参数、K 线、开平仓和逐笔盈亏。下面链接是完整两年的连续回测；上表“后一年”使用四段拼接，请勿混用交易数。</p><details><summary>展开全部 12 个版本的逐笔记录</summary><ul>{links}</ul></details><p class="muted">独立报告：D:\\Code\\Heimdall\\docs\\verification\\eth-cloud-manual-20260910<br>plan.json：固定计划；selection.json：前一年选择；results.json：结果；diagnostics.json：交易分类；project-runs.json：项目记录。010—012 副本保存本轮开始前与修改前的代码。</p></section></main><script>
const rowsByRange='''+json.dumps(byrange,ensure_ascii=False).replace('<','\u003c')+''';
document.getElementById('period').addEventListener('change',event=>{
  const body=document.querySelector('#results tbody'); body.replaceChildren();
  rowsByRange[event.target.value].forEach(row=>{const tr=document.createElement('tr');row.forEach(value=>{const td=document.createElement('td');td.textContent=String(value);tr.append(td)});body.append(tr)});
});
</script></html>'''
    (DOCS/'report.html').write_text(html,encoding='utf-8')
    (ROOT/'docs/verification/eth-cloud-two-year-20260910/manual-trading.html').write_text(html,encoding='utf-8')
    print('http://127.0.0.1:8787/manual-trading.html')


if __name__=='__main__':
    main()
