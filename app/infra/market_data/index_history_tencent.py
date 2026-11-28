"""Free Tencent daily index archive, paged without loading a market SDK."""
from datetime import datetime, timedelta, timezone

import httpx

from app.domain.market.index_fetch import IndexFetchResult
from app.domain.market.index_history_policy import live_index_rows, live_start_ms, utc_datetime, valid_index_row
from config import settings


class TencentIndexHistoryProvider:
    def fetch_history(self, instrument, source, start_dt, end_dt):
        start_dt = max(start_dt, utc_datetime(live_start_ms(instrument)))
        if end_dt < start_dt:
            return IndexFetchResult(data=[], source="not-launched")
        code = (source.baostock_code or "").replace(".", "") if instrument.market == "CN" else (
            "hk" + source.sina_hk_symbol if instrument.market == "HK" and source.sina_hk_symbol else "")
        if not code:
            return IndexFetchResult(data=[], source="tencent")
        rows, cursor = {}, end_dt.date()
        with httpx.Client(timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}) as client:
            while cursor >= start_dt.date():
                response = client.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                    params={"param": f"{code},day,{start_dt:%Y-%m-%d},{cursor:%Y-%m-%d},640,qfq"})
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data", {}).get(code, {})
                identity = data.get("qt", {}).get(code)
                if payload.get("code") != 0 or not identity or str(identity[2]) != code[2:]:
                    raise ValueError(f"腾讯返回的指数标识不匹配：{code}")
                page = data.get("day") or data.get("qfqday") or []
                if not page:
                    break
                dates = []
                for row in page:
                    day = datetime.strptime(row[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    dates.append(day.date())
                    if not start_dt.date() <= day.date() <= end_dt.date():
                        continue
                    values = [float(row[index]) for index in (1, 3, 4, 2)]
                    stamp = int(day.timestamp() * 1000)
                    observation = [stamp, *values, 0.0]
                    if valid_index_row(observation):
                        rows[stamp] = observation
                oldest = min(dates)
                if len(page) < 640 or oldest <= start_dt.date():
                    break
                next_cursor = oldest - timedelta(days=1)
                if next_cursor >= cursor:
                    raise ValueError(f"腾讯指数历史分页没有前进：{code}")
                cursor = next_cursor
        result = [rows[stamp] for stamp in sorted(rows)]
        return IndexFetchResult(data=live_index_rows(instrument,result), source="tencent")
