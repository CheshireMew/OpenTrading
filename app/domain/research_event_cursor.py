from datetime import datetime, timezone
import re

EventCursorKey = tuple[datetime, datetime, str]


def parse_event_cursor(value: str | None) -> EventCursorKey | None:
    if value is None:
        return None
    try:
        version, occurred, created, identity = value.split("|")
        if len(value) > 300 or version != "1" or not re.fullmatch(r"[\w-]{1,120}", identity, flags=re.ASCII):
            raise ValueError
        dates = [datetime.fromisoformat(item.replace("Z", "+00:00")) for item in (occurred, created)]
        if any(item.tzinfo is None for item in dates):
            raise ValueError
        return (*(item.astimezone(timezone.utc).replace(tzinfo=None) for item in dates), identity)
    except (ValueError, TypeError):
        raise ValueError("Invalid research event cursor") from None


def event_cursor(occurred: datetime, created: datetime, identity: str) -> str:
    def stamp(value: datetime) -> str:
        return value.replace(tzinfo=timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return f"1|{stamp(occurred)}|{stamp(created)}|{identity}"
