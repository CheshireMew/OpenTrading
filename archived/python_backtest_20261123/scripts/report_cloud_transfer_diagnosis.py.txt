"""Readable fixed-strategy diagnosis with annual/monthly evidence and real candles."""
from bisect import bisect_left
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import json
from app.domain.cloud_trade_attribution import features, ema
from scripts.cloud_transfer_diagnosis import DOCS, RUNTIME, ASSETS
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT, read, save


def pct(x): return '—' if x is None else f'{x:+,.2f}%'
def num(x): return '—' if x is None else f'{x:,.2f}'
def table(head,rows): return '\n'.join(['| '+' | '.join(head)+' |','|'+'---|'*len(head)]+['| '+' | '.join(map(str,r))+' |' for r in rows])


def excerpts(result):
    out={};cached={}
    for label,info in {**result['plan']['full'],**{f'{a}__hindsight':x for a,x in result['plan']['hindsight'].items()}}.items():
        asset=info['asset'];trace=read(ROOT/info['path'])
        if asset not in cached:cached[asset]=read(ROOT/result['plan']['data'][asset]['path'])
        rows=cached[asset];times=[r[0] for r in rows];f=features(rows,trace['parameters'])
        center=ema([(r[2]+r[3])/2 for r in rows],trace['parameters']['center_length'])
        candidates=[('全程最大盈利',max(trace['trades'],key=lambda t:t['return_pct'])),
                    ('全程最大亏损',min(trace['trades'],key=lambda t:t['return_pct']))]
        reversals=[t for t in trace['trades'] if t['return_pct']<0 and t['exit_reason'] in ('signal','reversal') and t['duration_minutes']<=240]
        if reversals:
            candidates.append(('常见的快速反向亏损（按亏损幅度取中间一笔）',sorted(reversals,key=lambda t:t['return_pct'])[len(reversals)//2]))
        samples=[]
        for name,t in candidates:
            i,j=bisect_left(times,t['entry_time']),bisect_left(times,t['exit_time'])
            a,b=max(0,i-48),min(len(rows),j+25)
            band=[dict(timestamp=rows[n][0],center=float(center[n]),
                       upper=float(center[n]+trace['parameters']['trigger_mult']*f['width_pct'][n]/100*rows[n][4]),
                       lower=float(center[n]-trace['parameters']['trigger_mult']*f['width_pct'][n]/100*rows[n][4])) for n in range(a,b)]
            samples.append(dict(label=name,trade=t,rows=rows[a:b],band=band))
        out[label]=samples
    return out


def markdown(r):
    full=r['full'];common=r['common'];select={'eth':'eth_original','btc':'btc_original','sol':'eth_original','bnb':'btc_original','paxg':'eth_original','zec':'eth_original'}
    texts=['# 六币逐笔诊断：亏在哪里，利润靠什么',
      '这轮没有再选参数。先把同一套 ETH 原参数用于六币，再检查 BTC 原参数及上轮各币第一名。补跑同一六年和只做多/只做空对照；所有原策略、原结果保持不变。',
      '## 结论',
      '不是简单的“长期涨，所以空单亏”。PAXG、ZEC 把空单关掉仍然大幅亏损；ETH、SOL 原参数的多单和空单都赚钱。BTC 的空单确实拖累收益；BNB 是否空单亏损还与版本及所看年份有关。',
      'PAXG 的主要问题是频繁穿越通道产生许多小亏，2%利润保护很少启动；ZEC 的主要问题是大量固定止损和快速反向亏损，获利交易不足以抵消。SOL 和 ZEC 的单根波动相近，但突破后的交易结果不同，不能只靠“波动更大”解释。',
      'ETH、SOL、BNB 的利润确实需要少数较大的赢家，但不只来自一个相同月份。删除各自最好的三个月后，ETH原参数、SOL原参数、BNB的BTC原参数仍然盈利。这个删除是算术压力检查，不是可以事先执行的交易规则。',
      '## 同一六年，同一套 ETH 原参数：把多空真的分开重跑',
      '2020-09-10至2026-09-10。只做一个方向时仍保留原反向平仓、初始止损和利润保护。已逐笔确认：单方向重跑与原双向策略中该方向的入场/退出时间、价格完全一致。多空收益相乘形成双向结果，不能相加。',
      table(['标的','双向收益','只做多收益','只做空收益','币价六年涨幅'],[[a.upper(),pct(common[a+'__eth_original']['summary']['compound_return_pct']),pct(r['direction_reruns'][a+'__eth_original']['long']['return_pct']),pct(r['direction_reruns'][a+'__eth_original']['short']['return_pct']),pct(common[a+'__eth_original']['market']['market_return_pct'])] for a in ASSETS]),
      '六币在同一六年里价格都是上涨的，SOL/BNB也有显著长期涨幅；因此不能把它们直接归为“长期横盘”，再用这个分类解释策略收益。它们都经历过很大的中途回撤，期初期末涨幅也不能完整描述价格路径。',
      '## PAXG、ZEC 为什么亏；ETH、SOL 为什么能赚',
      '以下用各自完整历史、同一 ETH 原参数。振幅是入场前的高低差 EMA，不是 ATR。“启动所需振幅倍数”只描述价格尺度，不能理解成多少根K线必然能达到。',
      table(['标的','胜率','平均一笔赚','平均一笔亏','赢单/亏单金额比例','回本所需比例','典型单根振幅','2%相当几倍振幅','保护启动率'],[[a.upper(),num((d:=full[a+'__eth_original'])['summary']['win_rate'])+'%',pct(d['summary']['mean_win_pct']),pct(d['summary']['mean_loss_pct']),num(d['summary']['win_loss_size_ratio']),num(d['summary']['breakeven_size_ratio']),num(d['scale']['median_entry_width_pct'])+'%',num(d['scale']['median_activation_widths']),num(d['scale']['activation_rate_pct'])+'%'] for a in ASSETS]),
      'PAXG：11,003笔中有8,779笔亏损，其中8,653笔因反向信号退出，126笔因固定止损退出。启动保护的只有245笔（2.23%）；一笔平均赚0.50%、亏0.20%，但每赢一笔约对应4.85笔亏损，赚得不够抵消次数。不能据此认定“把2%改小就一定赚钱”。',
      'ZEC：13,729笔中有9,701笔亏损，5,523笔是固定止损，4,157笔是反向退出，20笔是保护启动后遇到不利开盘价而亏损，还有1笔期末平仓。SOL 的赢单比例更高、平均赢家更大、平均亏损更小，这些不大的差异在上万笔交易和复利下造成很大的最终差距。',
      '## 持仓多久；利润是否依赖少数大单',
      '这里 ETH、SOL、PAXG、ZEC 用 ETH 原参数，BTC、BNB 用 BTC 原参数；这样同时解释上轮实际展示的较好原版本。所有版本均可在网页切换。',
      table(['标的','版本','总笔数','持仓中位数/小时','赢单中位数/小时','亏单中位数/小时','最佳10笔收益归零后','需要删去多少笔最佳赢家才不赚钱'],[[a.upper(),'ETH原参数（1%止损）' if c=='eth_original' else 'BTC原参数（2%止损）',num((d:=full[a+'__'+c])['summary']['trades']),num(d['summary']['median_hours']),num(d['winners']['median_hours']),num(d['losers']['median_hours']),pct(d['stress']['trade_checks'][0]['return_if_zero_pct']),d['stress']['best_winners_zeroed_to_erase_profit'] or '本来已亏损'] for a,c in select.items()]),
      '持仓多数是小时级，最大赢家往往持续一到数天。不能把“持仓久的单赚钱”变成“亏损单硬拿久一点”，因为持仓时间是退出之后才知道的结果。K线内退出的时间只精确到15分钟所属K线，实际可能比记录长不足15分钟。',
      '## 自然年收益：亏损年、盈利年都列出',
      '使用连续回测的年末账户权益，包含未平仓浮盈亏；没有每年强制清仓。首尾年份是部分年份。表中版本同上一表，BNB/BTC使用2%止损的BTC原参数；其余使用1%止损的ETH原参数。',
      table(['年份']+[a.upper() for a in ASSETS],[[str(y)]+[pct(next((m['return_pct'] for m in full[a+'__'+select[a]]['years'] if m['label']==str(y)),None)) for a in ASSETS] for y in range(2018,2027)]),
      '例如 ETH 在2022年币价跌67.5%而策略赚224.1%，在2023年币价涨90.8%而策略亏1.7%。SOL在2022年币价跌94.1%而策略赚120.6%。BNB的BTC参数在2023年价格涨26.6%但策略亏49.1%，2026年截至9月10日仍亏13.6%。因此“累计盈利”不能替代“逐年稳定盈利”。',
      '你的空单解释在部分年份确实成立：ZEC在2025、2026年上涨时，当年平仓多单合计为正，空单为负并拖累整体；PAXG在2025年也如此。ETH在2023年亦是多单赚钱、空单亏损。但ZEC在2024年多空都亏，PAXG在2021年多空都亏，BNB的BTC参数在2023年同样多空都亏，所以不能把所有失败统一归因于长期上涨时做空。',
      'BNB的BTC参数对比尤其清楚：2021年胜率44.06%、平均赢家2.28%；2023年胜率降至25.48%、平均赢家缩至1.36%，该年934笔中有671笔因反向信号亏损，只有12笔固定止损亏损。它的坏年份主要是频繁反向交易和较小的赢家，并不是止损线被触及太多。',
      '## 是否只是抓住同一轮行情',
      '同一六年、同一ETH原参数，比较每月收益，不以彼此不同的全部历史作相关性计算。',
      table(['组合','币价月涨跌相关性','策略月收益相关性','最赚钱10个月重合数'],[[pair,num((v:=r['relationships']['eth_original'][pair])['market_correlation']),num(v['strategy_correlation']),len(v['top10_overlap'])] for pair in ['eth__sol','eth__bnb','sol__bnb','eth__btc']]),
      'ETH/SOL币价月涨跌相关性约0.66，但策略月收益约0.06；各自最佳十个月重合三个。它们受共同市场影响，却不是每月都靠同样的交易赚钱。相关性低也不是独立验证，更不能证明没有过拟合。',
      '## 其他因素也查了',
      '入场前一天是否已有明确方向：固定分组中，“先前走得更单边”没有在所有币上更好。ETH/SOL在先前来回波动较多的分组反而平均每笔收益更高。强趋势组样本很少，不能看到某组好就直接当成新过滤规则。',
      '前30天涨跌与多空：BTC和BNB的ETH参数，在前30天已经上涨超过10%时，空单平均表现为负；这支持部分“逆大趋势做空拖累”的解释。但PAXG/ZEC在其他分组中也有亏损，不能用一条大趋势过滤解决全部问题。',
      '固定1%止损与2%保护，对不同波动尺度并不等价。PAXG典型单根振幅约0.14%，SOL/ZEC约0.71%。但ZEC与SOL振幅相近而收益相反，说明波动尺度之外还有突破持续性、假突破次数和盈亏分布的差别。',
      '零成交量信号、数据缺口和退出价格也保留检查。PAXG只有4笔入场前信号K线零成交量，其余五币的ETH参数为0；零成交量不是这批上万笔亏损的主要直接解释。原数据缺口仍存在，因此不能声称重建了缺口内路径。',
      '## 过拟合问题现在能说到哪一步',
      'SOL/BNB原参数直接搬过去仍然盈利、附近多组参数也盈利，说明不是只有一个孤立参数点好看。但整个会话已经反复查看并筛选了这些历史；新增币也属于相关市场，当前没有新增完全未见历史。不能根据这些描述统计宣称消除了过拟合，也没有计算整个会话的过拟合概率。反复试验后的最佳结果需要考虑完整试验范围，这是已有研究指出的选择偏差问题。',
      '[方法参考：Bailey等《The Probability of Backtest Overfitting》](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)；[Sullivan、Timmermann、White：技术交易规则与数据窥探](https://www.fmg.ac.uk/publications/discussion-papers/data-snooping-technical-trading-rule-performance-and-bootstrap)。这些文献支持方法边界，本文所有收益数字来自项目保存的行情和交易记录。',
      '不计手续费和滑点，不加杠杆，每笔当时全部本金复投；复利收益不可直接相加。以上是已发生交易的诊断，并非已经验证的新入场过滤器。原始参数、副本、31个补充回测和全部诊断结果都保留。']
    return '\n\n'.join(texts)+'\n'


def render():
    r=read(DOCS/'results.json');assert r['verification']['status']=='passed'
    samples=excerpts(r);save(DOCS/'candle-examples.json',samples)
    md=markdown(r);(DOCS/'REPORT.md').write_text(md,encoding='utf-8')
    payload={k:r[k] for k in ('full','common','hindsight','direction_reruns','relationships','shared_episode_check')}
    payload['samples']=samples
    html=TEMPLATE.replace('__DATA__',json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('</','<\\/'))
    (DOCS/'report.html').write_text(html,encoding='utf-8')
    served=ROOT/'docs/verification/eth-cloud-two-year-20260910/transfer-diagnosis.html'
    served.write_text(html,encoding='utf-8')
    (RUNTIME/'report-ui.js').write_text(html.split('<script>')[1].split('</script>')[0],encoding='utf-8')
    print('Rendered',served,flush=True)


TEMPLATE='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>六币策略诊断：亏在哪里，利润靠什么</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#1f3045;font:15px/1.75 "Microsoft YaHei",sans-serif}main{max-width:1450px;margin:auto;padding:28px}h1{font-size:32px;line-height:1.4}h2{font-size:22px;margin:0 0 12px}h3{margin:22px 0 8px}p{max-width:1150px}.card{background:white;border:1px solid #dde4ed;border-radius:15px;padding:24px;margin:20px 0}.lead{font-size:19px}.muted{color:#60738a}.note{background:#edf3fc;border-left:4px solid #6485b1;padding:12px 16px}.bad{color:#b44037}.good{color:#007d64}.toolbar{display:flex;gap:14px;flex-wrap:wrap;align-items:center;position:sticky;top:0;z-index:2;background:#f4f6faf5;padding:14px 0}select,button{font:inherit;padding:8px 12px;border:1px solid #bac9db;border-radius:8px;background:white;color:#233c5e}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:11px 13px;border-bottom:1px solid #e8edf4;text-align:left;white-space:nowrap}th{background:#f5f8fd;color:#526982}a{color:#386bb0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.mini{padding:16px;border:1px solid #e1e8ef;border-radius:10px}.mini b{font-size:21px}.mini p{margin:5px 0}.heatgrid{display:grid;grid-template-columns:repeat(12,minmax(56px,1fr));gap:4px;min-width:760px}.heat{font-size:12px;line-height:1.4;text-align:center;padding:8px 1px;border-radius:4px;color:#172c3d}.heat small{display:block;opacity:.8}.years-title{margin-top:18px;font-weight:bold}.plot{width:100%;height:auto;min-width:720px}.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}.assetbar{display:flex;gap:12px;flex-wrap:wrap;align-items:center}details{margin:12px 0}summary{cursor:pointer}svg text{font-family:"Microsoft YaHei",sans-serif}@media(max-width:850px){main{padding:14px}.card{padding:16px}.grid{grid-template-columns:1fr 1fr}.cols{grid-template-columns:1fr}h1{font-size:26px}.toolbar{position:static}}
</style><main><a href="alt-transfer.html">← 返回上一轮参数结果</a><h1>亏在哪里，利润究竟靠什么？</h1><p class="lead"><b>PAXG、ZEC 的亏损不只是空单造成的。ETH、SOL 的多空都能赚钱；BTC 的空单拖累较明显，BNB 则取决于所用版本和年份。</b></p>
<p>这轮保留全部原参数，分析逐笔交易，补做相同六年、只做多和只做空的对照，没有再搜索新参数。收益不含手续费和滑点，不加杠杆，每次当时全部本金复投；所有收益为累计收益。</p>
<section class="card"><h2>先把结论讲清楚</h2><div class="grid"><div class="mini"><b>PAXG：小亏太多</b><p>反复穿过通道，频繁反向退出；原参数的2%保护只有约2.23%的交易启动。</p></div><div class="mini"><b>ZEC：止损和假突破多</b><p>波动与SOL相近，但固定止损、反向亏损吃掉大赢家。仅关掉空单仍然亏。</p></div><div class="mini"><b>收益依赖大赢家</b><p>多数持仓只有数小时，少数持续一到数天。不是只靠一个共同月份，但尾部大单很重要。</p></div></div><p class="note">同一六年里六个币的期末价格都高于期初，SOL、BNB也有很大的涨幅。所以“它们长期横盘，另一些长期上涨”不足以解释策略差异。长期涨跌和15分钟策略所交易的小时级路径必须分开看。</p></section>
<div class="toolbar"><label>选择用于对照的原参数 <select id="config"><option value="eth_original">六币都用 ETH 原参数：1%止损</option><option value="btc_original">六币都用 BTC 原参数：2%止损</option></select></label><span class="muted" id="params"></span></div>
<section class="card"><h2>① 是不是空单把收益拖没了？</h2><p>统一用2020年9月10日至2026年9月10日。只做多/只做空都用项目引擎重新回测，保留反向平仓和保护；逐笔时间、价格与原策略对应方向一致。两个方向的累计收益不能相加。</p><div class="scroll" id="sides"></div></section>
<section class="card"><h2>② 每一年都发生了什么？</h2><p>各币完整历史的自然年收益，年末权益含未平仓浮盈亏，不在年末强制清仓。2018/2019/2020的起始年与2026年可能只覆盖部分年份；日期可在下方单币表核对。</p><div class="scroll" id="years"></div><p>你的空单解释在部分年份成立：ZEC的ETH参数在2025、2026年，多单总体为正、空单拖累；PAXG在2025年、ETH在2023年也如此。但ZEC在2024年、PAXG在2021年多空都亏，BNB的BTC参数在2023年也是多空都亏。</p><p class="note">BNB的BTC参数：2021年胜率44.06%，平均赢家2.28%；2023年胜率降到25.48%，平均赢家缩到1.36%。2023年的934笔中，671笔因反向信号亏损，仅12笔因固定止损亏损。这一年主要败在反复进出、赚不够大，而不是固定止损太频繁。</p></section>
<section class="card"><h2>③ 同样的百分比，对不同币并不等价</h2><div class="scroll" id="scale"></div><p>振幅是入场前高低差的 EMA。PAXG 的2%浮盈目标相当于约14倍典型单根振幅，而SOL/ZEC约2.8倍；这只是在比较价格尺度，不是所需K线根数。SOL与ZEC振幅相近却盈亏相反，说明还要看突破后能否走出足够大的行情。</p><div class="scroll" id="expectancy"></div><p class="muted">“回本需要几倍”按当前赚钱与亏钱的次数计算，不计复利损耗；实际平均赢家连这个比例都达不到，就已经无法覆盖平均亏损。</p></section>
<section class="card"><h2>④ 持仓多久，少了大赢家会怎样？</h2><div class="scroll" id="duration"></div><p>“最佳10笔归零”只把这10笔的收益当成0，其余交易的百分比结果不变，是算术压力检查。“要删多少赢家才不赚钱”从最大赢家依次计算，不能当成未来漏单的概率。</p><p class="note">持仓时间是交易结束后的结果。长单盈利更多，不意味着把亏损单强行多拿几个小时就会转盈。K线内退出时间可能比记录长不足15分钟。</p></section>
<section class="card"><h2>⑤ 是不是靠同一轮大行情赚钱？</h2><p>以下比较同一六年的月收益。相关性接近1表示经常同涨同跌，接近0表示这种同步关系弱。即使策略收益同步较弱，也不能把相关资产当成完全独立的验证。</p><div class="scroll" id="correlation"></div><p>将ETH、BTC、SOL、BNB合计表现最好的三个共同月份（2021年2月、2021年3月、2025年2月）收益全部归零，四者仍赚钱。这里ETH/SOL用ETH原参数，BTC/BNB用BTC原参数；结果如下。</p><div class="scroll" id="shared"></div></section>
<section class="card"><h2>⑥ 逐个币看：年份、月份、亏损方式和真实K线</h2><div class="assetbar"><label>标的 <select id="asset"><option>ETH</option><option>BTC</option><option>SOL</option><option>BNB</option><option>PAXG</option><option>ZEC</option></select></label><label><input type="checkbox" id="hindsight">查看上一轮该币全历史收益第一名（PAXG/ZEC/SOL/BNB）</label></div><p id="detailparams" class="muted"></p><div class="scroll" id="assetyears"></div><h3>月收益分布：每格都是一个月</h3><p class="muted">绿色赚钱、红色亏钱，深浅在±30%处封顶，格内仍显示真实收益；首尾月为部分月份。</p><div class="scroll" id="heatmap"></div><div class="cols"><div><h3>不同退出方式</h3><div class="scroll" id="exits"></div></div><div><h3>持仓长短与结果</h3><div class="scroll" id="holdgroups"></div></div></div><h3>具体赚在哪些交易</h3><div class="scroll" id="toptrades"></div><h3>真实K线：大赢家、最大亏损和常见反向亏损</h3><select id="example"></select><p id="sampletext"></p><div class="scroll" id="candles"></div><p class="muted">金线是中心EMA，浅蓝两线是实际入场门槛，虚线是初始止损价（不是之后的移动保护线）。标注对应真实成交价；盘中退出不能从整根K线推断精确先后顺序。</p><details><summary>展开：入场前其他因素与结果的关系</summary><p>均使用入场前已经完成的K线。这里只描述现有交易分组，不能当成已验证的入场过滤器，样本少的组尤其不能下结论。</p><div id="features"></div></details></section>
<section class="card"><h2>这轮能否排除过拟合？</h2><p>不能。SOL、BNB原参数能直接沿用，多组相邻参数也赚钱，这些提供支持；但整个会话已反复查看这些历史，各币也处在相关市场中。本次检查说明利润来自哪里、哪些解释不成立，没有计算整个研究过程的过拟合概率。</p><p>按最好的过去结果反复选参数，必须考虑完整试验范围带来的选择偏差。方法参考：<a href="https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf">Bailey等：回测过拟合</a>、<a href="https://www.fmg.ac.uk/publications/discussion-papers/data-snooping-technical-trading-rule-performance-and-bootstrap">Sullivan等：技术交易规则与数据窥探</a>。这里所有收益数字均来自本项目保存的行情和交易，不来自论文。</p><p class="muted">本次数据沿用项目 MarketDataService/KlineStore 的 Binance 15分钟历史，保留原缺口和零成交量K线，没有制造行情。方向分组和各年权益均核对；原参数、引擎和旧报告保持不变。研究记录：docs/verification/cloud-transfer-diagnosis-20260911。</p></section></main>
<script>
const D=__DATA__,assets=['eth','btc','sol','bnb','paxg','zec'];const $=id=>document.getElementById(id);let currentDetail,currentSamples;
const fmt=(v,n=2)=>v==null?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:n,maximumFractionDigits:n});const pct=v=>v==null?'—':`<span class="${v<0?'bad':'good'}">${v>0?'+':''}${fmt(v)}%</span>`;const day=t=>new Date(t).toISOString().slice(0,16).replace('T',' ');const reason={stop_loss:'初始止损',profit_protection:'利润保护',reversal:'反向平仓并反手',signal:'反向平仓',end_of_backtest:'测试结束'};const table=(h,r)=>`<table><thead><tr>${h.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${r.map(row=>`<tr>${row.map(x=>`<td>${x}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
function params(p){return `EMA${p.center_length} · 振幅${p.width_length} · 门槛${p.trigger_mult}倍 · 最远${p.chase_mult}倍 · 浮盈${p.activation_pct}%启动 · 回吐${p.giveback_pct}% · 止损${p.initial_stop_pct}%`;}
function render(){const config=$('config').value;const full=a=>D.full[a+'__'+config];$('params').textContent=params(full('eth').parameters);
$('sides').innerHTML=table(['标的','双向累计收益','只做多','只做空','币价同期涨幅'],assets.map(a=>[a.toUpperCase(),pct(D.common[a+'__'+config].summary.compound_return_pct),pct(D.direction_reruns[a+'__'+config].long.return_pct),pct(D.direction_reruns[a+'__'+config].short.return_pct),pct(D.common[a+'__'+config].market.market_return_pct)]));
$('years').innerHTML=table(['自然年',...assets.map(a=>a.toUpperCase())],Array.from({length:9},(_,i)=>2018+i).map(y=>[y+(y===2026?'（截至9月10日）':''),...assets.map(a=>pct(full(a).years.find(v=>v.label==y)?.return_pct))]));
$('scale').innerHTML=table(['标的','入场典型单根振幅','启动保护需几倍振幅','实际启动保护的比例','因距离过远挡住的突破'],assets.map(a=>{let d=full(a);return[a.toUpperCase(),fmt(d.scale.median_entry_width_pct)+'%',fmt(d.scale.median_activation_widths),fmt(d.scale.activation_rate_pct)+'%',`${d.scale.distance_blocked} / ${d.scale.raw_crossings}`]}));
$('expectancy').innerHTML=table(['标的','胜率','平均赚一笔','平均亏一笔','实际盈亏大小比','回本需要几倍','平均每笔收益'],assets.map(a=>{let s=full(a).summary;return[a.toUpperCase(),fmt(s.win_rate)+'%',pct(s.mean_win_pct),pct(s.mean_loss_pct),fmt(s.win_loss_size_ratio),fmt(s.breakeven_size_ratio),pct(s.mean_return_pct)]}));
$('duration').innerHTML=table(['标的','笔数','持仓中位数','赚钱单中位数','亏损单中位数','最佳10笔归零后','删多少最佳赢家后不赚钱'],assets.map(a=>{let d=full(a);return[a.toUpperCase(),d.summary.trades,fmt(d.summary.median_hours)+'小时',fmt(d.winners.median_hours)+'小时',fmt(d.losers.median_hours)+'小时',pct(d.stress.trade_checks[0].return_if_zero_pct),d.stress.best_winners_zeroed_to_erase_profit??'原本已亏损']}));
$('correlation').innerHTML=table(['标的组合','币价月涨跌相关性','策略月收益相关性','最赚钱10个月重合数','重合月份'],['eth__sol','eth__bnb','sol__bnb','eth__btc'].map(k=>{let x=D.relationships[config][k];return[k.replace('__',' / ').toUpperCase(),fmt(x.market_correlation),fmt(x.strategy_correlation),x.top10_overlap.length,x.top10_overlap.join('、')]}));
$('shared').innerHTML=table(['标的','三个共同月份收益归零后的六年累计收益'],Object.entries(D.shared_episode_check.return_if_these_months_zero_pct).map(([a,v])=>[a.toUpperCase(),pct(v)]));detail();}
const labels={volatility:'入场前的波动大小',efficiency:'此前96根K线是否走得单边',momentum30:'此前30天涨跌',body:'信号K线实体占全长比例',volume_bucket:'信号成交量/此前20根均量',zero_volume:'信号K线零成交量'};
const groupnames={below_015:'振幅低于0.15%','015_to_04':'振幅0.15%—0.4%',above_04:'振幅大于0.4%',below_01:'单边程度低于0.1','01_to_025':'单边程度0.1—0.25',above_025:'单边程度大于0.25',up_10:'前30天涨超10%',down_10:'前30天跌超10%',between_10:'前30天涨跌在±10%内',insufficient_history:'最早阶段不足30天历史',small:'实体不足1/3',medium:'实体1/3—2/3',large:'实体超过2/3',below_1:'成交量小于均量','1_to_2':'成交量1—2倍均量',above_2:'成交量大于2倍均量',False:'有成交量',True:'零成交量',under_1h:'不足1小时','1_to_4h':'1—4小时','4_to_12h':'4—12小时','12_to_24h':'12—24小时',over_24h:'24小时以上'};
function detail(){let a=$('asset').value.toLowerCase(),c=$('config').value,h=$('hindsight').checked&&D.hindsight[a];currentDetail=h?D.hindsight[a]:D.full[a+'__'+c];let d=currentDetail;currentSamples=D.samples[a+'__'+(h?'hindsight':c)];$('detailparams').textContent=params(d.parameters)+(h?'。这是事后全历史第一名，不能视为独立验证。':'。沿用已固定原参数。')+' 日期均为UTC。';
$('assetyears').innerHTML=table(['自然年','实际覆盖','策略收益','币价涨跌','年内币价最大收盘回撤','当年平仓笔数','当年平仓胜率','当年多单平均每笔','当年空单平均每笔'],d.years.map(y=>[y.label,day(y.start).slice(0,10)+' → '+day(y.end).slice(0,10),pct(y.return_pct),pct(y.market_return_pct),fmt(y.market_max_drawdown_pct)+'%',y.closed_trades.trades,fmt(y.closed_trades.win_rate)+'%',pct(y.side.long?.mean_return_pct),pct(y.side.short?.mean_return_pct)]));
let hm='';for(let y=+d.years[0].label;y<=+d.years.at(-1).label;y++){hm+=`<div class="years-title">${y}</div><div class="heatgrid">`;for(let m=1;m<=12;m++){let x=d.months.find(x=>x.label===`${y}-${String(m).padStart(2,'0')}`);let v=x?.return_pct;let color=v==null?'#f4f5f7':v>=0?`rgba(0,142,107,${.08+Math.min(v/30,.7)})`:`rgba(199,68,66,${.08+Math.min(-v/30,.7)})`;hm+=`<div class="heat" style="background:${color}" title="${x?`${x.label} 策略 ${fmt(v)}% 币价 ${fmt(x.market_return_pct)}%`:''}"><small>${m}月</small>${v==null?'—':fmt(v,1)+'%'}</div>`;}hm+='</div>';} $('heatmap').innerHTML=hm;
$('exits').innerHTML=table(['退出方式','笔数','亏损笔数','每笔平均收益'],Object.entries(d.exits).map(([k,v])=>[reason[k]||k,v.trades,v.losses,pct(v.mean_return_pct)]));
$('holdgroups').innerHTML=table(['持仓时间','笔数','胜率','每笔平均收益'],['under_1h','1_to_4h','4_to_12h','12_to_24h','over_24h'].filter(k=>d.duration[k]).map(k=>[groupnames[k],d.duration[k].trades,fmt(d.duration[k].win_rate)+'%',pct(d.duration[k].mean_return_pct)]));
$('toptrades').innerHTML=table(['方向','入场UTC','出场UTC','入场价','出场价','收益','持仓小时'],d.top_trades.slice(0,10).map(t=>[t.side==='long'?'做多':'做空',day(t.entry_time),day(t.exit_time),fmt(t.entry_price),fmt(t.exit_price),pct(t.return_pct),fmt(t.duration_minutes/60)]));
$('features').innerHTML=Object.entries(d.entry_groups).map(([field,groups])=>`<h3>${labels[field]}</h3><div class="scroll">${table(['条件','笔数','胜率','每笔平均收益'],Object.entries(groups).map(([k,v])=>[groupnames[k]||k,v.trades,fmt(v.win_rate)+'%',pct(v.mean_return_pct)]))}</div>`).join('');
$('example').innerHTML=currentSamples.map((s,i)=>`<option value="${i}">${s.label}</option>`).join('');draw();}
function draw(){let s=currentSamples[+$('example').value],t=s.trade,rows=s.rows,band=s.band,p=currentDetail.parameters;let W=1100,H=430,pad={l:65,r:20,t:24,b:40};let initial=t.entry_price*(1-t.direction*p.initial_stop_pct/100);let values=rows.flatMap(r=>[r[2],r[3]]).concat([initial,t.exit_price]);let lo=Math.min(...values),hi=Math.max(...values),extra=(hi-lo)*.08;lo-=extra;hi+=extra;let x=i=>pad.l+(i+.5)*(W-pad.l-pad.r)/rows.length;let y=v=>H-pad.b-(v-lo)/(hi-lo)*(H-pad.t-pad.b);let width=Math.max(1,(W-pad.l-pad.r)/rows.length*.66);let svg=`<svg viewBox="0 0 ${W} ${H}" class="plot" role="img" aria-label="真实K线、EMA通道及成交位置"><rect width="${W}" height="${H}" fill="#fff"/>`;
for(let n=0;n<5;n++){let price=lo+(hi-lo)*n/4,yy=y(price);svg+=`<line x1="${pad.l}" x2="${W-pad.r}" y1="${yy}" y2="${yy}" stroke="#e8edf3"/><text x="5" y="${yy+4}" fill="#667b94" font-size="12">${fmt(price)}</text>`;}
for(let field of ['upper','lower','center'])svg+=`<polyline points="${band.map((b,i)=>`${x(i)},${y(b[field])}`).join(' ')}" fill="none" stroke="${field==='center'?'#d3a236':'#92b5d6'}" stroke-width="${field==='center'?2:1.5}"/>`;
rows.forEach((r,i)=>{let col=r[4]>=r[1]?'#078a74':'#d75752';svg+=`<g><title>${day(r[0])} O ${r[1]} H ${r[2]} L ${r[3]} C ${r[4]}</title><line x1="${x(i)}" x2="${x(i)}" y1="${y(r[2])}" y2="${y(r[3])}" stroke="${col}"/><rect x="${x(i)-width/2}" y="${Math.min(y(r[1]),y(r[4]))}" width="${width}" height="${Math.max(1,Math.abs(y(r[1])-y(r[4])))}" fill="${col}"/></g>`;});
let ei=rows.findIndex(r=>r[0]===t.entry_time),xi=rows.findIndex(r=>r[0]===t.exit_time);svg+=`<line x1="${x(ei)}" x2="${x(xi)}" y1="${y(initial)}" y2="${y(initial)}" stroke="#b15e70" stroke-dasharray="5 4"/>`;
for(let [i,price,label,col] of [[ei,t.entry_price,'入场','#245fcc'],[xi,t.exit_price,'出场','#713e91']]){let yy=y(price);svg+=`<circle cx="${x(i)}" cy="${yy}" r="5" fill="${col}"/><line x1="${x(i)}" x2="${x(i)}" y1="${pad.t}" y2="${H-pad.b}" stroke="${col}" opacity=".22"/><text x="${Math.min(x(i)+8,W-80)}" y="${Math.max(18,yy-12)}" fill="${col}" font-size="14">${label}</text>`;}
for(let i of [0,Math.floor(rows.length/2),rows.length-1])svg+=`<text x="${Math.max(pad.l,Math.min(x(i),W-155))}" y="${H-10}" font-size="12" fill="#667b94">${day(rows[i][0])}</text>`;svg+='</svg>';$('candles').innerHTML=svg;$('sampletext').innerHTML=`${s.label}：${t.side==='long'?'做多':'做空'}，${day(t.entry_time)} → ${day(t.exit_time)}，收益 ${pct(t.return_pct)}，持仓约 ${fmt(t.duration_minutes/60)} 小时，${reason[t.exit_reason]||t.exit_reason}。`;}
$('config').addEventListener('change',render);$('asset').addEventListener('change',detail);$('hindsight').addEventListener('change',detail);$('example').addEventListener('change',draw);render();
</script></html>'''


if __name__=='__main__':render()
