from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


ModelCallStatus = Literal["success", "unavailable", "failed", "refused"]
ModelOutputT = TypeVar("ModelOutputT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ModelCallResult(Generic[ModelOutputT]):
    status: ModelCallStatus
    output: ModelOutputT | None
    error_code: str | None
    request_id: str

    @property
    def succeeded(self) -> bool:
        return self.status == "success" and self.output is not None


class MarketAnalysisModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: int = Field(ge=0, le=100)
    reasoning: str = Field(min_length=1, max_length=1000)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)


