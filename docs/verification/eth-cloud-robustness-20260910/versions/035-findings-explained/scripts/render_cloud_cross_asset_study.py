"""Plain-language comparison of the frozen cross-asset study, ranked by return."""
from html import escape
import json
from scripts.cloud_cross_asset_study import DOCS,RUNTIME,ROOT
from scripts.profit_protection_study import read
from scripts.cloud_study_findings import write_findings,html_block


def fmt(v):
    return f'{v:+,.2f}%'


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(map(str,r))+' |' for r in rows])


def rules(v):
    p,b,k=v['parameters'],v['batch'],v['old_key']
    if v['benchmark']:
        return '第一根正式收盘发买入信号，下一根开盘买入，一直拿到期末。' if k=='buy_hold' else '不交易，现金不计利息。'
    if b=='initial':
        if k.startswith('original_'):
            return '价格在云带内、位于中心线下方，RSI低于40且成交量超过20根平均量的1.8倍时做多；做空方向相反、RSI高于60。两次信号间隔超过10根。回测按反向信号退出，原Pine的止盈止损只是标签。'
        return '收盘价向上穿过上门槛做多，向下穿过下门槛做空；下一根开盘成交。出现反向信号时退出并换向，同向信号不加仓。没有额外止盈止损。各候选保留原均线、宽度和门槛。'
    if b=='experiments':
        detail=[]
        if p['entry_filter']=='distance2': detail.append('离中心超过两倍宽度就不追')
        if p['confirmation']==2: detail.append('突破后下一根仍收在门槛外才确认进场及反向退出')
        for f,n in [('stop_atr','固定止损'),('target_atr','固定止盈'),('trail_atr','跟随止损')]:
            if p[f]: detail.append(f'{n}距离按信号时{p[f]:g}倍ATR折算为开仓价百分比')
        if p['width']=='fixed': detail.append(f'宽度固定为中心价格的{p["fixed_pct"]:.5f}%，沿用旧ETH研究保存值，不在BTC重算')
        return '沿用EMA31突破进场，下一开盘成交；反向信号可以退出。'+('；'.join(detail)+'。' if detail else '仅改价格输入或波动周期，其他规则保持原样。')
    if b=='parameters' or b=='joint':
        exit_rule=f'浮盈达到{p["activation_pct"]:g}%后保护，最高浮盈回吐{p["giveback_pct"]:g}%可退出' if p['activation_pct'] else '关闭利润保护'
        stop=f'另设开仓价{p["initial_stop_pct"]:g}%的固定止损' if p['initial_stop_pct'] else '没有初始固定止损'
        return f'中心线EMA{p["center_length"]}，每根高低差用EMA{p["width_length"]}平滑得到宽度；向上/下突破中心线±{p["trigger_mult"]:g}倍宽度做多/空，距离超过{p["chase_mult"]:g}倍宽度不追。{exit_rule}；{stop}。反向信号也能退出。'
    if b=='robustness':
        desc={'none':'不额外过滤进场','slow_trend':'做多还要高于慢EMA96，做空低于它','efficiency':'过去32根的净移动至少占来回移动总路程的20%，才允许入场',
              'spacing':'新入场信号至少间隔4根，减少密集进出','alternate':'利润保护退出后不再连续开同方向的单'}[p['entry_method']]
        protect=f'浮盈{p["activation_pct"]:g}%启动、允许回吐{p["giveback_pct"]:g}%' if p['activation_pct'] else '不设利润保护'
        return f'EMA31高低价通道，突破0.8倍宽度，离中心超过2倍宽度不追。{desc}。{protect}，反向信号可退出。'
    base='沿用EMA31、门槛0.8倍宽度、不追超过2倍宽度、过去32根方向效率至少20%的基础版。'
    extra={
        'manual':{'confirm2':'突破后连续两根收在通道外才进场。','retest8':'突破后最多等8根，回踩通道边界并重新收回到外侧才进场。'},
        'entry':{'few_crossings':'过去16根穿越中心线不能超过两次。','no_spike':'突破K线的振幅不能超过先前常见振幅的1.5倍。','structure_break':'还要突破之前8根的最高价或最低价。','strong_close':'突破K线还要顺向涨/跌，收在有利一端的四分之一内。'},
        'context':{'support':'支撑/阻力既要触碰位置合适，也要前方空间足够。','support_room':'只检查前方支撑/阻力是否至少留出两倍宽度的空间。','support_touch':'只检查是否靠近并触碰身后的支撑/阻力。','momentum':'已收盘1小时RSI达到55以上且上升才做多，45以下且下降才做空。','trend':'已收盘4小时价格和SMA20方向都支持，才进场。','all_three':'同时满足支撑阻力、1小时动量、4小时趋势。'}
    }[b][k]
    return base+extra+'仍采用浮盈2%启动、允许回吐50%的保护，原反向信号也可退出。'


