"""Readable, fully disclosed results for the frozen short-window comparison."""
from copy import deepcopy
from collections import Counter
import json
from scripts.cloud_short_window_study import ROOT,DOCS,ASSETS,TFS,read,freeze

PUBLIC=ROOT/'docs/verification/eth-cloud-two-year-20260910'


def findings(result):
    out={}
    for a,ps in result['results'].items():
        names=[k for k in ps if k!='fixed']
        full=sorted(names,key=lambda k:(-ps[k]['metrics']['return_pct'],k))
        early=result['method_lock']['selections'][a]['chosen']
        score=read(DOCS/f'past-scores-{a}.json');coverage={}
        for w,dates in score.items():
            coverage[w]={}
            for tf in TFS:
                vals=[s for day in dates.values() for k,s in day.items() if k.startswith(tf+'__')]
                coverage[w][tf]=dict(candidate_reviews=len(vals),enough_trades=sum(v['closed_trades']>=20 for v in vals),
                    eligible=sum(v['closed_trades']>=20 and v['return_pct']>0 for v in vals))
        out[a]=dict(full_best=full[0],full_ranking=full,early_selected=early,
            full_beats_fixed=sum(ps[k]['metrics']['return_pct']>ps['fixed']['metrics']['return_pct'] for k in names),
            later_beats_fixed=sum(ps[k]['metrics']['later_return_pct']>ps['fixed']['metrics']['later_return_pct'] for k in names),
            positive_full=sum(ps[k]['metrics']['return_pct']>0 for k in names),coverage=coverage)
    return out


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>看几周、多久调整：四标的完整测试</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#24344a;font-family:system-ui,"Microsoft YaHei",sans-serif}main{max-width:1450px;margin:auto;padding:28px 24px 70px}h1{font-size:30px}h2{font-size:22px}h3{font-size:18px}p{line-height:1.9}.box{background:#fff;border:1px solid #dfe5ed;border-radius:12px;padding:24px;margin:24px 0}.intro{border-left:4px solid #3978b9;background:#ebf3fe;padding:18px 24px}.muted{color:#66758a;font-size:14px}.controls{display:flex;flex-wrap:wrap;align-items:center;gap:18px;margin:20px 0}select{padding:9px;font:inherit;border:1px solid #becada;border-radius:6px;max-width:100%}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:14px}th,td{padding:11px;border-bottom:1px solid #e1e6ee;text-align:right}th{background:#f5f7fa;font-weight:500}td:first-child,th:first-child{text-align:left}.scroll{overflow:auto}.pos{color:#087d64}.neg{color:#b33f54}.small{font-size:13px}.tag{display:inline-block;border-radius:4px;padding:2px 6px;background:#eef3fb;margin-left:5px;color:#47749e}a{color:#2867a7}svg{width:100%;height:auto}.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.step{padding:16px;border:1px solid #dce5f0;border-radius:9px}.step b{color:#2b69a4}@media(max-width:850px){main{padding:18px 12px}.box{padding:16px}.grid,.steps{grid-template-columns:1fr}h1{font-size:25px}}</style>
<main><a href="cloud-walkforward.html">← 上一轮三年观察窗口</a><p class="muted">ETH · BTC · PAXG · ZEC ｜ 原EMA通道策略 ｜ 24套候选 × 12种观察与调整办法</p><h1>看过去几周，多久重新选一次参数？</h1>
<div class="intro"><p><b>这次每次只看最近2、4、8或12周。</b> 每隔1、2或4周，从24套候选中选一套，再执行到下次检查。止损与利润保护保持相同。参数没有变，就继续原仓；只有选择改变才切换。</p><p id="mainConclusion"></p></div>
<section class="box"><h2>这轮留下哪些具体结论</h2><p><b>ETH值得保留短窗口选参。</b> 完整期间12种办法都超过固定小时参数，说明优势不只出现在一个孤立组合。不过差距很大：看8周、每2周检查累计+11,688.42%，每4周检查+7,377.20%，每周检查+3,291.21%。它支持继续保留8—12周这一组办法，不足以把“8周＋2周”定为长期最优。</p><p><b>BTC继续保留固定小时参数更有依据。</b> 固定版全期+769.94%，短窗口里最高只有+210.27%；后两年12种也都落后固定版。这次增加调整频率，并没有增加收益。</p><p><b>PAXG的12周窗口有用，主要价值是少做过去不合适的行情。</b> 三种检查频率全期分别赚36.94%、51.89%、45.72%，而2、4、8周的九种办法全亏。全期最高版本有938天空仓，2021年完全空仓，避开固定版当年−55.00%的亏损。后两年它+85.15%，与固定版+85.28%很接近。不能把全期改善说成后来每段行情都更会交易。</p><p><b>ZEC保留固定小时策略作参照，停止把这12种短窗口选择当作改进。</b> 固定版全期+81.58%，12种短窗口办法全亏。但固定版本也曾出现82.13%的最大回撤，所以“比这些方案好”不等于已经达到稳定盈利。</p><p><b>要更正此前关于固定参数的表述。</b> 上轮2023年10月以后四币都盈利；本轮加入更早年份后，固定小时策略的PAXG累计−63.28%。因此它只能作为统一对照，不能继续说成四币长期都盈利的版本。时期不同，结论的适用范围也不同。</p><p class="muted">上述均为本轮已计算结果。PAXG短窗口中的小时策略经常达不到20笔交易门槛，这与窗口长度混在一起；覆盖比例在页尾列出，不能把差异全部归因于行情适应速度。ETH全期最高版本胜率仍为27.49%，最大回撤51.20%，尚未解决亏损次数多的问题。</p></section>
<section class="box"><h2>先把“选择”和“检验”说清楚</h2><div class="steps"><div class="step"><b>① 观察过去几周</b><p>例如“看4周”：每次只比较刚过去4周的收益，要求窗口内至少20笔完整交易且收益为正。</p></div><div class="step"><b>② 决定下一段用什么</b><p>例如“每周检查”：选中的周期、EMA、突破门槛执行一周。下一周再按当时的过去4周重选。</p></div><div class="step"><b>③ 走过整段历史</b><p>从2020年12月28日一直重复到2026年9月10日。每次选择都不能使用之后的收益。</p></div></div><p>候选只有：5分钟／15分钟／半小时／1小时 × EMA34／55／89 × 突破0.4／0.8倍，共24套。固定高低差EMA31、不追超过2倍、初始止损1%、浮盈2%启动保护、允许回吐50%、反向一根确认。本轮没有更换ATR、止损或利润保护。</p><p class="muted">来源历史接近六年。最初12周用于提供共同观察数据，实际交易比较为2020-12-28—2026-09-10，五年八个多月。所有标的同起止日期，全本金复投，不加杠杆，不计手续费和滑点。日期采用UTC；周一00:00即北京时间周一08:00。</p></section>
<section class="box"><h2>较早年份选定一种办法，后面两年赚了吗？</h2><p>先只看2024年9月9日以前的成绩，从12种“看几周、多久调整”的办法中选一个。锁定这个办法后，再列出它在后两年的表现。它每次挑交易参数时，仍然只看最近几周，并没有改回看三年。</p><div id="lockedTable" class="scroll"></div><p id="lockedConclusion"></p><p>PAXG和ZEC在较早年份选出的办法仍是亏损的，只是12种里亏得最少；表格是预定的比较结果，不是当时值得采用它们的证明。ETH较早年份选中的是“12周＋4周”，后两年+215.71%，略低于固定参数+219.42%；不能用后来才知道的“8周＋2周”替换它，声称事先就选中了。</p><p class="muted">后两年：2024-09-09—2026-09-10。按该办法连续运行账户在这段时间的增长计算，分界处没有清仓或重置持仓。选择办法只接收早期成绩；这仍是此前研究过历史上的回顾检验，不能称为全新、完全没见过的数据。</p></section>
<section class="box"><h2>整段历史里，收益最高的是哪种？</h2><div id="bestTable" class="scroll"></div><p class="muted">这一表的第一名，是看完整段结果后得到的比较名次。上表才是只依据较早年份选出的办法，二者不能混为一谈。固定对照一直使用1小时、EMA55、突破0.4倍，其余规则与候选相同；没有定期清仓。</p></section>
<section class="box"><h2>12种办法全部列出，比较哪个因素影响大</h2><div class="controls"><label>标的 <select id="asset"><option value="eth">ETH</option><option value="btc">BTC</option><option value="paxg">PAXG</option><option value="zec">ZEC</option></select></label><label>收益期间 <select id="period"><option value="return_pct">完整交易期间</option><option value="early_return_pct">仅较早年份：2024-09-09以前</option><option value="later_return_pct">仅后两年：2024-09-09以后</option></select></label></div><p>每一行是看过去多久；每一列是隔多久重新选择。它们使用完全相同的24套候选。</p><div id="matrix" class="scroll"></div><p id="matrixNote"></p><div id="allMethods" class="scroll"></div></section>
<section class="box"><h2>选一个办法，看它具体做了什么</h2><div class="controls"><label>选择办法 <select id="method"></select></label></div><p id="methodNote"></p><div id="stats" class="scroll"></div><div id="chart"></div><p class="muted">蓝线为所选办法，灰线为固定小时参数。纵轴按账户倍数的对数刻度显示，初始1倍。下方逐年收益按年初到年末账户权益计算，含未平仓盈亏；首尾年份不足一年。</p><div id="years" class="scroll"></div><h3>时间主要分配给哪些交易周期</h3><div id="usage" class="scroll"></div><p class="muted">“使用天数”包括选中该周期但在等待信号的时间，不等于持续持仓。持仓时间是实际成交统计，盘中退出按所在K线近似。</p></section>
<section class="box"><h2>逐次选择：当时看了多久，选了什么</h2><div class="controls"><label>年份 <select id="year"></select></label></div><div id="ledger" class="scroll"></div><p class="muted">下面一表列出合并后的实际执行区间。连续多次选择相同参数会合并，原来的仓位与保护线继续保留；不是每次检查都强行平仓。</p><div id="segments" class="scroll"></div></section>
<section class="box"><h2>短窗口是否让某些周期几乎没有参选机会？</h2><p>本轮要求至少20笔窗口内完整交易。短窗口中的小时策略可能达不到这个数量，而5分钟更容易达到。下表显示，仅考虑交易数量，有多少比例的“候选×检查时点”达到门槛；真正入选还要求过去收益为正。这有助于区分“策略不好”和“样本条件没达到”。</p><div id="coverage" class="scroll"></div><p class="muted">20笔是开跑前固定的筛选条件，不是统计显著性的证明。本轮没有看着结果再优化这个门槛，也没有把未达到门槛的结果临时补进候选。</p></section>
<section class="box"><h2>保存与核对</h2><p id="verification"></p><p>行情沿用项目已核对的16份原生数据，96份候选历史路径按哈希复用。所有选择在计算实际执行结果前锁定。定期选择不变时不平仓；改变时取消旧挂起信号，按边界实际开盘价结束旧仓，新设置等待自己的下一次收盘信号，不追补已经发生的突破。</p><p>参数切换功能使用独立的项目引擎副本。无切换时与原引擎一致；连续指标状态恢复与完整历史预热输出一致。止损和利润保护按原策略所在周期执行：本根收盘后更新的保护线，下一根才生效；没有用本根最高价倒推本根之前应当退出。</p><p class="muted">各周期收盘权益用于回撤计算。四个标的并非完全独立，历史已被研究过；本轮只能说明这些明确规则在这些数据上的表现。原策略、旧结果、本轮方案、每次选择、逐笔交易、权益与编号副本均保留。</p></section></main>
<script>(()=>{const D=__DATA__,A=['eth','btc','paxg','zec'],P=D.plan,F=D.findings,$=id=>document.getElementById(id),tf={'5m':'5分钟','15m':'15分钟','30m':'半小时','1h':'1小时'},n=(x,d=2)=>x==null?'—':x.toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d}),pct=x=>x==null?'—':(x>=0?'+':'')+n(x)+'%',pc=x=>x==null?'—':`<span class="${x>=0?'pos':'neg'}">${pct(x)}</span>`,dt=x=>new Date(x).toISOString().slice(0,10),table=(h,rs)=>'<table><thead><tr>'+h.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rs.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table>',name=k=>k==='fixed'?'始终固定原小时参数':`看过去${k.match(/look(\d+)/)[1]}周，每${k.match(/update(\d+)/)[1]}周检查`,get=(a,k)=>D.results[a][k],detail=k=>{if(!k)return['空仓','—','—'];let v=P.candidates[k];return[tf[v.timeframe],'EMA'+v.parameters.center_length,v.parameters.trigger_mult+'倍']};
const methods=Object.keys(D.results.eth).filter(k=>k!=='fixed').sort((a,b)=>get('eth',a).lookback_weeks-get('eth',b).lookback_weeks||get('eth',a).update_weeks-get('eth',b).update_weeks);
$('method').innerHTML=['fixed',...methods].map(k=>`<option value="${k}">${name(k)}</option>`).join('');$('year').innerHTML=['全部',2020,2021,2022,2023,2024,2025,2026].map(y=>`<option value="${y}">${y}</option>`).join('');
let successes=A.filter(a=>get(a,F[a].early_selected).metrics.later_return_pct>get(a,'fixed').metrics.later_return_pct);
$('mainConclusion').innerHTML=`按较早年份成绩选定办法后，四个标的中有 <b>${successes.length}个</b> 在后两年超过固定原小时参数。下面分别列出提前选定的办法、完整历史比较第一名，以及12种办法的全部结果。`;
$('lockedTable').innerHTML=table(['标的','只用较早年份选定的办法','较早年份收益','该办法后两年收益','固定参数后两年收益','多／少多少个百分点'],A.map(a=>{let k=F[a].early_selected,m=get(a,k).metrics,b=get(a,'fixed').metrics;return[a.toUpperCase(),name(k),pc(m.early_return_pct),pc(m.later_return_pct),pc(b.later_return_pct),n(m.later_return_pct-b.later_return_pct)]}));
$('lockedConclusion').textContent=`后两年超过固定参数的标的：${successes.length?successes.map(a=>a.toUpperCase()).join('、'):'没有'}。这只是本轮固定范围的结果；不因为它落后，就改用后两年才知道的第一名。`;
$('bestTable').innerHTML=table(['标的','全期收益最高的办法','该办法全期收益','固定参数全期收益','12种中超过固定的数量','赢家交易数','赚钱','亏钱','胜率'],A.map(a=>{let k=F[a].full_best,m=get(a,k).metrics;return[a.toUpperCase(),name(k),pc(m.return_pct),pc(get(a,'fixed').metrics.return_pct),F[a].full_beats_fixed+'/12',m.trades,m.wins,m.losses,n(m.win_rate)+'%']}));
$('verification').textContent=`已复核${D.verification.candidate_histories}份候选历史、${D.verification.policies}份执行结果和${D.verification.decisions}次只用当时过去数据的选择。逐笔复利与账户终值一致，前后两段收益连乘与全期一致。早期选定办法可从仅含早期数值的记录复算。`;
function draw(){let a=$('asset').value,k=$('method').value,field=$('period').value,x=get(a,k),b=get(a,'fixed'),m=x.metrics;
$('matrix').innerHTML=table(['观察窗口',...P.updates_weeks.map(u=>'每'+u+'周检查')],P.lookbacks_weeks.map(w=>['过去'+w+'周',...P.updates_weeks.map(u=>pc(get(a,`look${w}w_update${u}w`).metrics[field]))]));
$('matrixNote').innerHTML=`固定原小时参数在同一期间的收益为 ${pc(b.metrics[field])}。各行各列只改变观察窗口和检查频率；固定对照没有定期换参数。`;
$('allMethods').innerHTML=table(['办法','全期收益','后两年收益','全期交易数','赚钱','亏钱','保本','胜率','实际选择变化次数','空仓天数','最大回撤'],methods.map(id=>{let z=get(a,id).metrics;return[name(id)+(id===F[a].early_selected?'<span class="tag">较早年份选定</span>':'')+(id===F[a].full_best?'<span class="tag">全期最高</span>':''),pc(z.return_pct),pc(z.later_return_pct),z.trades,z.wins,z.losses,z.flat,n(z.win_rate)+'%',z.parameter_changes,n(z.cash_days,1),n(z.max_drawdown_pct)+'%']}));
$('methodNote').textContent=name(k)+'。下面统计对应完整交易期间；上方“收益期间”只控制12种办法的收益矩阵。';
$('stats').innerHTML=table(['累计收益','交易数','赚钱','亏钱','保本','胜率','平均赚一笔','平均亏一笔','持仓中位数','最长连续亏损','最大回撤'],[[pc(m.return_pct),m.trades,m.wins,m.losses,m.flat,n(m.win_rate)+'%',pc(m.mean_win_pct),pc(m.mean_loss_pct),n(m.median_hours)+'小时',m.max_loss_streak+'笔',n(m.max_drawdown_pct)+'%']]);
$('years').innerHTML=table(['年份','所选办法收益','固定参数收益'],x.years.map(y=>[y.label,pc(y.return_pct),pc(b.years.find(q=>q.label===y.label)?.return_pct)]));
$('usage').innerHTML=table(['周期','使用天数','实际交易数','赚钱','亏钱','典型持仓'],Object.entries(tf).map(([t,label])=>{let z=x.by_timeframe[t];return[label,n(x.timeframe_days[t],1),z.trades,z.wins,z.losses,n(z.median_hours)+'小时']}));
let y=$('year').value,yearok=t=>y==='全部'||dt(t).startsWith(y);$('ledger').innerHTML=table(['检查日期','只看这段过去行情','选中周期','EMA','突破门槛','窗口内收益','完整交易数','合格候选数'],x.decisions.filter(d=>yearok(d.at)).map(d=>[dt(d.at),d.history_start?dt(d.history_start)+' → '+dt(d.at):'固定设置',...detail(d.chosen),pc(d.selected_past?.return_pct),d.selected_past?.closed_trades??'—',d.eligible??'—']));
$('segments').innerHTML=table(['实际执行区间','周期','EMA','突破门槛','连续相同选择次数','区间收益','交易数'],x.segments.filter(s=>y==='全部'||dt(s.start)<=y+'-12-31'&&dt(s.end)>=y+'-01-01').map(s=>[dt(s.start)+' → '+dt(s.end),...detail(s.chosen),s.decisions,pc(s.return_pct),s.trades]));
$('coverage').innerHTML=table(['观察窗口',...Object.values(tf)],Object.entries(F[a].coverage).map(([w,cs])=>['过去'+w+'周',...Object.keys(tf).map(t=>n(100*cs[t].enough_trades/cs[t].candidate_reviews,1)+'%')]));
let xs=x.curve,ys=b.curve,all=[...xs,...ys],x0=xs[0].timestamp,x1=xs.at(-1).timestamp,lo=Math.min(0,...all.map(e=>Math.log10(e.equity/10000))),hi=Math.max(.1,...all.map(e=>Math.log10(e.equity/10000))),xx=t=>75+(t-x0)/(x1-x0)*1000,yy=v=>245-(Math.log10(v/10000)-lo)/(hi-lo)*220,path=rs=>rs.map((e,i)=>(i?'L':'M')+xx(e.timestamp).toFixed(2)+' '+yy(e.equity).toFixed(2)).join(' '),grid='';for(let v of [.001,.01,.1,.25,.5,1,2,5,10,50,100,500,1000,5000,10000]){if(Math.log10(v)<lo||Math.log10(v)>hi)continue;let pos=yy(v*10000);grid+=`<path d="M75 ${pos}H1075" stroke="#e3e8ef"/><text x="66" y="${pos+4}" text-anchor="end" font-size="12">${v}倍</text>`}$('chart').innerHTML=`<svg viewBox="0 0 1100 285" role="img" aria-label="所选办法和固定参数账户增长比较">${grid}<path d="${path(ys)}" fill="none" stroke="#9eabbc" stroke-width="2"/><path d="${path(xs)}" fill="none" stroke="#337fc0" stroke-width="2.5"/><text x="75" y="276" font-size="12">${dt(x0)}</text><text x="970" y="276" font-size="12">${dt(x1)}</text></svg>`;
}
$('asset').addEventListener('change',()=>{$('method').value=F[$('asset').value].early_selected;draw()});for(let id of ['method','period','year'])$(id).addEventListener('change',draw);$('method').value=F.eth.early_selected;$('year').value='2026';draw();})();</script></html>'''


def name(k):
    if k=='fixed':return '固定原小时参数'
    p=k.split('_');return f"看过去{p[0][4:-1]}周，每{p[1][6:-1]}周检查"


def markdown(result,f):
    out=['# 短观察窗口与调整频率：完整结果','',
        '每次只看最近2/4/8/12周，每1/2/4周检查，从24套候选选择。买卖条件只允许改变K线周期、EMA和突破门槛；所有退出规则固定。',
        '完整交易比较2020-12-28—2026-09-10；较早阶段截至2024-09-09，之后两年单列。全本金复投，无手续费和滑点，无杠杆。',
        '', '## 只用较早年份选定办法，再看后两年','',
        '|标的|较早年份选定的办法|较早阶段收益|后两年收益|固定参数后两年收益|','|---|---|---:|---:|---:|']
    for a in ASSETS:
        p=result['results'][a];k=f[a]['early_selected'];m=p[k]['metrics'];b=p['fixed']['metrics']
        out.append(f"|{a.upper()}|{name(k)}|{m['early_return_pct']:+.2f}%|{m['later_return_pct']:+.2f}%|{b['later_return_pct']:+.2f}%|")
    out+=['','## 整段历史比较最高收益','',
          '|标的|全期最高办法|全期收益|固定参数全期收益|交易数|赚/亏/保本|胜率|','|---|---|---:|---:|---:|---|---:|']
    for a in ASSETS:
        p=result['results'][a];k=f[a]['full_best'];m=p[k]['metrics'];b=p['fixed']['metrics']
        out.append(f"|{a.upper()}|{name(k)}|{m['return_pct']:+.2f}%|{b['return_pct']:+.2f}%|{m['trades']}|{m['wins']}/{m['losses']}/{m['flat']}|{m['win_rate']:.2f}%|")
    out+=['','以上全期第一名是事后比较，不能当成事先已知的最佳办法。每次交易参数选择只接收当时之前的数据；选择哪种窗口办法也另有只含较早成绩的锁定记录。历史此前已被研究过，不是完全未接触过的新数据。']
    for a in ASSETS:
        out+=['',f'## {a.upper()}：12种办法全部结果','',
              '|观察周数|检查间隔周数|全期收益|后两年收益|胜率|实际选择变化次数|空仓天数|','|---:|---:|---:|---:|---:|---:|---:|']
        p=result['results'][a]
        for w in (2,4,8,12):
            for u in (1,2,4):
                x=p[f'look{w}w_update{u}w'];m=x['metrics']
                out.append(f"|{w}|{u}|{m['return_pct']:+.2f}%|{m['later_return_pct']:+.2f}%|{m['win_rate']:.2f}%|{m['parameter_changes']}|{m['cash_days']:.1f}|")
        k=f[a]['early_selected'];out+=['',f'较早年份选定的是{name(k)}。逐年表现如下：','',
                                     '|年份|所选办法|固定参数|','|---|---:|---:|']
        for y,b in zip(p[k]['years'],p['fixed']['years']):
            assert y['label']==b['label'];out.append(f"|{y['label']}|{y['return_pct']:+.2f}%|{b['return_pct']:+.2f}%|")
    out+=['','## 执行与边界','',
          '参数没有变就保留原仓和原保护线；改变时按边界实际开盘价结束旧仓，新设置等待自己的收盘信号。完整参数与每次选择、合并执行区间、逐笔交易和权益全部保存。',
          '最初12周仅提供共同观察数据；后段收益继承分界时的账户和仓位。20笔完整交易只是本轮固定门槛，不代表显著性，小时级别在短窗口中更难达到。',
          '原来的三年/半年研究还同时调整止损和利润保护，并在每个半年边界统一清仓，因此不能把它与本轮数字直接相减，当成仅改变观察窗口的效果。']
    return '\n'.join(out)+'\n'


def main():
    r=read(DOCS/'results.json');v=read(DOCS/'verification.json')
    assert r['status']=='completed' and v['status']=='passed'
    f=findings(r);freeze(DOCS/'findings.json',f)
    payload=deepcopy(r);payload['findings']=f;payload['verification']={k:x for k,x in v.items() if k!='manifest'}
    for ps in payload['results'].values():
        for p in ps.values():
            for key in ('trace_path','sha256','exits','months'):p.pop(key,None)
            for seg in p['segments']:
                seg.pop('trace_path',None);seg.pop('sha256',None)
    html=HTML.replace('__DATA__',json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
    (DOCS/'cloud-short-window.html').write_text(html,encoding='utf-8');(PUBLIC/'cloud-short-window.html').write_text(html,encoding='utf-8')
    (DOCS/'RESULTS.md').write_text(markdown(r,f),encoding='utf-8')
    print('REPORT http://127.0.0.1:8787/cloud-short-window.html',flush=True)


if __name__=='__main__':main()
