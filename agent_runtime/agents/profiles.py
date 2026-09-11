from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent_runtime.types import AutonomyLevel, FinancialIntent, IntentAction, ProfileType, RuntimeContext


class AgentPolicyError(ValueError):
    pass


AUTONOMY_ORDER = {
    AutonomyLevel.A0: 0,
    AutonomyLevel.A1: 1,
    AutonomyLevel.A2: 2,
    AutonomyLevel.A3: 3,
}


@dataclass(frozen=True)
class RunawayLimits:
    max_actions_per_run: int = 8
    max_retries: int = 2
    max_duration_seconds: int = 120
    max_denials: int = 2


@dataclass(frozen=True)
class ProfileConfig:
    profile_type: ProfileType
    profile_name: str
    profile_version: str
    allowed_actions: set[IntentAction]
    allowed_tools: set[str]
    autonomy_cap: AutonomyLevel
    mandatory_approval_conditions: set[str] = field(default_factory=set)
    forbidden_operations: set[str] = field(
        default_factory=lambda: {
            "bypass gateway",
            "direct rpc",
            "disable safety",
            "ignore policy",
            "change mandate",
            "modify capability",
            "increase limits",
            "self-approve",
            "raise autonomy",
            "change profile",
        }
    )
    runaway_limits: RunawayLimits = field(default_factory=RunawayLimits)


@dataclass(frozen=True)
class TreasuryAgentControls:
    per_tx: float
    per_window: float
    per_counterparty: dict[str, float] = field(default_factory=dict)
    cash_balance_floor: float = 0.0
    available_balances: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioAgentControls:
    max_drift_band: float
    concentration_limits: dict[str, float] = field(default_factory=dict)
    risk_budget: float = 0.0
    current_risk_usage: float = 0.0


@dataclass(frozen=True)
class ProcurementAgentControls:
    vendor_allowlist: set[str] = field(default_factory=set)
    require_invoice_reference: bool = True


@dataclass(frozen=True)
class MarketAgentControls:
    venue_allowlist: set[str] = field(default_factory=set)
    instrument_allowlist: set[str] = field(default_factory=set)
    max_exposure: float = 0.0
    max_leverage: float = 1.0
    allowed_execution_modes: set[str] = field(default_factory=lambda: {"BROKERED", "DARK"})
    allowed_privacy_modes: set[str] = field(default_factory=lambda: {"MASKED", "PRIVATE"})


@dataclass(frozen=True)
class SettlementAgentControls:
    reconciliation_mismatch_threshold: float


@dataclass
class AgentProfile:
    actor_id: str
    config: ProfileConfig

    def validate_context(self, context: RuntimeContext) -> None:
        if context.actor_id != self.actor_id:
            raise AgentPolicyError("ACTOR_MISMATCH")
        if context.profile_type != self.config.profile_type:
            raise AgentPolicyError("PROFILE_TYPE_MISMATCH")
        if not context.mandate_id:
            raise AgentPolicyError("MANDATE_REQUIRED")
        if not context.capability_ids:
            raise AgentPolicyError("CAPABILITY_REQUIRED")
        if AUTONOMY_ORDER[context.autonomy_level] > AUTONOMY_ORDER[self.config.autonomy_cap]:
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
        instrument_id: str | None = None,
        spent_in_window: float = 0.0,
        run_state: dict[str, Any] | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> FinancialIntent:
        self.validate_context(context)
        if context.autonomy_level == AutonomyLevel.A0:
            raise AgentPolicyError("AUTONOMY_LEVEL_NOT_ALLOWED")

        try:
            action_enum = IntentAction(action)
        except ValueError as exc:
            raise AgentPolicyError("UNSUPPORTED_ACTION") from exc
        if action_enum not in self.config.allowed_actions:
            raise AgentPolicyError("UNSUPPORTED_ACTION")

        self._check_forbidden_operation(" ".join([purpose, action, recipient or "", venue or "", instrument_id or ""]))
        normalized_amount = self._normalize_amount(amount)
        review_reasons = self._evaluate_review_reasons(
            action=action_enum,
            asset_id=asset_id,
            purpose=purpose,
            amount=normalized_amount,
            recipient=recipient,
            chain_id=chain_id,
            venue=venue,
            instrument_id=instrument_id,
            spent_in_window=spent_in_window,
            run_state=run_state or {},
            extra_params=extra_params or {},
        )
        review_required = bool(review_reasons)
        review_reason = ",".join(review_reasons) if review_reasons else None
        return FinancialIntent.create(
            actor_id=context.actor_id,
            action=action_enum,
            asset_id=asset_id,
            amount=normalized_amount,
            chain_id=chain_id,
            recipient=recipient,
            venue=venue,
            instrument_id=instrument_id,
            purpose=purpose,
            mandate_id=context.mandate_id,
            policy_version=context.policy_version,
            correlation_id=context.correlation_id,
            review_required=review_required,
            review_reason=review_reason,
        )

    def _normalize_amount(self, amount: float | None) -> float | None:
        if amount is None:
            return None
        try:
            normalized_amount = float(amount)
        except (TypeError, ValueError) as exc:
            raise AgentPolicyError("INVALID_AMOUNT") from exc
        if normalized_amount <= 0:
            raise AgentPolicyError("INVALID_AMOUNT")
        return normalized_amount

    def _check_forbidden_operation(self, text: str) -> None:
        lowered = text.lower()
        for forbidden in self.config.forbidden_operations:
            if forbidden in lowered:
                raise AgentPolicyError("FORBIDDEN_OPERATION")

    def _evaluate_review_reasons(
        self,
        *,
        action: IntentAction,
        asset_id: str,
        purpose: str,
        amount: float | None,
        recipient: str | None,
        chain_id: str | None,
        venue: str | None,
        instrument_id: str | None,
        spent_in_window: float,
        run_state: dict[str, Any],
        extra_params: dict[str, Any],
    ) -> list[str]:
        return []


