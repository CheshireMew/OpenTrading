"""Audit and explain four-asset transfer results; keep transfer and hindsight distinct."""
import json
from datetime import datetime, timezone
from math import isclose
from html import escape

from scripts.alt_cloud_parameter_study import DOCS, RUNTIME, ROOT, SOURCE, choose
from scripts.profit_protection_study import read, save
from scripts.cloud_strategy_versions import snapshot
from app.services.local_backtest_strategies import digest

LABELS = {'center_length':'中心均线周期','width_length':'振幅平均周期','trigger_mult':'突破门槛（倍振幅）',
          'chase_mult':'最远入场距离（倍振幅）','activation_pct':'浮盈多少启动保护（%）',
          'giveback_pct':'允许利润回吐（%）','initial_stop_pct':'初始止损（%）'}


def pct(v):
    return f'{v:+,.2f}%'


def params(p):
    return f'EMA{p["center_length"]} / 振幅{p["width_length"]} / 门槛{p["trigger_mult"]:g} / 最远{p["chase_mult"]:g} / 保护启动{p["activation_pct"]:g}% / 回吐{p["giveback_pct"]:g}% / 止损{p["initial_stop_pct"]:g}%'


def table(head, rows):
    return '\n'.join(['| '+' | '.join(head)+' |','| '+' | '.join(['---']*len(head))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])


def audit(result):
    plan=result['plan'];prov=result['provenance'];manifest=[]
    assert result['status']=='completed' and result['completed_results']==768
    assert digest((DOCS/'plan.json').read_bytes())==prov['plan_hash']
    assert digest((DOCS/'data.json').read_bytes())==prov['data_manifest_hash']
    assert digest(SOURCE.read_bytes())==plan['source_hash']
    assert digest((ROOT/'app/domain/local_backtest.py').read_bytes())==plan['engine_hash']
    assert digest((ROOT/'scripts/alt_cloud_parameter_study.py').read_bytes())==prov['runner_hash']
    for a,rows in result['results'].items():
        assert len(rows)==64
        selected=result['selection']['assets'][a]['selected']
        assert selected==choose(rows,plan['variants'])[0]
        for k,periods in rows.items():
            assert set(periods)=={'train','full','final'}
            for period,m in periods.items():
                path=RUNTIME/'traces'/a/f'{k}-{period}.json';raw=path.read_bytes();trace=json.loads(raw)
                assert trace['metrics']==m and trace['provenance']==prov
                assert trace['parameters']==plan['variants'][k]['parameters']
                assert trace['period']==plan['assets'][a]['periods'][period]
                assert len(trace['trades'])==m['total_trades']
                assert m['total_trades']==m['wins']+m['losses']+m['breakeven']
                assert isclose(trace['equity'][-1]['equity'],m['final_equity'],rel_tol=1e-10,abs_tol=1e-7)
                assert isclose(sum(t['profit'] for t in trace['trades']),m['profit'],rel_tol=1e-8,abs_tol=1e-6)
                manifest.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(raw),asset=a,variant=k,period=period))
        print(f'Audited {a}: 192 exact saved traces',flush=True)
    receipt=dict(checked_at=datetime.now(timezone.utc).isoformat(),status='passed',traces_checked=len(manifest),
        source_and_engine_unchanged=True,only_64_configurations_per_asset=True,pre2024_selection_reconciled=True,
        all_trades_counts_and_equity_reconciled=True,manifest=manifest)
    save(DOCS/'verification.json',receipt)
    return receipt


