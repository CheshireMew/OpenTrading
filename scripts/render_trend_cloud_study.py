"""Render the completed project study as a self-contained comparison page."""
import json
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[1]/'docs/verification/eth-cloud-two-year-20260910'

HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETH 两年策略比较 · OpenTrading</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#1a2934;font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1400px;margin:auto;padding:36px}h1{font-size:30px;margin:0}h2{font-size:20px;margin:0 0 14px}p{margin:10px 0}.muted{color:#63727d}.tag{display:inline-block;background:#e2ede7;color:#256046;padding:3px 10px;border-radius:5px;margin-bottom:12px}.panel{background:white;border:1px solid #dce3e7;border-radius:12px;padding:24px;margin:22px 0}.controls{display:flex;gap:16px;align-items:center;flex-wrap:wrap}select,button{padding:8px 12px;background:white;border:1px solid #aab8c0;border-radius:6px;font:inherit}#choices{display:flex;flex-wrap:wrap;gap:9px 16px;margin:20px 0}#choices label{font-size:13px;cursor:pointer}input{accent-color:#176b59}svg{width:100%;display:block}table{border-collapse:collapse;white-space:nowrap;width:100%;font-size:13px}th,td{text-align:right;padding:10px 12px;border-bottom:1px solid #e5eaed}th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:#fff;z-index:1}thead th{background:#f5f7f9;cursor:pointer}td a{color:#176b59}.scroll{overflow:auto}.positive{color:#167051}.negative{color:#b73b49}.note{border-left:3px solid #3c7c67;padding-left:16px}#verdict{font-size:17px}#months td{min-width:76px}footer{font-size:12px;color:#667782;margin:24px 0}@media(max-width:700px){main{padding:18px}.panel{padding:14px}h1{font-size:24px}}
</style><main><span class="tag">OpenTrading · 项目行情与模拟引擎</span><h1>ETH 15 分钟，两年策略比较</h1>
<p class="muted">2024-09-10 至 2026-09-10（UTC，结束不含） · 70,080 根 K 线 · 初始 10,000 · 仓位 100% · 不加杠杆</p>
<p>按用户要求，所有比较均不计算手续费和滑点。信号在收盘确定，下一根开盘成交；反向信号换仓，同向信号不加仓。</p>
<p><a href="diagnostics.html" style="color:#176b59">查看进一步分析：ATR 是否有效、亏损原因，以及九种改法的实际结果 →</a></p>
<section class="panel"><h2>收益与稳定性分别看</h2><div id="verdict"></div><p class="muted">“前一年选出”按收益／最大回撤排名，要求盈利、利润因子大于 1，且至少 30 笔交易。选出后保持规则不变，再看验证段。</p></section>
<section class="panel"><div class="controls"><h2>资金曲线</h2><label>区间 <select id="period"><option value="full">完整两年</option><option value="selection">前一年：筛选</option><option value="validation">后续历史：验证</option><option value="recent">最近 18 天：补充观察</option><option value="long_only">完整两年：仅做多</option></select></label><button id="all">显示全部</button><button id="none">清空选择</button></div><p id="periodnote" class="muted"></p><div id="choices"></div><svg id="chart" viewBox="0 0 1200 390" role="img" aria-label="所选策略的每日收盘资金曲线"></svg><p class="muted">曲线按每日收盘展示；表中最大回撤根据完整 15 分钟收盘权益计算。</p></section>
<section class="panel"><h2>同一区间的完整比较</h2><p class="muted">点击列名排序。点击策略名称可打开项目中的完整两年交易记录。</p><div class="scroll"><table id="table"></table></div></section>
<section class="panel"><h2>每月收益</h2><p class="muted">区间首尾可能是不完整月份。每月从上月末权益继续计算；各独立验证区间从 10,000 重新开始。</p><div class="scroll"><table id="months"></table></div></section>
<section class="panel note"><h2>这次比较说明什么</h2><p>这些结果比较的是明确的交易规则，不能只用云带的外观判断有效性。原 Pine 本身是信号指标；反向平仓和仓位设置是本次统一的回测约定。</p><p>参数曾参考 2026 年 8 月截图。验证段排除了 8 月 18—23 日，但历史拆分仍不是严格的前向实验，也不能证明已找到原作者公式。</p><p>项目使用 Binance ETH/USDT 现货价格进行多空模拟。仅做多对照可用来检查结果对做空交易的依赖。短期补充区间只有 18 天，单独不足以判断长期效果。</p></section><footer id="provenance"></footer></main>
<script>const D=__DATA__;
const R=D.results,keys=Object.keys(R),colors=['#11795c','#a34f18','#356cb0','#b05176','#956626','#735ac3','#2c8b8b','#648b32','#bb4247','#42788b','#9160a5','#976447','#172f48','#9aa6ad'];
let selected=new Set([D.full_return_ranking[0],D.selection_winner,'ema31_atr','buy_hold'].filter(Boolean)),period='full',sort='return_pct',descending=true;
const f=(n,d=2)=>n==null?'—':Number(n).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const cls=n=>n>0?'positive':n<0?'negative':'';
const fullbest=R[D.full_return_ranking[0]],winner=R[D.selection_winner];
document.getElementById('verdict').innerHTML=`<p>完整两年收益最高：<strong>${fullbest.name}</strong>，收益 ${f(fullbest.full.return_pct)}%，最大回撤 ${f(fullbest.full.max_drawdown_pct)}%。</p>`+(winner?`<p>只看前一年选出的方案：<strong>${winner.name}</strong>；后续验证段收益 ${f(winner.validation.return_pct)}%，最大回撤 ${f(winner.validation.max_drawdown_pct)}%。</p>`:'<p>前一年没有符合预设筛选条件的方案。</p>');
document.getElementById('provenance').textContent=`数据哈希：${D.data_hash}　·　引擎：OpenTrading 2　·　14 组正式运行；按无成本口径计算。`;
document.getElementById('choices').innerHTML=keys.map((k,i)=>`<label style="color:${colors[i]}"><input type="checkbox" value="${k}" ${selected.has(k)?'checked':''}> ${R[k].name}</label>`).join('');
const notes={full:'包含截图所在时段，用于整体表现描述。',selection:'2024-09-10 至 2025-09-10。用于确定候选，参数不按收益调整。',validation:'2025-09-10 至 2026-08-18。未参与截图形状拟合的后续历史区间。',recent:'2026-08-23 至 2026-09-10。样本只有 18 天。',long_only:'完整两年；做空信号仅平掉多仓，不开空。'};
function draw(){
 document.getElementById('periodnote').textContent=notes[period];
 let active=keys.filter(k=>selected.has(k)),svg=document.getElementById('chart');
 if(!active.length){svg.innerHTML='<text x="600" y="190" text-anchor="middle" fill="#657680">选择要比较的策略</text>';return}
 let arrays=active.map(k=>R[k][period].daily_equity),values=arrays.flatMap(a=>a.map(x=>x.equity)),lo=Math.min(10000,...values),hi=Math.max(10000,...values);if(hi===lo){lo-=100;hi+=100}
 let pad=(hi-lo)*.06;lo-=pad;hi+=pad;const x=i=>80+i/Math.max(arrays[0].length-1,1)*1090,y=v=>335-(v-lo)/(hi-lo)*300;
 let markup='';for(let i=0;i<5;i++){let value=lo+(hi-lo)*i/4,Y=y(value);markup+=`<line x1="80" y1="${Y}" x2="1170" y2="${Y}" stroke="#e7ecef"/><text x="70" y="${Y+4}" text-anchor="end" fill="#64747f" font-size="12">${f(value,0)}</text>`}
 markup+=`<line x1="80" y1="${y(10000)}" x2="1170" y2="${y(10000)}" stroke="#91a2ad" stroke-dasharray="5 5"/>`;
 arrays.forEach((a,j)=>{markup+=`<path d="${a.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(p.equity).toFixed(1)).join(' ')}" stroke="${colors[keys.indexOf(active[j])]}" fill="none" stroke-width="2"><title>${R[active[j]].name}</title></path>`});
 [0,Math.floor((arrays[0].length-1)/2),arrays[0].length-1].forEach(i=>markup+=`<text x="${x(i)}" y="369" text-anchor="${i===0?'start':i===arrays[0].length-1?'end':'middle'}" fill="#64747f" font-size="12">${arrays[0][i].date}</text>`);svg.innerHTML=markup;
}
function table(){const columns=[['name','策略'],['return_pct','收益 %'],['max_drawdown_pct','最大回撤 %'],['return_to_drawdown','收益／回撤'],['total_trades','交易次数'],['win_rate','胜率 %'],['profit_factor','利润因子'],['positive_months','盈利月份']];
 let ordered=[...keys].sort((a,b)=>{let av=sort==='name'?R[a].name:R[a][period][sort],bv=sort==='name'?R[b].name:R[b][period][sort];return (typeof av==='string'?av.localeCompare(bv):(av??-Infinity)-(bv??-Infinity))*(descending?-1:1)});
 document.getElementById('table').innerHTML='<thead><tr>'+columns.map(([k,n])=>`<th data-sort="${k}">${n}${sort===k?(descending?' ↓':' ↑'):''}</th>`).join('')+'</tr></thead><tbody>'+ordered.map(k=>{let r=R[k][period];return `<tr><td><a href="http://127.0.0.1:4173/research/backtests?run=${R[k].run_id}" target="_blank">${R[k].name}</a>${k===D.selection_winner?' · 前一年选出':''}</td><td class="${cls(r.return_pct)}">${f(r.return_pct)}</td><td>${f(r.max_drawdown_pct)}</td><td>${f(r.return_to_drawdown)}</td><td>${f(r.total_trades,0)}</td><td>${f(r.win_rate)}</td><td>${f(r.profit_factor)}</td><td>${r.positive_months} / ${r.month_count}</td></tr>`}).join('')+'</tbody>';
 document.querySelectorAll('[data-sort]').forEach(th=>th.onclick=()=>{let k=th.dataset.sort;descending=k===sort?!descending:true;sort=k;table()});
 let months=R[keys[0]][period].monthly_returns.map(m=>m.month);document.getElementById('months').innerHTML='<thead><tr><th>策略</th>'+months.map(m=>`<th>${m}</th>`).join('')+'</tr></thead><tbody>'+ordered.map(k=>'<tr><td>'+R[k].name+'</td>'+R[k][period].monthly_returns.map(m=>`<td class="${cls(m.return_pct)}" style="background:${m.return_pct>0?'#e5f2eb':m.return_pct<0?'#f9e9e9':'white'}">${f(m.return_pct,1)}%</td>`).join('')+'</tr>').join('')+'</tbody>';
}
document.querySelectorAll('#choices input').forEach(el=>el.onchange=()=>{el.checked?selected.add(el.value):selected.delete(el.value);draw()});
document.getElementById('period').onchange=e=>{period=e.target.value;draw();table()};
document.getElementById('all').onclick=()=>{selected=new Set(keys);document.querySelectorAll('#choices input').forEach(e=>e.checked=true);draw()};
document.getElementById('none').onclick=()=>{selected.clear();document.querySelectorAll('#choices input').forEach(e=>e.checked=false);draw()};draw();table();
</script></html>'''


if __name__ == '__main__':
    data = json.loads((DIRECTORY/'results.json').read_text(encoding='utf-8'))
    result = HTML.replace('__DATA__', json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c'))
    (DIRECTORY/'comparison.html').write_text(result, encoding='utf-8')
    print(DIRECTORY/'comparison.html')
