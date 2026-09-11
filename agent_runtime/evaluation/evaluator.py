from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EvaluationResult:
    intent_schema_validity: float
    policy_risk_linkage_completeness: float
    blocked_unsafe_attempts: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_schema_validity": self.intent_schema_validity,
            "policy_risk_linkage_completeness": self.policy_risk_linkage_completeness,
            "blocked_unsafe_attempts": self.blocked_unsafe_attempts,
        }


class RunEvaluator:
    REQUIRED_INTENT_FIELDS = {
        "intentId",
        "actorType",
        "actorId",
        "action",
        "assetId",
        "purpose",
        "mandateId",
        "policyVersion",
        "correlationId",
        "idempotencyKey",
        "expiresAt",
    }

    def evaluate(self, run_trace: list[dict[str, Any]], blocked_unsafe_attempts: int) -> EvaluationResult:
        intents = [entry.get("intent") for entry in run_trace if entry.get("type") == "financial_intent"]
        if intents:
            valid_count = sum(1 for intent in intents if self.REQUIRED_INTENT_FIELDS.issubset(set(intent.keys())))
            intent_schema_validity = valid_count / len(intents)
            linkage_complete_count = sum(
                1
                for intent in intents
                if intent.get("mandateId") and intent.get("policyVersion") and intent.get("correlationId")
            )
            linkage_score = linkage_complete_count / len(intents)
        else:
            intent_schema_validity = 1.0
            linkage_score = 1.0

        return EvaluationResult(
            intent_schema_validity=intent_schema_validity,
            policy_risk_linkage_completeness=linkage_score,
            blocked_unsafe_attempts=blocked_unsafe_attempts,
        )
