"""Plain-language report: original cloud strategy, only candle timeframe changes."""
import json
from scripts.cloud_timeframe_study import DOCS,RUNTIME,ROOT,ASSETS,TFS,read,save

PUBLIC=ROOT/'docs/verification/eth-cloud-two-year-20260910'
TF={'5m':'5分钟','15m':'15分钟对照','30m':'30分钟','1h':'1小时','1d':'日线'}
LABELS={
 'paxg':{'base':'原ETH参数：EMA55','full1':'EMA144，0.3%保护，反向等2根','full2':'EMA144，0.3%保护，原反向规则','recent1':'EMA89，2%保护'},
 'zec':{'base':'原ETH参数：EMA55','full1':'EMA144，1%保护','full2':'EMA89，1%保护','recent1':'EMA89，2%保护'}}


def pct(x):return '—' if x is None else f'{x:+,.2f}%'
def n(x):return '—' if x is None else f'{x:,.2f}'
def table(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'---|'*len(head)]+['| '+' | '.join(map(str,r))+' |' for r in rows])
def best(r,a,tf,period='common'):
    return max(r['results'][a],key=lambda k:r['results'][a][k][tf][period]['return_pct'])
def params(v):
    p=v['parameters']
    return [f'EMA{p["center_length"]}',p['width_length'],p['trigger_mult'],p['chase_mult'],str(p['activation_pct'])+'%',str(p['giveback_pct'])+'%',str(p['initial_stop_pct'])+'%',p['reverse_confirm_bars']]


