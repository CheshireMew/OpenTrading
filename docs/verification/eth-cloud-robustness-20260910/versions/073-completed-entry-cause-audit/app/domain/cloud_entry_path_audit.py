"""Read-only trade path attribution. Never supplies a strategy with future data."""
from bisect import bisect_left,bisect_right
from math import isclose


def barrier_path(rows,entry,direction,target_distance,adverse_distance,exit_time,exit_phase,step):
    """First observed target/adverse encounters, with OHLC ambiguity preserved.

    Caller supplies a complete, contiguous future diagnostic window. These
    barriers are measurements, not orders, and do not reproduce an exit policy.
    """
    first_target=first_adverse=None
    maximum_favourable=maximum_adverse=0.
    for offset,row in enumerate(rows):
        timestamp,o,h,l,c,v=row
        favourable=direction*((h if direction==1 else l)-entry)
        adverse=-direction*((l if direction==1 else h)-entry)
        maximum_favourable=max(maximum_favourable,favourable)
        maximum_adverse=max(maximum_adverse,adverse)
        opening=direction*(o-entry)
        if first_target is None and (favourable>=target_distance or isclose(favourable,target_distance,rel_tol=1e-12)):
            phase='open' if opening>=target_distance or isclose(opening,target_distance,rel_tol=1e-12) else 'intrabar'
            first_target=dict(timestamp=timestamp,offset=offset,phase=phase,rank=3*offset+(phase=='intrabar'))
        if first_adverse is None and (adverse>=adverse_distance or isclose(adverse,adverse_distance,rel_tol=1e-12)):
            phase='open' if -opening>=adverse_distance or isclose(-opening,adverse_distance,rel_tol=1e-12) else 'intrabar'
            first_adverse=dict(timestamp=timestamp,offset=offset,phase=phase,rank=3*offset+(phase=='intrabar'))
    if first_target is None:order='adverse_only' if first_adverse else 'neither'
    elif first_adverse is None or first_target['rank']<first_adverse['rank']:order='target_first'
    elif first_target['rank']>first_adverse['rank']:order='adverse_first'
    else:order='same_bar_ambiguous'
    target_vs_exit=None
    if first_target:
        tt=first_target['timestamp']
        if tt<exit_time:target_vs_exit='before_exit'
        elif tt>exit_time:target_vs_exit='after_exit'
        elif exit_phase=='close':target_vs_exit='before_exit'
        elif exit_phase=='open' and first_target['phase']=='intrabar':target_vs_exit='after_exit'
        else:target_vs_exit='same_time_ambiguous'
    if first_target is None:category='no_target'
    elif order=='adverse_first':category='adverse_before_target'
    elif order=='same_bar_ambiguous':category='bar_order_unknown'
    else:category='target_first_'+target_vs_exit
    return dict(order=order,category=category,target_vs_exit=target_vs_exit,
        first_target=first_target,first_adverse=first_adverse,
        mfe_pct=100*maximum_favourable/entry,mae_pct=100*maximum_adverse/entry,
        finish_return_pct=100*direction*(rows[-1][4]-entry)/entry,
        target_pct=100*target_distance/entry,adverse_pct=100*adverse_distance/entry)


def complete_window(rows,times,start,n,step):
    i=bisect_left(times,start);j=i+n
    if i>=len(times) or times[i]!=start:return None,'entry_missing'
    if j>len(times):return None,'history_end'
    if times[j-1]-start!=(n-1)*step:return None,'gap'
    return rows[i:j],None


def preentry_features(crossings,signal_time,entry_price,step,*,times=None):
    """All features stop at the actual signal candle, never actual entry OHLC."""
    if times is None:times=[x['timestamp'] for x in crossings]
    i=bisect_right(times,signal_time)-1
    if i<0 or times[i]!=signal_time:raise ValueError('Missing exact signal audit')
    x=crossings[i];lo=signal_time-15*step;j=bisect_left(times,lo)
    flips=sum(crossings[k]['side']!=crossings[k-1]['side'] for k in range(max(1,j),i+1))
    # Percent ratios are known at signal close. Do not use future fill price.
    stop_atr=1/x['atr_pct']
    return dict(signal_er=x['er'],signal_atr_pct=x['atr_pct'],prior16_direction_flips=flips,
        signal_stop_atr=stop_atr,er_good=x['er']>=.2,flips_good=flips<2,stop_good=stop_atr>=1)
