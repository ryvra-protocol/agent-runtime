from __future__ import annotations

from agent_runtime.adapters.base import ModelAdapter
from agent_runtime.types import PlanStep


class StubModelAdapter(ModelAdapter):
    """Config-driven deterministic adapter stub."""

    def __init__(self, default_tool: str = "search_docs") -> None:
        self.default_tool = default_tool

    def decompose_task(self, task: str) -> list[PlanStep]:
        steps: list[PlanStep] = []
        for index, raw in enumerate([x.strip() for x in task.split(";") if x.strip()], start=1):
            step_id = f"step-{index}"
            lowered = raw.lower()
            if any(word in lowered for word in ["pay", "transfer", "collect", "rebalance", "trade", "open position", "close position"]):
                action = "PAY"
                for candidate, resolved in (
                    ("open position", "OPEN_POSITION"),
                    ("close position", "CLOSE_POSITION"),
                    ("rebalance", "REBALANCE"),
                    ("collect", "COLLECT"),
                    ("transfer", "TRANSFER"),
                    ("trade", "TRADE"),
                    ("pay", "PAY"),
                ):
                    if candidate in lowered:
                        action = resolved
                        break
                recipient = None
                if action in {"PAY", "TRANSFER", "COLLECT"} and " to " in lowered:
                    recipient = raw.lower().split(" to ", 1)[1].split()[0]
                elif action in {"PAY", "TRANSFER", "COLLECT"}:
                    parts = raw.split()
                    if len(parts) >= 2 and parts[0].lower() in {"pay", "transfer", "collect"}:
                        recipient = parts[1]
                venue = "NASDAQ" if "nasdaq" in lowered else None
                instrument_id = None
                if action in {"TRADE", "OPEN_POSITION", "CLOSE_POSITION"}:
                    parts = raw.split()
                    if len(parts) >= 2:
                        instrument_id = parts[-1].upper()
                steps.append(
                    PlanStep(
                        id=step_id,
                        description=raw,
                        kind="financial",
                        action=action,
                        params={"purpose": raw, "assetId": "USD", "recipient": recipient, "venue": venue, "instrumentId": instrument_id},
                    )
                )
            else:
                steps.append(
                    PlanStep(
                        id=step_id,
                        description=raw,
                        kind="tool",
                        tool=self.default_tool,
                        params={"query": raw},
                    )
                )

        if not steps:
            steps.append(
                PlanStep(
                    id="step-1",
                    description="Analyze task",
                    kind="tool",
                    tool=self.default_tool,
                    params={"query": task},
                )
            )
        return steps