def main():
    r=read(DOCS/'results.json')
    assert r['status']=='completed'
    plan=r['plan'];vs=plan['variants'];rs=r['results']
    question_findings=write_findings(r)
    receipt=read(DOCS/'project-runs.json') if (DOCS/'project-runs.json').exists() else {'runs':{}}
    runs={k:v for k,v in receipt['runs'].items() if v['verified']}
    eth,btc=r['rankings']['eth']['full'][0],r['rankings']['btc']['full'][0]
    same=r['rankings']['btc']['same_six'][0]
    headline=f'ETH六年最高累计收益：{fmt(rs["eth"][eth]["full"]["return_pct"])}；BTC八年最高累计收益：{fmt(rs["btc"][btc]["full"]["return_pct"])}。'
    early=['initial__ema31_atr','initial__ema31_range','initial__high_low_ema','initial__wma41_atr','initial__sma28_atr','initial__dual_ema','initial__ema31_cross']
    keyrows=list(dict.fromkeys(r['rankings']['eth']['full'][:5]+r['rankings']['btc']['full'][:5]+early))
    positive={a:sum(rs[a][k]['full']['return_pct']>0 for k,v in vs.items() if not v['benchmark']) for a in ['eth','btc']}
    every={a:sum(all(rs[a][k][p]['return_pct']>0 for p in plan['periods'][a] if p.startswith('y')) for k,v in vs.items() if not v['benchmark']) for a in ['eth','btc']}
    interpretation=(f'48个策略版本中，ETH六年累计盈利{positive["eth"]}个，BTC八年累计盈利{positive["btc"]}个；'
                    f'每个年度都盈利的分别有{every["eth"]}个、{every["btc"]}个。'
                    f'ETH第一名原参数直接用于BTC八年，收益为{fmt(rs["btc"][eth]["full"]["return_pct"])}，排名第{r["rankings"]["btc"]["full"].index(eth)+1}。')
    findings=(f'按你要求只看收益，BTC八年第一仍低于同期买入持有的{fmt(rs["btc"]["initial__buy_hold"]["full"]["return_pct"])}；'
              f'这组第一名最近两年在BTC的收益为{fmt(rs["btc"][btc]["recent"]["return_pct"])}。'
              '因此，部分优化在ETH上有很高的历史收益，但本轮还不能确认它能稳定适用于其他市场。')
    atr_note=(f'最早EMA31候选中，只把ATR换成平滑高低差，ETH六年从{fmt(rs["eth"]["initial__ema31_atr"]["full"]["return_pct"])}'
              f'变为{fmt(rs["eth"]["initial__ema31_range"]["full"]["return_pct"])}，BTC八年从{fmt(rs["btc"]["initial__ema31_atr"]["full"]["return_pct"])}'
              f'变为{fmt(rs["btc"]["initial__ema31_range"]["full"]["return_pct"])}。没有看到ATR明显提高收益。'
              '另外，原脚本ATR1.5版在BTC相同六年里排名第一，但拉到八年又变为亏损；缩短或改变起止年份，确实可能改变结论。')
    scope='ETH/USDT：2020年9月10日至2026年9月10日，六年；BTC/USDT：2018年9月10日至2026年9月10日，八年。都使用15分钟K线，另列BTC与ETH相同的六年。按收益率排序，胜率不参与排名。'
    accounting='初始资金10,000，每笔投入当时全部资金，盈亏计入下一笔本金，不加杠杆，不计手续费和滑点。收益是整个区间的累计收益，不是年收益。收盘确认信号，下一条实际K线开盘成交。'
    limits='BTC测试前已固定全部版本，本轮没有根据BTC结果调参。ETH已反复研究，BTC与ETH也属于相关市场；跨币种和更长年份的结果能帮助判断，但不能证明没有过拟合或以后必然盈利。这里的第一名仅指这48个已选版本。'
    gap='；'.join(f'{a.upper()}缺{d["missing_bars"]}根、{len(d["gaps"])}段' for a,d in r['data'].items())+'。经项目接口补查后保留实际空档，没有补造K线；空档内部触发情况无法判断。详情中展示把直接跨空档交易的收益暂按零计算的敏感性结果，它不是另一套可执行策略。'
    annual='年度均指9月10日至次年9月10日；各年从空仓开始、年末平仓。完整六年/八年是连续回测，因此分年收益连乘不一定等于完整周期收益。'
    def row(k):
        return [vs[k]['name'],fmt(rs['eth'][k]['full']['return_pct']),fmt(rs['btc'][k]['same_six']['return_pct']),fmt(rs['btc'][k]['full']['return_pct'])]
    def ranking(asset,period):
        return table(['排名','策略','收益率','胜率','赚钱次数','亏钱次数','持平次数','总次数'],
             [[i+1,vs[k]['name'],fmt(rs[asset][k][period]['return_pct']),f'{rs[asset][k][period]["win_rate"]:.2f}%' if rs[asset][k][period]['win_rate'] is not None else '无交易',
               rs[asset][k][period]['wins'],rs[asset][k][period]['losses'],rs[asset][k][period]['breakeven'],rs[asset][k][period]['total_trades']]
              for i,k in enumerate(r['rankings'][asset][period])])
    paragraphs=['# ETH六年与BTC八年策略复测',headline,scope,accounting,interpretation,findings,atr_note,limits,
                '## 早期候选及两边收益靠前的版本',table(['策略','ETH六年','BTC相同六年','BTC八年'],[row(k) for k in keyrows]),
                '## ETH六年完整排名',ranking('eth','full'),'## BTC相同六年完整排名',ranking('btc','same_six'),
                '## BTC八年完整排名',ranking('btc','full'),'## 原始数据空档',gap,'## 每个版本的交易规则']
    paragraphs.extend(f'### {v["name"]}\n\n{rules(v)}\n\n配置编号：`{k}`；来源：`{v["source_record"]}`。' for k,v in vs.items())
    paragraphs+=['## 记录与恢复',annual,f'历史280条研究记录索引：history-inventory.json。选中的48个策略版本及2项参照：plan.json。旧版本未改动。',
                 f'全部950份逐笔记录、信号和资金曲线：{RUNTIME}/traces。各版本配置：{RUNTIME}/configs。源码副本：{RUNTIME}/sources。',
                 '项目正式K线与实际成交：\n'+ '\n'.join(f'- [{vs[v["version"]]["name"]} · {v["asset"].upper()}](http://127.0.0.1:4173/research/backtests?run={v["run_id"]}&view=chart&theme=light&tz=8)' for v in runs.values())]
    paragraphs[1:1]=['逐项结论已补全：见 [早期12个策略的8个问题与结论](FINDINGS.md)，包括通道是否有用、ATR是否有额外帮助，以及各版本对照的限制。']
    (DOCS/'REPORT.md').write_text('\n\n'.join(paragraphs)+'\n',encoding='utf-8')
    payload=dict(variants=vs,results=rs,rankings=r['rankings'],periods=plan['periods'],pairs=r['paired_changes'],
                 rules={k:rules(v) for k,v in vs.items()},runs=runs,data=r['data'],early=[k for k in vs if k.startswith('initial__') and not vs[k]['benchmark']],
                 highlights=keyrows,eth=eth,btc=btc)
    text=TEMPLATE
    for name,val in [('HEADLINE',headline),('SCOPE',scope),('ACCOUNTING',accounting),('LIMITS',limits),('INTERPRETATION',interpretation),('FINDINGS',findings),('ATR_NOTE',atr_note),('GAPS',gap),('ANNUAL',annual)]:
        text=text.replace('__'+name+'__',escape(val))
    text=text.replace('</header>','</header>'+html_block(question_findings),1)
    text=text.replace('__DATA__',json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('</','<\\/'))
    (DOCS/'report.html').write_text(text,encoding='utf-8')
    (ROOT/'docs/verification/eth-cloud-two-year-20260910/cross-asset.html').write_text(text,encoding='utf-8')
    print(headline)