def main():
    result=read(DOCS/'results.json');audit(result)
    plan=result['plan'];rows=result['results'];assets=list(plan['assets']);transfer=plan['transfer']
    passes={name:sum(rows[a][k]['full']['return_pct']>0 and rows[a][k]['final']['return_pct']>0 for a in assets) for name,k in transfer.items()}
    verdict='；'.join(f'{name}有 {passes[name]}/4 个标的同时在全历史和最近两年赚钱' for name in transfer)+'。'
    if max(passes.values())<4:
        verdict+='因此，这轮没有验证出一组在这四个标的上都满足上述条件的原参数。'
    else:
        verdict+='这提供了跨标的支持，但仍是历史、零成本条件下的结果，不证明以后稳定盈利。'
    best={a:result['rankings'][a]['full'][0] for a in assets}
    selected={a:result['selection']['assets'][a]['selected'] for a in assets}
    transfer_rows=[]
    for a in assets:
        for name,k in transfer.items():
            f,v=rows[a][k]['full'],rows[a][k]['final']
            transfer_rows.append([a.upper(),name,pct(f['return_pct']),pct(v['return_pct']),f['total_trades'],f['wins'],f['losses']])
    text=['# PAXG、ZEC、SOL、BNB：先验证原参数能否直接使用',verdict,
        '主测试：此前 ETH 六年第一名、BTC 较好版本的参数完全不改，分别用于四个新交易对。次测试：每个交易对恰好 64 组预先固定组合，不追加搜索。',
        'Binance 现货 K 线，15分钟，多空模拟；PAXG/SOL 为 2020-09-10 至 2026-09-10，ZEC 为 2019-09-10 至 2026-09-10，BNB 为 2018-09-10 至 2026-09-10。最后两年统一为 2024-09-10 至 2026-09-10。PAXG 是本次指定的黄金代币交易对，并非另取 XAU/USD 行情。',
        '每笔使用当时全部资金，盈亏计入下一笔；不加杠杆，不计手续费和滑点。表内收益为累计收益，不是年化收益。各分段从空仓重新开始，不能要求分段收益连乘与连续全历史完全相等。',
        '## 两组原参数，直接换标的',
        table(['标的','沿用哪组参数','全历史收益','最近两年收益','全历史笔数','赚钱次数','亏钱次数'],transfer_rows),
        table(['参数',*transfer],[[label,*[plan['variants'][k]['parameters'][f] for k in transfer.values()]] for f,label in LABELS.items()]),
        '## 各交易对全历史收益最高的参数：事后排名',
        '以下从每个币全部 64 组中按全历史收益挑选。它使用了最后两年的成绩，不能把这一组的最后两年再叫独立验证。',
        table(['项目',*[a.upper() for a in assets]],
            [[label,*[plan['variants'][best[a]]['parameters'][f] for a in assets]] for f,label in LABELS.items()]+
            [['全历史收益',*[pct(rows[a][best[a]]['full']['return_pct']) for a in assets]],
             ['最近两年收益',*[pct(rows[a][best[a]]['final']['return_pct']) for a in assets]],
             ['全历史胜率',*[f"{rows[a][best[a]]['full']['win_rate']:.2f}%" if rows[a][best[a]]['full']['win_rate'] is not None else '无交易' for a in assets]]]),
        '## 只用前面年份选参数，之后两年怎么样',
        '参数只按 2024-09-10 以前的累计收益选定，四个选择全部保存后才做剩余组合的后续评估。原参数的跨标的测试已先看过最后两年，且本报告还展示全部组合的后续结果，因此不能声称整个研究过程从未接触最后两年；筛选程序本身不读取它。',
        table(['标的','提前选定的完整参数','前面年份收益','之后两年收益'],
            [[a.upper(),params(plan['variants'][selected[a]]['parameters']),pct(rows[a][selected[a]]['train']['return_pct']),pct(rows[a][selected[a]]['final']['return_pct'])] for a in assets]),
        '## 64组中有多少组赚钱',
        '只看第一名容易掩盖大多数参数都亏损的情况。下表是固定范围内所有结果的计数，不增加搜索，也不改变提前选择。',
        table(['标的','全历史赚钱的组数','最近两年赚钱的组数','两个期间都赚钱的组数'],
            [[a.upper(),sum(r['full']['return_pct']>0 for r in rows[a].values()),
              sum(r['final']['return_pct']>0 for r in rows[a].values()),
              sum(r['full']['return_pct']>0 and r['final']['return_pct']>0 for r in rows[a].values())] for a in assets]),
        '## 每个币收益前三名']
    for a in assets:
        text += [a.upper(),table(['名次','完整参数','全历史收益','最近两年收益'],
             [[i+1,params(plan['variants'][k]['parameters']),pct(rows[a][k]['full']['return_pct']),pct(rows[a][k]['final']['return_pct'])] for i,k in enumerate(result['rankings'][a]['full'][:3])])]
    text+=['## 数据与保留记录',
        table(['标的','实际K线（含预热）','缺失K线','缺口段数','零成交量K线'],[[a.upper(),result['data'][a]['candles'],result['data'][a]['missing_bars'],len(result['data'][a]['gaps']),result['data'][a]['zero_volume_bars']] for a in assets]),
        '缺口经过相同项目数据服务补查，没有补造 K 线。逐笔交易跨越缺口的影响记录在各结果 gap_sensitivity 中。零成交量 K 线保留交易所原始数据。',
        '策略和引擎均与原版本逐字节核对。plan.json 固定研究范围，selection-lock.json 保留提前选择，results.json 保存全部 768 个期间结果，verification.json 核对全部逐笔记录与资金结果。原始行情、配置与逐笔记录在 .opentrading_runtime/alt-cloud-transfer-20260911。']
    (DOCS/'REPORT.md').write_text('\n\n'.join(text)+'\n',encoding='utf-8')
    payload={'verdict':verdict,'assets':plan['assets'],'axes':plan['axes'],'transfer':transfer,'parameters':{k:v['parameters'] for k,v in plan['variants'].items()},
             'results':rows,'rankings':result['rankings'],'selected':selected,'best':best,'labels':LABELS,'data':result['data']}
    html=TEMPLATE.replace('__DATA__',json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('</','<\\/'))
    (DOCS/'report.html').write_text(html,encoding='utf-8')
    served=ROOT/'docs/verification/eth-cloud-two-year-20260910/alt-transfer.html';served.write_text(html,encoding='utf-8')
    label='038-four-asset-transfer-completed'
    if not (ROOT/'docs/verification/eth-cloud-robustness-20260910/versions'/label).exists():
        snapshot(label,[SOURCE,ROOT/'app/domain/local_backtest.py',ROOT/'scripts/alt_cloud_parameter_study.py',ROOT/'scripts/report_alt_cloud_transfer.py',
            ROOT/'test/test_alt_cloud_transfer_study.py',*[DOCS/f for f in ('plan.json','data.json','selection-lock.json','results.json','transfer-results.json','verification.json','test-results.json','REPORT.md','report.html')],served])
    print(verdict,flush=True)
    for a in assets:print(a.upper(),params(plan['variants'][best[a]]['parameters']),pct(rows[a][best[a]]['full']['return_pct']),pct(rows[a][best[a]]['final']['return_pct']),flush=True)


