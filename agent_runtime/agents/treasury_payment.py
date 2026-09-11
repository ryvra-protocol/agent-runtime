from __future__ import annotations

from dataclasses import dataclass, field

from agent_runtime.types import AutonomyLevel, FinancialIntent, IntentAction, RuntimeContext


class AgentPolicyError(ValueError):
    pass


@dataclass
class TreasuryPaymentLimits:
    per_tx: float
    per_window: float
    per_counterparty: dict[str, float] = field(default_factory=dict)


@dataclass
class TreasuryPaymentAgent:
    actor_id: str
    limits: TreasuryPaymentLimits
    allowed_actions: set[IntentAction] = field(
        default_factory=lambda: {
            IntentAction.PAY,
            IntentAction.TRANSFER,
            IntentAction.COLLECT,
            IntentAction.REBALANCE,
        }
    )
    allowed_autonomy: set[AutonomyLevel] = field(default_factory=lambda: {AutonomyLevel.A1, AutonomyLevel.A2})

    def validate_context(self, context: RuntimeContext) -> None:
        if context.actor_id != self.actor_id:
            raise AgentPolicyError("ACTOR_MISMATCH")
        if not context.mandate_id:
            raise AgentPolicyError("MANDATE_REQUIRED")
        if not context.capability_ids:
            raise AgentPolicyError("CAPABILITY_REQUIRED")
        if context.autonomy_level not in self.allowed_autonomy:
            raise AgentPolicyError("AUTONOMY_LEVEL_NOT_ALLOWED")

    def create_intent(
        self,
        *,
        context: RuntimeContext,
        action: str,
        asset_id: str,
        purpose: str,
        amount: float | None,
        recipient: str | None = None,
        chain_id: str | None = None,
        venue: str | None = None,
        spent_in_window: float = 0.0,
    ) -> FinancialIntent:
        self.validate_context(context)

        try:
            action_enum = IntentAction(action)
        except ValueError as exc:
            raise AgentPolicyError("UNSUPPORTED_ACTION") from exc
        if action_enum not in self.allowed_actions:
            raise AgentPolicyError("UNSUPPORTED_ACTION")

        review_required = False
        review_reasons: list[str] = []
        normalized_amount: float | None = amount

        if amount is not None:
            try:
                normalized_amount = float(amount)
            except (TypeError, ValueError) as exc:
                raise AgentPolicyError("INVALID_AMOUNT") from exc
            if normalized_amount <= 0:
                raise AgentPolicyError("INVALID_AMOUNT")

        if normalized_amount is not None:
            if normalized_amount > self.limits.per_tx:
                review_required = True
                review_reasons.append("PER_TX_LIMIT_EXCEEDED")
            if spent_in_window + normalized_amount > self.limits.per_window:
                review_required = True
                review_reasons.append("WINDOW_LIMIT_EXCEEDED")
            if (
                recipient
                and recipient in self.limits.per_counterparty
                and normalized_amount > self.limits.per_counterparty[recipient]
            ):
                review_required = True
                review_reasons.append("COUNTERPARTY_LIMIT_EXCEEDED")

        review_reason = ",".join(review_reasons) if review_reasons else None

        return FinancialIntent.create(
            actor_id=context.actor_id,
            action=action_enum,
            asset_id=asset_id,
            amount=normalized_amount,
            chain_id=chain_id,
            recipient=recipient,
            venue=venue,
            purpose=purpose,
            mandate_id=context.mandate_id,
            policy_version=context.policy_version,
            correlation_id=context.correlation_id,
            review_required=review_required,
            review_reason=review_reason,
        )
