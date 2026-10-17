"""Explain the frozen parameter/ATR/opposite-confirmation experiment in Chinese."""
from html import escape
from bisect import bisect_right
from pathlib import Path
from statistics import median
import json

from scripts.paxg_zec_repair_study import DOCS, RUNTIME, ROOT
from scripts.profit_protection_study import read, save

PUBLIC=ROOT/'docs/verification/eth-cloud-two-year-20260910'


def pct(x):return '—' if x is None else f'{x:+,.2f}%'
def num(x):return '—' if x is None else f'{x:,.2f}'
def table(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'---|'*len(head)]+['| '+' | '.join(map(str,r))+' |' for r in rows])


def params(p):
    stop=f"{p['atr_stop_mult']:g}倍ATR14" if p.get('atr_stop_mult') else f"{p['initial_stop_pct']:g}%"
    return (f"中心EMA{p['center_length']}，振幅EMA{p['width_length']}，突破门槛{p['trigger_mult']:g}倍振幅，"
            f"超过{p['chase_mult']:g}倍振幅不追；浮盈{p['activation_pct']:g}%开始保护，允许回吐最高浮盈的{p['giveback_pct']:g}%；"
            f"初始止损{stop}，反向信号{p.get('reverse_confirm_bars',1)}根收盘确认")


def mode_name(mode,p):
    stop=f"{p['atr_stop_mult']:g}倍ATR止损" if p.get('atr_stop_mult') else f"固定{p['initial_stop_pct']:g}%止损"
    return stop+('＋反向等2根确认' if p.get('reverse_confirm_bars',1)==2 else '＋原反向规则')


def named_keys(r,a):
    s=r['selection']['assets'][a];b=r['plan']['assets'][a]['baseline']
    return [('原ETH参数',b),('只调入场参数',s['parameter_selected']['entry']),
            ('只调退出参数',s['parameter_selected']['exit']),('入场退出一起调',s['parameter_selected']['joint']),
            ('前面年份亏得最少的对照版本',s['overall_selected'])]


def build_payload(r,d):
    out={}
    for a,info in r['plan']['assets'].items():
        sel=r['selection']['assets'][a];keys=sel['evaluation_keys'];extra={}
        times=[x[0] for x in read(ROOT/info['data']['path'])]
        for k in keys:
            extra[k]={}
            for period in ('full','final','y2024','y2025'):
                t=read(RUNTIME/'traces'/a/f'{k}-{period}.json')
                signals={times[bisect_right(times,s['timestamp'])]:s for s in t['signals']
                         if s.get('status')=='executed' and s['action'] in ('long','short')}
                atr_stops=[]
                for tr in t['trades']:
                    sg=signals.get(tr['entry_time'])
                    assert sg and sg['action']==tr['side']
                    if sg and sg.get('stop_loss_distance'):
                        atr_stops.append(100*sg['stop_loss_distance']/tr['entry_price'])
                extra[k][period]=dict(protection_active=sum(bool(x.get('protection_active')) for x in t['trades']),
                    median_initial_atr_stop_pct=median(atr_stops) if atr_stops else None,
                    side={s:dict(trades=sum(x['side']==s for x in t['trades']),
                                 wins=sum(x['side']==s and x['profit']>0 for x in t['trades']),
                                 losses=sum(x['side']==s and x['profit']<0 for x in t['trades'])) for s in ('long','short')})
        out[a]=dict(selection=sel,periods=info['periods'],baseline=info['baseline'],
                    named=named_keys(r,a),variants={k:r['variants'][a][k] for k in keys},
                    metrics={k:r['results'][a][k] for k in keys},details=d[a],extra=extra)
    return out


