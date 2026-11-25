"""UTC timestamps at the API and persisted JSON boundaries."""
from datetime import date, datetime
import json
from typing import Any

from pydantic import BaseModel, field_validator
from utils.time import as_utc


def utc_datetime(value: datetime) -> datetime:
    return as_utc(value)


class UtcResponseModel(BaseModel):
    @field_validator("*", mode="after")
    @classmethod
    def normalize_timestamp(cls, value: Any) -> Any:
        return utc_datetime(value) if isinstance(value, datetime) else value


def json_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    def encode(item: Any) -> str:
        if isinstance(item, datetime):
            return utc_datetime(item).isoformat()
        if isinstance(item, date):
            return item.isoformat()
        raise TypeError(f"Unsupported snapshot value: {type(item).__name__}")

    return json.loads(json.dumps(value, default=encode, allow_nan=False))
