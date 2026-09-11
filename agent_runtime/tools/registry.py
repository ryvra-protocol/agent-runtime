from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from agent_runtime.safety import sanitize_tool_output


class ToolValidationError(ValueError):
    pass


@dataclass
class ToolSpec:
    name: str
    handler: Callable[[dict[str, Any]], str]
    validator: Callable[[dict[str, Any]], None]


class ToolRegistry:
    def __init__(self, profile_allowlist: dict[str, set[str]] | None = None) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._profile_allowlist = profile_allowlist or {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def set_allowlist(self, profile: str, tools: set[str]) -> None:
        self._profile_allowlist[profile] = tools

    def execute(self, profile: str, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name not in self._tools:
            raise ToolValidationError("TOOL_NOT_AVAILABLE")
        allowed = self._profile_allowlist.get(profile, set())
        if tool_name not in allowed:
            raise ToolValidationError("TOOL_NOT_AVAILABLE")

        spec = self._tools[tool_name]
        spec.validator(args)
        output = spec.handler(args)
        return sanitize_tool_output(output)
