"""Read saved BNB trades with project attribution helpers; never run a strategy."""
import json
from collections import Counter
from math import isclose
from pathlib import Path
from app.infra.research_files import read_json, file_hash
from app.domain.cloud_trade_attribution import summary, group, calendar_returns, periods, date

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
RUN = ROOT/'.heimdall_runtime/local_backtests/657b2b8086588a254442b82b128d34df'


def save(name, value):
    with (OUT/name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    meta = read_json(RUN/'metadata.json')
    for name, key in [('result.json', 'result_hash'), ('data.json', 'data_hash')]:
        assert file_hash(RUN/name) == meta[key]
    r = read_json(RUN/'result.json'); rows = read_json(RUN/'data.json')
    trades, equity = r['trades'], r['equity']
    losses = [t for t in trades if t['profit'] < 0]
    total_loss = -sum(t['profit'] for t in losses)
    equal_loss = -sum(t['return_pct'] for t in losses)
    reasons = {}
    for reason in sorted({t['exit_reason'] for t in losses}):
        ts = [t for t in losses if t['exit_reason'] == reason]
        reasons[reason] = dict(**summary(ts),
            losing_trade_share_pct=100*len(ts)/len(losses),
            cash_loss_share_pct=-100*sum(t['profit'] for t in ts)/total_loss,
            equal_principal_loss_share_pct=-100*sum(t['return_pct'] for t in ts)/equal_loss)
    years = calendar_returns(equity, rows, periods(equity[0]['timestamp'], equity[-1]['timestamp'], 'year'))
    months = calendar_returns(equity, rows, periods(equity[0]['timestamp'], equity[-1]['timestamp'], 'month'))
    for y in years:
        ts = [t for t in trades if y['start'] <= t['exit_time'] < y['end']]
        y.update(closed=summary(ts), sides=group(ts, 'side'), exits=group(ts, 'exit_reason'))
    peak = 0; worst = (0, 0, 0)
    for i, e in enumerate(equity):
        if e['equity'] >= equity[peak]['equity']: peak = i
        dd = 100*(1-e['equity']/equity[peak]['equity'])
        if dd > worst[0]: worst = dd, peak, i
    dd, pi, ti = worst; p, t = equity[pi], equity[ti]
    recovery = next((e for e in equity[ti+1:] if e['equity'] >= p['equity']), None)
    # Equity timestamps refer to candle close; exclude exits already reflected at the peak.
    closed = [x for x in trades if p['timestamp'] <= x['exit_time'] < t['timestamp']]
    net_closed = sum(x['profit'] for x in closed)
    # cash excludes principal allocated to an open position. Equity minus
    # unrealized is the realized account balance including that principal.
    assert isclose(net_closed, (t['equity']-t['unrealized'])-(p['equity']-p['unrealized']), abs_tol=1e-6)
    assert isclose(t['equity']-p['equity'], net_closed+t['unrealized']-p['unrealized'], abs_tol=1e-6)
    dd_loss = [x for x in closed if x['profit'] < 0]
    drawdown = dict(pct=dd, peak={**p, 'utc':date(p['timestamp'])}, trough={**t, 'utc':date(t['timestamp'])},
        recovery={**recovery, 'utc':date(recovery['timestamp'])} if recovery else None,
        days_to_trough=(t['timestamp']-p['timestamp'])/86400000,
        days_to_recover=(recovery['timestamp']-p['timestamp'])/86400000 if recovery else None,
        closed=summary(closed), sides=group(closed, 'side'), exits=group(closed, 'exit_reason'),
        losing_exits=group(dd_loss, 'exit_reason'),
        closed_cash_change=net_closed, unrealized_change=t['unrealized']-p['unrealized'],
        market=calendar_returns(equity[pi:ti+1], rows, [('drawdown', p['timestamp'], t['timestamp'])])[0],
        worst_trades=sorted(closed, key=lambda x:x['return_pct'])[:5])
    streak=[]; longest=[]
    for x in trades:
        streak=streak+[x] if x['profit']<0 else []
        if len(streak)>len(longest):longest=streak.copy()
    obs={o['timestamp']:o for o in r['indicators']}; prices={b[0]:b[4] for b in rows}
    annotated=[]
    for x in trades:
        signal=x['entry_order_signal_time']; v=obs[signal]['values']
        assert signal+900000 <= x['entry_time']
        width=100*v['宽度基准']/prices[signal]
        peak_pct=x.get('profit_peak_pct',0)
        annotated.append(dict(x, entry_utc=date(x['entry_time']), exit_utc=date(x['exit_time']),
            width_pct_before_entry=width,
            width_bucket='below_0.15%' if width<.15 else '0.15_to_0.4%' if width<.4 else 'at_least_0.4%',
            peak_bucket='below_0.5%' if peak_pct<.5 else '0.5_to_1%' if peak_pct<1 else '1_to_2%' if peak_pct<2 else 'at_least_2%',
            duration_bucket='below_1h' if x['duration_minutes']<60 else '1_to_4h' if x['duration_minutes']<240 else 'at_least_4h'))
    al=[x for x in annotated if x['profit']<0]
    result=dict(run_id=RUN.name, config=read_json(RUN/'config.json'), report=r['report'],
        all=summary(trades), sides=group(trades,'side'), all_exits=group(trades,'exit_reason'),
        losing_exits=reasons, losing_peak=group(al,'peak_bucket'), losing_duration=group(al,'duration_bucket'),
        entry_width_groups=group(annotated,'width_bucket'), years=years, worst_months=sorted(months,key=lambda m:m['return_pct'])[:8],
        max_drawdown=drawdown, longest_loss_streak=dict(summary=summary(longest),
            start=date(longest[0]['entry_time']),end=date(longest[-1]['exit_time']),trade_ids=[x['trade_id'] for x in longest]),
        stop_same_15m_candle=sum(x['entry_time']//900000==x['exit_time']//900000 for x in losses if x['exit_reason']=='stop_loss'),
        losing_ambiguous=sum(x.get('entry_bar_ambiguous',False) for x in losses),
        source={name:file_hash(RUN/name) for name in ['result.json','data.json','strategy.py','engine.py']},
        notes=['只读取已有回测，复用项目归因函数；不改参数、不下载、不重新回测。',
               '年份收益按连续账户权益；交易分组按退出时间。2018、2026是不完整自然年。',
               '分方向收益是已有交易的事后归因，不是另跑只做多或只做空策略。',
               '按每笔相同本金汇总亏损幅度，避免后期本金较大掩盖早期问题；实际现金占比另列。',
               '浮盈峰值仅使用引擎在退出前记录的路径，未猜测退出K线内高低点先后。',
               '通道宽度分组沿用已有0.15%/0.4%档位，只描述关系，没有据此筛选或证明因果。'])
    assert len(trades)==7903 and len(losses)==5123
    assert isclose(dd,r['report']['max_drawdown_pct'],abs_tol=1e-8)
    assert isclose(sum(x['profit'] for x in trades),r['report']['profit'],abs_tol=1e-6)
    save('results.json', result); save('trades.json', annotated); save('drawdown-trades.json', closed)
    keys=['trades','wins','losses','win_rate','mean_win_pct','mean_loss_pct','actual_cash_profit','compound_return_pct','median_hours','max_loss_streak']
    print(json.dumps(dict(all=result['all'],loss_reasons=reasons,
        sides={s:{k:v[k] for k in keys} for s,v in result['sides'].items()},
        drawdown={k:v for k,v in drawdown.items() if k not in ['sides','exits','losing_exits','worst_trades']},
        dd_sides={s:{k:v[k] for k in keys} for s,v in drawdown['sides'].items()},
        years=[{k:y[k] for k in ['label','return_pct','market_return_pct']} for y in years],
        losing_peaks={k:v['trades'] for k,v in result['losing_peak'].items()},
        losing_duration={k:v['trades'] for k,v in result['losing_duration'].items()},
        streak=result['longest_loss_streak']),ensure_ascii=False))


if __name__ == '__main__': main()
