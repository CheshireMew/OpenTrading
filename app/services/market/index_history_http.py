from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timedelta, timezone

import requests

from app.domain.market.index_catalog import IndexInstrument
from app.services.market.index_history_contracts import IndexFetchResult
from app.services.market.index_history_parsing import IndexHistoryParsing
from app.services.market.index_source_catalog import IndexSourceBinding
from config import settings


class EastmoneyIndexHistoryProvider(IndexHistoryParsing):
    def fetch_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.eastmoney_secid:
            return IndexFetchResult(data=[], source="eastmoney")

        params = {
            "secid": source.eastmoney_secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
            "klt": "101",
            "fqt": "0",
            "beg": start_dt.strftime("%Y%m%d"),
            "end": end_dt.strftime("%Y%m%d"),
        }
        response = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.get(
                    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
                    timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
                )
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
        if response is None:
            raise last_error or RuntimeError("Eastmoney request failed")
        response.raise_for_status()
        payload = response.json()
        rows = ((payload.get("data") or {}).get("klines") or [])
        return IndexFetchResult(
            data=[self.parse_eastmoney_row(row) for row in rows],
            source="eastmoney",
        )


class SohuIndexHistoryProvider(IndexHistoryParsing):
    def fetch_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.sohu_code:
            return IndexFetchResult(data=[], source="sohu")

        response = requests.get(
            "https://q.stock.sohu.com/hisHq",
            params={
                "code": source.sohu_code,
                "start": start_dt.strftime("%Y%m%d"),
                "end": end_dt.strftime("%Y%m%d"),
                "stat": "1",
                "order": "D",
                "period": "d",
                "rt": "json",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return IndexFetchResult(data=[], source="sohu")

        rows = payload[0].get("hq") or []
        data = [self.parse_sohu_row(row) for row in rows if len(row) >= 8]
        data.sort(key=lambda item: item[0])
        return IndexFetchResult(data=data, source="sohu")


class BaostockIndexHistoryProvider(IndexHistoryParsing):
    def fetch_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.baostock_code:
            return IndexFetchResult(data=[], source="baostock")

        try:
            import baostock as bs
        except ImportError:
            return IndexFetchResult(data=[], source="baostock")

        login_result = bs.login()
        if login_result.error_code != "0":
            return IndexFetchResult(data=[], source="baostock")

        try:
            query = bs.query_history_k_data_plus(
                source.baostock_code,
                "date,open,high,low,close,volume",
                start_date=start_dt.strftime("%Y-%m-%d"),
                end_date=end_dt.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="3",
            )
            if query.error_code != "0":
                return IndexFetchResult(data=[], source="baostock")

            data: list[list[float]] = []
            while query.next():
                row = query.get_row_data()
                if len(row) < 6 or not row[1] or not row[4]:
                    continue
                row_dt = self.parse_date(row[0])
                data.append([
                    self.to_ms(row_dt),
                    float(row[1]),
                    float(row[2]),
                    float(row[3]),
                    float(row[4]),
                    float(row[5] or 0.0),
                ])
            return IndexFetchResult(data=data, source="baostock")
        finally:
            bs.logout()


class CboeIndexHistoryProvider(IndexHistoryParsing):
    def fetch_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.cboe_csv_url:
            return IndexFetchResult(data=[], source="cboe")

        response = requests.get(
            source.cboe_csv_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        close_only = "OPEN" not in (reader.fieldnames or [])
        value_column = next((name for name in (reader.fieldnames or []) if name != "DATE"), None)
        data: list[list[float]] = []
        for row in reader:
            date_text = row.get("DATE")
            if not date_text or not value_column:
                continue
            row_dt = datetime.strptime(date_text, "%m/%d/%Y").replace(tzinfo=timezone.utc)
            if row_dt < start_dt or row_dt > end_dt:
                continue
            if close_only:
                value = float(row[value_column])
                data.append([self.to_ms(row_dt), value, value, value, value, 0.0])
                continue
            data.append([
                self.to_ms(row_dt),
                float(row["OPEN"]),
                float(row["HIGH"]),
                float(row["LOW"]),
                float(row["CLOSE"]),
                0.0,
            ])
        return IndexFetchResult(data=data, source="cboe", is_close_only=close_only)


class YFinanceIndexHistoryProvider(IndexHistoryParsing):
    def fetch_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.yfinance_symbol:
            return IndexFetchResult(data=[], source="yfinance")

        import yfinance as yf

        history = yf.Ticker(source.yfinance_symbol).history(
            start=start_dt.strftime("%Y-%m-%d"),
            end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
        )
        if history.empty:
            return IndexFetchResult(data=[], source="yfinance")

        data: list[list[float]] = []
        for row_date, row in history.iterrows():
            if row[["Open", "High", "Low", "Close"]].isna().any():
                continue
            ts = self.date_to_ms(row_date.to_pydatetime())
            data.append([
                ts,
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                float(row.get("Volume") or 0.0),
            ])
        return IndexFetchResult(data=data, source="yfinance")
