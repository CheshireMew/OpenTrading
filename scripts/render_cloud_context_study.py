"""Readable results for the frozen context-filter study, with no new search."""
from datetime import datetime,timezone,timedelta
from html import escape
import json

from scripts.cloud_context_study import DOCS,RUNTIME,ROOT,NAMES,CORE
from scripts.profit_protection_study import read,save
from scripts.render_cloud_entry_study import table,mdtable


def number(v,signed=False):
    return '—' if v is None else f'{v:+.2f}' if signed else f'{v:.2f}'


def pct(v,signed=False):
    return number(v,signed)+'%' if v is not None else '—'


SHORT=dict(baseline='原策略',support='加支撑阻力',momentum='加一小时动量',trend='加四小时趋势',
           support_momentum='支撑阻力＋动量',support_trend='支撑阻力＋趋势',momentum_trend='动量＋趋势',
           all_three='三个条件全部加上',support_room='只检查前方空间',support_touch='只检查入场位置')


def main():
    r=read(DOCS/'results.json'); receipts=read(DOCS/'project-runs.json')
    assert r['status']=='completed' and r['simulations']==60
    assert r['selection']['selected'] is None and r['accepted_candidate'] is None
    y=r['following_year']; b=y['baseline']; s=y['support']; m=y['momentum']; t=y['trend']; a=y['all_three']; touch=y['support_touch']
    cohorts=r['cohorts']['following-year']; cs=cohorts['support']; cm=cohorts['momentum']; ct=cohorts['trend']
    annotated=read(RUNTIME/'annotated-baseline.json')['full']
    examples={
        'first_original_loss_passing_all_three':next((v for v in annotated if v['profit']<0 and v['filters']['all_three']),None),
        'first_original_winner_rejected_by_momentum':next((v for v in annotated if v['profit']>0 and not v['filters']['momentum']),None),
        'selection_rule':'First in chronological order; original executed trades only. Not claimed to represent all trades or prove a causal explanation.'}
    save(DOCS/'examples.json',examples)
    headers=['入场条件','交易数','赚 / 亏','赚钱比例','总收益','最长连亏','最大跌幅','平均赚一笔','平均亏一笔']
    def performance(period,keys):
        rows=[]
        for k in keys:
            v=y[k] if period=='following-year' else r['results'][k][period]
            win=v.get('avg_win_return_pct',v.get('average_win_return_pct'))
            loss=v.get('avg_loss_return_pct',v.get('average_loss_return_pct'))
            rows.append([SHORT[k],v['total_trades'],f"{v['wins']} / {v['losses']}",pct(v['win_rate']),pct(v['return_pct'],True),
                         v['max_consecutive_losses'],pct(v['max_drawdown_pct']),pct(win),pct(-loss if loss is not None else None)])
        return rows
    rows={p:performance(p,CORE) for p in ('following-year','selection','full')}
    diagnostic={p:performance(p,['baseline','support_touch','support_room','support']) for p in rows}
    ch=['加入的条件','挡住原亏损','同时错过原盈利','原亏损中挡住多少','原盈利中错过多少','留下的赚钱比例']
    cr=[]
    for k in list(NAMES)[1:]:
        c=cohorts[k]
        cr.append([SHORT[k],c['rejected']['losses'],c['rejected']['wins'],pct(c['losing_trades_rejected_pct']),
                   pct(c['winning_trades_rejected_pct']),pct(c['kept']['win_rate'])])
    qh=['版本','2025/9/10—12/10','2025/12/10—2026/3/10','2026/3/10—6/10','2026/6/10—9/10']
    qr=[[SHORT[k]]+[f"{pct(r['results'][k][f'q{i}']['return_pct'],True)}；赚 {r['results'][k][f'q{i}']['wins']} / 亏 {r['results'][k][f'q{i}']['losses']}" for i in range(1,5)] for k in NAMES]
    sideheaders=['版本','方向','后一年赚 / 亏','赚钱比例','平均赚一笔','平均亏一笔']
    siderows=[]
    for k in NAMES:
        for side,label in [('long','做多'),('short','做空')]:
            v=r['side_breakdown'][k]['following-year'][side]
            siderows.append([SHORT[k],label,f"{v['wins']} / {v['losses']}",pct(v['win_rate']),pct(v['avg_win_return_pct']),
                             pct(-v['avg_loss_return_pct'] if v['avg_loss_return_pct'] is not None else None)])
    scope='使用项目已有 ETH/USDT 十五分钟行情和同一回测引擎，不计算手续费、滑点，不加杠杆，每次投入当时全部资金。完整两年为 2024-09-10 至 2026-09-10；前一年截至 2025-09-10，后一年从该日开始，均为 UTC，结束日期不含。后一年沿用原研究的四个季度分别运行，季度末平仓、资金接着计算；完整两年连续持仓运行，两者不能直接按交易数相减。'
    summary=[
        '这次已把支撑阻力、一小时动量、四小时趋势分别及组合加入原策略。结果仍然没有达到你“赚钱次数多于亏钱次数”的要求，没有选出可以采用的新版本。',
        f'后一年，原策略 {b["total_trades"]} 笔、赚 {b["wins"]} 笔、亏 {b["losses"]} 笔。三个条件全部加上，只剩 {a["total_trades"]} 笔、赚 {a["wins"]} 笔、亏 {a["losses"]} 笔，总收益 {pct(a["return_pct"],True)}。交易确实少了，但赚钱比例没有变好，而且样本太少，不能据此判断长期表现。',
        f'单独检查“靠近支撑做多、靠近阻力做空”，后一年赚钱比例从 {pct(b["win_rate"])} 到 {pct(touch["win_rate"])}，总收益从 {pct(b["return_pct"],True)} 到 {pct(touch["return_pct"],True)}。只有很小的胜率变化，仍是赚 {touch["wins"]} 笔、亏 {touch["losses"]} 笔。这个拆分版本完整两年的收益较高，但它没有达到你的胜率要求，也不能改称为已经验证成功。',
    ]
    rules=[
        ('支撑阻力：看位置，也看前面有没有障碍', '使用前一天的最高、最低价，以及已经确认的一小时高低点。做多时，原信号还要靠近下方支撑，信号那根 K 线触及支撑附近并收在上面；上方最近的已知阻力也不能太近。做空反过来。没有把后来才出现的高低点提前画回去。'),
        ('一小时动量：要求上涨或下跌力度正在增强', '做多要求已收盘一小时 RSI14 至少 55，而且比上一小时更高；做空要求不高于 45，而且比上一小时更低。它检查的是过去价格变化形成的力度，并不能直接知道下一根会怎么走。'),
        ('四小时趋势：要求大方向一致', '做多要求最近收盘的四小时价格在过去 20 根四小时收盘均价之上，而且这个均价比 16 小时前更高；做空全部反过来。只使用已经收盘的四小时 K 线。'),
        ('原来的触发和平仓方式保持不变', '新条件只是决定原十五分钟信号出现时能不能入场。价格仍需收盘越过原通道门槛，下一根开盘成交；浮盈达到 2% 后允许回吐其中一半，或出现原始反向信号，任一条件都可平仓。即使新条件不允许反手，也照常退出旧仓。保护线在收盘后更新，下一根才生效。'),
    ]
    detail='精确的位置规则：W 是高低价差的 EMA31，即近期每根十五分钟 K 线振幅的平滑平均。做多收盘价须高于最近支撑且距离不超过 1W，信号最低价须到达支撑上方 0.25W 以内；上方最近阻力至少距离 2W。做空镜像。高低点须比前后各两根小时线严格更高或更低，等后两根小时线收盘才确认，保留五天。触碰用的价位必须在信号那根开盘前已知；没有已知对面价位时只表示没有识别到障碍，不表示前面一定没有阻力。日高低点按 UTC 日计算。'
    findings=[
        f'支撑阻力没有显著分开好坏交易。把后一年原交易先按条件分类，它挡住 {cs["rejected"]["losses"]} 笔亏损，也错过 {cs["rejected"]["wins"]} 笔盈利。换成比例，是挡住 {pct(cs["losing_trades_rejected_pct"])} 的亏损，同时错过 {pct(cs["winning_trades_rejected_pct"])} 的盈利，几乎一视同仁。实际重跑后只有 {s["total_trades"]} 笔，总收益 {pct(s["return_pct"],True)}。',
        f'动量在前一年看着略好：赚钱比例 {pct(r["results"]["momentum"]["selection"]["win_rate"])}，原版 {pct(r["results"]["baseline"]["selection"]["win_rate"])}。后一年却变成 {pct(m["win_rate"])}，原版 {pct(b["win_rate"])}。它挡掉原来 {pct(cm["losing_trades_rejected_pct"])} 的亏损，却错过 {pct(cm["winning_trades_rejected_pct"])} 的盈利。这组“力度更强才进”的条件没有持续提高胜率。',
        f'四小时趋势同样没有解决问题。它挡掉原来 {pct(ct["losing_trades_rejected_pct"])} 的亏损，也错过 {pct(ct["winning_trades_rejected_pct"])} 的盈利，留下的好坏比例基本没变。实际重跑赚钱比例 {pct(t["win_rate"])}，总收益 {pct(t["return_pct"],True)}。大周期方向相同，不代表这次十五分钟突破就会延续。',
        '把更多条件同时加上，确实更少开仓，但这次没有获得更高胜率。比如三个条件全加上的版本，在后一年某个季度两笔全赚，另外三个季度合计六笔全亏；单看“两笔胜率 100%”会产生误解。',
    ]
    methodology=[
        '先固定八种主组合和两个支撑阻力拆分版本，共十个版本、六十次分段回测，再看结果。前一年先要求赚钱次数更多、收益为正、至少 50 笔，主组合中没有任何一个合格，所以没有进入采用名单。两个拆分版本只用于理解位置与空间各有什么影响，事先未允许用它们替换候选；它们的胜率也都没有达标。',
        '同一批两年行情此前已经多次研究。这次前后分段只是检查表现能否重复，不是第一次看到的新行情，不能把好看的某段收益当成将来稳定盈利的证明。本轮不再根据结果追加数字组合。',
        '能得出的结论是：本轮这几种明确写出的支撑阻力、动量和趋势定义，没有补好当前策略的入场问题。不能扩大成“所有支撑阻力或所有技术分析都没用”，也不能因为人类会看这些，就直接认定加上它们应当更赚钱。',
    ]
    md='# 支撑阻力、动量和趋势加入后的测试\n\n'+'\n\n'.join(summary)+'\n\n'+scope+'\n\n'
    md+='## 加了什么\n\n'+'\n\n'.join('### '+title+'\n\n'+body for title,body in rules)+'\n\n'+detail+'\n\n'
    md+='## 后一年实际重跑\n\n'+mdtable(headers,rows['following-year'])+'\n\n'
    md+='## 支撑阻力拆开检查\n\n'+mdtable(headers,diagnostic['following-year'])+'\n\n'
    md+='## 为什么没有达到要求\n\n'+'\n\n'.join(findings)+'\n\n'+mdtable(ch,cr)+'\n\n'
    md+='上表是原交易分类，并非新策略收益。筛掉入场会改变后续持仓状态，实际新交易数以重新回测为准。\n\n'
    md+='## 完整两年\n\n'+mdtable(headers,performance('full',NAMES))+'\n\n## 前一年\n\n'+mdtable(headers,performance('selection',NAMES))+'\n\n'
    md+='## 后一年各季度\n\n'+mdtable(qh,qr)+'\n\n## 多空分开\n\n'+mdtable(sideheaders,siderows)+'\n\n'
    md+='## 如何限制事后挑结果\n\n'+'\n\n'.join(methodology)+'\n\n'
    links=[f'- [{NAMES[k]}](http://127.0.0.1:4173/research/backtests?run={v["run_id"]})' for k,v in receipts['runs'].items()]
    md+='## 独立版本与逐笔记录\n\n'+'\n'.join(links)+'\n\n策略：strategies/trend_cloud_context_v3.py；冻结规则：plan.json；六十次结果：results.json；正式记录：project-runs.json；技术验证：verification.json。旧策略与旧报告保留，副本记录从 017 起。\n'
    (DOCS/'REPORT.md').write_text(md,encoding='utf-8')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>支撑阻力、动量与趋势 · 新一轮测试</title><style>
