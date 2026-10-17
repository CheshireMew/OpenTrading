"""Readable comparison of twelve frozen trend rules and chronological transfers."""
from bisect import bisect_left
from html import escape
from pathlib import Path
import json

from scripts.cross_market_trend_study import DOCS,RUNTIME,ROOT,ASSETS,FOLDS,read,save

PUBLIC=ROOT/'docs/verification/eth-cloud-two-year-20260910'


def pct(x):return '—' if x is None else f'{x:+,.2f}%'
def num(x):return '—' if x is None else f'{x:,.2f}'
def table(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'---|'*len(head)]+['| '+' | '.join(map(str,r))+' |' for r in rows])


def name(k):
    if k is None:return '空仓'
    if k=='old_ema55':return '旧EMA55／15分钟'
    f,s,tf=k.split('_');frame='4小时' if tf=='4h' else '日线'
    rule={'breakout':('突破20／退出10','突破55／退出20'),'average':('均线20／60','均线50／150'),'momentum':('涨跌方向30根','涨跌方向90根')}[f][s=='slow']
    return frame+' · '+rule


def desc(k):
    if k=='old_ema55':return '旧版EMA55，振幅EMA31，门槛0.4倍，超过2倍不追；浮盈2%启动保护，回吐50%，初始止损1%。'
    f,s,tf=k.split('_');n=20 if s=='fast' else 55;e=10 if s=='fast' else 20
    if f=='breakout':rule=f'收盘超过此前{n}根K线最高价做多，跌破此前{n}根最低价做空；多单跌破此前{e}根最低价退出，空单反过来。当前K线不计入此前高低点。'
    elif f=='average':
        a,b=(20,60) if s=='fast' else (50,150)
        rule=f'较快的{a}根收盘简单均价高于{b}根均价时做多，低于时做空；两条均线方向交换时退出或反手，完全相等时退出。'
    else:
        n=30 if s=='fast' else 90
        rule=f'收盘价高于{n}根以前的收盘价时做多，低于时做空；涨跌方向改变时退出或反手，恰好不涨不跌时退出。'
    return rule+' 均按所选周期收盘确认，下一根实际开盘成交。初始止损为入场前ATR14的3倍；固定距离，不放宽，不叠加2%利润保护。'+('突破止损后等待新的合格突破。' if f=='breakout' else '回测起点按已知方向首次入场；止损后等待方向重新变化，不因方向仍相同马上重开。')


