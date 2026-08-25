from __future__ import annotations


class ResearchNotFoundError(Exception):
    """The requested research record does not exist in the requested state."""


class ResearchRevisionConflictError(Exception):
    """The caller attempted to overwrite a newer research record."""


class ResearchDuplicateError(Exception):
    """A uniqueness rule would be violated by the requested research record."""
