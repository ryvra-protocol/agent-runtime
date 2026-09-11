from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class IntentAction(str, Enum):
    PAY = "PAY"
    TRANSFER = "TRANSFER"
    COLLECT = "COLLECT"
    REBALANCE = "REBALANCE"
    TRADE = "TRADE"
    OPEN_POSITION = "OPEN_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"


class AutonomyLevel(str, Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"


class AgentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class IntentState(str, Enum):
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REVIEW = "REVIEW"
    DENIED = "DENIED"
    CHALLENGE = "CHALLENGE"
    DELAY = "DELAY"
    QUARANTINE = "QUARANTINE"
    KILLSWITCH = "KILLSWITCH"


class ProfileType(str, Enum):
    TREASURY = "TREASURY_AGENT"
    PORTFOLIO = "PORTFOLIO_AGENT"
    PROCUREMENT = "PROCUREMENT_AGENT"
    MARKET = "MARKET_AGENT"
    SETTLEMENT = "SETTLEMENT_AGENT"


class EscalationState(str, Enum):
    NONE = "NONE"
    REVIEW = "REVIEW"
    CHALLENGE = "CHALLENGE"
    DELAY = "DELAY"
    QUARANTINE = "QUARANTINE"
    PAUSED = "PAUSED"
    HALTED = "HALTED"


@dataclass(frozen=True)
class FinancialIntent:
    intentId: str
    actorType: str
    actorId: str
    action: str
    assetId: str
    purpose: str
    mandateId: str
    policyVersion: str
    correlationId: str
    idempotencyKey: str
    expiresAt: str
    amount: float | None = None
    chainId: str | None = None
    recipient: str | None = None
    venue: str | None = None
    instrumentId: str | None = None
    reviewRequired: bool = False
    reviewReason: str | None = None

    @classmethod
    def create(
        cls,
        *,
        actor_id: str,
        action: IntentAction,
        asset_id: str,
        purpose: str,
        mandate_id: str,
        policy_version: str,
        correlation_id: str,
        amount: float | None = None,
        chain_id: str | None = None,
        recipient: str | None = None,
        venue: str | None = None,
        instrument_id: str | None = None,
        ttl_minutes: int = 30,
        review_required: bool = False,
        review_reason: str | None = None,
    ) -> "FinancialIntent":
        now = datetime.now(timezone.utc)
        return cls(
            intentId=str(uuid4()),
            actorType="AGENT",
            actorId=actor_id,
            action=action.value,
            assetId=asset_id,
            amount=amount,
            chainId=chain_id,
            recipient=recipient,
            venue=venue,
            instrumentId=instrument_id,
            purpose=purpose,
            mandateId=mandate_id,
            policyVersion=policy_version,
            correlationId=correlation_id,
            idempotencyKey=str(uuid4()),
            expiresAt=(now + timedelta(minutes=ttl_minutes)).isoformat(),
            reviewRequired=review_required,
            reviewReason=review_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intentId": self.intentId,
            "actorType": self.actorType,
            "actorId": self.actorId,
            "action": self.action,
            "assetId": self.assetId,
            "amount": self.amount,
            "chainId": self.chainId,
            "recipient": self.recipient,
            "venue": self.venue,
            "instrumentId": self.instrumentId,
            "purpose": self.purpose,
            "mandateId": self.mandateId,
            "policyVersion": self.policyVersion,
            "correlationId": self.correlationId,
            "idempotencyKey": self.idempotencyKey,
            "expiresAt": self.expiresAt,
            "reviewRequired": self.reviewRequired,
            "reviewReason": self.reviewReason,
        }


@dataclass
class PlanStep:
    id: str
    description: str
    kind: str
    tool: str | None = None
    action: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeContext:
    session_id: str
    task_id: str
    actor_id: str
    mandate_id: str
    capability_ids: list[str]
    policy_version: str
    profile_type: ProfileType = ProfileType.TREASURY
    autonomy_level: AutonomyLevel = AutonomyLevel.A1
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