TEMPLATE='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ETH六年 · BTC八年策略复测</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f9;color:#25334a;font:15px/1.8 "Microsoft YaHei",sans-serif}main{max-width:1540px;padding:32px 26px 70px;margin:auto}h1{font-size:32px;line-height:1.35}h2{font-size:22px;margin-top:0}.lead{font-size:20px;font-weight:600;color:#176953}.muted{color:#697a90;font-size:13px}section{padding:25px;background:white;border:1px solid #e1e7ee;border-radius:12px;margin:24px 0}select,input,button{font:inherit;border:1px solid #bdcbd9;background:white;border-radius:6px;padding:7px 10px;max-width:100%}button{cursor:pointer}button:hover{background:#edf4f9}.toolbar{display:flex;flex-wrap:wrap;gap:18px;align-items:center}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums;margin:18px 0}td,th{padding:11px 12px;text-align:right;border-bottom:1px solid #e7edf2;white-space:nowrap}td:first-child,th:first-child{text-align:left}th{background:#f5f8fb}.pos{color:#087352}.neg{color:#b63942}a{color:#285eae}small{display:block;color:#708097;font-size:11px}pre{white-space:pre-wrap;font-size:12px;overflow-wrap:anywhere;background:#f6f8fb;padding:14px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0}.card{border:1px solid #e0e8ef;border-radius:9px;padding:15px}.card b{display:block;font-size:23px}.note{padding:14px;background:#fff5df;border-radius:8px}svg{width:100%;height:280px;background:#fbfcfe;border:1px solid #e5ebf1;border-radius:8px}details{margin-top:20px}@media(max-width:750px){main{padding:18px 12px}.cards{grid-template-columns:repeat(2,1fr)}section{padding:16px}h1{font-size:26px}}
</style><main><header><div class="muted">48个策略版本 · 2项参照 · 950个期间结果 · 参数已固定</div><h1>把早期候选和后期优化放在一起比较</h1><p class="lead">__HEADLINE__</p><p>__SCOPE__</p><p class="muted">__ACCOUNTING__</p><p>__INTERPRETATION__</p><p>__FINDINGS__</p><p>__ATR_NOTE__</p><p class="note">__LIMITS__</p></header>
<section><h2>先看最早的候选，包括ATR</h2><p>这些是最初那12个版本。截图像不像与长期赚不赚钱分开判断。三列各自代表完整累计收益，比较策略时看同一列。</p><div id="early"></div></section>
<section><h2>全部策略，按收益率排名</h2><div class="toolbar"><label>行情 <select id="asset"><option value="eth">ETH</option><option value="btc">BTC</option></select></label><label>期间 <select id="period"></select></label><label>名称筛选 <input id="search" placeholder="例如 ATR、EMA、支撑"></label></div><p class="muted">胜率、赚钱和亏钱次数用于描述结果，不参与排序。持有和现金另列在表末。</p><div id="ranking"></div></section>
<section id="inspection"><h2>检查某个版本</h2><label>策略 <select id="variant"></select></label><p id="rules"></p><div class="cards" id="cards"></div><div id="annual"></div><p class="muted">__ANNUAL__</p><div id="chartLinks" class="toolbar"></div><p id="gapDetail" class="muted"></p><details><summary>完整参数和原版本位置</summary><pre id="config"></pre><button id="download">保存这个版本配置</button></details></section>
<section><h2>只改一个条件，收益变了多少</h2><p>每一行都与它当时实际使用的基础版本比较。正数表示该改动提高累计收益，负数表示降低，单位为百分点；数值跟随上方行情和期间选择。</p><div id="pairs"></div></section>
<section><h2>数据与记录</h2><p>__GAPS__</p><p>已回看会话起点，并整理9批共280条研究记录，其中包含重复基准和同一策略换参数。本轮选48个策略版本与2项参照；未选的版本仍保留在历史索引，不会被覆盖。</p><p class="muted">本轮记录：D:/Code/Heimdall/docs/verification/cloud-cross-asset-20260911<br>逐笔结果与源码副本：D:/Code/Heimdall/.heimdall_runtime/cloud-cross-asset-20260911</p><p><a href="joint-six-year.html">上一轮128组联合参数</a> · <a href="comparison.html">最早两年对照</a></p></section></main>
<script>
const D=__DATA__;const $=id=>document.getElementById(id), esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const fmt=x=>x==null?'—':(x>=0?'+':'')+x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+'%';
const pc=x=>`<span class="${x>=0?'pos':'neg'}">${fmt(x)}</span>`;
const tab=(h,rows)=>'<div class="scroll"><table><thead><tr>'+h.map(v=>'<th>'+v+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
const label=(a,p)=>p==='full'?(a==='eth'?'六年累计（2020/9—2026/9）':'八年累计（2018/9—2026/9）'):p==='same_six'?'相同六年（2020/9—2026/9）':p==='recent'?'近两年（2024/9—2026/9）':p.slice(1)+'/9—'+(Number(p.slice(1))+1)+'/9';
const name=k=>esc(D.variants[k].name);
$('early').innerHTML=tab(['早期版本','ETH六年','BTC相同六年','BTC八年'],D.early.map(k=>[name(k),pc(D.results.eth[k].full.return_pct),pc(D.results.btc[k].same_six.return_pct),pc(D.results.btc[k].full.return_pct)]));
$('variant').innerHTML=Object.keys(D.variants).map(k=>`<option value="${k}">${esc(D.variants[k].name)}</option>`).join('');$('variant').value=D.eth;
function periods(){const a=$('asset').value;$('period').innerHTML=['full',...(a==='btc'?['same_six']:[]),'recent',...Object.keys(D.periods[a]).filter(k=>k.startsWith('y'))].map(p=>`<option value="${p}">${label(a,p)}</option>`).join('');update()}
function update(){const a=$('asset').value,p=$('period').value,s=$('search').value.trim().toLowerCase(),rank=D.rankings[a][p];let keys=rank.filter(k=>(D.variants[k].name+' '+k).toLowerCase().includes(s));keys.push(...Object.keys(D.variants).filter(k=>D.variants[k].benchmark));$('ranking').innerHTML=tab(['排名 / 策略',label(a,p)+'收益','胜率','赚钱','亏钱','持平','总次数','详情'],keys.map(k=>{let m=D.results[a][k][p];return [(D.variants[k].benchmark?'参照':rank.indexOf(k)+1)+'. '+name(k),pc(m.return_pct),m.win_rate==null?'无交易':m.win_rate.toFixed(2)+'%',m.wins,m.losses,m.breakeven,m.total_trades,`<button data-key="${k}">查看</button>`]}));$('ranking').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('variant').value=b.dataset.key;inspect();$('inspection').scrollIntoView({behavior:'smooth'})});$('pairs').innerHTML=tab(['改动','基础版收益','改后收益','变化（百分点）'],D.pairs[a][p].map(v=>[esc(/[a-z]/i.test(v.name.replaceAll('ATR','').replaceAll('EMA',''))?D.variants[v.changed].name:v.name),pc(D.results[a][v.baseline][p].return_pct),pc(D.results[a][v.changed][p].return_pct),pc(v.return_change_pct_points).replace('%','')]));inspect()}
function inspect(){const k=$('variant').value,a=$('asset').value,p=$('period').value,v=D.variants[k],m=D.results[a][k][p];$('rules').textContent=D.rules[k];$('cards').innerHTML=[['所选期间收益',fmt(m.return_pct)],['胜率',m.win_rate==null?'无交易':m.win_rate.toFixed(2)+'%'],['赚钱 / 亏钱',m.wins+' / '+m.losses],['总交易次数',m.total_trades]].map(([l,n])=>`<div class="card">${l}<b>${n}</b></div>`).join('');$('annual').innerHTML=tab(['行情',...Array.from({length:8},(_,i)=>(2018+i)+'/9—'+(2019+i)+'/9')],['eth','btc'].map(a=>[a.toUpperCase(),...Array.from({length:8},(_,i)=>D.results[a][k]['y'+(2018+i)]?pc(D.results[a][k]['y'+(2018+i)].return_pct):'—')]));$('config').textContent=JSON.stringify(v,null,2);$('chartLinks').innerHTML=['eth','btc'].map(asset=>{let x=D.runs[asset+'__'+k];return x?`<a href="http://127.0.0.1:4173/research/backtests?run=${x.run_id}&view=chart&theme=light&tz=8" target="_blank" rel="noopener">${asset.toUpperCase()}完整周期：K线、指标与实际成交 ↗</a>`:''}).join(' ');if(!$('chartLinks').innerHTML.trim())$('chartLinks').textContent='本版本的逐笔记录已保存；图表重点展示两边收益第一及最早ATR、高低价通道候选。';let g=m.gap_sensitivity;$('gapDetail').textContent=`这个期间有${g.affected_trades}笔交易直接跨过数据空档。若仅在账面上把这些交易收益按零计算，累计收益为${fmt(g.return_with_affected_set_to_zero_pct)}；此数值不是另一套可执行策略。`}
$('download').onclick=()=>{let k=$('variant').value;let blob=new Blob([JSON.stringify(D.variants[k],null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=k+'.json';a.click();URL.revokeObjectURL(url)};
$('asset').onchange=periods;$('period').onchange=update;$('search').oninput=update;$('variant').onchange=inspect;periods();
</script></html>'''


if __name__=='__main__':
    main()
