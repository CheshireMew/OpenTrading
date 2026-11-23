from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Self, SupportsIndex


class FrozenDict(dict):
    """A JSON-compatible dictionary whose contents cannot change after construction."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("frozen mapping cannot be modified")

    __delitem__ = _immutable
    __setitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable  # type: ignore[assignment]
    setdefault = _immutable
    update = _immutable

    def __deepcopy__(self, _memo: dict[int, Any]) -> FrozenDict:
        return self


class FrozenList(list[Any]):
    """A JSON-compatible list whose contents cannot change after construction."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("frozen sequence cannot be modified")

    __delitem__ = _immutable
    __setitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable

    def __iadd__(self, _values: Iterable[Any]) -> Self:  # type: ignore[misc]
        raise TypeError("frozen sequence cannot be modified")

    def __imul__(self, _value: SupportsIndex) -> Self:
        raise TypeError("frozen sequence cannot be modified")

    def __deepcopy__(self, _memo: dict[int, Any]) -> FrozenList:
        return self


def deep_freeze(value: Any) -> Any:
    """Recursively freeze JSON-shaped values while retaining JSON serialization."""

    if isinstance(value, (FrozenDict, FrozenList)):
        return value
    if isinstance(value, Mapping):
        return FrozenDict((key, deep_freeze(item)) for key, item in value.items())
    if isinstance(value, list):
        return FrozenList(deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    return value
