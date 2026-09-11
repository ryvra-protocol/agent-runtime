from __future__ import annotations

from abc import ABC, abstractmethod

from agent_runtime.types import PlanStep


class ModelAdapter(ABC):
    @abstractmethod
    def decompose_task(self, task: str) -> list[PlanStep]:
        raise NotImplementedError
