"""Mechanism-first report: preserve failed arms and avoid promoting a winner."""
import json
from statistics import median
from scripts.cloud_direct_adaptation_study import ROOT,DOCS,RUNTIME,ASSETS,TFS,read,freeze

PUBLIC=ROOT/'docs/verification/eth-cloud-two-year-20260910'
PRIMARY=['c0r0t0','slow89','wide12','c1r0t0','c0r1t0','c0r0t1','c1r1t1','base_gate','adaptive_gate']


def findings(d):
    out={}
    for a,fs in d['results'].items():
        out[a]={}
        for tf,vs in fs.items():
            b=vs['c0r0t0']['metrics']; full=vs['c1r1t1']['metrics'];pairs={}
            for field,idx in [('center',1),('risk',3),('trailing',5)]:
                effects=[]
                for key in list(vs):
                    if len(key)!=6 or key[idx]!='0':continue
                    other=key[:idx]+'1'+key[idx+1:]
                    if other not in vs:continue
                    off,on=vs[key]['metrics'],vs[other]['metrics']
                    effects.append(dict(off=key,on=other,full_difference_log=on['log_growth']-off['log_growth'],
                        later_on=on['later_return_pct'],later_off=off['later_return_pct'],
                        full_improved=on['return_pct']>off['return_pct'],later_improved=on['later_return_pct']>off['later_return_pct']))
                pairs[field]=dict(pairs=effects,full_improved=sum(e['full_improved'] for e in effects),later_improved=sum(e['later_improved'] for e in effects))
            out[a][tf]=dict(full_adaptive_positive=full['return_pct']>0,late_adaptive_positive=full['later_return_pct']>0,
                full_adaptive_improved=full['return_pct']>b['return_pct'],late_adaptive_improved=full['later_return_pct']>b['later_return_pct'],
                positive_full_variants=sum(v['metrics']['return_pct']>0 for v in vs.values()),pairs=pairs,
                continuation=read(DOCS/'diagnostics'/f'{a}-{tf}.json'))
    return out


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>直接自适应与通道灵敏度：四币检验</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#24344a;font:16px system-ui,"Microsoft YaHei",sans-serif}main{max-width:1450px;margin:auto;padding:26px 22px 65px}p{line-height:1.9}h1{font-size:29px}h2{font-size:22px}.box{background:white;border:1px solid #dfe5ed;border-radius:12px;padding:22px;margin:22px 0}.intro{background:#eaf2ff;border-left:4px solid #3978b9;padding:18px}.muted{color:#66758a;font-size:14px}.controls{display:flex;flex-wrap:wrap;gap:20px;margin:20px 0}select{padding:8px;font:inherit;max-width:100%;border:1px solid #bbc6d4;border-radius:6px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;white-space:nowrap;font-size:14px}td,th{border-bottom:1px solid #e1e6ee;padding:10px;text-align:right}td:first-child,th:first-child{text-align:left}th{background:#f5f7fa;font-weight:500}.pos{color:#067e65}.neg{color:#b33f54}a{color:#2867a7}svg{width:100%;height:auto}details{margin:15px 0}summary{cursor:pointer}@media(max-width:800px){main{padding:16px 12px}.box{padding:15px}h1{font-size:24px}}</style>
<main><a href="cloud-short-window.html">← 前一轮短窗口选择</a><p class="muted">ETH · BTC · PAXG · ZEC｜保留原通道框架｜96个固定公式回测</p><h1>不挑历史冠军，按价格直接调整，能减少亏损吗？</h1>
<div class="intro"><p>每个标的使用同一公式，不根据过去收益挑选参数，也不在时间周期之间切换。先固定全部规则，再比较结果。15分钟检查原问题，1小时单列作不同交易尺度的对照。</p><p>全期：2020-10-01—2026-09-10；后两年：2024-09-10—2026-09-10。每笔当前本金全额复投，不计手续费和滑点，不加杠杆。分段收益来自连续账户，边界不清仓。</p></div>
<section class="box"><h2>这轮真正发现了什么</h2><p><b>“通道太灵敏”解释了一部分损失，但没有解释全部。</b> PAXG 15分钟加宽门槛，快速反向亏损从3299笔降至204笔；ZEC从1234笔降至12笔。但两者全期仍分别亏94.71%和96.18%。PAXG仍是赢家不够补亏损，ZEC则更多转为固定止损退出。减少反向标签，不能代替减少实际损失。</p><p><b>直接自适应没有普遍改善，入场过滤留下了局部线索。</b> 原版只加方向效率过滤：ZEC 15分钟从全期−99.77%变为+29.44%，后两年+16.91%；PAXG 1小时从−68.78%变为+9.75%，后两年+33.17%。但同一过滤把ETH 15分钟从+24,695.71%降为−9.07%，不能当成所有标的的通用过滤器。</p><p><b>ZEC的转正也包含了入场时机改变，不能全部说成识别出了好信号。</b> 过滤版与原版入场时间相同的861笔，合起来仍亏23.45%；过滤后新出现的361笔入场，合起来赚69.10%。过滤先前信号后，原本因已有同方向仓位而忽略的后续信号，可以成为新的入场。共有交易的退出时间和价格已经逐笔核对一致。</p><p><b>一个具体例子揭示了保护启动门槛的敏感性。</b> 2026年2月13日，原版ZEC多单以233.44入场，价格到238.23时刚超过2%保护门槛，随后在235.26退出，赚0.78%。过滤版当天稍后以233.71入场，同一个238.23高点还未达到它的2%门槛，于是保留下来，最终赚33.56%。这笔赢家足以影响整个版本是否盈利；不是“入场过滤后每笔都更准”。日期为UTC。</p><p><b>暂时不能说已经修好。</b> PAXG小时过滤版2021—2024每年仍亏，利润主要来自2025—2026；ZEC 15分钟过滤版若把最赚钱月份2026年2月的收益归零，全期从+29.44%变为−8.94%。三项自适应再加过滤的ZEC版本全期+67.58%，但把最佳月份2025年10月归零则为−3.44%。这是算术集中度检查，不是实际可以提前删除交易的策略。</p></section>
<section class="box"><h2>先看三项自适应全部开启，是否解决问题</h2><div id="overview" class="scroll"></div><p id="overviewText"></p><p class="muted">表中的自适应始终指同一个事先确定的“自动均线＋波动止损与启动＋波动跟踪保护”，不是每个币各自的第一名。完整年份数量只计2021—2025，2020和2026不足一年。</p></section>
<section class="box"><h2>这次到底改了什么</h2><p><b>自动均线：</b>过去31根收盘价的净移动距离，除以每根变化绝对值的总和，得到0—1的方向效率。接近0表示反复折返，接近1表示走得顺。把它直接换成EMA21—89之间的平滑速度。中心仍用最高最低价平均，宽度仍用高低差EMA31。这是直接调整EMA权重的规则，不是标准KAMA的平方公式。</p><p><b>波动止损与启动：</b>初始止损距离取信号收盘时2倍ATR14；浮盈达到当时4倍ATR14启动保护。两条距离开仓后固定，以实际成交价为起点，不会因波动变大而扩大初始止损。这个分支同时改变止损和保护启动尺度，不能单独归功于其中一个。</p><p><b>波动跟踪保护：</b>启动后，多单保护价按最高价减去当前2倍ATR14计算，空单反过来。保护线只向盈利方向推进，最差守到入场价；按刚收盘K线更新，下一根生效。关闭此项就沿用最高浮盈回吐50%。</p><p><b>直接检查是否太灵敏：</b>另有只放慢到固定EMA89、只把突破门槛加宽到1.2倍振幅两个对照，其他全部不变。它们既改变入场，也改变原反向退出边界。</p><p><b>入场过滤：</b>原版和三项自适应各加一个相同对照：方向效率低于0.2时不进场，但已经持仓仍按原反向信号退出。过滤只看当时价格，不看未来盈利。这个0.2及所有倍数都在开跑前固定，没有证明是最佳数字。</p></section>
<section class="box"><h2>逐项改动后，收益和亏损次数有什么变化</h2><div class="controls"><label>标的 <select id="asset"><option value="paxg">PAXG</option><option value="zec">ZEC</option><option value="eth">ETH</option><option value="btc">BTC</option></select></label><label>固定交易周期 <select id="tf"><option value="15m">15分钟</option><option value="1h">1小时</option></select></label></div><div id="primary" class="scroll"></div><p class="muted">“快速反向亏损”指4根K线内因反向退出且亏损的交易：15分钟图对应1小时，1小时图对应4小时。减少这些亏损不等于收益必然增加；同时看赢家是否减少、每笔亏损是否扩大。</p><details><summary>查看全部12种方法（包括三项改动的两两组合）</summary><div id="all" class="scroll"></div></details><h3>同一因素，搭配其他规则时是否也有效</h3><div id="pairs" class="scroll"></div><p class="muted">例如均线有4组严格配对：其他两个开关相同时，只比较自动均线开和关。这能检查改善是否依赖某一个组合；这里不按收益选参数。</p></section>
<section class="box"><h2>亏在反向信号，还是止损？</h2><div class="controls"><label>具体版本 <select id="variant"></select></label></div><div id="detail" class="scroll"></div><div id="exits" class="scroll"></div><div id="sides" class="scroll"></div><p class="muted">反向退出标签只说明订单因什么条件结束，不足以单独证明“太灵敏”。保护后跳空穿过入场价，也可能产生保护退出亏损。</p><div id="chart"></div><p class="muted">蓝线是当前版本，灰线是原版。同一初始本金，纵轴为账户倍数的对数刻度。</p><div id="years" class="scroll"></div><div id="months" class="scroll"></div></section>
<section class="box"><h2>事先能否判断：方向效率较高的入场更好吗？</h2><div id="groups" class="scroll"></div><p>这里先把原版真实交易按入场前方向效率分组，再查看各组后来结果。它是诊断，不能把已知亏损单从历史中删掉冒充可交易策略。上面的“原版＋过滤”才是重新完整执行过滤规则的结果。</p><div id="forward" class="scroll"></div><p class="muted">顺向比例：入场后第4或16根收盘时，价格是否沿着入场方向移动。数值用当时ATR衡量，缺口内路径或历史末尾不足根数则不计。这些未来数值仅用于解释，策略从不读取；即使最终方向正确，也可能中途先触及止损。</p></section>
<section class="box"><h2>过滤后，收益改善来自哪里？</h2><div id="attribution" class="scroll"></div><p>“共同入场”是原版与过滤版在同一时刻同一方向开仓的交易，退出已核对相同。“不再出现”是原版有、过滤版没有的交易；“新的入场”是过滤版有、原版没有的入场时刻。新入场不等于增加信号：原版可能早已持有同方向仓位，忽略了后面的同方向信号。各组复利仅作拆解，不代表可单独事先挑出该组交易。</p></section>
<section class="box"><h2>结果的适用范围和记录</h2><p id="checks"></p><p>这些年份已经在此前研究中出现过，本轮不是全新未见数据。自动公式也有观察长度、范围和倍数；本轮没有根据结果再改它们。有限规则未解决亏损，只能否定这些具体改法，不能推广成所有趋势策略无效。</p><p>原策略与原模拟器未修改；新功能在独立引擎副本中运行。保存全部96份逐笔、信号、原始穿越、权益、逐年逐月、公式配置与源文件哈希。沿用项目已核对的原生行情，真实缺口保留，未补造K线。<a href="cloud-direct-adaptation-results.json">下载本轮统计与配置JSON</a></p></section></main>
<script>(()=>{const D=__DATA__,P=D.plan,F=D.findings,$=id=>document.getElementById(id),A=['paxg','zec','eth','btc'],V=P.variants,primary=__PRIMARY__,n=(x,d=2)=>x==null?'—':x.toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d}),pct=x=>x==null?'—':(x>=0?'+':'')+n(x)+'%',pc=x=>x==null?'—':`<span class="${x>=0?'pos':'neg'}">${pct(x)}</span>`,table=(h,rs)=>'<table><thead><tr>'+h.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rs.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table>',dt=x=>new Date(x).toISOString().slice(0,10),reason={signal:'反向平仓（不反手）',reversal:'反向平仓并反手',stop_loss:'初始止损',profit_protection:'盈利保护',end_of_backtest:'历史结束平仓'};
$('overview').innerHTML=table(['标的','周期','原版全期','三项自适应全期','原版后两年','三项自适应后两年','自适应盈利完整年份'],A.flatMap(a=>['15m','1h'].map(tf=>{let rs=D.results[a][tf],b=rs.c0r0t0.metrics,x=rs.c1r1t1.metrics;return[a.toUpperCase(),tf==='15m'?'15分钟':'1小时',pc(b.return_pct),pc(x.return_pct),pc(b.later_return_pct),pc(x.later_return_pct),x.positive_full_years+'/5']})));
let repaired=['paxg','zec'].flatMap(a=>['15m','1h'].filter(tf=>F[a][tf].full_adaptive_positive&&F[a][tf].late_adaptive_positive).map(tf=>a.toUpperCase()+' '+tf));$('overviewText').textContent='PAXG、ZEC中，这个预先确定的三项自适应版本在全期和后两年都盈利的组合：'+(repaired.join('、')||'没有')+'。';
$('variant').innerHTML=Object.entries(V).map(([k,v])=>`<option value="${k}">${v.label}</option>`).join('');$('variant').value='c1r1t1';
function draw(){let a=$('asset').value,tf=$('tf').value,k=$('variant').value,rs=D.results[a][tf],x=rs[k],b=rs.c0r0t0,m=x.metrics;
const headings=['方法','全期收益','后两年收益','交易数','赚钱','亏钱','胜率','快速反向亏损','平均一笔赚','平均一笔亏'];const row=id=>{let z=rs[id].metrics;return[V[id].label,pc(z.return_pct),pc(z.later_return_pct),z.trades,z.wins,z.losses,n(z.win_rate)+'%',z.rapid_reversal_losses,pc(z.mean_win_pct),pc(z.mean_loss_pct)]};$('primary').innerHTML=table(headings,primary.map(row));$('all').innerHTML=table(headings,Object.keys(V).map(row));
$('pairs').innerHTML=table(['只改变的因素','全期改善的配对数','后两年改善的配对数'],Object.entries(F[a][tf].pairs).map(([id,z])=>[{center:'自动均线',risk:'波动止损与启动',trailing:'波动跟踪保护'}[id],z.full_improved+'/4',z.later_improved+'/4']));
$('detail').innerHTML=table(['方法','持仓中位数','最长连亏','最大回撤','启动过保护','退出前亏单平均最高浮盈'],[[V[k].label,n(m.median_hours)+'小时',m.max_loss_streak,n(m.max_drawdown_pct)+'%',m.protected_trades+'/'+m.trades,pc(m.losing_mean_peak_pct)]]);
$('exits').innerHTML=table(['退出原因','交易数','赚钱','亏钱','平均单笔收益'],Object.entries(x.exits).map(([id,z])=>[reason[id]||id,z.trades,z.wins,z.losses,pc(z.mean_return_pct)]));$('sides').innerHTML=table(['方向','交易数','赚钱','亏钱','平均一笔赚','平均一笔亏','该方向逐笔复利'],Object.entries(x.sides).map(([id,z])=>[id==='long'?'多单':'空单',z.trades,z.wins,z.losses,pc(z.mean_win_pct),pc(z.mean_loss_pct),pc(z.compound_return_pct)]));
$('years').innerHTML=table(['年份（首尾不足一年）','本版本收益','原版收益','标的价格涨跌'],x.years.map(y=>[y.label,pc(y.return_pct),pc(b.years.find(q=>q.label===y.label).return_pct),pc(y.market_return_pct)]));$('months').innerHTML=table(['本版本最赚钱的3个月','该月收益'],x.concentration.best_months.slice(0,3).map(y=>[y.label,pc(y.return_pct)]));
$('groups').innerHTML=table(['原版入场前特征','交易数','胜率','平均单笔收益','平均一笔赚','平均一笔亏'],Object.entries(b.entry_groups).map(([id,z])=>[id==='er_below_02'?'方向效率低于0.2':'方向效率至少0.2',z.trades,n(z.win_rate)+'%',pc(z.mean_return_pct),pc(z.mean_win_pct),pc(z.mean_loss_pct)]));
$('forward').innerHTML=table(['原版入场前特征','观察到第几根','样本数','顺着入场方向的比例','平均顺向移动/ATR'],Object.entries(F[a][tf].continuation).flatMap(([id,ns])=>Object.entries(ns).map(([n0,z])=>[{all:'全部',er_below_02:'方向效率低于0.2',er_atleast_02:'方向效率至少0.2'}[id],n0,z.samples,n(z.directional_positive_pct)+'%',n(z.mean_directional_atr)])));
let attr=D.entry_attribution[a][tf];$('attribution').innerHTML=table(['交易组','交易数','赚钱','亏钱','平均单笔收益','该组逐笔复利'],[['retained','共同入场'],['removed','过滤后不再出现'],['new_entries','过滤后新的入场']].map(([id,label])=>{let z=attr[id];return[label,z.trades,z.wins,z.losses,pc(z.mean_return_pct),pc(z.compound_return_pct)]}));
let xs=x.curve,ys=b.curve,all=[...xs,...ys],x0=xs[0].timestamp,x1=xs.at(-1).timestamp,lo=Math.min(0,...all.map(e=>Math.log10(e.equity/10000))),hi=Math.max(.1,...all.map(e=>Math.log10(e.equity/10000))),xx=t=>75+(t-x0)/(x1-x0)*1000,yy=v=>245-(Math.log10(v/10000)-lo)/(hi-lo)*220,path=es=>es.map((e,i)=>(i?'L':'M')+xx(e.timestamp).toFixed(2)+' '+yy(e.equity).toFixed(2)).join(' '),grid='';for(let q of [.000001,.00001,.0001,.001,.01,.1,.5,1,2,10,100,1000]){if(Math.log10(q)<lo||Math.log10(q)>hi)continue;let y=yy(q*10000);grid+=`<path d="M75 ${y}H1075" stroke="#e1e7ed"/><text x="66" y="${y+4}" text-anchor="end" font-size="12">${q}倍</text>`}$('chart').innerHTML=`<svg viewBox="0 0 1100 285" role="img" aria-label="自适应与原版账户曲线">${grid}<path d="${path(ys)}" fill="none" stroke="#9da9b9" stroke-width="2"/><path d="${path(xs)}" fill="none" stroke="#397ab6" stroke-width="2.5"/><text x="75" y="276" font-size="12">${dt(x0)}</text><text x="970" y="276" font-size="12">${dt(x1)}</text></svg>`;
$('checks').textContent='96个回测已经完成，8个原版对照与未改动的原引擎逐笔、信号、权益、保护线完全一致。当前数据 '+a.toUpperCase()+' '+tf+' 保留缺失K线 '+x.missing_bars+' 根。验证了无未来数据参与、按真实开盘成交、新保护线下一根生效、波动扩大不放宽保护线，以及入场过滤不妨碍反向平仓。';}
for(let id of ['asset','tf','variant'])$(id).addEventListener('change',draw);draw();})();</script></html>'''


def main():
    d=read(DOCS/'results.json');d['findings']=findings(d);d['entry_attribution']=read(DOCS/'entry-gate-attribution.json')
    freeze(DOCS/'findings.json',d['findings'])
    html=HTML.replace('__DATA__',json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')).replace('__PRIMARY__',json.dumps(PRIMARY))
    (DOCS/'cloud-direct-adaptation.html').write_text(html,encoding='utf-8')
    (PUBLIC/'cloud-direct-adaptation.html').write_text(html,encoding='utf-8')
    (PUBLIC/'cloud-direct-adaptation-results.json').write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    lines=['# 直接自适应：固定规则检验','',f'{d["plan"]["start"]} 至 {d["plan"]["end"]}。后两年从 {d["plan"]["split"]} 开始。没有根据收益选参数。','']
    for a in ASSETS:
        for tf in TFS:
            lines += [f'## {a.upper()} {tf}','','|方法|全期收益|后两年收益|胜率|赚钱|亏钱|快速反向亏损|','|---|---:|---:|---:|---:|---:|---:|']
            for k,v in d['plan']['variants'].items():
                z=d['results'][a][tf][k]['metrics'];lines.append(f'|{v["label"]}|{z["return_pct"]:+.2f}%|{z["later_return_pct"]:+.2f}%|{z["win_rate"]:.2f}%|{z["wins"]}|{z["losses"]}|{z["rapid_reversal_losses"]}|')
            lines.append('')
    (DOCS/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Report ready: http://127.0.0.1:8787/cloud-direct-adaptation.html')


if __name__=='__main__':main()
