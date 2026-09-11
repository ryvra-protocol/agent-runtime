from __future__ import annotations

from agent_runtime.adapters.base import ModelAdapter
from agent_runtime.types import PlanStep


class TaskPlanner:
    def __init__(self, model_adapter: ModelAdapter) -> None:
        self.model_adapter = model_adapter

    def create_plan(self, task: str) -> list[PlanStep]:
        return self.model_adapter.decompose_task(task)
