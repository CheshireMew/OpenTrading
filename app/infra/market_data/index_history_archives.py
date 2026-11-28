"""Public, identified index archives for gaps in the main daily feeds."""
from datetime import datetime, timedelta, timezone
from io import BytesIO

import httpx

from app.domain.market.index_fetch import IndexFetchResult
from app.domain.market.index_history_policy import live_index_rows, live_start_ms, utc_datetime
from config import settings


class NasdaqIndexHistoryProvider:
    def fetch_history(self, instrument, source, start_dt, end_dt):
        ticker = {"US_NASDAQ100":"NDX", "US_NASDAQ_COMP":"COMP"}.get(instrument.symbol)
        if not ticker:
            return IndexFetchResult(data=[], source="nasdaq")
        lower = max(start_dt, utc_datetime(live_start_ms(instrument)))
        rows = {}
        with httpx.Client(timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
            headers={"User-Agent":"Mozilla/5.0", "Referer":f"https://indexes.nasdaqomx.com/Index/History/{ticker}"}) as client:
            # HistoryData is the public history table, not its chart's `Open`
            # field (which may contain the previous close). It has no actual
            # opening prices, so retain its published closing levels explicitly.
            while lower <= end_dt:
                upper = min(lower+timedelta(days=5*365), end_dt)
                response = client.post("https://indexes.nasdaqomx.com/Index/HistoryData",
                    data={"id":ticker,"startDate":lower.date().isoformat(),
                        "endDate":upper.date().isoformat(),"timeOfDay":"16:00:00"})
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload,dict) or not isinstance(payload.get("aaData"),list):
                    raise ValueError(f"Nasdaq {ticker} 历史表格式无效")
                for item in payload["aaData"]:
                    day = datetime.fromisoformat(item["TimeStamp"]).replace(tzinfo=timezone.utc)
                    if not lower.date() <= day.date() <= upper.date() or item.get("Value") is None:
                        continue
                    close = float(item["Value"])
                    stamp = int(day.timestamp()*1000)
                    rows[stamp] = [stamp,close,close,close,close,0.0]
                lower = upper.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
        return IndexFetchResult(data=live_index_rows(instrument,[rows[stamp] for stamp in sorted(rows)]),
            source="nasdaq",is_close_only=True)


class DowJonesHistoryProvider:
    # DePaul QRC preserves Dow Jones & Company's original daily files.
    # https://qrc.depaul.edu/Excel_File_Listing_Pages/DowDataList.asp
    FILES = ((1896,1900),(1900,1921),(1921,1946),(1946,1971),(1971,1996))

    def fetch_history(self, instrument, source, start_dt, end_dt):
        if instrument.symbol != "US_DOW":
            return IndexFetchResult(data=[],source="dow-jones-depaul")
        import pandas as pd  # Reuse the installed pandas/xlrd daily readers.

        first = max(start_dt,utc_datetime(live_start_ms(instrument)))
        rows = {}
        with httpx.Client(timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
            headers={"User-Agent":"Mozilla/5.0"}) as client:
            for year,next_year in self.FILES:
                if first.year >= next_year or end_dt.year < year:
                    continue
                response=client.get(f"https://qrc.depaul.edu/Excel_Files/DowData/DJIA{year}.xls")
                response.raise_for_status()
                frame=pd.read_excel(BytesIO(response.content),usecols=[0,1])
                if list(frame.columns)!=["Date","Close"]:
                    raise ValueError("Dow Jones 历史档案列名不匹配")
                days=pd.to_datetime(frame["Date"],format="mixed",errors="coerce",utc=True)
                for day,value in zip(days,frame["Close"]):
                    if pd.isna(day) or pd.isna(value) or not first.date() <= day.date() <= end_dt.date():
                        continue
                    stamp=int(day.timestamp()*1000)
                    close=float(value)
                    # The files have no opening price. Do not invent candles
                    # using the previous close or their partial high/low fields.
                    rows[stamp]=[stamp,close,close,close,close,0.0]
        return IndexFetchResult(data=live_index_rows(instrument,[rows[stamp] for stamp in sorted(rows)]),
            source="dow-jones-depaul",is_close_only=True)
