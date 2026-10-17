"""Audit and display the locked BTC parameter experiment, without selecting again."""
from datetime import datetime, timezone
from html import escape
from math import isclose
from statistics import median
import json

from scripts.btc_cloud_parameter_study import DOCS, RUNTIME, ROOT, SOURCE, key, neighbors, ranking, choose_validation
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import read, save
from app.services.local_backtest_strategies import digest

LABELS = dict(center_length='中心 EMA 周期',width_length='振幅 EMA 周期',trigger_mult='突破门槛（倍振幅）',
              chase_mult='不追价距离（倍振幅）',activation_pct='浮盈多少启动保护（%）',
              giveback_pct='最高浮盈允许回吐（%）',initial_stop_pct='初始止损（%）')


def percent(x):
    return '—' if x is None else f'{x:+,.2f}%'


def audit(r):
    assert r['status']=='completed'
    p=r['plan'];lock=read(DOCS/'final-lock.json');vp=read(DOCS/'validation-plan.json')
    assert r['selection']==lock
    assert digest((DOCS/'plan.json').read_bytes())==r['provenance']['plan_hash']
    assert digest(SOURCE.read_bytes())==p['source_hash']
    assert digest((ROOT/'app/domain/local_backtest.py').read_bytes())==p['engine_hash']
    assert digest((ROOT/'scripts/btc_cloud_parameter_study.py').read_bytes())==r['provenance']['runner_hash']
    assert choose_validation(r['results'],vp['shortlist'])==lock['selected']
    assert vp['shortlist']==r['training_ranking'][:12]
    manifest=read(DOCS/'trace-manifest.json')['traces']
    expected={f'{k}-{period}.json' for k,v in r['results'].items() for period in v}
    assert expected=={__import__('pathlib').Path(x['path']).name for x in manifest}
    assert len(manifest)==r['simulations']
    old_exact=[]
    annual={}
    for i,item in enumerate(manifest,1):
        path=ROOT/item['path'];raw=path.read_bytes()
        assert digest(raw)==item['sha256']
        t=json.loads(raw)
        assert t['provenance']==r['provenance']
        k=key(t['parameters']);period=path.stem[len(k)+1:]
        assert t['parameters']==r['variants'][k]['parameters']
        assert t['metrics']==r['results'][k][period]
        assert t['period']==p['periods'][period]
        assert len(t['trades'])==t['report']['total_trades']
        assert t['report']['wins']+t['report']['losses']+t['report']['breakeven']==len(t['trades'])
        if period not in ('train','validation'):
            assert k in lock['evaluation_keys'] and t['phase']=='final'
        assert isclose(t['equity'][-1]['equity'],t['report']['final_equity'],abs_tol=1e-7)
        if t['metrics'].get('original_trace_exact'):old_exact.append(period)
        if period=='full':
            points=t['equity'];opening=p['initial_cash'];rows=[]
            for y in range(2018,2026):
                boundary=int(datetime(y+1,9,10,tzinfo=timezone.utc).timestamp()*1000)
                end=points[-1]['equity'] if y==2025 else next(x['equity'] for x in reversed(points) if x['timestamp']<boundary)
                rows.append(dict(year=y,return_pct=(end/opening-1)*100,opening_equity=opening,ending_equity=end))
                opening=end
            annual[k]=rows
        if i%100==0:print(f'Audited {i}/{len(manifest)} saved traces',flush=True)
    assert set(old_exact)=={'full','final',*[f'y{y}' for y in range(2018,2026)]}
    receipt=dict(completed_at=datetime.now(timezone.utc).isoformat(),status='passed',traces_checked=len(manifest),
                 selection_uses_middle_period_only=True,final_only_locked_candidates=True,unchanged_strategy_engine=True,
                 original_baseline_exact_periods=sorted(old_exact),continuous_annual_returns=annual)
    save(DOCS/'verification.json',receipt)
    return receipt


