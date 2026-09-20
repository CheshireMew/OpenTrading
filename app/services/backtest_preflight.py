"""Read-only cache coverage. Never downloads, queues, or changes requested dates."""
from sqlalchemy import func
from datetime import datetime
from app.infra.db.schema import Kline
from app.domain.market.constants import timeframe_to_milliseconds


def intersect_intervals(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        start = max(left[i]['start_ms'], right[j]['start_ms'])
        end = min(left[i]['end_ms'], right[j]['end_ms'])
        if start < end:
            result.append(dict(start_ms=start, end_ms=end))
        if left[i]['end_ms'] <= right[j]['end_ms']:
            i += 1
        else:
            j += 1
    return result


def coverage(database, symbol, timeframe, start, end, warmup=0):
    step = timeframe_to_milliseconds(timeframe)
    required_start = start - warmup * step
    count = 0
    segments = []
    first = previous = None
    with database.session_scope() as session:
        query = session.query(Kline.timestamp).filter(Kline.symbol == symbol, Kline.timeframe == timeframe)
        bounds = query.with_entities(func.min(Kline.timestamp), func.max(Kline.timestamp)).one()
        for (timestamp,) in query.filter(Kline.timestamp >= required_start, Kline.timestamp < end).order_by(Kline.timestamp).yield_per(4096):
            if timestamp % step:
                continue
            count += 1
            if previous is None or timestamp != previous + step:
                if previous is not None:
                    segments.append((first, previous + step))
                first = timestamp
            previous = timestamp
        if previous is not None:
            segments.append((first, previous + step))
    complete = [dict(start_ms=max(start, a + warmup * step), end_ms=b)
                for a, b in segments if max(start, a + warmup * step) < b]
    expected = (end - required_start) // step
    return dict(timeframe=timeframe, required_start_ms=required_start, required_end_ms=end,
                first_cached_ms=bounds[0], last_cached_close_ms=bounds[1] + step if bounds[1] is not None else None,
                expected_bars=expected, cached_bars=count, missing_bars=expected-count, complete_intervals=complete)


def preview_prepared(database, config, metadata, cache=None):
    cache = {} if cache is None else cache
    recipe = metadata.get('execution_recipe') or dict(
        start_ms=int(datetime.fromisoformat(config['start'].replace('Z', '+00:00')).timestamp()*1000),
        end_ms=int(datetime.fromisoformat(config['end'].replace('Z', '+00:00')).timestamp()*1000),
        step_ms=timeframe_to_milliseconds(config['timeframe']),
        warmup_bars=metadata.get('warmup_bars', metadata.get('strategy', {}).get('warmup_bars', 0)))
    start, end = recipe['start_ms'], recipe['end_ms']
    symbol = metadata['source']['storage_symbol']
    def read(frame, warmup=0):
        key = (symbol, frame, start, end, warmup)
        if key not in cache:
            cache[key] = coverage(database, symbol, frame, start, end, warmup)
        return cache[key]
    signal = read(config['timeframe'], recipe['warmup_bars'])
    execution = read(config['execution_timeframe']) if config.get('execution_timeframe') else None
    intervals = signal['complete_intervals']
    warnings = ['只检查本地缓存时间戳；缓存最早时间不等于交易所上市时间。缺失数据由运行时获取，预览不下载行情、不提交任务。',
                '共同可比区间表示本地连续数据及完整预热覆盖；不会自动替换请求区间。行情值、细周期 OHLC 对齐和最终快照仍由运行时校验。']
    if signal['missing_bars']:
        warnings.append(f"信号周期含预热尚缺 {signal['missing_bars']} 根本地行情。")
    if execution:
        intervals = intersect_intervals(intervals, execution['complete_intervals'])
        step = recipe['step_ms']
        intervals = [dict(start_ms=((v['start_ms']+step-1)//step)*step, end_ms=(v['end_ms']//step)*step) for v in intervals]
        intervals = [v for v in intervals if v['start_ms'] < v['end_ms']]
        if execution['missing_bars']:
            warnings.append(f"细周期尚缺 {execution['missing_bars']} 根本地行情；实际获取后按已选缺口政策处理。")
    return dict(config=config, warmup_bars=recipe['warmup_bars'],
                warmup_explanation=metadata.get('warmup_explanation', '沿用原运行保存的预热根数。'), rules_summary=metadata.get('rules_summary', [metadata.get('strategy', {}).get('description', '旧记录没有规则说明')]),
                signal_data=signal, execution_data=execution, comparable_intervals=intervals, warnings=warnings)
