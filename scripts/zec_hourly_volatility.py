"""Attribute the existing ZEC hourly EMA55 result without changing its strategy."""
import hashlib
import json
from datetime import datetime, timezone
from math import isclose, log1p
from pathlib import Path

import numpy as np

from app.domain.cloud_trade_attribution import calendar_returns, compound, date, periods, summary

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.opentrading_runtime/cloud-timeframe-20260911'
OUT = ROOT / 'docs/verification/zec-hourly-volatility-20260911'
PUBLIC = ROOT / 'docs/verification/eth-cloud-two-year-20260910'


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def keep(p, content):
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.read_text(encoding='utf-8') != content:
        raise ValueError(f'Existing output differs; create a new revision: {p}')
    p.write_text(content, encoding='utf-8')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def calculate():
    trace_path = SOURCE / 'traces/zec/base-1h-recent.json'
    rows_path = SOURCE / 'data/zec-1h.json'
    trace, rows = read(trace_path), read(rows_path)
    verification = read(ROOT / 'docs/verification/cloud-timeframe-20260911/verification.json')
    archived = next(x for x in verification['manifest'] if x['path'].replace('\\', '/') == str(trace_path.relative_to(ROOT)).replace('\\', '/'))
    assert sha(trace_path) == archived['hash']
    trades, equity = trace['trades'], trace['equity']
    start, end = equity[0]['timestamp'], equity[-1]['timestamp']
    array = np.array(rows, dtype=float)
    months = calendar_returns(equity, rows, periods(start, end, 'month'))
    years = calendar_returns(equity, rows, periods(start, end, 'year'))
    for period in months + years:
        bars = array[(array[:, 0] >= period['start']) & (array[:, 0] < period['end'])]
        # Hourly range is descriptive contemporaneous data, never an entry filter.
        ranges = 100 * (bars[:, 2] - bars[:, 3]) / bars[:, 1]
        closed = [t for t in trades if period['start'] <= t['exit_time'] < period['end']
                  or (period['end'] == end and t['exit_time'] == end)]
        period.update(hourly_mean_range_pct=float(np.mean(ranges)),
                      hourly_median_range_pct=float(np.median(ranges)),
                      hourly_log_return_std_pct=float(np.std(np.diff(np.log(bars[:, 4])), ddof=1) * 100),
                      bars=len(bars), expected_bars=int((period['end'] - period['start']) / 3600000),
                      cash_change=period['end_equity'] - period['start_equity'],
                      closed_trades=summary(closed),
                      long_closed=summary([t for t in closed if t['side'] == 'long']),
                      short_closed=summary([t for t in closed if t['side'] == 'short']))
        period['missing_bars'] = period['expected_bars'] - period['bars']
    ordered = sorted(trades, key=lambda t: t['return_pct'], reverse=True)
    top_trades = []
    for t in ordered[:10]:
        top_trades.append({**{k: t[k] for k in ('trade_id', 'side', 'entry_time', 'exit_time', 'entry_price', 'exit_price', 'return_pct', 'profit', 'duration_minutes', 'exit_reason')},
                           'entry_date_utc': date(t['entry_time']), 'exit_date_utc': date(t['exit_time'])})
    sensitivity = []
    for n in (1, 3, 5):
        sensitivity.append(dict(zeroed_best_trades=n, return_pct=compound(t['return_pct'] for t in ordered[n:])))
    ordered_months = sorted(months, key=lambda p: p['return_pct'], reverse=True)
    complete = months[1:-1]
    range_values = np.array([m['hourly_mean_range_pct'] for m in complete])
    growth = np.array([log1p(m['return_pct'] / 100) for m in complete])
    correlation = float(np.corrcoef(range_values, growth)[0, 1])
    # A descriptive check that the single strongest month does not drive the association.
    excluding_best = [m for m in complete if m['label'] != ordered_months[0]['label']]
    correlation_without_best = float(np.corrcoef(
        [m['hourly_mean_range_pct'] for m in excluding_best],
        [log1p(m['return_pct'] / 100) for m in excluding_best])[0, 1])
    jan_jul = [m for m in months if '2026-01' <= m['label'] <= '2026-07']
    aug_sep = [m for m in months if '2026-08' <= m['label'] <= '2026-09']
    current_year = next(y for y in years if y['label'] == '2026')
    concentration = dict(
        jan_jul_2026_return_pct=compound(m['return_pct'] for m in jan_jul),
        aug_sep_2026_return_pct=compound(m['return_pct'] for m in aug_sep),
        aug_sep_cash_change=sum(m['cash_change'] for m in aug_sep),
        aug_sep_share_of_2026_cash_gain_pct=100 * sum(m['cash_change'] for m in aug_sep) / current_year['cash_change'],
        year2026_share_of_total_cash_gain_pct=100 * current_year['cash_change'] / trace['report']['profit'],
        best_three_months=[m['label'] for m in ordered_months[:3]],
        best_three_months_zeroed_return_pct=compound(m['return_pct'] for m in ordered_months[3:]))
    assert sum(m['closed_trades']['trades'] for m in months) == len(trades)
    assert sum(y['closed_trades']['trades'] for y in years) == len(trades)
    assert isclose(sum(m['cash_change'] for m in months), trace['report']['profit'], abs_tol=1e-7)
    assert isclose(compound(m['return_pct'] for m in months), trace['report']['return_pct'], abs_tol=1e-7)
    assert isclose(compound(t['return_pct'] for t in trades), trace['report']['return_pct'], abs_tol=1e-7)
    return dict(status='verified', analysis='descriptive_only_no_strategy_changes',
                source_files=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for p in (trace_path, rows_path)],
                start_utc=date(start), end_utc=date(end), parameters=trace['parameters'],
                report=trace['report'], summary=summary(trades),
                months=months, years=years, concentration=concentration, top_trades=top_trades,
                sensitivity=sensitivity, volatility_association=dict(
                    complete_months=len(complete), pearson_range_vs_log_growth=correlation,
                    excluding_best_month=ordered_months[0]['label'],
                    pearson_without_best_month=correlation_without_best),
                checks=dict(source_trace_matches_completed_study=True, monthly_trade_count_reconciles=True,
                            calendar_compounding_reconciles=True, monthly_cash_reconciles=True,
                            trade_compounding_reconciles=True))


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ZEC小时策略 · 收益集中在哪些月份</title>
<style>:root{font-family:system-ui,"Microsoft YaHei",sans-serif;background:#f4f6f9;color:#24344a}*{box-sizing:border-box}body{margin:0}main{max-width:1200px;margin:auto;padding:30px 24px 60px}h1{font-size:29px}h2{font-size:21px}p{line-height:1.85}.box{margin:24px 0;background:white;border:1px solid #e0e5ee;border-radius:12px;padding:22px}.lead{background:#edf4ff;border-left:4px solid #407bc4;padding:16px 22px}.muted{font-size:14px;color:#657288}.scroll{overflow:auto}table{border-collapse:collapse;white-space:nowrap;width:100%;font-size:14px}th,td{text-align:right;border-bottom:1px solid #e3e8ef;padding:11px}th{font-weight:500;background:#f6f8fb}th:first-child,td:first-child{text-align:left}.pos{color:#087a60}.neg{color:#b64252}a{color:#2b68aa}select{font:inherit;padding:8px;border:1px solid #b9c7d9;border-radius:5px}svg{width:100%;height:auto}.plot{min-width:720px}@media(max-width:650px){main{padding:18px 12px}.box{padding:15px}h1{font-size:25px}}</style>
<main><a href="cloud-timeframes.html">← 原策略各周期对比</a><p class="muted">ZECUSDT · 1小时 · 原ETH参数EMA55 · 2024-09-10—2026-09-10</p><h1>436%的收益，靠哪些行情赚到？</h1>
<div class="lead"><p><b>今年的利润确实集中在8月和9月初，但两年中收益最高的单月是去年10月。证据更支持“依赖少数持续的大行情”，不能简单说“波动越大越赚钱”。</b></p><p>例如2025年11月，每小时平均振幅达到3.94%，策略反而亏21.30%；2026年8月，平均振幅只有1.44%，策略却赚44.89%。</p></div>
<section class="box"><h2>先分清是哪段时间赚的钱</h2><div id="years" class="scroll"></div><p id="yearNote"></p><p class="muted">本金从10,000开始，每笔使用当时全部资金，盈亏带到下一笔；不计手续费、滑点，不加杠杆。各年收益不能直接相加。2024年从9月10日开始，2026年截至9月10日零点，日期按UTC。原表的2,323笔是四年交易数；这份两年结果实际为1,154笔，376笔赚、778笔亏，胜率32.58%。</p></section>
<section class="box"><h2>每个月的收益和波动放在一起看</h2><label>查看年份 <select id="year"><option value="all">全部月份</option><option>2024</option><option>2025</option><option>2026</option></select></label><div class="scroll"><div id="bars" class="plot"></div></div><div id="months" class="scroll"></div><p class="muted">平均小时振幅＝每根小时K线的（最高价−最低价）÷开盘价，再取当月平均。它表示一小时内上下动了多大，不等于整月上涨多少。收益按月末账户总额计算，包含尚未平仓的浮盈亏；交易数按平仓月份计算。首尾月份不完整。</p></section>
<section class="box"><h2>最赚钱的几笔，实际拿了多久？</h2><div id="trades" class="scroll"></div><p>前三笔都是多单，分别持有约3.6天、6.3天、4.7天。它们的共同点是入场后出现了一段能拿住的明显上涨，而不是每小时都剧烈来回摆动。</p><p id="sensitivity"></p><p class="muted">这里把已经发生的最好几笔收益改为0，其他每笔百分比保持原样，再计算复利，只用于衡量结果对大赢家的依赖。这不是提前知道要跳过哪些交易，也不是一套新的回测策略。</p></section>
<section class="box"><h2>这能说明什么</h2><p>这组策略先用1%止损承担一连串小亏，等少数大赢家补回来。两年赢单平均赚2.68%，亏单平均亏0.99%；胜率只有32.58%。因此，它更需要能延续、并且不会很快把持仓震出去的大行情。波动放大可能让利润跑得更远，也可能更容易触发1%止损。</p><p>2025年11月就是“大波动仍然亏钱”的反例。仅凭今年几个月赚钱，不能推出“只挑波动大的月份做，就能稳定赚钱”。而且整月波动大小是事后才知道的，这次没有把它拿来筛选入场。</p><p id="correlation" class="muted"></p><p class="muted">参数完全沿用：中心EMA55，宽度为高低差EMA31，突破0.4倍，不追2倍，浮盈2%开启保护，允许回吐50%，初始止损1%。只读取项目已完成的交易和小时行情，未更换参数，未覆盖原回测；这段历史已经反复研究，不能当成新的未知数据验证。</p></section></main>
<script>(()=>{const D=__DATA__,$=id=>document.getElementById(id),num=x=>x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}),pct=x=>(x>=0?'+':'')+num(x)+'%',pc=x=>`<span class="${x>=0?'pos':'neg'}">${pct(x)}</span>`,table=(h,rs)=>'<table><thead><tr>'+h.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rs.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
$('years').innerHTML=table(['年份','策略收益','这一段赚的钱','期末账户','平均小时振幅'],D.years.map(y=>[y.label+(y.label==='2025'?'全年':'（部分）'),pc(y.return_pct),num(y.cash_change),num(y.end_equity),num(y.hourly_mean_range_pct)+'%']));
const C=D.concentration;$('yearNote').innerHTML=`今年1—7月合起来赚 <b>${pct(C.jan_jul_2026_return_pct)}</b>；8月与9月初合起来赚 <b>${pct(C.aug_sep_2026_return_pct)}</b>。后面这段贡献了今年账户增长的 <b>${num(C.aug_sep_share_of_2026_cash_gain_pct)}%</b>（按月末账户总额变化，包含浮盈亏）。今年赚的钱占两年总盈利的 ${num(C.year2026_share_of_total_cash_gain_pct)}%，但这也受到去年盈利后本金变大的影响。`;
$('trades').innerHTML=table(['入场→平仓（UTC）','方向','这笔收益','持仓小时','退出原因'],D.top_trades.slice(0,5).map(t=>[t.entry_date_utc.slice(0,16).replace('T',' ')+' → '+t.exit_date_utc.slice(0,16).replace('T',' '),t.side==='long'?'做多':'做空',pc(t.return_pct),num(t.duration_minutes/60),t.exit_reason==='reversal'?'反向信号':'利润保护']));
$('sensitivity').innerHTML=`如果只把最赚钱的3笔收益设为0，两年总收益会从 <b>+436.06%</b> 降至 <b>${pct(D.sensitivity[1].return_pct)}</b>；把最赚钱的5笔设为0，就变成 <b>${pct(D.sensitivity[2].return_pct)}</b>。所以，这个好成绩确实高度依赖少数大盈利单。`;
$('correlation').textContent=`补充核查：排除首尾不足月的月份后，共${D.volatility_association.complete_months}个完整月。平均小时振幅与策略月度复利增长的相关系数为${num(D.volatility_association.pearson_range_vs_log_growth)}；去掉收益最高的2025年10月后为${num(D.volatility_association.pearson_without_best_month)}。样本很少，关系又受单月影响，不能据此制定有效的波动过滤标准。`;
function draw(){const ms=D.months.filter(m=>$('year').value==='all'||m.label.startsWith($('year').value));$('months').innerHTML=table(['月份','策略收益','ZEC价格涨跌','平均小时振幅','平仓数','赚钱','亏钱'],ms.map(m=>[m.label,pc(m.return_pct),pc(m.market_return_pct),num(m.hourly_mean_range_pct)+'%',m.closed_trades.trades,m.closed_trades.wins,m.closed_trades.losses]));let svg='',W=1100,H=340,L=60,R=1080,Z=253,S=2.25,step=(R-L)/ms.length,bw=Math.min(28,step*.65);for(let p of [-20,0,20,40,60,80]){let y=Z-p*S;svg+=`<path d="M${L} ${y}H${R}" stroke="#e2e7ee"/><text x="50" y="${y+4}" text-anchor="end" font-size="12" fill="#69788c">${p}%</text>`}ms.forEach((m,i)=>{let x=L+step*(i+.5),y=Z-m.return_pct*S;svg+=`<rect x="${x-bw/2}" y="${Math.min(y,Z)}" width="${bw}" height="${Math.abs(y-Z)}" fill="${m.return_pct>=0?'#168669':'#c65563'}"><title>${m.label} 收益${pct(m.return_pct)}；小时振幅${num(m.hourly_mean_range_pct)}%</title></rect><text transform="translate(${x},316) rotate(-45)" font-size="11" text-anchor="end" fill="#56677d">${m.label}</text>`});$('bars').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="每月策略收益柱状图">${svg}</svg>`}draw();$('year').addEventListener('change',draw);})();</script></html>'''


def main():
    result = calculate()
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    keep(OUT / 'analysis.json', payload)
    html = HTML.replace('__DATA__', payload.replace('</', '<\\/'))
    keep(OUT / 'zec-hourly-volatility.html', html)
    keep(PUBLIC / 'zec-hourly-volatility.html', html)
    print(json.dumps({k: result[k] for k in ('status', 'concentration', 'sensitivity', 'volatility_association')}, ensure_ascii=False, indent=2))
    print('YEAR RANGES', [(y['label'], y['hourly_mean_range_pct']) for y in result['years']])
    print('MISSING HOURS', sum(m['missing_bars'] for m in result['months']))
    print('REPORT http://127.0.0.1:8787/zec-hourly-volatility.html')


if __name__ == '__main__':
    main()
