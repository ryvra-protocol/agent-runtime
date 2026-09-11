from __future__ import annotations

from agent_runtime.agents.profiles import AgentPolicyError, TreasuryAgentControls, TreasuryAgentProfile


class TreasuryPaymentLimits(TreasuryAgentControls):
    pass


class TreasuryPaymentAgent(TreasuryAgentProfile):
    def __init__(self, *, actor_id: str, limits: TreasuryPaymentLimits, profile_version: str = "10.0") -> None:
        super().__init__(actor_id=actor_id, controls=limits, profile_version=profile_version)


__all__ = ["AgentPolicyError", "TreasuryPaymentAgent", "TreasuryPaymentLimits"]