body{background:#f3f5f7;color:#243642;font:16px/1.85 system-ui,"Microsoft YaHei",sans-serif;margin:0}main{max-width:1220px;margin:30px auto;padding:0 22px 46px}section{background:#fff;border:1px solid #d7e0e7;border-radius:12px;padding:24px;margin:20px 0}h1{font-size:30px;line-height:1.5}h2{font-size:22px;margin-top:0}h3{font-size:18px}.notice{background:#fff5df;border-color:#d7b979}.muted{font-size:14px;color:#627583}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;border-bottom:1px solid #e0e7ec;white-space:nowrap;text-align:right}td:first-child,th:first-child{text-align:left}th{background:#f4f7f9}p{max-width:1090px}a,summary{color:#25608c}summary{cursor:pointer}select{font:inherit;padding:7px 12px;border:1px solid #91a4b2;border-radius:6px;background:white;margin:0 0 15px 8px}li{margin:7px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}.card{padding:14px;background:#fff;border:1px solid #e0d5ba;border-radius:8px}.card strong{display:block;font-size:22px}
</style><main><a href="entry-inspection.html">← 上一轮入场检查</a><p class="muted">ETH / USDT · 十五分钟 · 原平仓规则不变 · 无手续费和滑点</p><h1>支撑阻力、动量和趋势，加上以后有没有更好？</h1>'''
    paragraphs=lambda texts:''.join('<p>'+escape(p)+'</p>' for p in texts)
    html+='<section class="notice"><h2>仍未找到赚钱次数更多的版本</h2>'+paragraphs(summary)+'<div class="cards">'+''.join(f'<div class="card">后一年 · {SHORT[k]}<strong>{y[k]["wins"]} 赚 / {y[k]["losses"]} 亏</strong><span>总收益 {pct(y[k]["return_pct"],True)}</span></div>' for k in ['baseline','support_touch','all_three'])+'</div></section>'
    html+='<section><h2>实际重跑结果</h2><label for="period">查看范围</label><select id="period"><option value="following-year">后一年：2025/9/10—2026/9/10</option><option value="selection">前一年：2024/9/10—2025/9/10</option><option value="full">完整两年：2024/9/10—2026/9/10</option></select><div id="performance">'+table(headers,rows['following-year'])+'</div><p class="muted">'+scope+'</p><p class="muted">总收益按资金连续计算；平均赚、亏一笔是单笔价格收益率的平均值。最大跌幅指账户从此前高点跌下多少。</p><h3>支撑阻力拆开检查（跟随上面的日期选择）</h3><p>“位置”检查是否靠近支撑或阻力；“空间”检查前面是否很快遇到对面的价位。下表两个拆分版本用于解释原因，不是事后追加搜索。</p><div id="diagnostic">'+table(headers,diagnostic['following-year'])+'</div><details><summary>查看后一年各季度</summary>'+table(qh,qr)+'</details><details><summary>查看后一年多空分别表现</summary>'+table(sideheaders,siderows)+'</details></section>'
    html+='<section><h2>加进去的条件，到底怎么决定能不能进？</h2>'+''.join('<h3>'+title+'</h3><p>'+body+'</p>' for title,body in rules)+'<details><summary>查看支撑阻力的具体距离与确认时间</summary><p>'+detail+'</p></details></section>'
    html+='<section><h2>为什么交易少了，胜率却没有明显提高？</h2>'+paragraphs(findings)+'<details><summary>查看后一年：挡掉多少原亏损，又错过多少原盈利</summary>'+table(ch,cr)+'<p class="muted">这里先把原本执行的交易分类。过滤后持仓状态不同，可能又出现另外的入场，所以这些留下的交易不是新策略的完整结果。表格只说明当时可见的条件如何区分原交易，不能把分组收益当成重新回测。</p></details></section>'
    html+='<section><h2>这次结论适用到哪里</h2>'+paragraphs(methodology)+'</section>'
    html+='<section><h2>十个版本和逐笔记录都已保留</h2><p>点击某个版本，可查看完整两年的成交与每根 K 线对应的已知价位、RSI、四小时均线和入场检查结果。</p><details><summary>展开全部版本</summary><ul>'+''.join(f'<li><a href="http://127.0.0.1:4173/research/backtests?run={v["run_id"]}">{escape(NAMES[k])}</a></li>' for k,v in receipts['runs'].items())+'</ul></details><p class="muted">独立策略 trend_cloud_context_v3；研究记录位于 D:\\Code\\OpenTrading\\docs\\verification\\eth-cloud-context-20260910。规则、源码、结果和逐笔记录可追溯；先前版本未覆盖。</p></section></main><script>const tables='+json.dumps(dict(performance=rows,diagnostic=diagnostic),ensure_ascii=False).replace('<','\\u003c')+''';
document.getElementById('period').addEventListener('change',event=>{for(const id of ['performance','diagnostic']){const body=document.querySelector('#'+id+' tbody');body.replaceChildren();tables[id][event.target.value].forEach(row=>{const tr=document.createElement('tr');row.forEach(value=>{const td=document.createElement('td');td.textContent=String(value);tr.append(td)});body.append(tr)})}});
</script></html>'''
    (DOCS/'report.html').write_text(html,encoding='utf-8')
    (ROOT/'docs/verification/eth-cloud-two-year-20260910/context-signals.html').write_text(html,encoding='utf-8')
    print('http://127.0.0.1:8787/context-signals.html')


if __name__=='__main__':
    main()
