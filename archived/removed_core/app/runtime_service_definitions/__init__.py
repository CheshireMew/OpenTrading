from __future__ import annotations

from app.runtime_definition import RuntimeServiceDefinition

from .infra import INFRA_SERVICE_DEFINITIONS
from .market import MARKET_SERVICE_DEFINITIONS
from .system import SYSTEM_SERVICE_DEFINITIONS
from .tools import TOOL_SERVICE_DEFINITIONS


RUNTIME_SERVICE_DEFINITIONS: tuple[RuntimeServiceDefinition, ...] = (
    *INFRA_SERVICE_DEFINITIONS,
    *MARKET_SERVICE_DEFINITIONS,
    *TOOL_SERVICE_DEFINITIONS,
    *SYSTEM_SERVICE_DEFINITIONS,
)