@dataclass
class TreasuryAgentProfile(AgentProfile):
    controls: TreasuryAgentControls

    def __init__(self, *, actor_id: str, controls: TreasuryAgentControls, profile_version: str = "10.0") -> None:
        super().__init__(
            actor_id=actor_id,
            config=ProfileConfig(
                profile_type=ProfileType.TREASURY,
                profile_name="TreasuryAgent",
                profile_version=profile_version,
                allowed_actions={IntentAction.PAY, IntentAction.TRANSFER, IntentAction.REBALANCE, IntentAction.COLLECT},
                allowed_tools={"search_docs", "calc", "balance_sheet"},
                autonomy_cap=AutonomyLevel.A2,
                mandatory_approval_conditions={"PER_TX_LIMIT_EXCEEDED", "WINDOW_LIMIT_EXCEEDED", "COUNTERPARTY_LIMIT_EXCEEDED", "CASH_FLOOR_BREACH"},
            ),
        )
        self.controls = controls

    def _evaluate_review_reasons(self, **kwargs: Any) -> list[str]:
        amount = kwargs["amount"]
        recipient = kwargs["recipient"]
        asset_id = kwargs["asset_id"]
        spent_in_window = kwargs["spent_in_window"]
        reasons: list[str] = []
        if amount is None:
            return reasons
        if amount > self.controls.per_tx:
            reasons.append("PER_TX_LIMIT_EXCEEDED")
        if spent_in_window + amount > self.controls.per_window:
            reasons.append("WINDOW_LIMIT_EXCEEDED")
        if recipient and recipient in self.controls.per_counterparty and amount > self.controls.per_counterparty[recipient]:
            reasons.append("COUNTERPARTY_LIMIT_EXCEEDED")
        available = self.controls.available_balances.get(asset_id)
        if available is not None and available - amount < self.controls.cash_balance_floor:
            reasons.append("CASH_FLOOR_BREACH")
        return reasons


@dataclass
class PortfolioAgentProfile(AgentProfile):
    controls: PortfolioAgentControls

    def __init__(self, *, actor_id: str, controls: PortfolioAgentControls, profile_version: str = "10.0") -> None:
        super().__init__(
            actor_id=actor_id,
            config=ProfileConfig(
                profile_type=ProfileType.PORTFOLIO,
                profile_name="PortfolioAgent",
                profile_version=profile_version,
                allowed_actions={IntentAction.REBALANCE, IntentAction.TRADE, IntentAction.COLLECT},
                allowed_tools={"search_docs", "calc", "risk_check"},
                autonomy_cap=AutonomyLevel.A2,
                mandatory_approval_conditions={"DRIFT_BAND_EXCEEDED", "CONCENTRATION_LIMIT_EXCEEDED", "RISK_BUDGET_EXCEEDED"},
            ),
        )
        self.controls = controls

    def _evaluate_review_reasons(self, **kwargs: Any) -> list[str]:
        extra_params = kwargs["extra_params"]
        instrument_id = kwargs["instrument_id"] or kwargs["asset_id"]
        reasons: list[str] = []
        drift = extra_params.get("drift")
        if drift is not None and abs(float(drift)) > self.controls.max_drift_band:
            reasons.append("DRIFT_BAND_EXCEEDED")
        concentration = extra_params.get("concentration")
        limit = self.controls.concentration_limits.get(str(instrument_id))
        if concentration is not None and limit is not None and float(concentration) > limit:
            reasons.append("CONCENTRATION_LIMIT_EXCEEDED")
        risk_cost = float(extra_params.get("riskCost", 0.0))
        if self.controls.current_risk_usage + risk_cost > self.controls.risk_budget:
            reasons.append("RISK_BUDGET_EXCEEDED")
        return reasons


