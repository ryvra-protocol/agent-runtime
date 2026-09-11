from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptSafetyResult:
    allowed: bool
    reason: str | None = None


class PromptDefense:
    BLOCKED_PATTERNS = (
        "bypass gateway",
        "direct rpc",
        "ignore policy",
        "disable safety",
        "change mandate",
        "modify capability",
        "increase limits",
        "self-approve",
    )

    def check(self, text: str) -> PromptSafetyResult:
        lowered = text.lower()
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in lowered:
                return PromptSafetyResult(allowed=False, reason=f"PROMPT_BLOCKED:{pattern}")
        return PromptSafetyResult(allowed=True)
