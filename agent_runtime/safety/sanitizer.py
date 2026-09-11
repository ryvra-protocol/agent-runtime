from __future__ import annotations

import re


def sanitize_tool_output(output: str) -> str:
    cleaned = output
    cleaned = re.sub(r"(?i)(api[_-]?key|secret|token)\s*([:=])\s*(\S+)", r"\1\2[REDACTED]", cleaned)
    cleaned = re.sub(r"(?i)(ignore previous instructions|escalate privileges|bypass policy)", "[BLOCKED]", cleaned)
    return cleaned.strip()
