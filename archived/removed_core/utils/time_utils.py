from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive_datetime(value: Any) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.to_pydatetime().replace(tzinfo=None)
    # Database timestamps are stored as UTC without tzinfo, so every runtime path
    # must strip timezone only after converting to UTC.
    return timestamp.tz_convert("UTC").to_pydatetime().replace(tzinfo=None)
