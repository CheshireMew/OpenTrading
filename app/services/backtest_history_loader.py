"""Bound long data requests and keep verified chunks for batch recovery."""
from datetime import datetime, timezone
from app.domain.market.constants import timeframe_to_milliseconds
from app.infra.research_files import read_json, atomic_json, encode, sha, native_path


def load_history(market, symbol, timeframe, start, end, cache, check, *, chunk_bars=10000, allow_gaps=True):
    """Exclusive end; market service owns fetching/caching, never invent candles."""
    step = timeframe_to_milliseconds(timeframe)
    chunks = list(range(start, end, chunk_bars * step))
    cache = native_path(cache) / timeframe
    rows = []
    for index, begin in enumerate(chunks):
        until = min(end, begin + chunk_bars * step)
        check(index / len(chunks))
        path = cache / f'{begin}-{until}.json'
        signature = dict(symbol=symbol, timeframe=timeframe, start=begin, end=until)
        if path.exists():
            saved = read_json(path)
            part = saved['rows']
            if saved['request'] != signature or sha(encode(part)) != saved['rows_hash']:
                raise ValueError('已保存的分段行情校验失败')
        else:
            result = market.load_ohlcv_range(symbol, timeframe,
                datetime.fromtimestamp(begin/1000, timezone.utc),
                datetime.fromtimestamp((until-1)/1000, timezone.utc))
            part = sorted([r for r in result.rows if begin <= r[0] < until], key=lambda r:r[0])
            if not part:
                raise RuntimeError(f'{symbol} {timeframe} 未返回行情；请检查区间或恢复重试')
            # fetch_gap may return a truncated prefix on timeout. Do not freeze
            # that as if it were a fully visited historical gap.
            if part[0][0] != begin or part[-1][0] != until-step:
                raise ValueError(f'{symbol} {timeframe} 在 {begin}—{until} 未返回完整边界；请恢复重试，已完成分段会保留')
            if not allow_gaps and getattr(result, 'missing_ranges', []):
                raise RuntimeError(f'Incomplete OHLCV history：{symbol} {timeframe} 行情存在缺口 {result.missing_ranges}')
            check((index + 1)/len(chunks))
            atomic_json(path, dict(request=signature, rows=part, rows_hash=sha(encode(part))))
        if not allow_gaps and len(part) != (until-begin)//step:
            raise RuntimeError(f'Incomplete OHLCV history：{symbol} {timeframe} 分段行情根数不足')
        rows.extend(part)
        if len(chunks)>1:
            print(f'准备 {symbol} {timeframe}：{index+1}/{len(chunks)} 段，已保存 {len(rows)} 根', flush=True)
    check(1.)
    return rows
