"""Render fixed-candidate profit sources without changing strategy selection."""
from datetime import datetime, timezone, timedelta
from html import escape
from scripts.cloud_profit_audit import AUDIT
from scripts.cloud_robustness_study import DOCS, ROOT
from scripts.profit_protection_study import read


def pct(x):
    return f'{x:+.2f}%'


def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join(f'<th>{escape(str(h))}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def main():
    data=read(AUDIT/'results.json')
    assert data['status']=='completed'
    e=data['results']['efficiency20']
    full,year=e['full'],e['following_year']
    fs,ys=full['summary'],year['summary']
    top=year['top_ten_trades'][0]
    local=lambda t:datetime.fromtimestamp(t/1000,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    text=f'''# 固定参数后的盈利来源检查

结论：过滤震荡版改善了原策略的交易频率和跌幅，但仍靠少数较大的趋势交易覆盖大量小亏损。它尚未达到可以认定稳定盈利的程度。本轮不再调参数，不新增买卖规则；保留现有候选和全部旧版，到此停止在同一批历史行情上继续优化。

这份补充只分析已完成的项目回测，没有重下行情，也没有增加手续费和滑点。两年范围为 2024-09-10 至 2026-09-10；后一年为 2025-09-10 至 2026-09-10，沿用上一份报告每三个月平仓、资金连续计算的规则。日期范围均为 UTC，结束不含。

## 目前比较好的候选实际做了多少笔

固定中心 EMA31、宽度 EMA31、突破门槛 0.8 倍宽度、离中心超过 2 倍宽度不追单。最近 32 根十五分钟 K 线（八小时）的净变化距离，至少占累计涨跌距离 20%，才允许新开仓。浮盈达到 2% 后，允许回吐一半最高浮盈；出现反向信号也可平仓，两者独立。

| 范围 | 收益 | 交易 | 盈利笔数 | 亏损笔数 | 最长连续亏损 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 完整两年 | {pct(full['return_pct'])} | {fs['trades']} | {fs['wins']} | {fs['losses']} | {fs['max_consecutive_losses']} |
| 后一年，四段拼接 | {pct(year['return_pct'])} | {ys['trades']} | {ys['wins']} | {ys['losses']} | {ys['max_consecutive_losses']} |

两年平均赚的一笔赚 {fs['avg_win_return_pct']:.2f}%，平均亏的一笔亏 {fs['avg_loss_return_pct']:.2f}%。但约三分之二的交易会亏，所以不是每次容易做对，而是依靠赚钱时赚得更多。

## 最赚钱的一笔就在原截图时段

这笔是北京时间 {local(top['entry_time'])} 做多，{local(top['exit_time'])} 平仓，价格从 {top['entry_price']:,.2f} 到 {top['exit_price']:,.2f}，该笔收益 {pct(top['return_pct'])}。它与最初拿来反推指标的截图时段重合，是已经看过、并参与过策略构思的行情，不能当成独立验证证据。

为检查依赖程度，按每笔收益百分比排序，把最好几笔的收益设成零，其余入场时刻和每笔涨跌保持原样，再计算复利。下面只是算术压力检查，不是一个可以事先避开这些交易的策略，也不是重新运行的回测。

| 假设 | 原利润保护版后一年 | 过滤震荡 20% 后一年 | 过滤震荡 30% 后一年 |
| --- | ---: | ---: | ---: |
'''
    names={'anchor':'原利润保护版','efficiency20':'过滤震荡 20%','efficiency30':'过滤震荡 30%'}
    stress_rows=[['原始结果']+[pct(data['results'][k]['following_year']['return_pct']) for k in names]]
    for i,n in enumerate((1,5,10,20)):
        stress_rows.append([f'最好 {n} 笔利润归零']+[pct(data['results'][k]['following_year']['stress'][i]['remaining_compounded_return_pct']) for k in names])
    for row in stress_rows:
        text+='| '+' | '.join(row)+' |\n'
    text+='''
过滤震荡 20% 版如果少了最好一笔的利润，后一年仍赚钱；如果最好五笔都没有赚到钱，就转亏。完整两年，把最好五笔归零后剩 +8.84%，把最好十笔归零后变 -20.96%。它比原版的后一年更耐受漏掉单笔大赚，但仍明显依赖较大的趋势交易。

不能把“删掉大赢家后亏损”当作策略必然无效的证明。许多趋势策略天然会有这种分布。这里的实际问题是：未来能否继续抓住足够多的大行情，抵消平时积累的小亏损；现有反复看过的数据无法可靠回答这一点。

## 亏损主要发生在哪里

'''
    short_losses=sum(full['duration'][k]['losses'] for k in ('up_to_1h','1h_to_4h'))
    text+=f'''两年 {fs['losses']} 笔亏损中，有 {short_losses} 笔在四小时以内就结束，占 {short_losses/fs['losses']*100:.1f}%。这些仓位最终是被反向信号平掉的。走势没有延续到足够大的盈利，许多小亏损反复累积；过滤震荡减少了交易，但没有消除这种情况。

相反，持仓超过十二小时的 {full['duration']['over_12h']['trades']} 笔里有 {full['duration']['over_12h']['wins']} 笔盈利。这是对已发生结果的描述，不能在开仓时提前知道一笔单子将持有多久，更不能据此事后只保留长时间持仓。

利润保护退出的两年 {full['exit_reasons']['profit_protection']['trades']} 笔都盈利；反向退出的 622 笔中，97 笔盈利、525 笔亏损。这也不能解释成“反向平仓不好，应该取消”：按退出原因分组本来就会把已经上涨并触发保护的交易分到盈利组，而未走出行情的交易留给反向退出。取消反向退出会形成另一个风险不同的策略，本轮没有这样改。

## 做多、做空和月份

| 方向 | 后一年笔数 | 盈利 / 亏损笔数 | 实际利润贡献（USDT） |
| --- | ---: | ---: | ---: |
'''
    side_rows=[]
    for side,name in [('long','做多'),('short','做空')]:
        s=year['side'][side]
        row=[name,s['trades'],f"{s['wins']} / {s['losses']}",f"{s['profit']:+,.2f}"]
        side_rows.append(row)
        text+='| '+' | '.join(map(str,row))+' |\n'
    text+=f'''
两边在这段历史都贡献了正利润，做多贡献更大。上表只是原账户中的利润归属，不是单独只做多或只做空的回测，不能拿它直接决定删掉做空。

按日历月拆开，后一年覆盖 13 个自然月片段，7 个赚钱、6 个亏损；首尾九月都不是完整月份。最差的是 2025 年 12 月，亏 6.81%；最好的是 2026 年 8 月，赚 17.75%。因此“每个三个月合计都赚钱”不等于“每个月赚钱”，中间仍需承受连亏。

## 停止继续调参，保存候选

现在能确认的是：少在来回震荡时入场，历史表现比频繁来回交易更平稳。但这个 20% 门槛是比较多个方法之后看到的候选，最大盈利交易又来自最初截图时段，不能因此宣布已经找到稳定赚钱的方法。

保留两个固定候选 20% 和 30% 以及全部旧版，不再把门槛改成 19%、21% 等继续搜历史最优。未来如用真正新增的数据重新检查，应先固定规则；本次没有安排自动任务，也没有实际交易。

文件：`profit-audit-v1/plan.json` 是本次只读检查计划，`results.json` 是全部分类与计算结果，旧研究文件没有覆盖。所有参数、行情快照和逐笔交易仍可在项目正式记录中找到。
'''
    (AUDIT/'REPORT.md').write_text(text,encoding='utf-8')
    metric_rows=[['完整两年',pct(full['return_pct']),fs['trades'],fs['wins'],fs['losses'],fs['max_consecutive_losses']],
                 ['后一年，四段拼接',pct(year['return_pct']),ys['trades'],ys['wins'],ys['losses'],ys['max_consecutive_losses']]]
    duration_names={'up_to_1h':'一小时以内','1h_to_4h':'一至四小时','4h_to_12h':'四至十二小时','over_12h':'超过十二小时'}
    duration_rows=[[duration_names[k],s['trades'],s['wins'],s['losses']] for k,s in full['duration'].items()]
    monthly_rows=[[m['month'],pct(m['return_pct'])] for m in year['monthly_returns']]
    html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>盈利从哪里来 · 固定参数检查</title>
<style>body{{background:#f3f5f7;color:#23313e;font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif;margin:0}}main{{max-width:1120px;margin:34px auto;padding:0 22px 50px}}h1{{font-size:30px;line-height:1.4}}h2{{font-size:22px}}section{{background:white;border:1px solid #d9e0e7;border-radius:12px;padding:22px;margin:20px 0}}.notice{{background:#fff5df;border-color:#d7b979}}a{{color:#285d94}}.muted{{color:#657789;font-size:14px}}table{{border-collapse:collapse;width:100%;font-size:15px}}th,td{{padding:11px;border-bottom:1px solid #e1e7ec;text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}th{{background:#f7f9fb}}.scroll{{overflow-x:auto}}p{{max-width:1000px}}details{{margin:16px 0}}summary{{cursor:pointer;color:#285d94}}</style>
<main><a href="robustness.html">← 返回全部版本比较</a><p class="muted">ETH / USDT · 十五分钟 · 参数固定 · 只检查已有交易 · 不计算手续费和滑点</p>
<h1>过滤震荡有帮助，但收益仍依赖少数大行情</h1>
<section class="notice"><p>继续检查后，结论没有变：保留候选，停止在同一批历史上继续调参。历史上它比原版平稳，但尚不能认定能稳定盈利。</p></section>
<section><h2>实际交易情况</h2>{table(['范围','收益','总笔数','盈利','亏损','最长连续亏损'],metric_rows)}<p>两年平均赚的一笔赚 {fs['avg_win_return_pct']:.2f}%，平均亏的一笔亏 {fs['avg_loss_return_pct']:.2f}%。大约三分之二的交易会亏，靠赚的时候赚得更多来补偿。</p><p class="muted">完整两年：2024-09-10 至 2026-09-10；后一年：2025-09-10 至 2026-09-10，每三个月平仓后拼接，资金连续计算。日期为 UTC，结束不含。</p></section>
<section><h2>最大盈利恰好来自最初的截图时段</h2><p>北京时间 {local(top['entry_time'])} 做多，{local(top['exit_time'])} 平仓，价格从 {top['entry_price']:,.2f} 到 {top['exit_price']:,.2f}，这一笔赚了 {top['return_pct']:.2f}%。这段行情已经参与过指标反推，不能当成独立验证。</p><p>如果最好一笔没有赚到利润，过滤震荡版后一年从 +62.63% 降到 +27.72%；最好五笔都不赚钱，就变成 -2.33%。</p>
{table(['算术压力检查','原利润保护版后一年','过滤震荡 20% 后一年','过滤震荡 30% 后一年'],stress_rows)}
<p class="muted">按每笔收益百分比排序，把最好几笔设为零，其余入场时刻与每笔涨跌不变，重新计算复利。这是依赖程度检查，不是可执行策略，也不是重新回测。</p><p>趋势策略常靠少数大赚覆盖很多小亏，不能只因这个检查就判定它无效。但这说明未来必须继续抓住大行情，才可能维持盈利；现有数据还不足以确认这一点。</p></section>
<section><h2>亏损多发生在行情没能延续的时候</h2><p>两年 525 笔亏损里，322 笔在四小时以内结束，约占 61%。持仓超过十二小时的 94 笔，85 笔赚钱。过滤减少了无效入场，但没有消除反复的小亏损。</p>{table(['持仓时间（两年）','笔数','盈利','亏损'],duration_rows)}<p class="muted">持仓时间是平仓以后才知道的结果，不能用它事后筛选入场。</p><p>188 笔利润保护退出都赚钱；622 笔反向信号退出中，97 笔赚钱、525 笔亏损。这不意味着应该取消反向平仓：分组本来就把先赚钱并触发保护的交易分走了。取消它会是另一套策略，本轮没有改。</p></section>
<section><h2>多空都贡献利润，但不是每个月都赚</h2>{table(['方向','后一年笔数','盈利 / 亏损','利润贡献（USDT）'],side_rows)}<p class="muted">只是同一个账户中多空交易的利润归属，不是两套独立的只做多 / 只做空回测。</p><p>后一年覆盖 13 个自然月片段，其中 7 个赚钱、6 个亏损；首尾九月都不是完整月份。最差的 2025 年 12 月亏 6.81%，最好的 2026 年 8 月赚 17.75%。每三个月合计赚钱，并不代表每个月赚钱。</p><details><summary>查看每月收益</summary>{table(['月份','当月收益'],monthly_rows)}</details></section>
<section><h2>候选规则和保存位置</h2><p>中心 EMA31，宽度 EMA31，收盘突破 0.8 倍宽度且不追到 2 倍宽度之外。八小时净移动距离 / 累计涨跌距离至少 20% 才新开仓。浮盈达到 2% 后回吐一半，或出现反向信号，任一条件满足就平仓；过滤条件不会阻拦反向退出。保护线每十五分钟收盘更新，下一根生效。</p><p>20% 和 30% 两个版本与旧策略都保留。继续把数字调细容易迎合同一段历史，本次到此停止。以后若检查新增行情，沿用固定参数，不能边看结果边改。</p><p><a href="http://127.0.0.1:4173/research/backtests?run=f6bdf2e5831c468381a1a7c224ec1afa">查看 20% 版两年全部 810 笔交易</a> · <a href="robustness.html">查看全部 20 个版本</a></p><p class="muted">独立补充目录：D:\\Code\\OpenTrading\\docs\\verification\\eth-cloud-robustness-20260910\\profit-audit-v1<br>旧策略、报告、参数和结果均保留。本次没有新增回测方法、自动任务或实际交易。</p></section></main></html>'''
    (AUDIT/'report.html').write_text(html,encoding='utf-8')
    (ROOT/'docs/verification/eth-cloud-two-year-20260910/profit-audit.html').write_text(html,encoding='utf-8')
    print('Wrote separate report: http://127.0.0.1:8787/profit-audit.html')


if __name__=='__main__':
    main()