def markdown(r,d):
    text=['# PAXG、ZEC：改参数、ATR止损和反向确认有没有用',
          '所有数字都来自项目原行情和模拟器。PAXG测试六年，ZEC测试七年，均为15分钟。每笔当时全部本金复投，不加杠杆，不计手续费和滑点；收益均为累计收益。',
          '每个币先固定64组参数：中心55/144、振幅周期31、突破门槛0.4/1.2、最远距离2/3、回吐35%/50%。PAXG保护启动0.3%/2%、固定止损0.3%/1%；ZEC保护启动1%/2%、固定止损1%/3%。',
          '只用最早三年（PAXG）/四年（ZEC）挑出每类前三名，再用2023-09-10至2024-09-10选定参数。之后在原参数、选定参数上各比较固定止损/2ATR/3ATR与反向1根/2根确认，共六种规则。仍只按这一个筛选年确定最终版本，然后检查2024-09-10至2026-09-10。',
          '最后两年没有参加本轮排名选择，但整个会话此前已研究过这些年份，且本轮范围依据前面的诊断制定。因此不能称作全新、从未看过的验证数据，也不能证明已经排除过拟合。分段从空仓重新开始，全历史为连续回测。',
          '## 明确结论',
          '本轮没有找到能在完整历史扭亏的版本。PAXG更像这套频繁突破交易规则不适合当前数据中的价格路径；ZEC对参数确实敏感，部分改法后两年能赚钱，但早年损失依旧严重。不能据此认定只是几个参数没调好，也不能把有限范围的失败推广成所有技术策略无效。',
          'ATR止损没有表现出普遍优势。保持原ETH其他参数不变，PAXG后两年从亏45.19%变成2ATR亏49.80%、3ATR亏48.36%，并未改善。ZEC从亏46.06%变成2ATR亏13.95%、3ATR赚11.86%，但3ATR七年仍亏99.95%。',
          '反向等两根确认有帮助，但没有消除根本问题。保持原参数，PAXG后两年反向亏损从2554笔降至1463笔，总亏损从2579笔降至1515笔，收益从亏45.19%改善到亏8.05%；平均一次亏损却从0.179%扩大到0.238%。ZEC反向亏损从881笔降到281笔，但初始止损亏损从1832笔增加到2030笔，后两年仍亏36.29%。',
          '提高胜率也可能更亏。ZEC沿用本轮一起调整入场退出后的参数，固定1%止损后两年赚11.36%，改3ATR后亏22.64%；胜率反而从47.43%升至65.21%。原因是平均一笔盈利仍约1.10%，平均一笔亏损却从0.97%扩大到2.05%，多赢的次数没补上少数更大的亏损。',
          '只改ZEC入场参数（中心144、突破1.2倍、超过2倍不追，其他沿用原版），后两年赚229.76%，但完整七年仍亏91.30%。这是参数会影响结果的证据，不是长期有效的证据。',
          '在预先规定的邻近参数检查中，ZEC也有七年接近回本的一组：EMA144、振幅周期31、突破1.2倍、最远3倍、浮盈1%保护、回吐35%、固定1%止损、原反向规则。七年亏0.75%，后两年赚142.86%；但早期训练段亏58.48%、筛选年亏1.50%，没有入选按训练选出的前三名，所以不能事后更换提前选定的版本。2020年亏55.64%、2023年亏46.02%，仍不满足长期稳定盈利。',
          '筛选年里，所有进入最终比较的版本都亏损。因此下表所谓选定版本，只是前面年份亏得最少的对照，不是通过盈利标准的可用策略。这轮到此停止扩大搜索，保留全部版本。']
    for a in ('paxg','zec'):
        s=r['selection']['assets'][a];b=r['plan']['assets'][a]['baseline'];chosen=s['overall_selected']
        text += [f'## {a.upper()}：参数调整与最终版本',
            table(['版本','全历史收益','后两年收益','后两年交易数','赚钱','亏钱','胜率'],
                [[name,pct(r['results'][a][k]['full']['return_pct']),pct((m:=r['results'][a][k]['final'])['return_pct']),m['trades'],m['wins'],m['losses'],num(m['win_rate'])+'%'] for name,k in named_keys(r,a)]),
            '以上各版本的具体参数：\n\n'+'\n\n'.join(f'**{n}**：{params(r["variants"][a][k]["parameters"])}。' for n,k in named_keys(r,a))]
        for anchor,modes in s['rules'].items():
            text += [f'### {"沿用原ETH参数" if anchor=="original" else "沿用本轮选定参数"}，逐项比较退出规则',
                table(['方法','全历史收益','后两年收益','后两年胜率','反向亏损数','初始止损亏损数','全部亏损数'],
                    [[mode_name(mode,r['variants'][a][k]['parameters']),pct(r['results'][a][k]['full']['return_pct']),pct((m:=r['results'][a][k]['final'])['return_pct']),num(m['win_rate'])+'%',
                      sum(x['losses'] for reason,x in m['exit_reasons'].items() if reason in ('signal','reversal')),
                      sum(x['losses'] for reason,x in m['exit_reasons'].items() if reason=='stop_loss'),m['losses']] for mode,k in modes.items()])]
        nei=d[a]['neighbor_final']
        text += ['### 按前面年份选定的最终版本：每年表现',
                 table(['年份（首尾为部分年）','策略收益','币价涨跌'],[[y['label'],pct(y['return_pct']),pct(y['market_return_pct'])] for y in d[a]['periods'][chosen]['years']]),
                 f'只改选定固定参数中的一个数，得到六个邻近版本；后两年其中{nei["positive"]}/6盈利，中间水平收益{pct(nei["median_return_pct"])}。这些仅作敏感性检查，不重新选冠军。']
    text += ['## ATR和反向确认究竟怎么执行',
        'ATR14衡量最近14根K线的价格波动，包含相邻收盘之间的跳变。2ATR止损就是：若入场前ATR为10美元，多单在实际买入价下方20美元止损，空单在卖出价上方20美元止损。这个距离在信号收盘时确定，成交后固定，不会因为行情变坏而越放越远。这里没有把通道改成ATR通道，也没有用ATR做持续移动止损。',
        '反向2根确认：持有多单时，第一次收盘跌破做空门槛先等待；紧接着第二根仍收在当时的做空门槛下方，下一根开盘才退出。空单相反。价格回到通道内就取消等待；数据缺口不算连续。空仓时第一次入场保持原规则。等待期间，初始止损和利润保护一直有效。',
        '确认后距离不过远就反手，否则只平仓。增加确认可能避开短暂假突破，也会在真正反转时晚走；不能把减少反向亏损次数直接当成解决了亏损。',
        '利润保护仍按原设定执行：达到启动浮盈后，允许回吐最高浮盈的指定比例；已抬高的保护线不放松。单根K线只能知道开高低收，模拟器沿用原有保守执行顺序，新保护线不会利用尚未知道的价格提前成交。',
        f'共完成{r["simulations"]}次分段模拟。每组参数、训练名单、筛选结果、最终锁定名单、逐笔交易和代码版本均保留。旧版四个完整/后两年对照的报告、交易、信号、权益与此前逐项完全一致。']
    return '\n\n'.join(text)+'\n'


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PAXG / ZEC · 参数与退出规则验证</title>
<style>:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#243047;background:#f4f6f9}*{box-sizing:border-box}body{margin:0}main{max-width:1480px;margin:auto;padding:32px 28px 80px}h1{font-size:30px;margin:12px 0}h2{font-size:22px;margin:0 0 16px}h3{font-size:17px}p{line-height:1.8;max-width:1150px}.tag{color:#637591;font-size:13px;letter-spacing:.05em}.muted,small{color:#67768a}a{color:#266acc}nav{display:flex;gap:20px;margin-bottom:26px}.box{background:white;border:1px solid #dde4ee;border-radius:12px;padding:24px;margin:22px 0}.controls{display:flex;gap:24px;flex-wrap:wrap;align-items:center;padding:18px 0}select{font:inherit;border:1px solid #cbd6e4;padding:9px 16px;border-radius:7px;background:white}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;white-space:nowrap}th,td{padding:13px 15px;border-bottom:1px solid #e7ecf3;text-align:right}th{background:#f8fafc;color:#576880;font-weight:500}td:first-child,th:first-child{text-align:left}tr.chosen{background:#edf4ff}.pos{color:#158069}.neg{color:#bf4052}.large{font-size:23px;font-weight:650}.callout{border-left:4px solid #5d84d5;padding:2px 18px;background:#f5f8ff}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.params{white-space:normal;line-height:1.8;min-width:360px}details{margin-top:18px}summary{cursor:pointer;color:#365c94}svg{width:100%;max-height:310px;display:block}.legend{display:flex;gap:25px;font-size:13px}code{font-size:12px}@media(max-width:850px){main{padding:20px 12px}.grid{grid-template-columns:1fr}.box{padding:18px}h1{font-size:25px}}</style>
<main><nav><a href="transfer-diagnosis.html">← 上一轮亏损诊断</a><a href="alt-transfer.html">四币原始测试</a></nav><div class="tag">保留旧版 · 同一项目数据和模拟器 · 不计手续费与滑点</div><h1>PAXG、ZEC：改参数能救回来吗？</h1><p id="lead"></p><div class="callout"><p>看两件事：改完有没有真的赚钱，以及前面年份选好的规则，到后面年份还能不能赚钱。最后两年在此前研究中已经被看过，这次只是排除在本轮选择之外，不能称为全新的独立验证。</p></div>
<section class="box"><h2>结论：有些改法减少亏损，但没有验证出长期可用的版本</h2><p><b>ATR不是普遍更好。</b>保持原ETH其他参数，PAXG后两年原本亏45.19%，改2倍ATR亏49.80%，改3倍ATR亏48.36%。ZEC原本亏46.06%，改3倍ATR赚11.86%，但七年仍亏99.95%。</p><p><b>反向等两根确认有帮助，也有代价。</b>PAXG原参数后两年反向亏损2554笔降至1463笔，收益从亏45.19%改善到亏8.05%，但平均一次亏损从0.179%扩大至0.238%。ZEC反向亏损881笔降至281笔，初始止损亏损却从1832笔增加到2030笔，仍亏36.29%。</p><p><b>胜率高，也可能更亏。</b>ZEC在本轮一起调过入场退出的参数上，把1%止损换成3ATR：胜率从47.43%提高到65.21%，收益却从赚11.36%变成亏22.64%。平均赢一笔仍约1.10%，平均亏一笔从0.97%扩大到2.05%。</p><p>ZEC也有一个邻近版本接近回本：EMA144、突破1.2倍、最远3倍、浮盈1%保护、回吐35%、固定1%止损，七年亏0.75%、后两年赚142.86%。但它2020年亏55.64%、2023年亏46.02%，此前训练阶段亏58.48%。这说明参数影响大，却还没有证明长期稳定可用。本轮停止扩大搜索，保留所有版本。</p></section>
<div class="controls"><label>交易对 <select id="asset"><option value="paxg">PAXGUSDT</option><option value="zec">ZECUSDT</option></select></label><label>下方逐项诊断期间 <select id="period"><option value="final">后两年：2024.09—2026.09</option><option value="full">完整历史</option><option value="y2024">2024.09—2025.09</option><option value="y2025">2025.09—2026.09</option></select></label></div>
<section class="box"><h2>先看答案：只改参数，还是要改规则？</h2><p id="answer"></p><div id="overview" class="scroll"></div><p class="muted">这五行都按前面年份选定；最后一行还比较了 ATR 止损、反向两根确认。筛选年所有参选版本都亏损，最后一行只是亏得最少的对照，并不是合格策略。相同参数可能重复出现，是因为不同测试最后选到了同一组。</p><details><summary>展开五个版本的完整参数</summary><div id="parameters"></div></details></section>
<section class="box"><h2>ATR 止损、反向确认：每一步究竟改变了什么</h2><label>入场和利润保护参数 <select id="anchor"><option value="original">保持之前 ETH 第一名参数</option><option value="tuned">保持入场退出一起调整的参数</option></select></label><p id="anchorparams"></p><div id="methods" class="scroll"></div><p class="muted">“反向亏损”包括反手和平仓信号退出；初始止损、利润保护另算。少掉的反向亏损有可能转移到其他退出方式，需要对照总亏损数、平均亏损和总收益。</p><h3>六种规则的收益对比</h3><div id="bars"></div><h3>这些方法亏在什么地方</h3><div id="exits" class="scroll"></div><details><summary>后两年：找到相同入场时刻、同方向的交易，逐笔比较退出结果</summary><p class="muted">只能配对入场相同的交易；延迟确认会改变后续入场，因此配对结果只是解释，完整收益仍以上表为准。改本金后不比较现金金额，只比较每笔涨跌百分比。</p><div id="pairs" class="scroll"></div></details></section>
<div class="grid"><section class="box"><h2>最终选定版本：哪些年赚、哪些年亏</h2><div id="years" class="scroll"></div><p class="muted">连续全历史回测，按年末账户权益计算，包含未平仓浮盈亏。首尾是部分年份。</p></section><section class="box"><h2>只改一个参数，还行不行？</h2><p id="neighbors"></p><div id="neighborlist" class="scroll"></div><p class="muted">六个邻近版本只作检查，不看后两年结果重新挑赢家。这里检查的是选定的固定止损参数；不代表所有 ATR 组合也通过敏感性验证。</p><h3>利润是否只靠极少数赢家</h3><p id="concentration"></p></section></div>
<section class="box"><h2>两项新规则，用人话说</h2><p><b>ATR 止损：</b>让止损距离跟随入场前的波动大小。假设 ATR 是10美元，2倍 ATR 就把多单初始止损放在买入价下方20美元。入场时算好这个距离，此后不往亏损方向放宽。空单反过来。这次比较2倍、3倍 ATR，ATR周期固定14；它只替换初始止损，通道还是原来的均线通道。</p><p><b>反向信号等两根确认：</b>持有多单时，第一次收盘跌破做空门槛先不退出；下一根15分钟K线仍收在当时门槛下方，才在再下一根开盘退出。中途回到通道内就取消等待。空单相反。确认后如果没追得太远就反手，太远只平仓；止损和利润保护始终有效，空仓入场规则不变。</p><p>这会过滤一些“一闪而过”的反向信号，也会让真正的反转晚退出。能否得益，以测试结果为准。利润保护继续沿用原参数，不是用 ATR 持续移动止损。</p></section>
<section class="box"><h2>这轮怎么测、保留了什么</h2><p>每币64组固定参数，拆成只改入场、只改退出、两边一起改。PAXG用最早三年、ZEC用最早四年初选，每类留前三名和原版；下一年（2023.09—2024.09）选定。再对原参数和选定参数各比较六种退出规则，同样只按这个筛选年选择。保存选择结果后才计算最后两年。没有根据最后两年继续扩大搜索。</p><p>范围：中心EMA55/144，振幅周期31，突破门槛0.4/1.2倍振幅，最远2/3倍振幅，利润回吐35%/50%。PAXG保护启动0.3%/2%、固定止损0.3%/1%；ZEC保护启动1%/2%、固定止损1%/3%。ATR14止损2/3倍，反向确认1/2根。</p><p id="provenance"></p><p>所有收益都是每笔当时全部本金复投的累计收益，各分段从空仓重新开始；不加杠杆，不计手续费和滑点。行情沿用项目保存的15分钟数据，原有缺口没有补成虚构K线。亏损接近100%的版本仍完整展示，不作为可用策略推荐。</p></section></main>
<script>const DATA=__DATA__;const $=id=>document.getElementById(id),p=x=>x==null?'—':(x>=0?'+':'')+x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+'%',n=x=>x==null?'—':x.toLocaleString('zh-CN',{maximumFractionDigits:2}),pc=x=>`<span class="${x>=0?'pos':'neg'}">${p(x)}</span>`;
function tbl(head,rows){return '<table><thead><tr>'+head.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rows.map(x=>'<tr>'+x.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function prm(v){let s=v.atr_stop_mult?v.atr_stop_mult+'倍ATR14':v.initial_stop_pct+'%';return `EMA${v.center_length}，振幅周期${v.width_length}，突破${v.trigger_mult}倍，最远${v.chase_mult}倍；浮盈${v.activation_pct}%开始保护，回吐${v.giveback_pct}%；初始止损${s}，反向${v.reverse_confirm_bars||1}根确认`}
function mn(v){return(v.atr_stop_mult?v.atr_stop_mult+'倍ATR止损':'固定'+v.initial_stop_pct+'%止损')+' / '+((v.reverse_confirm_bars||1)==2?'等2根反向确认':'原反向规则')}
function losses(m,reasons){return Object.entries(m.exit_reasons).filter(([k,v])=>reasons.includes(k)).reduce((s,[k,v])=>s+v.losses,0)}
function draw(){const a=DATA[$('asset').value],period=$('period').value,sel=a.selection,chosen=sel.overall_selected,base=a.metrics[a.baseline],best=a.metrics[chosen],joint=a.metrics[sel.parameter_selected.joint];
$('answer').innerHTML=`原参数完整历史 ${pc(base.full.return_pct)}；只调整原策略参数后 ${pc(joint.full.return_pct)}。加入本轮规定的退出规则、按前面年份选好的版本，完整历史 ${pc(best.full.return_pct)}，后两年 ${pc(best.final.return_pct)}。<b>${best.full.return_pct>0&&best.final.return_pct>0?'两个期间都赚钱，但还要看逐年和邻近参数。':best.final.return_pct>0?'后两年赚钱，完整历史仍未扭亏，不能说长期问题已经解决。':'没有找到同时在完整历史和后两年都赚钱的选定版本。'}</b>`;
$('overview').innerHTML=tbl(['版本','全历史收益','后两年收益','后两年笔数','赚钱','亏钱','胜率'],a.named.map(([name,k])=>{let m=a.metrics[k].final;return[name,pc(a.metrics[k].full.return_pct),pc(m.return_pct),n(m.trades),n(m.wins),n(m.losses),n(m.win_rate)+'%']}));
$('parameters').innerHTML=a.named.map(([name,k])=>`<p><b>${name}：</b>${prm(a.variants[k].parameters)}。</p>`).join('');
const anchor=$('anchor').value,modes=sel.rules[anchor],entries=Object.entries(modes),mkeys=entries.map(([mode,k])=>k),anchorKey=modes.atr0_confirm1;
$('anchorparams').textContent=prm(a.variants[anchorKey].parameters)+'。';
$('methods').innerHTML=tbl(['方法','当前期间收益','笔数','胜率','赚钱','亏钱','平均赚一笔','平均亏一笔','典型持仓小时'],entries.map(([mode,k])=>{let m=a.metrics[k][period];return[mn(a.variants[k].parameters),pc(m.return_pct),n(m.trades),n(m.win_rate)+'%',n(m.wins),n(m.losses),pc(m.mean_win_pct),pc(m.mean_loss_pct),n(m.median_hours)]}));
$('exits').innerHTML=tbl(['方法','反向亏损','初始止损亏损','保护退出却亏损','其他亏损','总亏损','利润保护启动笔数'],entries.map(([mode,k])=>{let m=a.metrics[k][period],rev=losses(m,['signal','reversal']),st=losses(m,['stop_loss']),pr=losses(m,['profit_protection']);return[mn(a.variants[k].parameters),n(rev),n(st),n(pr),n(m.losses-rev-st-pr),n(m.losses),n(a.extra[k][period].protection_active)]}));
let limit=Math.max(...mkeys.map(k=>Math.abs(a.metrics[k][period].return_pct)),1);$('bars').innerHTML='<svg viewBox="0 0 1100 270" role="img" aria-label="六种规则收益率对比">'+entries.map(([mode,k],i)=>{let m=a.metrics[k][period],w=280*Math.abs(m.return_pct)/limit,y=15+i*42;return `<text x="0" y="${y+18}" font-size="14" fill="#41536e">${mn(a.variants[k].parameters)}</text><rect x="${m.return_pct<0?640-w:640}" y="${y}" width="${w}" height="26" rx="3" fill="${m.return_pct<0?'#d27981':'#51a997'}"/><text x="930" y="${y+18}" font-size="14">${p(m.return_pct)}</text>`}).join('')+'<line x1="640" x2="640" y1="5" y2="265" stroke="#a3b0c4"/></svg>';
$('pairs').innerHTML=tbl(['方法','相同入场笔数','原本亏损笔数','其中转盈','其中亏损减轻','原本盈利笔数','其中盈利减少'],entries.map(([mode,k])=>{let q=a.details.pairs[anchor][mode];return[mn(a.variants[k].parameters),q.matched,q.matched_baseline_losses,q.losses_turned_into_wins,q.losses_reduced,q.matched_baseline_winners,q.winners_reduced]}));
$('years').innerHTML=tbl(['年份','策略收益','币价涨跌'],a.details.periods[chosen].years.map(y=>[y.label,pc(y.return_pct),pc(y.market_return_pct)]));let nei=a.details.neighbor_final;
$('neighbors').innerHTML=`只改一个参数的六个邻近版本，后两年 <b>${nei.positive}/6</b> 盈利，中间水平收益 ${pc(nei.median_return_pct)}。`;
const jp=a.variants[sel.parameter_selected.joint].parameters,labels={center_length:'中心周期',trigger_mult:'突破门槛',chase_mult:'最远距离',activation_pct:'保护启动%',giveback_pct:'回吐%',initial_stop_pct:'止损%'};
$('neighborlist').innerHTML=tbl(['只改哪一个数','全历史收益','后两年收益'],sel.neighbors.map(k=>{let v=a.variants[k].parameters,f=Object.keys(labels).find(f=>v[f]!==jp[f]);return[labels[f]+': '+jp[f]+' → '+v[f],pc(a.metrics[k].full.return_pct),pc(a.metrics[k].final.return_pct)]}));
let st=a.details.periods[chosen].stress;$('concentration').innerHTML=`把完整历史最赚钱的10笔收益算作零，其余交易不变，收益为 ${pc(st.trade_checks[0].return_if_zero_pct)}；把最赚钱三个月的收益算作零，为 ${pc(st.best_three_months_zeroed_pct)}。这是事后算术检查，不是能事先执行的过滤条件。`;
}
for(const id of ['asset','period','anchor'])$(id).addEventListener('change',draw);$('lead').innerHTML=__LEAD__;$('provenance').textContent=__PROVENANCE__;draw();</script></html>'''


def main():
    r=read(DOCS/'results.json');d=read(DOCS/'details.json');v=read(DOCS/'verification.json')
    assert r['status']=='completed' and v['status']=='passed' and v['baseline_legacy_exact']
    payload=build_payload(r,d);save(DOCS/'report-data.json',payload)
    report=markdown(r,d);(DOCS/'REPORT.md').write_text(report,encoding='utf-8')
    lead='356次分段回测已完成。PAXG没有找到扭亏的方法；ZEC有些改法后两年赚钱，但完整七年仍未验证出盈利版本。下面逐项说明参数、ATR和反向确认到底有没有帮助。'
    provenance=f"共{r['simulations']}次分段模拟，{v['traces_checked']}份逐笔记录核对通过。旧版的4份全历史/后两年报告、交易、信号和权益逐项完全一致。新旧代码、参数、选择名单与结果均已保存。"
    html=HTML.replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('</','<\\/')).replace('__LEAD__',json.dumps(lead,ensure_ascii=False)).replace('__PROVENANCE__',json.dumps(provenance,ensure_ascii=False))
    (DOCS/'paxg-zec-repair.html').write_text(html,encoding='utf-8')
    (PUBLIC/'paxg-zec-repair.html').write_text(html,encoding='utf-8')
    print('Saved report: http://127.0.0.1:8787/paxg-zec-repair.html')


if __name__=='__main__':main()
