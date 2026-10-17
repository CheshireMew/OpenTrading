"""Read-only explanation of saved ZEC trades. No new strategy or backtest."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, median

from app.infra.research_files import read_json, file_hash
from app.domain.cloud_trade_attribution import summary
from scripts.cloud_width_reentry_study import ROOT, keep

PARENT=ROOT/'docs/verification/zec-intrabar-no-stop-20260913'
OUT=PARENT/'loss-audit-20260913'
BASE=ROOT/'.heimdall_runtime/local_backtests/2a0c67e629a77db26e664880bab12d44'
NO_STOP=ROOT/'.heimdall_runtime/local_backtests/a3f988c546a7d514c979ba0f4c98fca2'
STEP=1800000


def date(t):
    return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    saved=read_json(PARENT/'results.json')['results']
    for cid,folder in [('entry_only',BASE),('combined',NO_STOP)]:
        assert file_hash(folder/'result.json')==saved[cid]['result_hash']
        assert file_hash(folder/'data.json')==saved[cid]['data_hash']
    r=read_json(BASE/'result.json'); no_stop=read_json(NO_STOP/'result.json')
    rows=read_json(BASE/'data.json'); idx={int(x[0]):i for i,x in enumerate(rows)}
    obs={x['timestamp']:x for x in r['indicators']}; ordered=r['indicators']; oi={x['timestamp']:i for i,x in enumerate(ordered)}
    trades=r['trades']; loss=[t for t in trades if t['profit']<0]
    assert len(trades)==4445 and len(loss)==2310
    total_loss=-sum(t['profit'] for t in loss)
    equal_loss=-sum(t['return_pct'] for t in loss)
    exits={}
    for reason in sorted({t['exit_reason'] for t in loss}):
        group=[t for t in loss if t['exit_reason']==reason]
        exits[reason]=dict(count=len(group),share_of_losing_trades_pct=100*len(group)/len(loss),
            equal_principal_loss_share_pct=-100*sum(t['return_pct'] for t in group)/equal_loss,
            actual_cash_loss_share_pct=-100*sum(t['profit'] for t in group)/total_loss,
            mean_return_pct=mean(t['return_pct'] for t in group),
            phase=dict(Counter(t['exit_phase'] for t in group)),
            same_entry_bar=sum(t['entry_time']==t['exit_time'] for t in group))
    annotated=[]; buckets=defaultdict(list)
    for t in trades:
        i,j=idx[t['entry_time']],idx[t['exit_time']]
        v=obs[t['entry_order_signal_time']]['values']; signal_close=rows[idx[t['entry_order_signal_time']]][4]
        # Features only use the completed candle that posted the entry order.
        width_pct=100*v['宽度基准']/signal_close
        o=oi[t['entry_order_signal_time']]
        contiguous_slope=o>=6 and ordered[o]['timestamp']-ordered[o-6]['timestamp']==6*STEP
        slope=t['direction']*(v['中心线']-ordered[o-6]['values']['中心线']) if contiguous_slope else None
        wb='<0.5%' if width_pct<.5 else '0.5%-1%' if width_pct<1 else '>=1%'
        sb='unknown_gap_or_start' if slope is None else 'aligned' if slope>0 else 'against_or_flat'
        previous=rows[j-1]
        prev_close_return=100*t['direction']*(previous[4]-t['entry_price'])/t['entry_price'] if j>i else None
        close_return=100*t['direction']*(rows[j][4]-t['entry_price'])/t['entry_price']
        record=dict(t,entry_iso=date(t['entry_time']),exit_iso=date(t['exit_time']),
            bars_until_exit=j-i,preentry_width_pct=width_pct,width_bucket=wb,
            signed_center_move_3h=slope,center_direction_bucket=sb,
            previous_close_return_pct=prev_close_return,exit_bar_close_return_pct=close_return,
            exit_previous_bar_contiguous=t['exit_time']-previous[0]==STEP,
            previous_close_already_beyond_protection=bool(t['exit_reason']=='profit_protection' and
                t['direction']*(previous[4]-t['stop'])<0))
        annotated.append(record)
        for kind,bucket in [('side',t['side']),('width',wb),('center_slope_3h',sb),
                            ('exit_year',date(t['exit_time'])[:4])]:
            buckets[(kind,bucket)].append(record)
    groups={}
    for (kind,bucket),ts in buckets.items():
        groups.setdefault(kind,{})[bucket]=summary(ts)
    sl=[t for t in annotated if t['exit_reason']=='stop_loss']
    same=[t for t in sl if t['bars_until_exit']==0]
    later=[t for t in sl if t['bars_until_exit']>0]
    protection=[t for t in annotated if t['exit_reason']=='profit_protection' and t['profit']<0]
    assert len(sl)==2213 and all(not t['protection_active'] for t in sl)
    assert len(protection)==89 and all(t['exit_phase']=='open' for t in protection)
    assert all(t['previous_close_already_beyond_protection'] and t['exit_previous_bar_contiguous'] for t in protection)
    stop_paths=dict(count=len(sl),same_bar=len(same),same_bar_order_unknown=sum(t['entry_bar_ambiguous'] for t in same),
        same_bar_order_known=sum(not t['entry_bar_ambiguous'] for t in same),
        exit_in_first_two_candles=sum(t['bars_until_exit']<2 for t in sl),
        median_bars_to_exit=median(t['bars_until_exit'] for t in sl),
        later_candle_stops=len(later),later_stops_peak_below_half_pct=sum(t['profit_peak_pct']<.5 for t in later),
        later_stops_peak_half_to_one_pct=sum(.5<=t['profit_peak_pct']<1 for t in later),
        exit_candle_closed_back_above_stop=sum(t['direction']*(rows[idx[t['exit_time']]][4]-t['stop'])>0 for t in sl),
        exit_candle_closed_back_beyond_entry=sum(t['exit_bar_close_return_pct']>0 for t in sl),
        exit_candle_recovered_entry_excluding_unknown=sum(t['exit_bar_close_return_pct']>0 and not t['entry_bar_ambiguous'] for t in sl),
        note='同根252笔的最低/最高价可能在入场之前；其余同根止损有开盘成交或收盘穿过止损的证据。峰值只统计退出前已完成K线，不把退出K线的极值当成持仓中已实现的先后顺序。')
    protection_paths=dict(count=len(protection),all_next_open=True,all_prior_close_already_crossed_new_stop=True,
        prior_close_already_losing=sum(t['previous_close_return_pct']<0 for t in protection),
        prior_close_not_losing_but_next_open_losing=sum(t['previous_close_return_pct']>=0 for t in protection),
        history_gap_count=sum(not t['exit_previous_bar_contiguous'] for t in protection),
        explanation='模型在K线收盘后用本根最高/最低价抬升保护，下一根才生效；这89笔前一根收盘时已越过新保护价。不能说全部是下一根突然跳空，或盘中保护价确实成交后仍亏损。')
    key=lambda t:(t['entry_time'],t['side'],t['entry_price'])
    bykey={key(t):t for t in no_stop['trades']}
    pairs=[(t,bykey[key(t)]) for t in sl if key(t) in bykey]
    pair_records=[dict(trade_id=t['trade_id'],no_stop_trade_id=u['trade_id'],entry_time=t['entry_time'],side=t['side'],
        original_return_pct=t['return_pct'],no_stop_return_pct=u['return_pct'],no_stop_exit_time=u['exit_time'],
        no_stop_exit_reason=u['exit_reason']) for t,u in pairs]
    paired=dict(pairs=len(pairs),now_winners=sum(u['profit']>0 for t,u in pairs),
        now_larger_losses=sum(u['return_pct']<t['return_pct']-1e-8 for t,u in pairs),
        now_same_or_smaller_losses=sum(u['profit']<0 and u['return_pct']>=t['return_pct']-1e-8 for t,u in pairs),
        now_flat=sum(u['profit']==0 for t,u in pairs),
        old_mean_return_pct=mean(t['return_pct'] for t,u in pairs),new_mean_return_pct=mean(u['return_pct'] for t,u in pairs),
        rescued_mean_return_pct=mean(u['return_pct'] for t,u in pairs if u['profit']>0),
        worsened_mean_return_pct=mean(u['return_pct'] for t,u in pairs if u['return_pct']<t['return_pct']-1e-8),
        unpaired_fixed_stops=len(sl)-len(pairs),
        note='只对两次已存回测中时间、方向、价格完全相同的入场配对；保留仓位会改变后续入场机会，所以不是所有止损的独立反事实实验。')
    keep(OUT/'loss-trades.json',[t for t in annotated if t['profit']<0])
    keep(OUT/'same-entry-no-stop-pairs.json',pair_records)
    example=protection[0]; j=idx[example['exit_time']]; i=idx[example['entry_time']]
    keep(OUT/'profit-protection-example.json',dict(trade=example,candles=rows[i:j+1],
        explanation=f"做多{example['entry_price']}，先涨到{example['best']}，新保护价{example['stop']}；抬升保护的这根已收于{rows[j-1][4]}，下一开盘只能按{example['exit_price']}平仓。"))
    report=dict(run_id=BASE.name,source_hashes={str(p.relative_to(ROOT)):file_hash(p) for p in
        [BASE/'result.json',BASE/'data.json',BASE/'strategy.py',BASE/'engine.py',NO_STOP/'result.json']},
        total_trades=len(trades),losing_trades=len(loss),exit_reasons=exits,stop_paths=stop_paths,
        protection_paths=protection_paths,groups=groups,no_stop_same_entry_comparison=paired,
        annual_equity=saved['entry_only']['annual'],
        rules='只读已完成回测。不改策略、不搜索阈值、不新增回测。宽度分组0.5%/1%和过去6根中心方向只作描述；相关性不等于原因，不能据此声称过滤后收益提高。')
    keep(OUT/'diagnosis.json',report)
    print(__import__('json').dumps({k:report[k] for k in ['exit_reasons','stop_paths','protection_paths','no_stop_same_entry_comparison']},ensure_ascii=False))
    print('GROUPS',__import__('json').dumps({kind:{k:{x:v[x] for x in ['trades','wins','losses','win_rate','mean_return_pct']} for k,v in vals.items()} for kind,vals in groups.items()},ensure_ascii=False))


if __name__=='__main__': main()