def markdown(r,d):
    text=['# 原EMA通道策略：PAXG、ZEC换K线周期测试',
          '**本轮结果：PAXG的1小时改善最明显；ZEC的30分钟更值得保留。5分钟在本轮各组参数的共同四年中全部亏损，ZEC日线也全部亏损。** PAXG的EMA89组在1小时四年赚101.23%，但约六年只赚1.48%；ZEC的EMA144组在30分钟四年赚40.73%、七年赚125.86%，最近两年只有1.86%。换周期确实会改变结果，但盈利发生的年份差异很大。',
          '这次保留原策略的EMA中心线、高低差通道、突破入场、不追远价、初始止损、利润回吐保护和反向平仓。只测试用户要求的5分钟、30分钟、1小时、日线；原15分钟同参数重跑作为对照。没有再使用上一轮的30天涨跌、双均线或前高前低突破策略。',
          '每币4组已有参数，共40个标的/参数/周期组合，分别跑共同期间、更长历史、最近两年，合计120次模拟。每笔当时全部本金复投，不加杠杆、不计手续费和滑点。所有原策略和旧结果保留。',
          '主表统一2022-09-10至2026-09-10。原策略必须先预热650根K线，PAXG上市较晚，日线无法支持从2020年就开始交易，因此共同对比从2022年开始。5分钟、15分钟、30分钟、1小时另有原六/七年长历史；日线起点按真实数据单独列明。没有用不足预热的日线冒充六年结果。',
          '## 每个周期，已有4组参数中表现最好的是哪一组',
          '以下仅按共同四年累计收益选出每个周期的最高组；它们是本轮事后比较结果。具体参数已在本轮开始前固定。']
    for a in ASSETS:
        text += ['### '+a.upper(),table(['周期','参数组','四年收益','最近两年收益','交易数','赚钱','亏钱','持平','胜率'],
            [[TF[tf],LABELS[a][(k:=best(r,a,tf))],pct((m:=r['results'][a][k][tf]['common'])['return_pct']),pct(r['results'][a][k][tf]['recent']['return_pct']),m['trades'],m['wins'],m['losses'],m['flat'],n(m['win_rate'])+'%'] for tf in TFS]),
            '### '+a.upper()+'：同一组参数换周期后的全部收益',
            table(['已有参数组',*[TF[tf] for tf in TFS]],[[LABELS[a][k],*[pct(r['results'][a][k][tf]['common']['return_pct']) for tf in TFS]] for k in r['results'][a]]),
            table(['参数组','中心','宽度周期','突破倍数','不追倍数','保护启动','允许回吐','初始止损','反向确认根数'],[[LABELS[a][k],*params(v)] for k,v in r['plan']['variants'][a].items()])]
        for k in r['results'][a]:
            text += ['### '+a.upper()+' / '+LABELS[a][k]+'：共同四年逐年收益',
                table(['年份（首尾不足全年）',*[TF[tf] for tf in TFS]],[[str(y),*[pct(next(x['return_pct'] for x in d[a][k][tf]['common']['years'] if x['label']==str(y))) for tf in TFS]] for y in range(2022,2027)]),
                table(['周期','完整历史开始','完整历史结束','完整历史收益','最近两年收益'],[[TF[tf],r['data'][a][tf]['periods']['full'][0][:10],r['data'][a][tf]['periods']['full'][1][:10],pct(r['results'][a][k][tf]['full']['return_pct']),pct(r['results'][a][k][tf]['recent']['return_pct'])] for tf in TFS])]
    text += ['## 原策略到底怎么算',
        '每根K线用(最高价+最低价)/2计算中心EMA，用(最高价−最低价)的EMA算宽度W。收盘从下向上穿过“中心+突破倍数×W”产生做多信号；从上向下穿过“中心−突破倍数×W”产生做空信号。价格离中心超过“不追倍数×W”，就不新开仓，但反向退出仍有效。EMA周期始终按K线根数计算，例如EMA144在5分钟是144根5分钟K线，在日线是144根日线。',
        '信号收盘确认，下一根实际开盘成交；初始止损用表中固定百分比。盈利达到保护启动值后，止损线跟随最高浮盈，保留未允许回吐的部分。沿用原模拟器：当前K线收盘后才更新保护线，下一根开始生效；已经存在的止损在本根最高/最低价范围内检查，不假设能知道同一根内先涨后跌的顺序。反向确认2根的版本，要连续两根所选周期的K线满足条件。',
        '本次所选8组旧参数原本都是固定百分比止损，ATR止损倍数为0；没有因为换周期擅自替换成ATR止损。ATR14并未参与这些版本的交易止损。',
        '## 参数从哪里来、结果能说明什么',
        '从此前alt-cloud-transfer和paxg-zec-repair已有结果中合并去重，每币取原ETH参数、原15分钟全历史收益前两组、原15分钟最近两年收益第一组。这里“较好”可能只是亏得较少，不代表旧版本已盈利。没有读取新周期结果后再换参数。',
        '这些参数的挑选已经使用了历史结果，最近两年也参与过旧研究；所以这里只能说明原策略对周期的敏感性，不能把最近两年称作从未看过的验证。没有每年换策略，也没有对新周期重新优化参数。',
        '换周期会同时改变均线所覆盖的实际时间、信号频率和利润保护更新频率。因此结果差异是原策略整体运行周期的效果，不能全部归因于EMA是否准确。最大回撤按相应周期收盘权益计算；日线会漏掉日内更深回撤，持仓盘内退出的具体时刻也只能定位到该根K线。持仓显示0小时表示入场同一根K线内退出，并不代表瞬间平仓。',
        '新建v6副本仅把旧v5写死的15分钟反向确认间隔适配为实际K线间隔。16份原15分钟完整历史/最近两年结果须逐笔、逐信号、逐权益与旧版完全一致，全部120份记录核对后才生成此报告。旧v4/v5与此前全部报告不覆盖。',
        '数据检查把原生30分钟、1小时和日线，与完整5分钟片段中的实际成交价格汇总交叉比较，共346686个完整片段。无成交5分钟K线重复的旧价格不当作本段新成交。发现PAXG的2026-05-05 07:00 UTC小时缓存尚未更新完整，向项目数据源复查后修正1根；修正前后行情与原数据清单全部保留，本次回测使用修正后行情。']
    return '\n\n'.join(text)+'\n'


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>原EMA通道 · PAXG与ZEC换周期</title><style>
:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#203049;background:#f4f6fa}*{box-sizing:border-box}body{margin:0}main{max-width:1450px;margin:auto;padding:28px 26px 65px}h1{font-size:29px}h2{font-size:21px}p{line-height:1.9}.muted{color:#65758b;font-size:14px}.box{background:white;padding:24px;border:1px solid #dfe5ef;border-radius:12px;margin:22px 0}.callout{background:#edf3fc;border-left:4px solid #507db8;padding:15px 22px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;white-space:nowrap}td,th{text-align:right;padding:12px;border-bottom:1px solid #e2e7ef}td:first-child,th:first-child{text-align:left}th{font-weight:500;background:#f6f8fc}.pos{color:#087c62}.neg{color:#b84451}.controls{display:flex;flex-wrap:wrap;gap:22px;margin:22px 0}select{font:inherit;padding:8px;border:1px solid #bfcde0;border-radius:6px;max-width:100%}a{color:#2965a8}.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}svg{width:100%;height:auto}summary{cursor:pointer;color:#2965a8}@media(max-width:850px){main{padding:18px 12px}.box{padding:16px}.grid{grid-template-columns:1fr}}</style>
<main><a href="paxg-zec-repair.html">← 原15分钟参数与止损测试</a><p class="muted">原策略不换 · 仅PAXG、ZEC · 4组已有参数 × 4个指定周期，另列15分钟对照</p><h1>原EMA通道策略：换K线周期有没有帮助？</h1><div class="callout"><p id="lead"></p><p>仍使用原来的突破入场、不追远价、固定止损、利润回吐保护和反向退出。没有使用上一轮的30天涨跌方向策略。每笔全本金复投，不加杠杆，不计手续费和滑点。</p></div>
<section class="box"><h2>先看同一段历史，每个周期能做到什么</h2><p>共同期间：2022年9月10日—2026年9月10日。下面每个周期只在本次固定的4组旧参数中比较，列出收益最高的一组；不是继续搜索新参数。完整矩阵在后面。</p><div id="winners" class="scroll"></div><p class="muted">最近两年指2024年9月10日—2026年9月10日，单独从空仓开始回测；没有更换参数。参数来自已研究过的15分钟历史，这列不是全新的未知数据验证。</p></section>
<section class="box"><h2>同一组参数，换周期后的全部结果</h2><div class="controls"><label>标的 <select id="asset"><option value="paxg">PAXG</option><option value="zec">ZEC</option></select></label><label>期间 <select id="period"><option value="common">共同四年：2022—2026</option><option value="recent">最近两年：2024—2026</option><option value="full">各周期全部可用历史</option></select></label></div><p id="rangeNote"></p><div id="matrix" class="scroll"></div><h3>这些参数到底是什么</h3><div id="parameters" class="scroll"></div><p>宽度W是每根K线最高价减最低价，再取EMA。突破倍数决定做多/做空门槛离中心多远；不追倍数决定离中心多远就不再入场。“允许回吐35%”就是保留最高浮盈的65%。本次所选旧参数都是固定百分比止损，未改成ATR止损。</p></section>
<section class="box"><h2>逐年表现与交易明细统计</h2><div class="controls"><label>查看参数组 <select id="variant"></select></label></div><p id="rule"></p><div id="stats" class="scroll"></div><p class="muted">典型持仓按K线记录估算并取中位数；0小时表示同一根K线内退出，并不代表瞬间平仓。盘内退出时刻只能定位到该根K线。最大回撤按所选周期的收盘权益算，日线看不到日内更深回撤。</p><h3>同一参数组：每一年，各周期赚亏多少</h3><div id="years" class="scroll"></div><p class="muted">自然年按连续账户的年末权益计算，包含浮盈亏；首尾可能不足一年。空白表示该周期还没有足够预热历史。</p><div class="controls"><label>查看周期 <select id="timeframe"></select></label></div><p id="range"></p><div id="chart"></div><p class="muted">蓝线是所选周期，灰线是相同参数的15分钟对照。1倍表示初始本金；对数纵轴便于同时观察较大的收益和亏损。</p><div class="grid"><div><h3>多单和空单</h3><div id="sides" class="scroll"></div></div><div><h3>什么原因平仓</h3><div id="exits" class="scroll"></div></div></div><p class="muted">多空方向收益仅把已有交易分组复乘，不能相加，也不代表关闭另一方向后的新回测。</p></section>
<section class="box"><h2>测试规则和保留记录</h2><p>从此前PAXG、ZEC的原15分钟结果里，各取完整历史收益前2组、最近两年收益第1组，另保留原ETH六年第一参数。每币4组，在新周期结果出来前固定。本次120份分段模拟，不按结果追加参数，也不每年换策略。</p><p>EMA144在5分钟就是144根5分钟K线，在日线就是144根日线；各参数数值不变。原利润保护在每根K线收盘后更新，下一根开始生效，所以改变周期也会改变保护更新频率。已经存在的止损，在本根高低价范围内检查；信号收盘确认、下一根开盘成交。</p><p>原策略预热650根。PAXG日线上市历史不够支持2020年开始交易，因此主表统一从2022年开始；5分钟到1小时还会展示原六/七年更长历史，日线的真实开始日期另列。行情由项目MarketDataService/KlineStore获取，5分钟使用原生行情，不从15分钟伪造。缺失K线向数据源复查后仍不存在的，保持空缺。</p><div id="data" class="scroll"></div><p id="verification"></p><p>这轮比较的是“原策略换运行周期”的效果，不能将差异全部归因于均线或止损。旧参数挑选时已看过后两年，不能说已经排除过拟合。每次参数、策略、行情与逐笔结果均保留，旧报告不覆盖。</p></section></main>
<script>(()=>{const D=__DATA__,A=['paxg','zec'],T=['5m','15m','30m','1h','1d'],L=__LABELS__,TN=__TF__,$=id=>document.getElementById(id),nm=x=>x==null?'—':x.toLocaleString('zh-CN',{maximumFractionDigits:2}),pct=x=>x==null?'—':(x>=0?'+':'')+x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+'%',pc=x=>x==null?'—':`<span class="${x>=0?'pos':'neg'}">${pct(x)}</span>`,tbl=(h,r)=>'<table><thead><tr>'+h.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+r.map(x=>'<tr>'+x.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</tbody></table>',win=(a,tf)=>Object.keys(D.r.results[a]).sort((k,j)=>D.r.results[a][j][tf].common.return_pct-D.r.results[a][k][tf].common.return_pct)[0];
const globalBest=a=>T.filter(t=>t!=='15m').map(tf=>({tf,k:win(a,tf)})).sort((x,y)=>D.r.results[a][y.k][y.tf].common.return_pct-D.r.results[a][x.k][x.tf].common.return_pct)[0];
$('lead').innerHTML=A.map(a=>{const b=globalBest(a),m=D.r.results[a][b.k][b.tf].common;return `<b>${a.toUpperCase()}</b>：本次四个指定周期中，${TN[b.tf]}的「${L[a][b.k]}」共同四年收益最高，为 ${pc(m.return_pct)}；相同参数15分钟为 ${pc(D.r.results[a][b.k]['15m'].common.return_pct)}。`}).join('<br>');
$('winners').innerHTML=tbl(['标的','周期','已有参数组','四年收益','最近两年','笔数','赚钱','亏钱','胜率'],A.flatMap(a=>T.map(tf=>{let k=win(a,tf),m=D.r.results[a][k][tf].common;return[a.toUpperCase(),TN[tf],L[a][k],pc(m.return_pct),pc(D.r.results[a][k][tf].recent.return_pct),m.trades,m.wins,m.losses,nm(m.win_rate)+'%']})));
$('timeframe').innerHTML=T.map(tf=>`<option value="${tf}">${TN[tf]}</option>`).join('');
$('data').innerHTML=tbl(['标的','周期','完整历史开始','结束','行情根数','缺根数'],A.flatMap(a=>T.map(tf=>{let x=D.r.data[a][tf];return[a.toUpperCase(),TN[tf],x.periods.full[0].slice(0,10),x.periods.full[1].slice(0,10),nm(x.rows),x.missing]})));
$('verification').textContent=`已完成${D.v.traces_checked}份逐笔记录核对；16份15分钟完整历史/最近两年结果与旧版的交易、信号、收益曲线完全一致。346686个完整行情片段交叉核对后，修正1根PAXG旧小时缓存，修正前数据保留。独立适配文件trend_cloud_timeframe_v6只修正连续确认的时间间隔，旧v4/v5继续保留。`;
function updateAsset(){let a=$('asset').value;$('variant').innerHTML=Object.keys(L[a]).map(k=>`<option value="${k}">${L[a][k]}</option>`).join('');let b=globalBest(a);$('variant').value=b.k;$('timeframe').value=b.tf;draw()}
function draw(){let a=$('asset').value,p=$('period').value,k=$('variant').value,tf=$('timeframe').value,all=D.r.results[a],spec=D.r.plan.variants[a][k].parameters,m=all[k][tf][p],d=D.d[a][k][tf][p];$('rangeNote').textContent=p==='full'?'注意：日线历史开始得更晚；这张表各周期的日期不完全相同。跨周期公平比较请使用共同四年。':p==='recent'?'所有周期统一2024年9月10日—2026年9月10日。':'所有周期统一2022年9月10日—2026年9月10日。';
$('matrix').innerHTML=tbl(['已有参数组',...T.map(t=>TN[t])],Object.keys(L[a]).map(k=>[L[a][k],...T.map(tf=>pc(all[k][tf][p].return_pct))]));
$('parameters').innerHTML=tbl(['参数组','中心EMA','宽度EMA','突破倍数','不追倍数','保护启动','允许回吐','初始止损','反向确认'],Object.entries(D.r.plan.variants[a]).map(([k,v])=>{let s=v.parameters;return[L[a][k],s.center_length,s.width_length,s.trigger_mult,s.chase_mult,s.activation_pct+'%',s.giveback_pct+'%',s.initial_stop_pct+'%',s.reverse_confirm_bars+'根']}));
$('rule').textContent=`${L[a][k]}：中心EMA${spec.center_length}，宽度EMA${spec.width_length}；收盘穿过中心线上下${spec.trigger_mult}倍宽度时触发买卖，超过${spec.chase_mult}倍宽度不追。浮盈${spec.activation_pct}%启动保护，允许回吐最高浮盈的${spec.giveback_pct}%；初始止损${spec.initial_stop_pct}%，反向${spec.reverse_confirm_bars}根收盘确认。所有周期使用这套相同参数。`;
$('stats').innerHTML=tbl(['周期','收益','笔数','赚钱','亏钱','持平','胜率','平均盈利','平均亏损','典型持仓小时','最大收盘回撤'],T.map(tf=>{let x=all[k][tf][p];return[TN[tf],pc(x.return_pct),x.trades,x.wins,x.losses,x.flat,nm(x.win_rate)+'%',pc(x.mean_win_pct),pc(x.mean_loss_pct),nm(x.median_hours),pc(-x.max_drawdown_pct)]}));
let years=[...new Set(T.flatMap(t=>D.d[a][k][t][p].years.map(y=>y.label)))].sort();$('years').innerHTML=tbl(['年份',...T.map(t=>TN[t])],years.map(y=>[y,...T.map(t=>pc(D.d[a][k][t][p].years.find(x=>x.label===y)?.return_pct))]));
let range=D.r.data[a][tf].periods[p];$('range').textContent=a.toUpperCase()+' / '+TN[tf]+'：'+range[0].slice(0,10)+'至'+range[1].slice(0,10)+'。';
$('sides').innerHTML=tbl(['方向','笔数','赚钱','亏钱','方向收益'],['long','short'].map(s=>{let x=m.sides[s];return[s==='long'?'多单':'空单',x.trades,x.wins,x.losses,pc(x.compound_return_pct)]}));let reasons={signal:'反向退出，不追新仓',reversal:'反向换仓',stop_loss:'初始止损',profit_protection:'利润保护',end_of_backtest:'期末结算'};
$('exits').innerHTML=tbl(['原因','笔数','赚钱','亏钱','平均每笔'],Object.entries(m.exits).map(([why,x])=>[reasons[why]||why,x.trades,x.wins,x.losses,pc(x.mean_return_pct)]));
let one=d.curve,two=D.d[a][k]['15m'][p].curve,z=[...one,...two],x0=Math.min(...z.map(x=>x[0])),x1=Math.max(...z.map(x=>x[0])),lo=Math.min(...z.map(x=>Math.log10(Math.max(x[1],1e-12)))),hi=Math.max(...z.map(x=>Math.log10(Math.max(x[1],1e-12))));if(hi-lo<.1){hi+=.1;lo-=.1}let xx=x=>80+980*(x-x0)/(x1-x0),yy=y=>250-225*(Math.log10(Math.max(y,1e-12))-lo)/(hi-lo),path=xs=>xs.map((x,i)=>(i?'L':'M')+xx(x[0]).toFixed(1)+','+yy(x[1]).toFixed(1)).join(' '),grid='';for(let i=0;i<5;i++){let y=250-225*i/4,v=Math.pow(10,lo+(hi-lo)*i/4);grid+=`<line x1="80" x2="1060" y1="${y}" y2="${y}" stroke="#e2e7ef"/><text x="72" y="${y+4}" text-anchor="end" font-size="12">${v<.01?v.toExponential(1):nm(v)}倍</text>`}
$('chart').innerHTML=`<svg viewBox="0 0 1100 295" role="img" aria-label="所选周期与15分钟账户增长比较">${grid}<path d="${path(two)}" fill="none" stroke="#a6b1be" stroke-width="2"/><path d="${path(one)}" fill="none" stroke="#3676b9" stroke-width="2.5"/><text x="80" y="283" font-size="12">${new Date(x0).toISOString().slice(0,10)}</text><text x="965" y="283" font-size="12">${new Date(x1).toISOString().slice(0,10)}</text></svg>`;
}
$('asset').addEventListener('change',updateAsset);for(let id of ['period','variant','timeframe'])$(id).addEventListener('change',draw);updateAsset();})();</script></html>'''


def main():
    r=read(DOCS/'results.json');d=read(DOCS/'details.json');v=read(DOCS/'verification.json')
    assert r['status']=='completed' and v['status']=='passed' and v['legacy_15m_exact'] and v['traces_checked']==120
    payload=dict(r=r,d=d,v={k:x for k,x in v.items() if k!='manifest'})
    save(DOCS/'report-data.json',payload)
    html=HTML.replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('</','<\\/')).replace('__LABELS__',json.dumps(LABELS,ensure_ascii=False)).replace('__TF__',json.dumps(TF,ensure_ascii=False))
    (DOCS/'REPORT.md').write_text(markdown(r,d),encoding='utf-8')
    for path in (DOCS/'cloud-timeframes.html',PUBLIC/'cloud-timeframes.html'):path.write_text(html,encoding='utf-8')
    print('REPORT http://127.0.0.1:8787/cloud-timeframes.html')


if __name__=='__main__':main()
