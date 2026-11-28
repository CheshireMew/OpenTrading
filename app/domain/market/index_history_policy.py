"""Actual index observations only: no pre-launch back series or proxy candles."""
from datetime import datetime, timezone
import math

from app.domain.market.index_catalog import INDEX_CATALOG, IndexInstrument
from app.domain.market.candles import utc_datetime as utc_datetime


def live_start_ms(instrument: IndexInstrument | str) -> int:
    item = INDEX_CATALOG[instrument] if isinstance(instrument, str) else instrument
    if not item.launch_date:
        return 0
    return int(datetime.fromisoformat(item.launch_date).replace(tzinfo=timezone.utc).timestamp() * 1000)


def valid_index_row(row) -> bool:
    if len(row) < 6:
        return False
    opened, high, low, close, volume = map(float, row[1:6])
    # Older vendor floats can differ by less than one declared 0.01 index point.
    return (all(math.isfinite(value) for value in (opened, high, low, close, volume))
        and min(opened,high,low,close)>0 and volume>=0
        and round(low,2) <= min(round(opened,2),round(close,2)) <= max(round(opened,2),round(close,2)) <= round(high,2))


def full_index_row(row) -> bool:
    return valid_index_row(row) and not (row[1] == row[2] == row[3] == row[4] and not row[5])


def live_index_rows(instrument, rows, *, full_only=False):
    start = live_start_ms(instrument)
    valid = full_index_row if full_only else valid_index_row
    return [row for row in rows if row[0] >= start and valid(row)]
