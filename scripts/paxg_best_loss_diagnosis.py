"""Read-only attribution of the selected PAXG run. No new strategy/backtest."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isclose
from statistics import mean, median

from app.domain.cloud_trade_attribution import calendar_returns, periods, features, bucket
from app.infra.research_files import read_json, file_hash
from scripts.cloud_strategy_versions import ROOT, snapshot
from scripts.cloud_width_reentry_study import keep
from scripts.paxg_intrabar_combined_study import save_text

STUDY=ROOT/'docs/verification/zec-paxg-entry-parameters-20260913/paxg'
OUT=STUDY/'best-loss-diagnosis'
KEY='4h_c55_w50_t1p2'
STEP=14400000


def date(ts):return datetime.fromtimestamp(ts/1000,timezone.utc).isoformat()


def stats(ts):
    wins=[t for t in ts if t['return_pct']>0];loss=[t for t in ts if t['return_pct']<0]
    return dict(trades=len(ts),wins=len(wins),losses=len(loss),win_rate=100*len(wins)/len(ts) if ts else None,
        mean_return_pct=mean(t['return_pct'] for t in ts) if ts else None,
        mean_win_pct=mean(t['return_pct'] for t in wins) if wins else None,
        mean_loss_pct=mean(t['return_pct'] for t in loss) if loss else None,
        sum_win_pct=sum(t['return_pct'] for t in wins),sum_loss_pct=sum(t['return_pct'] for t in loss),
        gross_winning_cash=sum(t['profit'] for t in wins),gross_losing_cash=-sum(t['profit'] for t in loss),
        net_cash=sum(t['profit'] for t in ts),median_hours=median(t['duration_minutes']/60 for t in ts) if ts else None,
        mean_hours=mean(t['duration_minutes']/60 for t in ts) if ts else None)


def groups(ts,field):
    out=defaultdict(list)
    for t in ts:out[str(t[field])].append(t)
    return {k:stats(v) for k,v in sorted(out.items())}


def main():
    OUT.mkdir(exist_ok=True)
    selected=read_json(STUDY/'results.json')['results'][KEY]
    folder=ROOT/'.heimdall_runtime/local_backtests'/selected['run_id']
    for file,key in [('result.json','result_hash'),('data.json','data_hash'),('execution_data.json','execution_data_hash')]:
        assert file_hash(folder/file)==selected[key]
    r=read_json(folder/'result.json');rows=read_json(folder/'data.json');obs={o['timestamp']:o for o in r['indicators']}
    idx={b[0]:i for i,b in enumerate(rows)};f=features(rows,selected['config']['parameters'])
    trades=[];raw=0
    for t in r['trades']:
        posted=t['entry_order_signal_time'];v=obs[posted]['values'];i=idx[posted]
        assert posted+STEP<=t['entry_time']
        origin=int(v['确认起点时间']);side=t['direction'];width_pct=100*v['宽度基准']/rows[i][4]
        recent=[obs[b[0]] for b in rows[max(650,i-11):i+1]]
        signals=[1 if x['checks']['原做多信号'] else -1 for x in recent if x['checks']['原做多信号'] or x['checks']['原做空信号']]
        flips=sum(a!=b for a,b in zip(signals,signals[1:]))
        record=dict(t,entry_utc=date(t['entry_time']),exit_utc=date(t['exit_time']),signal_utc=date(origin),posted_utc=date(posted),
            exit_year=date(t['exit_time'])[:4],exit_month=date(t['exit_time'])[:7],
            recorded_peak_bucket=bucket(t.get('profit_peak_pct',0),[.5,1,2],['below_0p5','0p5_to_1','1_to_2','at_least_2']),
            duration_bucket=bucket(t['duration_minutes']/60,[4,24,72,168],['under_4h','4_to_24h','1_to_3d','3_to_7d','at_least_7d']),
            width_pct=width_pct,width_bucket=bucket(width_pct,[.5,1],['below_0p5','0p5_to_1','at_least_1']),
            stop_to_width=2/width_pct,center_slope_aligned=side*v['中心线过去6根变化']>0,
            prior_48h_direction_flips=flips,flip_bucket='at_least_2' if flips>=2 else 'below_2',
            prior30d_momentum=float(f['momentum30'][i]),momentum_aligned=bool(side*f['momentum30'][i]>0),
            entry_parent_bar=t['entry_time']//STEP*STEP,exit_parent_bar=t['exit_time']//STEP*STEP)
        if t['exit_reason']=='signal':
            et=t['exit_time']//STEP*STEP;j=idx[et]-1;x=obs[rows[j][0]]
            assert x['checks']['原做空信号' if side==1 else '原做多信号']
            assert x['timestamp']+STEP==et
            record['opposite_signal_utc']=date(x['timestamp']);raw+=1
        trades.append(record)
    losses=[t for t in trades if t['return_pct']<0];wins=[t for t in trades if t['return_pct']>0]
    stop=[t for t in losses if t['exit_reason']=='stop_loss'];reverse=[t for t in losses if t['exit_reason']=='signal']
    total_loss=-sum(t['return_pct'] for t in losses)
    why={reason:{**stats(group),'equal_principal_loss_share_pct':-100*sum(t['return_pct'] for t in group)/total_loss}
         for reason,group in [('opposite_signal',reverse),('fixed_stop',stop)]}
    equity=r['equity'];peak_i=0;worst=(0,0,0)
    for i,e in enumerate(equity):
        if e['equity']>=equity[peak_i]['equity']:peak_i=i
        dd=100*(1-e['equity']/equity[peak_i]['equity'])
        if dd>worst[0]:worst=(dd,peak_i,i)
    dd,pi,ti=worst;recover=next((x for x in equity[ti+1:] if x['equity']>=equity[pi]['equity']),None)
    drawdown=dict(pct=dd,peak_time=date(equity[pi]['timestamp']),trough_time=date(equity[ti]['timestamp']),
        recovery_time=date(recover['timestamp']) if recover else None,peak_equity=equity[pi]['equity'],trough_equity=equity[ti]['equity'],
        closed_trades=stats([t for t in trades if equity[pi]['timestamp']<t['exit_time']<=equity[ti]['timestamp']]))
    streak=[];best=[]
    for t in trades:
        streak=streak+[t] if t['return_pct']<0 else []
        if len(streak)>len(best):best=streak.copy()
    months=calendar_returns(equity,rows,periods(equity[0]['timestamp'],equity[-1]['timestamp'],'month'))
    years=calendar_returns(equity,rows,periods(equity[0]['timestamp'],equity[-1]['timestamp'],'year'))
    for y in years:
        ts=[t for t in trades if y['start']<=t['exit_time']<y['end']]
        y.update(closed=stats(ts),sides=groups(ts,'side'))
    worst_months=sorted(months,key=lambda m:m['return_pct'])[:8]
    for m in worst_months:m['closed']=stats([t for t in trades if m['start']<=t['exit_time']<m['end']])
    note='Only read saved run; no new backtest or parameter choice. Loss percentage shares sum each trade return at equal principal; cash sums use actual compounding. Years/months use continuous marked equity, while win/loss counts use exit date. Features use posted completed 4h candle, never the unfinished entry candle. Peak profit is engine-recorded before exit, not an assumption about the whole exit candle. Feature associations are descriptive, not causal proof or tested filters.'
    result=dict(run_id=selected['run_id'],config=selected['config'],report=r['report'],note=note,
        all=stats(trades),winners=stats(wins),losers=stats(losses),loss_causes=why,sides=groups(trades,'side'),
        yearly=years,worst_months=worst_months,negative_months=sum(m['return_pct']<0 for m in months),total_months=len(months),
        loss_peak_groups=groups(losses,'recorded_peak_bucket'),loss_duration=groups(losses,'duration_bucket'),
        entry_features={key:groups(trades,key) for key in ['width_bucket','center_slope_aligned','momentum_aligned','flip_bucket']},
        stop_same_parent_bar=sum(t['entry_parent_bar']==t['exit_parent_bar'] for t in stop),
        loss_same_parent_bar=sum(t['entry_parent_bar']==t['exit_parent_bar'] for t in losses),
        fixed_stop_returns=[t['return_pct'] for t in stop],max_drawdown=drawdown,
        longest_loss_streak=dict(trades=len(best),first=best[0]['entry_utc'],last=best[-1]['exit_utc'],trade_ids=[t['trade_id'] for t in best]),
        opposite_exits_checked=raw,example_losses=sorted(losses,key=lambda t:t['return_pct'])[:5],
        source={file:file_hash(folder/file) for file in ['result.json','data.json','execution_data.json','strategy.py','engine.py']})
    assert len(losses)==83 and len(reverse)+len(stop)==83 and len(wins)==99 and raw==66
    assert isclose(dd,r['report']['max_drawdown_pct'],abs_tol=1e-8)
    assert isclose(sum(t['profit'] for t in trades),r['report']['profit'],abs_tol=1e-7)
    keep(OUT/'trades.json',trades);keep(OUT/'results.json',result)
    june=[t for t in trades if t['exit_month']=='2024-06']
    dd_examples=[t for t in trades if t['entry_utc']<'2026-02-20' and t['exit_utc']>='2026-01-29']
    keep(OUT/'examples.json',dict(june2024=june,drawdown2026=dd_examples))
    lines=['# PAXG最高收益版本：亏损发生在哪里','',
        '仅分析已有4小时、EMA55、振幅50、突破1.2倍的+207.76%版本，2021-01-22至2026-09-10；没有新增回测或修改策略。原182笔中99笔赢、83笔亏。','',
        '83笔亏损中60笔由原反向信号退出，平均亏1.01%；23笔触发固定2%止损，每笔亏2%。按每笔相同本金的亏损幅度相加，两类分别占56.94%和43.06%。没有利润保护退出却亏损的交易。','',
        '| 方向 | 交易 | 赢 | 亏 | 胜率 | 平均盈利单 | 平均亏损单 |','|---|---:|---:|---:|---:|---:|---:|']
    for side,name in [('long','做多'),('short','做空')]:
        s=result['sides'][side];lines.append(f'| {name} | {s["trades"]} | {s["wins"]} | {s["losses"]} | {s["win_rate"]:.2f}% | {s["mean_win_pct"]:.2f}% | {s["mean_loss_pct"]:.2f}% |')
    lines+=['','空单更弱，但实际交易中的空单总体仍有正贡献，不能由此说取消空单一定更好。','',
        '亏损路径：23笔在退出前记录的最高浮盈不足0.5%，24笔达到0.5%—1%，36笔达到1%—2%（其中19笔达到1.5%），都未启动2%保护。前两组主要是突破后延续有限；后一组是已有一定浮盈但尚未触发保护就回落。降低启动值也会改变赢家退出，此次没有测试，不能承诺改善。','',
        '并非普遍刚入场就被扫出：开仓所属4小时K线内退出的亏损为0笔；74/83笔亏损持仓至少1天。反向退出亏损的持仓中位数约6.06天，固定止损亏损中位约2.13天。','',
        '| 年份 | 账户收益 | 当年平仓亏损次数 |','|---|---:|---:|']
    for y in years:lines.append(f'| {y["label"]} | {y["return_pct"]:+.2f}% | {y["closed"]["losses"]} |')
    lines+=['','2021和2026为不完整年度。只有2021整体轻微亏损，但各年都有亏损交易，2022最多21笔。','',
        '| 最差月份 | 账户收益 | 当月平仓亏损次数 |','|---|---:|---:|']
    for m in worst_months[:5]:lines.append(f'| {m["label"]} | {m["return_pct"]:+.2f}% | {m["closed"]["losses"]} |')
    lines+=['','2024年6月是明确的反复掉头例子：6月16日约2340.01做多，2306反向退出（−1.45%）；随后2304.99做空，2340退出（−1.52%）；再在2340.01做多，2308退出（−1.37%）。原突破和实体确认都出现了，但之后没有足够的持续涨跌空间。时间以UTC记；完整交易见examples.json。','',
        '账户最大回撤14.37%发生于2026-01-29至2026-02-19，6月30日恢复前高。它还包括盈利回吐：1月16日的多单最高记录浮盈22.78%，1月30日保护退出实现11.39%；随后2月出现4笔固定2%止损。盈利单回吐与亏损单是不同概念，不能把整段账户回撤都归给止损。','',
        '补查了入场前通道宽度、均线方向和过去30天涨跌方向。宽度0.5%—1%区间有57笔亏损，但也有58笔盈利且样本最多；不能只按亏损笔数判断该区间不可交易。宽度不足0.5%的50笔胜率58%，并不支持所有窄通道都应过滤。顺均线方向组胜率51.92%，逆向组69.23%但只有26笔；顺过去30天方向组51.43%，逆向组58.44%。这些分组没有给出可直接过滤亏损的确定条件，尚未测试删除某组后的策略结果。','',
        '所有66笔原反向信号退出均核对到前一根已完成4小时K线，逐笔特征使用挂单前已完成K线；没有把尚未收盘的入场K线算作预知信息。退出前浮盈使用原引擎记录，不推测退出K线内全部价格先后。账户月/年收益包括持仓浮盈；交易次数按平仓时间分组。全仓复利，不计手续费滑点。','',
        '来源：原run_id '+selected['run_id']+'；results.json保留指标、全部分组与源文件哈希，trades.json保留182笔标注，examples.json保留亏损密集月和回撤期交易。','']
    save_text(OUT/'README.md','\n'.join(lines))
    checkpoint=ROOT/'docs/verification/eth-cloud-robustness-20260910/versions/105_paxg_best_loss_diagnosis'
    if not checkpoint.exists():snapshot('105_paxg_best_loss_diagnosis',[ROOT/'scripts/paxg_best_loss_diagnosis.py']+list(OUT.glob('*.json'))+[OUT/'README.md'])
    print('CAUSES',why,'SIDES',result['sides'])
    print('YEARS',[(y['label'],round(y['return_pct'],2),y['closed']['losses'],round(y['closed']['sum_loss_pct'],2)) for y in years])
    print('MONTHS',[(m['label'],round(m['return_pct'],2),m['closed']['losses']) for m in worst_months])
    print('PEAK',result['loss_peak_groups'],'DURATION',result['loss_duration'])
    print('FEATURES',result['entry_features'])
    print('DRAWDOWN',drawdown,'STREAK',result['longest_loss_streak'],'SAME_BAR',result['stop_same_parent_bar'])


if __name__=='__main__':main()
