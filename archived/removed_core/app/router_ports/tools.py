from __future__ import annotations

from typing import Any, Protocol

from app.contracts.tools import ComparePairsCommand, SimulateDcaCommand


class ToolsAppPort(Protocol):
    async def simulate_dca(self, command: SimulateDcaCommand) -> dict[str, Any]: ...
    async def compare_pairs(self, command: ComparePairsCommand) -> dict[str, Any]: ...
