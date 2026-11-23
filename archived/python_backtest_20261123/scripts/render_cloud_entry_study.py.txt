"""Entry diagnostics, with fixed exits and kept/rejected winners shown together."""
from datetime import datetime,timezone,timedelta
from html import escape
import json

from scripts.cloud_entry_study import DOCS,RUNTIME,ROOT,NAMES
from scripts.profit_protection_study import read,save


def pct(v):
    return f'{v:+.2f}%'


def mdtable(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for h in headers)+' |']+
                     ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])


def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join(f'<th>{escape(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def main():
    r=read(DOCS/'results.json')
    assert r['status']=='completed' and r['selection']['selected'] is None and r['accepted_candidate'] is None
    receipts=read(DOCS/'project-runs.json')
    a=read(RUNTIME/'annotated-baseline.json')['full']
    # Illustration rule: earliest losing baseline trade satisfying all eight
    # prespecified entry checks. Not a new combined strategy or performance test.
    example=next(t for t in a if t['profit']<0 and all(t['filters'].values()))
    rejected_loss=next(t for t in a if t['profit']<0 and not t['filters']['few_crossings'])
    rejected_win=next(t for t in a if t['profit']>0 and not t['filters']['few_crossings'])
    save(DOCS/'examples.json',dict(earliest_loss_with_all_eight_features=example,
                                 first_loss_excluded_by_crossing_filter=rejected_loss,
                                 first_win_excluded_by_crossing_filter=rejected_win,
                                 selection_rule='Earliest in chronological order; illustrative counterexamples, not a new combined filter backtest. All features at signal close, one bar before entry.'))
    short={
        'baseline':'原入场规则', 'aligned_slope':'顺中心线近两小时方向', 'local_trend':'近两小时也必须走得顺',
        'few_crossings':'均线附近反复穿越时少做', 'strong_close':'突破那根必须收得强', 'closer_entry':'更靠近中心线才进',
        'no_spike':'突破那根太大就不进', 'active_market':'波动太小就不进', 'structure_break':'突破前两小时高低点才进',
    }
    performance_headers=['入场条件','交易数','赚 / 亏','赚钱比例','总收益','最长连亏','最大跌幅']
    def performance(period):
        rows=[]
        for k in NAMES:
            m=r['following_year'][k] if period=='following-year' else r['results'][k][period]
            rows.append([short[k],m['total_trades'],f"{m['wins']} / {m['losses']}",f"{m['win_rate']:.1f}%",pct(m['return_pct']),m['max_consecutive_losses'],f"{m['max_drawdown_pct']:.2f}%"])
        return rows
    yearrows,fullrows,trainrows=performance('following-year'),performance('full'),performance('selection')
    cohort_headers=['过滤条件','挡住亏损','同时错过盈利','原亏损中挡住多少','原盈利中错过多少','留下的赚钱比例']
    cohortrows=[]
    for k in list(NAMES)[1:]:
        c=r['cohorts']['following-year'][k]
        cohortrows.append([short[k],c['rejected']['losses'],c['rejected']['wins'],f"{c['losing_trades_rejected_pct']:.1f}%",f"{c['winning_trades_rejected_pct']:.1f}%",f"{c['kept']['win_rate']:.1f}%"])
    qheaders=['条件','2025/9/10—12/10','2025/12/10—2026/3/10','2026/3/10—6/10','2026/6/10—9/10']
    qrows=[[short[k]]+[f"{pct(r['results'][k][f'q{i}']['return_pct'])}；赚 {r['results'][k][f'q{i}']['wins']} / 亏 {r['results'][k][f'q{i}']['losses']}" for i in range(1,5)] for k in NAMES]
    local=lambda t:datetime.fromtimestamp(t/1000,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    b=r['following_year']['baseline']; f=r['following_year']['few_crossings']; c=r['cohorts']['following-year']['few_crossings']
    sections=[
        ('这次确实只检查入场',[
            '你指出的问题成立：之前“很多亏损单曾经有浮盈”的统计，主要解释了出场过程，没有证明当初就不该入场。这次固定原来的平仓规则，单独检查进场前可以看见的条件。',
            '结论是：均线附近反复穿越，确实能筛出稍差一些的交易，但作用很弱；其余这轮测试的入场条件，没有稳定地区分出之后会亏和会赚的交易。还没有找到符合你“赚钱次数多于亏钱次数”的入场方法。这不是说亏损没有原因，而是目前没有证据表明这些原因能被这组指标事先可靠识别。']),
        ('到底有没有挡住坏入场',[
            f'例如不做过去四小时穿越中心线超过两次的信号：在原后一年交易中，它挡住 {c["rejected"]["losses"]} 笔亏损，也错过 {c["rejected"]["wins"]} 笔盈利。原来本就有 249 笔亏损、129 笔盈利，所以“挡住的亏损笔数更多”本身不代表过滤有效。换成比例，它挡住 {c["losing_trades_rejected_pct"]:.1f}% 的亏损，也错过 {c["winning_trades_rejected_pct"]:.1f}% 的盈利，区分能力很有限。',
            f'把这个条件真正放进项目重新回测后，后一年由 {b["wins"]} 赚、{b["losses"]} 亏，变成 {f["wins"]} 赚、{f["losses"]} 亏。赚钱比例只从 {b["win_rate"]:.1f}% 变成 {f["win_rate"]:.1f}%，总收益从 {pct(b["return_pct"])} 降到 {pct(f["return_pct"])}，最长仍连续亏 {f["max_consecutive_losses"]} 笔。它让交易减少了，远没有达到你要的效果。']),
        ('哪些“亏损原因”没有得到数据支持',[
            '“进得太远、太晚”这次用离中心线的距离来检查：把不追单的上限从 2 倍宽度收紧到 1.25 倍。它挡掉原来 32.1% 的亏损，却同时错过 35.7% 的盈利；重新跑后胜率由 34.1% 降到 33.1%。所以不能把离中心线远，直接当成坏入场的可靠标志。这里检查的是距离，不是已经证明辨认出每段趋势的末尾。',
            '“突破那根不够强”也没有改善：要求阳线收在顶部四分之一才做多，阴线收在底部四分之一才做空。重新跑后，后一年赚钱比例 32.9%，比原版低。强势的一根 K 线也可能是最后一冲，单凭收盘形态没有分开这两种情况。',
            '“行情不够顺”在前一年看起来稍有帮助：额外要求近两小时净移动占累计移动至少 30%，胜率从 36.1% 到 39.5%；到了后一年却从原版 34.1% 变成 31.0%。这正是不能拿同一段历史上的改善当成可靠规则的例子。',
            '“波动太小容易亏”也不能直接成立。挡掉低于 0.25% 常见振幅的交易后，错过了部分后来走出大趋势的入场，后一年总收益从 +62.63% 降到 +25.12%，赚钱比例也没有提高。不能事后看到波动小就统一认定不该进。']),
        ('一笔入场看起来合格，却仍然亏损的例子',[
            f'北京时间 {local(example["entry_time"])}，原版在 {example["entry_price"]:,.2f} 做多。进场前，中心线近两小时向上、价格已收过之前两小时高点、突破阳线收在自身顶部四分之一，距离中心约 {example["features"]["distance_width"]:.2f} 倍宽度，过去四小时只穿越中心两次，也没有异常大 K 线。它符合本轮检查的全部八项条件。',
            f'之后价格没有延续上涨，反向信号在 {local(example["exit_time"])} 让它以 {example["exit_price"]:,.2f} 平仓，亏 {abs(example["return_pct"]):.2f}%。这个例子说明：能在图上描述“后来失败了”，与能在当时识别“这个突破不该做”，是两件需要分别验证的事。',
            '例子按时间顺序选择第一个符合全部条件的亏损单，用来检查“条件看起来好就不会亏”的推断。没有把八项条件临时叠加成新策略，也没有拿几笔案例替代完整统计。']),
        ('当前入场规则的问题在哪里',[
            '目前做多的核心是价格收盘越过平滑中心线上的一道门槛，做空反过来。再用过去八小时是否走得顺，限制新开仓。它能捕捉已经出现的价格移动，但这轮证据没有显示它能可靠判断“这次移动还会不会继续”。不少亏损来自突破后又折返，然而同样的进场特征，也出现在后来赚钱的交易里。',
            '当前过滤震荡的方法是：过去八小时累计来回走了 100 美元，起点到终点至少要走出 20 美元才开仓。它看的是过去八小时，所以过去有趋势、眼前开始来回折返时，仍可能放行。加上“近四小时少穿越”的检查，只带来了上面那一点改善。']),
        ('测试规则与下一步判断',[
            '本轮事先固定原版加八种单独的入场过滤，共九个版本、54 次回测。中心和宽度 EMA31、突破门槛 0.8 倍、八小时过滤 20% 均保持原值；利润保护固定为浮盈 2% 后允许回吐一半，原始反向信号也始终可以平仓。入场过滤不会拖延反向退出。没有改动止盈止损来抬高胜率。',
            '所有过滤只读取进场前已经收盘的 K 线，下一根开盘成交。先用前一年要求“赚钱次数更多、总收益正、至少 50 笔”，没有任何版本合格，所以没有选出一个准备采用的策略。后一年的比较完整保留，用于检查看似合理的解释有没有重复出现，而不是再从中挑一个宣布成功。',
            '这次能确认的是哪些条件没能解决问题，以及反复穿越只提供了很弱的帮助。按你的手工交易要求，这些版本暂不采用。本轮不继续把数字调细或不断叠加条件来追求历史高胜率；这两年行情已反复看过，继续这样搜很容易只适应这批行情。不能因此宣称所有入场方法都无效。']),
    ]
    scope='行情沿用项目缓存的 ETH/USDT 十五分钟数据，不计算手续费、滑点，不加杠杆，每次使用当时全部资金。完整两年：2024-09-10 至 2026-09-10；后一年：2025-09-10 至 2026-09-10，按原研究每三个月末平仓、资金连续计算。均为 UTC，结束不含。分段拼接的交易数与完整两年连续运行不能直接相减。这是重复使用已有历史的检查，不是未见过的新行情验证。'
    md='# 只检查入场：能否事先挡住坏交易\n\n'
    for title,paragraphs in sections:
        md+='## '+title+'\n\n'+'\n\n'.join(paragraphs)+'\n\n'
    md+='## 后一年：实际重新回测\n\n'+scope+'\n\n'+mdtable(performance_headers,yearrows)+'\n\n'
    md+='## 后一年：原交易中挡掉了什么\n\n'+mdtable(cohort_headers,cohortrows)+'\n\n这里把原本已经执行的交易按进场前特征分组，并非新策略收益。筛掉一些入场会改变后来的持仓状态，新策略可能多出其他入场，所以必须与上表真正重新回测的结果分开看。\n\n'
    md+='## 前一年结果\n\n'+mdtable(performance_headers,trainrows)+'\n\n## 完整两年\n\n'+mdtable(performance_headers,fullrows)+'\n\n## 后一年四段\n\n'+mdtable(qheaders,qrows)+'\n\n'
    md+='## 精确规则和保存记录\n\n'
    for k,name in NAMES.items():
        md+=f'- `{k}`：{name}。\n'
    md+='\n精确公式保存在 `plan.json` 与独立策略 `strategies/trend_cloud_entry_v2.py`；全部结果在 `results.json`，前一年选择记录在 `selection.json`，案例在 `examples.json`，逐笔带入场特征的标注在 `.opentrading_runtime/cloud-entry-20260910/annotated-baseline.json`。所有九个版本均有项目正式记录，见 `project-runs.json`。旧策略、旧报告、先前研究没有被覆盖。\n'
    (DOCS/'REPORT.md').write_text(md,encoding='utf-8')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>只检查入场 · 能否事先挡住坏交易</title><style>
body{background:#f3f5f7;color:#243642;font:16px/1.85 system-ui,"Microsoft YaHei",sans-serif;margin:0}main{max-width:1160px;margin:30px auto;padding:0 22px 46px}section{background:#fff;border:1px solid #d7e0e7;border-radius:12px;padding:22px;margin:20px 0}h1{font-size:30px;line-height:1.45}h2{font-size:22px;margin-top:0}.notice{background:#fff5df;border-color:#d7b979}.muted{font-size:14px;color:#627583}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;border-bottom:1px solid #e0e7ec;white-space:nowrap;text-align:right}td:first-child,th:first-child{text-align:left}th{background:#f4f7f9}p{max-width:1040px}a,summary{color:#25608c}summary{cursor:pointer}select{font:inherit;padding:7px 12px;border:1px solid #91a4b2;border-radius:6px;background:white;margin:0 0 15px 8px}li{margin:5px 0}
</style><main><a href="manual-trading.html">← 上一轮入场和利润保护比较</a><p class="muted">ETH / USDT · 十五分钟 · 只改入场条件 · 平仓规则固定 · 无手续费和滑点</p><h1>只检查入场：能否事先挡住坏交易？</h1>'''
    for index,(title,paragraphs) in enumerate(sections):
        html+=f'<section class="{"notice" if index==0 else ""}"><h2>{title}</h2>'+''.join(f'<p>{escape(p)}</p>' for p in paragraphs)+'</section>'
        if index==1:
            html+=f'<section><h2>实际重跑：省下的是坏交易，还是连好交易也错过了？</h2><label for="period">查看范围</label><select id="period"><option value="following-year">后一年</option><option value="selection">前一年</option><option value="full">完整两年</option></select><div id="performance">{table(performance_headers,yearrows)}</div><p class="muted">{scope}</p><details><summary>查看后一年的四个季度</summary>{table(qheaders,qrows)}</details></section>'
            html+=f'<section><h2>先把原来的交易分组，看看挡掉了什么</h2><p>后一年原交易有 129 笔盈利、249 笔亏损。有效过滤应当更多地挡住坏交易，同时尽量保留好交易；不能只比较被挡住的笔数。</p>{table(cohort_headers,cohortrows)}<p class="muted">这是原交易的分类，不是新策略回测。筛掉一次入场后，后面可能多出另一笔入场，所以分类留下的笔数可能与重跑结果不同。分组只使用进场前收盘数据，没有使用后面的涨跌来决定是否通过。</p></section>'
    html+='<section><h2>全部版本和逐笔记录保留</h2><details><summary>展开九个版本的完整两年记录</summary><ul>'+''.join(f'<li><a href="http://127.0.0.1:4173/research/backtests?run={v["run_id"]}">{escape(NAMES[k])}</a></li>' for k,v in receipts['runs'].items())+'</ul></details><p class="muted">D:\\Code\\OpenTrading\\docs\\verification\\eth-cloud-entry-20260910<br>plan.json：事先固定的规则；results.json：完整结果与分类；examples.json：案例及进场特征；project-runs.json：项目逐笔记录。旧策略和报告都保留，版本副本从 014 起。</p></section></main><script>const rows='+json.dumps({'following-year':yearrows,'selection':trainrows,'full':fullrows},ensure_ascii=False).replace('<','\\u003c')+''';
document.getElementById('period').addEventListener('change',event=>{const body=document.querySelector('#performance tbody');body.replaceChildren();rows[event.target.value].forEach(row=>{const tr=document.createElement('tr');row.forEach(value=>{const td=document.createElement('td');td.textContent=String(value);tr.append(td)});body.append(tr)})});
</script></html>'''
    (DOCS/'report.html').write_text(html,encoding='utf-8')
    (ROOT/'docs/verification/eth-cloud-two-year-20260910/entry-inspection.html').write_text(html,encoding='utf-8')
    print('http://127.0.0.1:8787/entry-inspection.html')


if __name__=='__main__':
    main()
