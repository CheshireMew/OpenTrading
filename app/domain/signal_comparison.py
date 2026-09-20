"""Compare bar-aligned reference signals with recorded decisions, never fills."""
from datetime import datetime
from bisect import bisect_left
from math import isfinite, log, sqrt
from statistics import median


def compare_cloud(observations, reference, step_ms):
    samples = reference.get('cloud_samples', [])
    if not samples:
        return None
    scale, bias = reference['price_to_pixel_log']
    if not all(isfinite(v) for v in (scale, bias)) or scale >= 0:
        raise ValueError('截图对数价格坐标应为有限数值，比例系数须小于零')
    observed = sorted((r for r in observations if r.get('cloud')), key=lambda r:r['timestamp'])
    times = [r['timestamp'] for r in observed]
    errors, used, unavailable = [], [], []
    for sample in samples:
        ts = sample['timestamp']
        j = bisect_left(times, ts)
        if not observed or j == len(times) or (j == 0 and times[j] != ts):
            unavailable.append(sample); continue
        a, b = (observed[j], observed[j]) if times[j] == ts else (observed[j-1], observed[j])
        if b['timestamp']-a['timestamp'] not in (0, step_ms):
            unavailable.append(sample); continue
        fraction = 0 if a is b else (ts-a['timestamp'])/step_ms
        delta = {}
        for key in ('upper','lower'):
            if min(a['cloud'][key], b['cloud'][key]) <= 0:
                raise ValueError('对数图的云带价格必须大于零')
            y = (1-fraction)*(scale*log(a['cloud'][key])+bias) + fraction*(scale*log(b['cloud'][key])+bias)
            d = y-sample[key+'_y']
            errors.append(d); delta[key+'_error_px'] = d
        used.append({'timestamp':ts, **delta})
    return {'sample_count':len(used), 'unavailable_count':len(unavailable),
        'rmse_px':sqrt(sum(e*e for e in errors)/len(errors)) if errors else None,
        'median_absolute_error_px':median(abs(e) for e in errors) if errors else None,
        'maximum_absolute_error_px':max(map(abs,errors)) if errors else None,
        'method':'按截图对数坐标，比较无遮挡采样列的云带上下沿；栅格与数据源误差保留，不据此认定原公式',
        'samples':used}


def compare_signals(result, reference, step_ms, tolerance_bars=0):
    if isinstance(tolerance_bars, bool) or not isinstance(tolerance_bars, int) or not 0 <= tolerance_bars <= 20:
        raise ValueError('允许偏差须为 0–20 根 K 线')
    expected = []
    for item in reference['signals']:
        value = item['timestamp']
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                raise ValueError('参考信号时间必须包含时区')
            value = dt.timestamp()*1000
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value % step_ms:
            raise ValueError('参考信号必须是对齐周期的 UTC 毫秒或含时区的 ISO 时间')
        if item['action'] not in ('long', 'short'):
            raise ValueError('参考信号方向应为 long/short')
        expected.append({'timestamp': int(value), 'action': item['action']})
    if len({(r['timestamp'], r['action']) for r in expected}) != len(expected):
        raise ValueError('参考信号有重复记录')
    if not expected:
        raise ValueError('参考信号不能为空')
    start = int(datetime.fromisoformat(result['run']['config']['start'].replace('Z','+00:00')).timestamp()*1000)
    end = int(datetime.fromisoformat(result['run']['config']['end'].replace('Z','+00:00')).timestamp()*1000)
    if any(not start <= r['timestamp'] < end for r in expected):
        raise ValueError('参考信号位于运行区间之外；请使用相同的完整区间核验')
    actual = [{'timestamp':int(r['timestamp']), 'action':r['action']} for r in result['signals'] if r['action'] in ('long','short')]
    matched, missing, extra = [], [], []
    # Ordered earliest-eligible matching maximizes match count within a fixed window.
    for action in ('long','short'):
        refs=sorted((r for r in expected if r['action']==action), key=lambda r:r['timestamp'])
        events=sorted((r for r in actual if r['action']==action), key=lambda r:r['timestamp'])
        i=j=0
        while i<len(refs) and j<len(events):
            d=events[j]['timestamp']-refs[i]['timestamp']
            if d < -tolerance_bars*step_ms:
                extra.append(events[j]); j+=1
            elif d > tolerance_bars*step_ms:
                missing.append(refs[i]); i+=1
            else:
                matched.append({'reference':refs[i], 'actual':events[j], 'difference_bars':d//step_ms})
                i+=1; j+=1
        missing.extend(refs[i:]); extra.extend(events[j:])
    observed={r['timestamp']:r for r in result.get('indicators',[])}
    return {'run_id':result['run']['id'], 'reference_context':reference.get('context'),
        'scope':'仅核验提供的时间区间与信号位置；匹配不证明原始公式相同，也不检验区间外表现',
        'tolerance_bars':tolerance_bars, 'reference_count':len(expected), 'actual_count':len(actual),
        'matched_count':len(matched), 'missing_count':len(missing), 'extra_count':len(extra),
        'all_signals_match':not missing and not extra, 'matched':matched, 'missing':missing, 'extra':extra,
        'cloud_comparison':compare_cloud(result.get('indicators', []), reference, step_ms),
        'reference_observations':[{'reference':r, 'observation':observed.get(r['timestamp'])} for r in expected]}