def build(r,d):
    keys=list(r['plan']['variants'])+['old_ema55'];curves={};metrics={}
    for a in ASSETS:
        curves[a]={};metrics[a]={}
        for k in keys:
            curves[a][k]={};metrics[a][k]={p:r['results'][a][k][p] for p in ('common','full')}
            for p in ('common','full'):
                eq=read(RUNTIME/'traces'/a/f'{k}-{p}.json')['equity'];stride=max(1,len(eq)//250)
                sampled=eq[::stride]
                if sampled[-1]!=eq[-1]:sampled.append(eq[-1])
                curves[a][k][p]=[[x['timestamp'],x['equity']/10000] for x in sampled]
    return dict(names={k:name(k) for k in keys},descriptions={k:desc(k) for k in keys},
        assets=ASSETS,variants=r['plan']['variants'],metrics=metrics,details=d,choices=r['choices'],
        periods={a:r['data'][a]['periods'] for a in ASSETS},curves=curves,
        simulations=r['simulations'],data={a:{tf:{f:r['data'][a][tf][f] for f in ('rows','missing','first_safe_start')} for tf in ('4h','1d')} for a in ASSETS})


def markdown(r,d):
    ranking=d['rankings']['common'];best=ranking[0]['key']
    text=['# 跨标的趋势测试：4小时与日线，三种方法、12个版本',
      '本轮规则和参数在获取结果前固定，沒有按币调参，也沒有按结果追加版本。六币共同期间是2021-09-10至2026-09-10；更长历史在各币具备200根连续预热K线后开始，完整日期如下。',
      '使用项目MarketDataService/KlineStore中的Binance原生4小时/日线现货价格，多空模拟；不是把有缺口的15分钟数据拼成完整日线。每笔使用当时全部本金，不加杠杆、不计手续费和滑点。每个币是独立账户，中间水平收益不是组合收益。',
      f'完成{r["simulations"]}次分段模拟；12个新规则之外，旧EMA55作为独立对照。三种方法分别为前高前低突破、双简单均线、过去涨跌方向。所有新规则统一ATR14×3初始止损；入场和趋势退出均按各自周期收盘决定，没有沿用十五分钟反向退出或2%利润保护。',
      '## 一套参数用于六币：共同五年完整结果',
      '以下按六币累计收益的中位数（排序后中间两项的平均）排列，只用于事后描述；不能当成每年事先能选到的成绩。',
      table(['策略',*[a.upper() for a in ASSETS],'盈利币数','六币中间水平'],
            [[name(x['key']),*[pct(r['results'][a][x['key']]['common']['return_pct']) for a in ASSETS],f"{x['positive']}/6",pct(x['median_return_pct'])] for x in ranking]),
      table(['对照',*[a.upper() for a in ASSETS]],
            [[name('old_ema55'),*[pct(r['results'][a]['old_ema55']['common']['return_pct']) for a in ASSETS]],
             ['买入持有',*[pct(d['assets'][a][best]['common']['market']['market_return_pct']) for a in ASSETS]]]),
      '## 事先只看前面年份选，再运行后面一年',
      '每轮用2021-09-10至当年9月10日的六币数据选择。同一版本必须至少4个币盈利、六币收益中位数为正，再按中位数最高选择。若没有版本合格就空仓。每年9月10日重选一次、平仓换规则；分年从空仓开始，收益连续复投。这与五年连续持仓的完整表不同。',
      table(['测试年（9月到次年9月）','事先选定规则',*[a.upper() for a in ASSETS]],
            [[f'{y}—{y+1}',name(r['choices'][str(y)]['global_choice']['selected']),*[pct(next(x for x in d['tracks'][a]['global_choice']['annual'] if x['year']==y)['return_pct']) for a in ASSETS]] for y in FOLDS]),
      table(['三年合计',*[a.upper() for a in ASSETS],'盈利币数','中间水平'],
            [[label,*[pct(d['tracks'][a][kind]['summary']['compound_return_pct']) for a in ASSETS],f"{d['rankings'][kind]['positive']}/6",pct(d['rankings'][kind]['median_return_pct'])] for kind,label in [('global_choice','六币共同选规则'),('held_asset','不看该币选规则，再用到该币'),('old','旧EMA55，每年同样结算重开')]]),
      '## 留出一个币的具体选择',
      '每次挑规则时只看另外五个币此前的年份，至少3/5盈利且中间水平为正；然后测试被留下那个币的下一年。不是看见该币结果后再替它选冠军。整个会话此前已看过这六币历史，因此它是程序选择层面的排除，不是真正完全未知的市场验证。',
      table(['留下哪个币','测试年','用另外五币选出的规则','留下这个币的收益'],
            [[a.upper(),f'{y}—{y+1}',name(r['choices'][str(y)]['held_asset'][a]['selected']),pct(next(x for x in d['tracks'][a]['held_asset']['annual'] if x['year']==y)['return_pct'])] for a in ASSETS for y in FOLDS]),
      '## 六币共同五年中间水平最高的固定规则：具体交易情况',desc(best),
      table(['标的','收益','总笔数','赚钱','亏钱','持平','胜率','平均盈利','平均亏损','典型持仓天数','最大收盘回撤'],
            [[a.upper(),pct((m:=r['results'][a][best]['common'])['return_pct']),m['trades'],m['wins'],m['losses'],m['flat'],num(m['win_rate'])+'%',pct(m['mean_win_pct']),pct(m['mean_loss_pct']),num(m['median_hours']/24 if m['median_hours'] is not None else None),pct(-m['max_drawdown_pct'])] for a in ASSETS]),
      '最大回撤来自各策略原生周期的收盘权益，日线看不到日内最低权益，不能与15分钟收盘回撤当成完全相同的观测精度。止损仍用原生K线高低价检查；盘内实际退出时间只能定位在这根K线内。',
      '## 这套固定规则：自然年表现',
      table(['年份（首尾不足全年）',*[a.upper() for a in ASSETS]],
            [[str(y),*[pct(next(x['return_pct'] for x in d['assets'][a][best]['common']['years'] if x['label']==str(y))) for a in ASSETS]] for y in range(2021,2027)]),
      '## 各币更长历史，同一套规则',
      table(['标的','开始日期','结束日期','策略收益','旧EMA55收益','买入持有'],
            [[a.upper(),r['data'][a]['periods']['full'][0][:10],r['data'][a]['periods']['full'][1][:10],pct(r['results'][a][best]['full']['return_pct']),pct(r['results'][a]['old_ema55']['full']['return_pct']),pct(d['assets'][a][best]['full']['market']['market_return_pct'])] for a in ASSETS]),
      '## 不让最赚钱的一个币掩盖其他标的',
      table(['比较对象','移除哪个币','剩余五币收益中间水平'],
            [['共同五年固定规则第一名',ranking[0]['best_asset'].upper(),pct(ranking[0]['median_without_best'])],
             *[[label,d['rankings'][kind]['best_asset'].upper(),pct(d['rankings'][kind]['median_without_best'])] for kind,label in [('global_choice','按前面年份每年选择'),('held_asset','留一币验证')]]]),
      '## 每一种规则是什么',*['**'+name(k)+'**：'+desc(k) for k in r['plan']['variants']],
      '## 本轮能确认与不能确认的事',
      '日线与4小时版本同时改变信号周期、入场和退出规则。本轮能比较完整策略组合，不能把收益差全部归因于周期变长或某一个指标。ATR倍数固定3，未测试其他倍数；快慢两档不是全参数寻优。',
      '新旧方法的入场止损尺度不同，但都使用当时全部本金，因此实际每笔风险不同。较大的收益可能伴随更大的单笔损失，不能说只靠选对方向提高了效果。',
      '规则简单、跨币一致以及按时间排除后年，有助于检查过拟合，却不证明过拟合已消除；本会话反复使用过这些历史。日线交易少，少量大赢家可能支撑数年收益。盈利币数、亏损年份、持仓天数、最大回撤与每笔记录全部保留，不承诺以后或每一年赚钱。',
      '本轮不按结果追加参数，也不执行真实交易。原策略、副本、冻结名单、数据来源、每轮选择与逐笔记录均已保留。']
    return '\n\n'.join(text)+'\n'


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>六币趋势测试 · 4小时与日线</title>
<style>:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#203049;background:#f4f6fa}*{box-sizing:border-box}body{margin:0}main{max-width:1540px;margin:auto;padding:30px 28px 70px}h1{font-size:30px}h2{font-size:22px;margin:0 0 15px}h3{font-size:17px}p{line-height:1.85}a{color:#2966b4}.tag,.muted{color:#687b91}.tag{font-size:13px}nav{display:flex;gap:20px}.box{background:#fff;border:1px solid #dee5f0;border-radius:12px;padding:24px;margin:22px 0}.callout{background:#edf3fc;border-left:4px solid #5a83c2;padding:12px 20px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;white-space:nowrap}th,td{padding:12px 14px;border-bottom:1px solid #e4ebf2;text-align:right}th{background:#f5f8fc;color:#526a88;font-weight:500}th:first-child,td:first-child{text-align:left}.pos{color:#13846e}.neg{color:#bc4457}.controls{display:flex;gap:25px;flex-wrap:wrap;align-items:center;margin:18px 0}select{font:inherit;background:#fff;border:1px solid #c7d2e4;border-radius:7px;padding:8px 12px;max-width:100%}.grid{display:grid;grid-template-columns:1fr 1fr;gap:25px}svg{width:100%;height:auto;display:block}summary{cursor:pointer;color:#35619b}details{margin-top:15px}.cards{display:flex;gap:45px;flex-wrap:wrap;margin:20px 0}.cards strong{font-size:23px;display:block}.pill{font-size:12px;background:#eef3fa;color:#597395;padding:4px 8px;border-radius:5px}@media(max-width:900px){main{padding:20px 12px}.box{padding:18px}.grid{grid-template-columns:1fr}h1{font-size:25px}}</style>
<main><nav><a href="paxg-zec-repair.html">← ATR与反向确认</a><a href="transfer-diagnosis.html">此前六币亏损诊断</a></nav><p class="tag">同一套规则用于六个币 · 参数先固定再测试 · 新旧版本完整保留</p><h1>4小时与日线：能不能更好地跨标的使用？</h1><p id="lead"></p><div class="callout"><p id="verdict"></p></div>
<section class="box"><h2>一套参数换六个币：共同五年完整结果</h2><p>2021年9月10日—2026年9月10日，按六币收益的中间水平排列。六个币各自独立投入，不是把资金分成六份的组合。这里的第一名使用了全部五年结果，是事后排名。</p><div id="matrix" class="scroll"></div><p class="muted">中间水平：六项收益排序后，中间两项的平均。它不是账户收益，也没有把各币收益相加。每笔全本金复投，不加杠杆，不计手续费和滑点。</p></section>
<section class="box"><h2>真正按前面年份选，后一年会怎么样？</h2><p>每次只看2021年9月起到当年9月之前的数据，至少4/6币盈利才入选，再选中间水平最高的一套，下一年六币都用它。没有合格版本就空仓。三个年份分别保存选择结果后才计算后一年。</p><div id="folds" class="scroll"></div><h3>2023年9月—2026年9月，三年累计结果</h3><div id="tracks" class="scroll"></div><p id="tracknote"></p><details><summary>展开：每次不看一个币，只用其他五个币选规则，再用于被留下的币</summary><p class="muted">至少3/5币盈利、中间水平为正才选择。被留下的币和后一年均不参加该轮选择。这六币历史在前面的会话已经被研究过，不能称作整个研究从未接触的未知数据。</p><div id="held" class="scroll"></div></details></section>
<section class="box"><h2>具体交易：选一个版本，看每个币赚亏在哪里</h2><div class="controls"><label>策略 <select id="strategy"></select></label><label>期间 <select id="period"><option value="common">六币共同五年</option><option value="full">各币可用的更长历史</option></select></label></div><p id="rule"></p><div id="stats" class="scroll"></div><p class="muted">典型持仓采用中位数。最大回撤按该策略周期收盘权益观察；日线无法反映盘中最深回撤，与旧15分钟版的观测精度不同。初始止损仍在每根K线的高低价范围内检查。</p><h3>每年赚亏都列出</h3><div id="years" class="scroll"></div><p class="muted">按连续回测每年末权益计算，包含未平仓浮盈亏。首尾为部分年份；较长历史每币开始时间不同，空白表示不在该币回测期间。</p><div class="controls"><label>查看标的 <select id="asset"></select></label></div><p id="range"></p><h3>账户增长曲线</h3><div id="chart"></div><p class="muted">蓝线为所选规则，灰线为旧EMA55。1表示初始本金；纵轴使用对数刻度，方便同时看很大的增长和回撤。图线抽样用于显示，收益及回撤取完整逐根记录。</p><div class="grid"><div><h3>多单、空单分别怎样</h3><div id="sides" class="scroll"></div><p class="muted">方向收益把原双向交易里该方向的收益单独复乘，不是关闭另一个方向后的重新选时回测，两个方向的收益也不能相加。</p></div><div><h3>怎么退出，亏在哪一类</h3><div id="exits" class="scroll"></div></div></div><p id="tail"></p><details><summary>快慢两档的附近参数表现</summary><div id="nearby" class="scroll"></div><p class="muted">这是预先规定的另一档，跨度较大，只能看粗略敏感性；没有根据结果再细调周期。</p></details></section>
<section class="box"><h2>每个版本的完整规则</h2><div id="rules"></div></section>
<section class="box"><h2>数据、验证范围与保留记录</h2><div id="data" class="scroll"></div><p>使用项目的原生4小时与日线行情；上市前没有数据的部分没有补造。新策略先预热200根，六币主表统一采用都有充分历史的五年；更长历史从每个币满足预热的最早日界线开始。缺口通过项目数据服务复查，仍缺少的K线保持空缺。</p><p>所有新规则采用ATR14的3倍作为固定初始止损。突破是20根进场/10根退出或55根进场/20根退出；简单均线是20/60或50/150；涨跌方向看30或90根以前。分别用于4小时和日线，一共12组。旧策略参数完全不改，只按相同日期重新跑。</p><p>新旧规则还同时改变了退出方法和每笔可能承受的亏损，不能把差距全部归因于周期更长，也不能把一组参数的失败推广为所有趋势交易无效。日线交易少，某些好成绩可能依赖少数大赢家。历史排名不证明未来稳定盈利。</p><p id="audit"></p><p>本轮不追加参数搜索，不下真实订单。每组参数、数据来源、三次年度选择、十八次留一币选择、全部逐笔交易和策略源码都有保存。所有旧报告和旧策略继续保留。</p></section></main>
<script>const D=__DATA__;const $=id=>document.getElementById(id),n=x=>x==null?'—':x.toLocaleString('zh-CN',{maximumFractionDigits:2}),p=x=>x==null?'—':(x>=0?'+':'')+x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+'%',pc=x=>x==null?'—':`<span class="${x>=0?'pos':'neg'}">${p(x)}</span>`,nm=k=>k?D.names[k]:'空仓';
function tbl(head,rows){return '<table><thead><tr>'+head.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
const ranking=D.details.rankings.common,top=ranking[0],assets=D.assets;
$('lead').textContent=`三种趋势方法、12个版本，已完成${D.simulations}次分段回测。入场和退出都按4小时或日线判断，统一使用3倍ATR初始止损。`;
let g=D.details.rankings.global_choice,h=D.details.rankings.held_asset;
$('verdict').innerHTML=`共同五年中间水平最高的是 <b>${nm(top.key)}</b>，${top.positive}/6币盈利；按前面年份每年选择，后面三年${g.positive}/6币盈利；不看目标币选择规则再转过去，${h.positive}/6币盈利。<b>${g.positive>=4&&h.positive>=4?'这轮出现了跨币迁移的正面证据，但还要看亏损币、年份和交易数量。':'事后好成绩没有充分重复到按时间、按标的排除的选择中，不能宣布找到通用策略。'}</b>`;
$('matrix').innerHTML=tbl(['规则',...assets.map(x=>x.toUpperCase()),'盈利币数','中间水平'],[...ranking.map(x=>[nm(x.key),...assets.map(a=>pc(D.metrics[a][x.key].common.return_pct)),x.positive+'/6',pc(x.median_return_pct)]),[nm('old_ema55'),...assets.map(a=>pc(D.metrics[a].old_ema55.common.return_pct)),'—','—'],['买入持有',...assets.map(a=>pc(D.details.assets[a][top.key].common.market.market_return_pct)),'—','—']]);
$('folds').innerHTML=tbl(['测试年份','事先选择',...assets.map(x=>x.toUpperCase())],Object.entries(D.choices).map(([y,c])=>[y+'—'+(+y+1),nm(c.global_choice.selected),...assets.map(a=>pc(D.details.tracks[a].global_choice.annual.find(x=>x.year==y).return_pct))]));
const kinds=[['global_choice','六币共同选一套'],['held_asset','用其他五币选，再转到该币'],['old','旧EMA55每年同样结算重开']];
$('tracks').innerHTML=tbl(['做法',...assets.map(x=>x.toUpperCase()),'盈利币数'],kinds.map(([kind,label])=>[label,...assets.map(a=>pc(D.details.tracks[a][kind].summary.compound_return_pct)),D.details.rankings[kind].positive+'/6']));
$('tracknote').innerHTML=`移除表现最好的${g.best_asset.toUpperCase()}后，按前面年份选择这套做法的剩余五币收益中间水平为 ${pc(g.median_without_best)}。这是独立账户间比较，不是组合收益。每年9月结算重开，区别于上方五年连续持仓的成绩。`;
$('held').innerHTML=tbl(['被留下的币','测试年份','其他五币选出的规则','该币收益'],assets.flatMap(a=>Object.entries(D.choices).map(([y,c])=>[a.toUpperCase(),y+'—'+(+y+1),nm(c.held_asset[a].selected),pc(D.details.tracks[a].held_asset.annual.find(x=>x.year==y).return_pct)])));
$('strategy').innerHTML=[...ranking.map(x=>x.key),'old_ema55'].map(k=>`<option value="${k}">${nm(k)}</option>`).join('');$('asset').innerHTML=assets.map(a=>`<option value="${a}">${a.toUpperCase()}</option>`).join('');
$('rules').innerHTML=Object.keys(D.variants).map(k=>`<p><b>${nm(k)}：</b>${D.descriptions[k]}</p>`).join('');
$('data').innerHTML=tbl(['标的','更长历史开始','结束','4小时K线','日线K线','4小时缺根','日线缺根'],assets.map(a=>[a.toUpperCase(),D.periods[a].full[0].slice(0,10),D.periods[a].full[1].slice(0,10),n(D.data[a]['4h'].rows),n(D.data[a]['1d'].rows),D.data[a]['4h'].missing,D.data[a]['1d'].missing]));
$('audit').textContent=`${D.simulations}份逐笔记录及全部年度选择核对通过。公开项目策略名：cross_market_trend_v1；12个版本参数、源代码和报告已留档。`;
function draw(){let k=$('strategy').value,per=$('period').value,a=$('asset').value,m=D.metrics[a][k][per],v=D.details.assets[a][k][per];$('rule').textContent=D.descriptions[k];
$('stats').innerHTML=tbl(['标的','收益','笔数','赚钱','亏钱','持平','胜率','平均盈利','平均亏损','典型持仓天数','最大收盘回撤'],assets.map(a=>{let m=D.metrics[a][k][per];return[a.toUpperCase(),pc(m.return_pct),n(m.trades),m.wins,m.losses,m.flat,n(m.win_rate)+'%',pc(m.mean_win_pct),pc(m.mean_loss_pct),n(m.median_hours==null?null:m.median_hours/24),pc(-m.max_drawdown_pct)]}));
let ys=[...new Set(assets.flatMap(a=>D.details.assets[a][k][per].years.map(y=>y.label)))].sort();$('years').innerHTML=tbl(['年份',...assets.map(x=>x.toUpperCase())],ys.map(y=>[y,...assets.map(a=>pc(D.details.assets[a][k][per].years.find(x=>x.label===y)?.return_pct))]));
$('range').textContent=a.toUpperCase()+'，'+D.periods[a][per][0].slice(0,10)+'至'+D.periods[a][per][1].slice(0,10)+'。';
$('sides').innerHTML=tbl(['方向','笔数','赚钱','亏钱','方向收益'],['long','short'].map(s=>[s==='long'?'多单':'空单',m.sides[s].trades,m.sides[s].wins,m.sides[s].losses,pc(m.sides[s].compound_return_pct)]));
const reasons={reversal:'反向换仓',signal:'趋势退出',stop_loss:'初始止损',profit_protection:'利润保护',end_of_backtest:'期末结算'};
$('exits').innerHTML=tbl(['退出原因','笔数','赚钱','亏钱','平均每笔'],Object.entries(m.exits).map(([s,x])=>[reasons[s]||s,x.trades,x.wins,x.losses,pc(x.mean_return_pct)]));
let c=v.concentration;$('tail').innerHTML=`把最赚钱的10笔收益算成零，保留其余交易，累计收益变为 ${pc(c.trade_checks[0].return_if_zero_pct)}。这是事后算术敏感性检查；日线交易总数可能不多，要同时看上方笔数，不能把删除10笔当成现实可执行的规则。`;
let near=k==='old_ema55'?[]:[k,k.replace(k.includes('_fast_')?'_fast_':'_slow_',k.includes('_fast_')?'_slow_':'_fast_')];$('nearby').innerHTML=near.length?tbl(['版本',...assets.map(x=>x.toUpperCase())],near.map(k=>[nm(k),...assets.map(a=>pc(D.metrics[a][k][per].return_pct))])):'旧版只作为固定对照。';
const one=D.curves[a][k][per],two=D.curves[a].old_ema55[per],all=[...one,...two];let x0=Math.min(...all.map(t=>t[0])),x1=Math.max(...all.map(t=>t[0])),lo=Math.min(...all.map(t=>Math.log10(Math.max(t[1],1e-9)))),hi=Math.max(...all.map(t=>Math.log10(Math.max(t[1],1e-9))));if(hi-lo<.1){hi+=.1;lo-=.1}let xx=x=>60+1000*(x-x0)/(x1-x0),yy=y=>260-230*(Math.log10(Math.max(y,1e-9))-lo)/(hi-lo);let path=ts=>ts.map((t,i)=>(i?'L':'M')+xx(t[0]).toFixed(1)+','+yy(t[1]).toFixed(1)).join(' ');let grid='';for(let i=0;i<=4;i++){let z=lo+(hi-lo)*i/4,Y=260-230*i/4;grid+=`<line x1="60" x2="1060" y1="${Y}" y2="${Y}" stroke="#e5ebf4"/><text x="52" y="${Y+4}" text-anchor="end" fill="#697e99" font-size="12">${n(Math.pow(10,z))}倍</text>`}
$('chart').innerHTML=`<svg viewBox="0 0 1100 300" role="img" aria-label="账户相对本金的增长曲线">${grid}<path d="${path(two)}" fill="none" stroke="#a5adbb" stroke-width="1.8"/><path d="${path(one)}" fill="none" stroke="#326eae" stroke-width="2.4"/><text x="60" y="288" font-size="12">${new Date(x0).toISOString().slice(0,10)}</text><text x="960" y="288" font-size="12">${new Date(x1).toISOString().slice(0,10)}</text></svg>`;
}
for(const id of ['strategy','period','asset'])$(id).addEventListener('change',draw);draw();</script></html>'''


def main():
    r=read(DOCS/'results.json');d=read(DOCS/'details.json');v=read(DOCS/'verification.json')
    assert r['status']=='completed' and v['status']=='passed' and v['traces_checked']==r['simulations']
    payload=build(r,d);save(DOCS/'report-data.json',payload)
    (DOCS/'REPORT.md').write_text(markdown(r,d),encoding='utf-8')
    html=HTML.replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('</','<\\/'))
    (DOCS/'cross-market-trend.html').write_text(html,encoding='utf-8')
    (PUBLIC/'cross-market-trend.html').write_text(html,encoding='utf-8')
    print('REPORT http://127.0.0.1:8787/cross-market-trend.html')


if __name__=='__main__':main()