@dataclass
class ProcurementAgentProfile(AgentProfile):
    controls: ProcurementAgentControls

    def __init__(self, *, actor_id: str, controls: ProcurementAgentControls, profile_version: str = "10.0") -> None:
        super().__init__(
            actor_id=actor_id,
            config=ProfileConfig(
                profile_type=ProfileType.PROCUREMENT,
                profile_name="ProcurementAgent",
                profile_version=profile_version,
                allowed_actions={IntentAction.PAY, IntentAction.TRANSFER},
                allowed_tools={"search_docs", "calc", "invoice_lookup"},
                autonomy_cap=AutonomyLevel.A1,
                mandatory_approval_conditions={"VENDOR_NOT_ALLOWLISTED", "INVOICE_REFERENCE_REQUIRED"},
            ),
        )
        self.controls = controls

    def _evaluate_review_reasons(self, **kwargs: Any) -> list[str]:
        recipient = kwargs["recipient"]
        extra_params = kwargs["extra_params"]
        purpose = kwargs["purpose"]
        reasons: list[str] = []
        if recipient and self.controls.vendor_allowlist and recipient not in self.controls.vendor_allowlist:
            reasons.append("VENDOR_NOT_ALLOWLISTED")
        invoice_ref = extra_params.get("invoiceRef") or self._extract_invoice_ref(str(purpose))
        if self.controls.require_invoice_reference and not invoice_ref:
            reasons.append("INVOICE_REFERENCE_REQUIRED")
        return reasons

    @staticmethod
    def _extract_invoice_ref(purpose: str) -> str | None:
        match = re.search(r"invoice[\s:#-]*([A-Za-z0-9-]+)", purpose, re.IGNORECASE)
        if not match:
            return None
        candidate = match.group(1).strip()
        if not candidate or not any(char.isdigit() for char in candidate):
            return None
        return candidate


@dataclass
class MarketAgentProfile(AgentProfile):
    controls: MarketAgentControls

    def __init__(self, *, actor_id: str, controls: MarketAgentControls, profile_version: str = "10.0") -> None:
        super().__init__(
            actor_id=actor_id,
            config=ProfileConfig(
                profile_type=ProfileType.MARKET,
                profile_name="MarketAgent",
                profile_version=profile_version,
                allowed_actions={IntentAction.TRADE, IntentAction.OPEN_POSITION, IntentAction.CLOSE_POSITION},
                allowed_tools={"search_docs", "calc", "market_data"},
                autonomy_cap=AutonomyLevel.A1,
                mandatory_approval_conditions={"VENUE_NOT_ALLOWLISTED", "INSTRUMENT_NOT_ALLOWLISTED", "EXPOSURE_LIMIT_EXCEEDED", "LEVERAGE_LIMIT_EXCEEDED", "EXECUTION_MODE_NOT_ALLOWED", "PRIVACY_MODE_NOT_ALLOWED"},
            ),
        )
        self.controls = controls

    def _evaluate_review_reasons(self, **kwargs: Any) -> list[str]:
        venue = kwargs["venue"]
        instrument_id = kwargs["instrument_id"]
        extra_params = kwargs["extra_params"]
        reasons: list[str] = []
        if venue and self.controls.venue_allowlist and venue not in self.controls.venue_allowlist:
            reasons.append("VENUE_NOT_ALLOWLISTED")
        if instrument_id and self.controls.instrument_allowlist and instrument_id not in self.controls.instrument_allowlist:
            reasons.append("INSTRUMENT_NOT_ALLOWLISTED")
        exposure = extra_params.get("exposure")
        if exposure is not None and float(exposure) > self.controls.max_exposure:
            reasons.append("EXPOSURE_LIMIT_EXCEEDED")
        leverage = extra_params.get("leverage")
        if leverage is not None and float(leverage) > self.controls.max_leverage:
            reasons.append("LEVERAGE_LIMIT_EXCEEDED")
        execution_mode = extra_params.get("executionMode")
        if execution_mode and str(execution_mode) not in self.controls.allowed_execution_modes:
            reasons.append("EXECUTION_MODE_NOT_ALLOWED")
        privacy_mode = extra_params.get("privacyMode")
        if privacy_mode and str(privacy_mode) not in self.controls.allowed_privacy_modes:
            reasons.append("PRIVACY_MODE_NOT_ALLOWED")
        return reasons


@dataclass
class SettlementAgentProfile(AgentProfile):
    controls: SettlementAgentControls

    def __init__(self, *, actor_id: str, controls: SettlementAgentControls, profile_version: str = "10.0") -> None:
        super().__init__(
            actor_id=actor_id,
            config=ProfileConfig(
                profile_type=ProfileType.SETTLEMENT,
                profile_name="SettlementAgent",
                profile_version=profile_version,
                allowed_actions={IntentAction.COLLECT, IntentAction.TRANSFER},
                allowed_tools={"search_docs", "calc", "reconcile_ledger"},
                autonomy_cap=AutonomyLevel.A1,
                mandatory_approval_conditions={"OPS_RESTRICTED_TRANSFER", "RECONCILIATION_MISMATCH"},
            ),
        )
        self.controls = controls

    def _evaluate_review_reasons(self, **kwargs: Any) -> list[str]:
        action = kwargs["action"]
        extra_params = kwargs["extra_params"]
        reasons: list[str] = []
        if action == IntentAction.TRANSFER:
            reasons.append("OPS_RESTRICTED_TRANSFER")
        mismatch = extra_params.get("mismatchAmount")
        if mismatch is not None and float(mismatch) > self.controls.reconciliation_mismatch_threshold:
            reasons.append("RECONCILIATION_MISMATCH")
        return reasons
