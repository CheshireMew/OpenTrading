"""Free Tencent daily index archive, paged without loading a market SDK."""
from datetime import datetime, timedelta, timezone
import math

import httpx

from app.domain.market.index_fetch import IndexFetchResult
from config import settings


class TencentIndexHistoryProvider:
    def fetch_history(self, instrument, source, start_dt, end_dt):
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
                    if not all(math.isfinite(value) and value > 0 for value in values) or not (
                        values[2] <= min(values[0], values[3]) <= max(values[0], values[3]) <= values[1]):
                        raise ValueError(f"腾讯指数日线数值无效：{code}")
                    stamp = int(day.timestamp() * 1000)
                    rows[stamp] = [stamp, *values, 0.0]
                oldest = min(dates)
                if len(page) < 640 or oldest <= start_dt.date():
                    break
                next_cursor = oldest - timedelta(days=1)
                if next_cursor >= cursor:
                    raise ValueError(f"腾讯指数历史分页没有前进：{code}")
                cursor = next_cursor
        result = [rows[stamp] for stamp in sorted(rows)]
        # Other archives may contain pre-launch back series which Tencent lacks.
        # Fall through rather than silently replacing that history with a later
        # beginning (e.g. CSI A500's 2004 back series versus its 2024 launch).
        if result and result[0][0] - int(start_dt.timestamp()*1000) > 14 * 86_400_000:
            result = []
        return IndexFetchResult(data=result, source="tencent")
