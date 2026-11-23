"""Explicit observed-bar history validation; does not synthesize missing candles."""
from app.domain.local_backtest import validate_bars
from math import isclose


def validate_observed_bars(rows, start_ms, end_ms, step_ms, warmup, now_ms):
    expected_start = start_ms-warmup*step_ms
    if not rows or rows[0][0] != expected_start or rows[-1][0] != end_ms-step_ms:
        raise ValueError('观测行情必须覆盖起止边界，不能缺少头尾数据')
    if sum(row[0] < start_ms for row in rows) != warmup:
        raise ValueError('预热区间有缺口，不能减少预热根数')
    gaps, chunks, first = [], [], 0
    for i in range(1, len(rows)):
        delta = rows[i][0]-rows[i-1][0]
        if delta <= 0 or delta % step_ms:
            raise ValueError('行情时间必须递增且对齐周期，不能重复或乱序')
        if delta > step_ms:
            gaps.append({'start': int(rows[i-1][0]+step_ms), 'end': int(rows[i][0]), 'missing_bars': int(delta//step_ms-1)})
            chunks.append(rows[first:i])
            first = i
    chunks.append(rows[first:])
    # Reuse all original OHLC, numeric, boundary and future-bar checks per
    # contiguous span. There is no fill, interpolation or simulator change.
    bars = []
    for chunk in chunks:
        bars.extend(validate_bars(chunk, int(chunk[0][0]), int(chunk[-1][0]+step_ms), step_ms, 0, now_ms))
    if start_ms % step_ms or end_ms % step_ms or end_ms <= start_ms:
        raise ValueError('起止时间必须对齐周期且结束晚于开始')
    return bars, gaps


def align_execution_bars(signal_bars, fine_bars, signal_step, fine_step):
    """Accept only complete finer candles reproducing the saved signal OHLC.

    Rejected intervals remain explicit; caller uses original coarse semantics.
    Neither the signal history nor the finer prices are repaired or fabricated.
    """
    if fine_step>=signal_step or signal_step%fine_step:
        raise ValueError('成交周期必须小于信号周期并可整除')
    groups={}
    for b in fine_bars:
        groups.setdefault(b.timestamp//signal_step*signal_step,[]).append(b)
    accepted={}; rejected=[]
    for b in signal_bars:
        group=groups.get(b.timestamp,[])
        if len(group)!=signal_step//fine_step or [x.timestamp for x in group]!=list(range(b.timestamp,b.timestamp+signal_step,fine_step)):
            rejected.append(dict(timestamp=b.timestamp,reason='missing_fine_bars',observed=len(group)))
            continue
        aggregate=[group[0].open,max(x.high for x in group),min(x.low for x in group),group[-1].close]
        if not all(isclose(a,c,rel_tol=1e-9,abs_tol=1e-8) for a,c in zip(aggregate,[b.open,b.high,b.low,b.close])):
            rejected.append(dict(timestamp=b.timestamp,reason='ohlc_mismatch',fine_aggregate=aggregate,
                                 signal_ohlc=[b.open,b.high,b.low,b.close]))
            continue
        accepted[b.timestamp]=group
    return accepted,dict(signal_candles=len(signal_bars),matched=len(accepted),fallback=len(rejected),rejected=rejected)
