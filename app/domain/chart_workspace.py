"""Versioned workspace values independent of HTTP and persistence."""
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceConflict(ValueError):
    pass


class WorkspaceDocument(BaseModel):
    id: str
    name: str
    version: int
    data: dict[str, Any]
    updated_at: int
    readonly: bool = False


class WorkspaceWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    data: dict[str, Any]
    expected_version: int = Field(0, ge=0)