TEMPLATE='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>原参数换标的：PAXG · ZEC · SOL · BNB</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#192940;font:15px/1.7 "Microsoft YaHei",sans-serif}main{max-width:1420px;margin:auto;padding:30px}h1{font-size:31px;margin:8px 0}h2{font-size:23px;margin:0 0 12px}h3{font-size:20px}.tag{color:#416ca6;font-weight:700}.lead{font-size:19px}.muted{color:#66758a}.card{padding:22px;background:white;border:1px solid #dde5ef;border-radius:15px;margin:22px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:12px;text-align:left;border-bottom:1px solid #e6ebf3;white-space:nowrap}th{color:#52627c;font-size:14px;background:#f8faff}.pos{color:#008464}.neg{color:#bb453c}.params{white-space:normal;min-width:280px;max-width:500px}select{font:inherit;padding:9px 16px;border:1px solid #cad5e4;border-radius:8px;background:white}.result{font-size:20px;font-weight:700}.note{padding:12px 16px;border-left:4px solid #547caf;background:#f0f5fc}a{color:#3568af}@media(max-width:800px){main{padding:16px}h1{font-size:25px}.card{padding:16px}}
</style><main><div class="tag">4个新交易对 · 每个64组参数 · 768个期间结果 · 沿用原项目模拟器</div><h1>先看原参数，换个标的还能不能赚钱</h1><p class="lead" id="verdict"></p>
<p class="muted">15分钟，多空模拟，不计手续费和滑点，不加杠杆；每笔用当时全部资金，盈亏滚入下一笔。PAXG、SOL 六年；ZEC 七年；BNB 八年，均截至2026年9月10日。最近两年统一为2024年9月10日至2026年9月10日。收益均为累计收益。</p>
<section class="card"><h2>① 两组原参数完全不改：这是主要检验</h2><p>ETH 那组与 BTC 那组直接用于四个新标的。如果调整参数后才赚钱，不能据此说原参数通过了跨标的检验。</p><div class="scroll" id="transfer"></div><details><summary>展开两组原参数</summary><div class="scroll" id="original-params"></div></details></section>
<section class="card"><h2>② 每个币全历史收益最高的参数</h2><p class="note">这是看完全部历史后的排名。下面这组的“最近两年收益”已经参与选第一名，不能再当成独立验证。</p><div class="scroll" id="best"></div></section>
<section class="card"><h2>③ 如果当时只看前面年份，选出的参数后来如何？</h2><p>先用2024年9月10日以前的数据选第一名，再固定下来查看之后两年；没有根据后来的成绩改选。</p><div class="scroll" id="selected"></div><p class="muted">原参数的检验先看过最后两年；本报告也展示所有固定组合的后续结果。因此这只是将最后两年排除在自动选参规则外，不声称整个研究从未看过这段历史。</p></section>
<section class="card"><h2>④ 每个币的64组里，有多少组赚钱？</h2><p>不能只看第一名；这里把全部固定参数范围的结果一并列出。</p><div class="scroll" id="positive-counts"></div></section>
<section class="card"><h2>⑤ 看某个币的全部64组参数</h2><label>交易对 <select id="asset"><option value="paxg">PAXG/USDT</option><option value="zec">ZEC/USDT</option><option value="sol">SOL/USDT</option><option value="bnb">BNB/USDT</option></select></label><p>按全历史收益排序。振幅是每根最高价减最低价的 EMA 平滑，不是 ATR；回吐比例固定50%。</p><div class="scroll" id="ranking"></div></section>
<section class="card"><h2>数据范围与实际缺口</h2><div class="scroll" id="data"></div><p class="muted">来源为项目 MarketDataService / Binance 现货 / KlineStore。缺口经相同服务补查，不补造K线。PAXG是用户指定的黄金代币交易对。各期间从空仓开始，全历史连续回测，分段收益连乘可能与全历史不同。</p><details><summary>本轮固定的参数范围与记录</summary><div id="axes"></div><p>64组固定联合参数，没有追加搜索。逐笔成交、信号、资金曲线、提前选择、源码副本和核对记录均另存；旧策略和旧结果未改变。</p></details></section>
<p><a href="entry-explained.html">看K线理解买卖规则</a> · <a href="btc-parameters.html">之前BTC参数测试</a></p></main><script>
const D=__DATA__,assets=Object.keys(D.assets),p=v=>`${v>=0?'+':''}${v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}%`,money=v=>`<span class="${v>=0?'pos':'neg'}">${p(v)}</span>`,percent=v=>v===null?'无交易':`${v.toFixed(2)}%`;
function table(headers,rows){return `<table><thead><tr>${headers.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(x=>`<td>${x}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
function desc(k){let q=D.parameters[k];return `<span class="params">EMA${q.center_length}，振幅${q.width_length}，门槛${q.trigger_mult}倍，最远${q.chase_mult}倍；浮盈${q.activation_pct}%启动保护，回吐${q.giveback_pct}%，止损${q.initial_stop_pct}%</span>`}
document.querySelector('#verdict').textContent=D.verdict;
document.querySelector('#transfer').innerHTML=table(['标的','使用参数','全历史收益','最近两年收益','全历史胜率','赚钱 / 亏钱'],assets.flatMap(a=>Object.entries(D.transfer).map(([name,k])=>{let r=D.results[a][k];return [a.toUpperCase(),name,money(r.full.return_pct),money(r.final.return_pct),percent(r.full.win_rate),`${r.full.wins} / ${r.full.losses}`]})));
document.querySelector('#original-params').innerHTML=table(['参数',...Object.keys(D.transfer)],Object.entries(D.labels).map(([f,label])=>[label,...Object.values(D.transfer).map(k=>D.parameters[k][f])]));
document.querySelector('#best').innerHTML=table(['项目',...assets.map(a=>a.toUpperCase())],[...Object.entries(D.labels).map(([f,label])=>[label,...assets.map(a=>D.parameters[D.best[a]][f])]),['全历史收益',...assets.map(a=>money(D.results[a][D.best[a]].full.return_pct))],['最近两年收益（已参与排名）',...assets.map(a=>money(D.results[a][D.best[a]].final.return_pct))],['全历史交易笔数',...assets.map(a=>D.results[a][D.best[a]].full.total_trades)],['赚钱 / 亏钱',...assets.map(a=>{let r=D.results[a][D.best[a]].full;return `${r.wins} / ${r.losses}`})]]);
document.querySelector('#selected').innerHTML=table(['标的','提前选定的具体参数','前面年份收益','之后两年收益'],assets.map(a=>{let k=D.selected[a],r=D.results[a][k];return [a.toUpperCase(),desc(k),money(r.train.return_pct),money(r.final.return_pct)]}));
document.querySelector('#positive-counts').innerHTML=table(['标的','全历史赚钱','最近两年赚钱','两个期间都赚钱'],assets.map(a=>{let rs=Object.values(D.results[a]);return [a.toUpperCase(),`${rs.filter(r=>r.full.return_pct>0).length} / 64`,`${rs.filter(r=>r.final.return_pct>0).length} / 64`,`${rs.filter(r=>r.full.return_pct>0&&r.final.return_pct>0).length} / 64`]}));
function ranking(){let a=document.querySelector('#asset').value;document.querySelector('#ranking').innerHTML=table(['名次','完整参数','全历史收益','最近两年收益','全历史胜率','赚钱 / 亏钱'],D.rankings[a].full.map((k,i)=>{let r=D.results[a][k];return [i+1,desc(k),money(r.full.return_pct),money(r.final.return_pct),percent(r.full.win_rate),`${r.full.wins} / ${r.full.losses}`]}))}document.querySelector('#asset').addEventListener('change',ranking);ranking();
document.querySelector('#data').innerHTML=table(['标的','全历史起点','实际K线（含预热）','缺失K线 / 段数','零成交量K线'],assets.map(a=>{let r=D.data[a];return [a.toUpperCase(),r.start.slice(0,10),r.candles,`${r.missing_bars} / ${r.gaps.length}`,r.zero_volume_bars]}));
document.querySelector('#axes').innerHTML=table(['参数','已测试的值'],Object.entries(D.labels).map(([f,label])=>[label,D.axes[f].join('、')]));
</script></html>'''


if __name__=='__main__':main()
