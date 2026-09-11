from __future__ import annotations

from collections import deque


class SessionMemory:
    def __init__(self, max_items: int = 20) -> None:
        self._events: deque[dict] = deque(maxlen=max_items)
        self._summaries: list[str] = []

    def add_event(self, event: dict) -> None:
        self._events.append(event)

    def events(self) -> list[dict]:
        return list(self._events)

    def add_summary(self, summary: str) -> None:
        self._summaries.append(summary)

    def summaries(self) -> list[str]:
        return list(self._summaries)