def main():
    r=read(DOCS/'results.json');v=audit(r);p=r['plan'];lock=r['selection'];rs=r['results']
    picked,base=lock['selected'],p['baseline'];leaders=lock['evaluation_keys']
    names={base:'原 ETH 六年第一名',lock['training_leader']:'前四年收益第一名',picked:'中间两年筛选后锁定的候选'}
    # Keep the original label if identical roles happen to share a configuration.
    if picked==base:names[base]='锁定候选（仍是原版）'
    rows=[]
    for k in leaders:
        m=rs[k]
        rows.append([names[k],*[percent(m[x]['return_pct']) for x in ('train','validation','final','full')]])
    winner=rs[picked];baseline=rs[base]
    positive=sum(x for x in r['assessment'].values())
    summary=f'锁定候选在最后两年收益 {percent(winner["final"]["return_pct"])}；原版同期 {percent(baseline["final"]["return_pct"])}。'
    checks=lock['neighborhood'][picked]
    stability=f'中间两年中，候选的 {checks["total"]} 组相近参数有 {checks["positive"]} 组赚钱，中间位置的收益为 {percent(checks["median_return_pct"])}。'
    verdict=('候选通过本轮预设的五项检查，但这不能证明未来盈利或已经排除过拟合。' if positive==5 else
             f'本轮五项检查通过 {positive} 项；请逐项看下方结果，不能把选参数期间的高收益当作已经验证成功。')
    scope='BTC/USDT，15分钟。2018-09-10—2022-09-10：前四年选参数；2022-09-10—2024-09-10：中间两年筛选；2024-09-10—2026-09-10：最后两年验证。'
    accounting='起始资金1万元，每笔投入当时全部资金，盈亏计入下一笔本金，不加杠杆，不计手续费和滑点。三个分段都从空仓开始；完整八年连续持仓，所以分段连乘不一定等于八年结果。'
    caveat='最后两年此前已经看过原版和其他历史策略的表现，并非完全未接触的数据。这次只在前六年选择新参数，锁定之后才计算新候选的最后两年；没有按最后两年成绩换候选。所谓较优，仅限本轮参数范围和筛选方法。'
    counts=f'实际比较 {len(rs)} 组不同参数。初始 {len(p["variants"])} 组组合；前四年实际测试 {len(r["training_ranking"])} 组；中间两年检查 {sum("validation" in x for x in rs.values())} 组候选与相近参数；合计保存 {r["simulations"]} 个期间回测结果。'
    all_checks={'final_profitable':'最后两年累计赚钱','both_final_years_profitable':'最后两年的每一年分别赚钱',
                'final_beats_baseline':'最后两年收益超过原版','validation_neighbors_two_thirds_positive':'中间两年至少三分之二相近参数赚钱',
                'validation_neighbor_median_positive':'中间两年相近参数的中位收益为正'}
    def table(headers, data):
        return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,row))+' |' for row in data])
    params=[[LABELS[f],p['axes'][f],r['variants'][base]['parameters'][f],r['variants'][picked]['parameters'][f]] for f in LABELS]
    markdown=['# BTC 参数选择与后续两年验证',summary,verdict,scope,accounting,caveat,counts,
              table(['版本','前四年选参','中间两年筛选','最后两年验证','完整八年（事后描述）'],rows),
              '## 测试范围和锁定参数',table(['参数','测试值','原版','锁定候选'],params),
              '## 最后两年的实际交易',table(['版本','收益','总笔数','赚钱','亏钱','胜率','最大资金回落'],
                    [[names[k],percent(rs[k]['final']['return_pct']),rs[k]['final']['total_trades'],rs[k]['final']['wins'],rs[k]['final']['losses'],percent(rs[k]['final']['win_rate']),percent(rs[k]['final']['max_drawdown_pct'])] for k in leaders]),
              '## 验证检查',stability,table(['检查','结果'],[[label,'符合' if r['assessment'][k] else '不符合'] for k,label in all_checks.items()]),
              '## 八年分别怎样（连续资金按年分账）',table(['每年9月10日至次年9月10日',*[names[k] for k in leaders]],
                  [[f'{2018+i}—{2019+i}',*[percent(v['continuous_annual_returns'][k][i]['return_pct']) for k in leaders]] for i in range(8)]),
              '## 保留记录',f'计划：plan.json；前四年扩展记录：training-expansion.json；中间两年名单：validation-plan.json；最终参数锁定：final-lock.json。所有逐笔交易、信号、资金曲线和源码副本在 {RUNTIME}。',
              '## 复现', '在项目根目录运行：`venv/Scripts/python.exe -m scripts.btc_cloud_parameter_study run --workers 2`；已完成的结果会保留并复用。之后运行 `venv/Scripts/python.exe -m scripts.report_btc_cloud_parameters` 检查并生成报告。']
    (DOCS/'REPORT.md').write_text('\n\n'.join(markdown)+'\n',encoding='utf-8')
    payload=dict(names=names,selected=picked,baseline=base,keys=leaders,parameters={k:r['variants'][k]['parameters'] for k in leaders},
                 parameter_labels=LABELS,axes=p['axes'],results={k:rs[k] for k in leaders},annual=v['continuous_annual_returns'],
                 checks={label:r['assessment'][k] for k,label in all_checks.items()},
                 shortlist=[dict(key=k,parameters=r['variants'][k]['parameters'],train=rs[k]['train']['return_pct'],validation=rs[k]['validation']['return_pct'],
                                 neighbor=lock['neighborhood'][k]) for k in lock['validation_ranking']],curves={})
    for k in leaders:
        t=read(RUNTIME/'traces'/f'{k}-final.json');daily={}
        for point in t['equity']:daily[point['timestamp']//86400000]=point
        payload['curves'][k]=[t['equity'][0],*daily.values()]
    text=TEMPLATE
    for f,value in dict(SUMMARY=summary,SCOPE=scope,ACCOUNTING=accounting,CAVEAT=caveat,COUNTS=counts,STABILITY=stability,VERDICT=verdict).items():
        text=text.replace('__'+f+'__',escape(value))
    text=text.replace('__DATA__',json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('</','<\\/'))
    (DOCS/'report.html').write_text(text,encoding='utf-8')
    target=ROOT/'docs/verification/eth-cloud-two-year-20260910/btc-parameters.html'
    target.write_text(text,encoding='utf-8')
    done=ROOT/'docs/verification/eth-cloud-robustness-20260910/versions/033-btc-parameters-completed'
    if not done.exists():
        snapshot('033-btc-parameters-completed',[SOURCE,ROOT/'scripts/btc_cloud_parameter_study.py',ROOT/'scripts/report_btc_cloud_parameters.py',
                 ROOT/'test/test_btc_cloud_parameter_study.py',*[DOCS/x for x in ('plan.json','training-expansion.json','validation-plan.json','final-lock.json','results.json','verification.json','test-results.json','trace-manifest.json','REPORT.md','report.html')]])
    print(summary,flush=True)


TEMPLATE='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BTC 参数测试 · 最后两年验证</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4f6f9;color:#25334a;font:15px/1.8 "Microsoft YaHei",sans-serif}main{max-width:1420px;padding:30px 24px 60px;margin:auto}h1{font-size:30px;line-height:1.4}h2{font-size:22px;margin-top:0}section{padding:24px;background:#fff;border:1px solid #e1e7ee;border-radius:12px;margin:24px 0}.lead{font-size:20px;font-weight:600}.muted{color:#67778a;font-size:13px}.note{padding:16px;background:#fff4dc;border-radius:8px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;margin:18px 0}th,td{padding:11px 12px;border-bottom:1px solid #e7edf2;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{background:#f5f8fb}.pos{color:#087352}.neg{color:#b63942}a{color:#285eae}select,button{font:inherit;padding:7px 12px;border:1px solid #c3ceda;border-radius:6px;background:#fff}svg{width:100%;height:330px}pre{white-space:pre-wrap;background:#f6f8fb;padding:16px}small{display:block;color:#708097} @media(max-width:750px){main{padding:18px 12px}section{padding:16px}h1{font-size:25px}}</style>
<main><header><p class="muted">原 ETH 六年第一名 · 同一策略换参数 · 项目数据与回测引擎</p><h1>在 BTC 上选参数，再看之后两年</h1><p class="lead">__SUMMARY__</p><p>__VERDICT__</p><p>__SCOPE__</p><p class="muted">__ACCOUNTING__</p><p class="note">__CAVEAT__</p><p>__COUNTS__</p></header>
<section><h2>原版和提前锁定的候选</h2><div id="comparison"></div><p>完整八年包含选参数用过的年份，只作事后描述。决定是否有效，先看最后两年这列；没有在最后两年重新选第一名。</p></section>
<section><h2>究竟改了哪些参数</h2><div id="parameters"></div><p>中心线平滑每根K线最高价与最低价的平均值；振幅取最高价减最低价，再用EMA平滑。这版没有计算ATR。做多向上突破，做空向下突破；下一根实际K线开盘成交。反向信号、初始止损、盈利后的回吐保护都能退出。</p></section>
<section><h2>最后两年的交易情况</h2><div id="trades"></div><label>查看资金变化 <select id="curveKey"></select></label><div id="curve"></div><p class="muted">曲线从1万元开始，展示每日最后一条账户权益；包括未平仓浮盈亏。</p></section>
<section><h2>相近参数是否也有效</h2><p>__STABILITY__</p><div id="checks"></div><p>这些检查不改变收益排名，也不改变已经锁定的候选。若结果不理想，本轮就停下，不根据最后两年继续调参。</p></section>
<section><h2>八年里每一年怎样</h2><div id="annual"></div><p class="muted">每行均为9月10日至次年9月10日；从连续八年资金曲线分账，跨年持仓保留。因此，与每年单独从空仓重跑的结果可能略有不同。</p></section>
<section><h2>前四年留下的12组候选</h2><p>只由前四年的收益选出这12组，再按中间两年的收益筛选。旁边的14组相近参数只用于检查是否脆弱，不能加入候选名单。</p><div id="shortlist"></div></section>
<section><h2>记录</h2><p>初始计划、每次候选名单、最终锁定参数、每组逐笔结果和源码副本均已保存。原策略没有覆盖。</p><p class="muted">D:/Code/Heimdall/docs/verification/btc-cloud-parameters-20260911<br>D:/Code/Heimdall/.heimdall_runtime/btc-cloud-parameters-20260911</p><button id="download">保存锁定候选参数</button><p><a href="cross-asset.html">查看此前 ETH 与 BTC 的历史版本对比</a></p></section></main>
<script>const D=__DATA__;const $=x=>document.getElementById(x),esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');const fmt=x=>x==null?'—':(x>=0?'+':'')+x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+'%';const pc=x=>'<span class="'+(x>=0?'pos':'neg')+'">'+fmt(x)+'</span>';const table=(h,rs)=>'<div class="scroll"><table><thead><tr>'+h.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rs.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
$('comparison').innerHTML=table(['版本','前四年选参数','中间两年筛选','最后两年验证','完整八年'],D.keys.map(k=>[D.names[k],...['train','validation','final','full'].map(p=>pc(D.results[k][p].return_pct))]));
$('parameters').innerHTML=table(['参数','本轮测试值','原版','锁定候选'],Object.entries(D.parameter_labels).map(([f,n])=>[n,D.axes[f].join(' / '),D.parameters[D.baseline][f],D.parameters[D.selected][f]]));
$('trades').innerHTML=table(['版本','收益','总笔数','赚钱','亏钱','胜率','最大资金回落'],D.keys.map(k=>{const m=D.results[k].final;return [D.names[k],pc(m.return_pct),m.total_trades,m.wins,m.losses,fmt(m.win_rate),fmt(m.max_drawdown_pct)]}));
$('checks').innerHTML=table(['检查','结果'],Object.entries(D.checks).map(([n,b])=>[n,b?'符合':'不符合']));
$('annual').innerHTML=table(['每年9月10日开始',...D.keys.map(k=>D.names[k])],Array.from({length:8},(_,i)=>[(2018+i)+'—'+(2019+i),...D.keys.map(k=>pc(D.annual[k][i].return_pct))]));
$('shortlist').innerHTML=table(['完整参数编号','前四年收益','中间两年收益','相近参数盈利数'],D.shortlist.map(x=>[esc(x.key)+(x.key===D.selected?' <b>已锁定</b>':''),pc(x.train),pc(x.validation),x.neighbor.positive+' / '+x.neighbor.total]));
$('curveKey').innerHTML=D.keys.map(k=>'<option value="'+k+'">'+D.names[k]+'</option>').join('');$('curveKey').value=D.selected;
function draw(){const vs=D.curves[$('curveKey').value],W=1120,H=300,L=80,R=25,T=25,B=35;let lo=Math.min(...vs.map(x=>x.equity)),hi=Math.max(...vs.map(x=>x.equity));if(hi===lo)hi=lo+1;const x=t=>L+(t-vs[0].timestamp)/(vs.at(-1).timestamp-vs[0].timestamp)*(W-L-R),y=v=>T+(hi-v)/(hi-lo)*(H-T-B);let s='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="最后两年的账户资金曲线">';for(let i=0;i<5;i++){let n=lo+(hi-lo)*i/4,yy=y(n);s+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+'" stroke="#e5eaf1"/><text x="'+(L-8)+'" y="'+(yy+5)+'" text-anchor="end" font-size="12" fill="#67778a">'+Math.round(n).toLocaleString()+'</text>'}s+='<polyline fill="none" stroke="#316bc1" stroke-width="2" points="'+vs.map(v=>x(v.timestamp)+','+y(v.equity)).join(' ')+'"/><text x="'+L+'" y="'+(H-4)+'" font-size="12">2024-09-10</text><text x="'+(W-R)+'" y="'+(H-4)+'" text-anchor="end" font-size="12">2026-09-10</text></svg>';$('curve').innerHTML=s}draw();$('curveKey').onchange=draw;
$('download').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({strategy:'trend_cloud_parameters_v4',parameters:D.parameters[D.selected]},null,2)],{type:'application/json'}));a.download='btc-locked-parameters.json';a.click();URL.revokeObjectURL(a.href)};
</script></html>'''


if __name__=='__main__':main()
