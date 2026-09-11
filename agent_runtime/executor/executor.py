from __future__ import annotations

from typing import Any

from agent_runtime.agents.treasury_payment import TreasuryPaymentAgent
from agent_runtime.gateway.client import GatewayClient
from agent_runtime.tools.registry import ToolRegistry
from agent_runtime.types import PlanStep, RuntimeContext


class DirectExecutionBlockedError(PermissionError):
    pass


class RuntimeExecutor:
    BLOCKED_DIRECT_PATHS = {
        "chain_rpc_execute",
        "accounts_direct_execute",
        "pay_direct_execute",
        "markets_direct_execute",
    }

    def __init__(self, *, tool_registry: ToolRegistry, gateway_client: GatewayClient, profile: TreasuryPaymentAgent) -> None:
        self.tool_registry = tool_registry
        self.gateway_client = gateway_client
        self.profile = profile

    def execute_step(self, context: RuntimeContext, step: PlanStep, spent_in_window: float = 0.0) -> dict[str, Any]:
        if step.kind == "tool":
            if not step.tool:
                raise ValueError("Tool step missing tool")
            if step.tool in self.BLOCKED_DIRECT_PATHS:
                raise DirectExecutionBlockedError("DIRECT_EXECUTION_PATH_BLOCKED")
            output = self.tool_registry.execute("TreasuryPaymentAgent", step.tool, step.params)
            return {"type": "tool", "stepId": step.id, "tool": step.tool, "output": output}

        if step.kind == "financial":
            action = step.action
            if not action:
                raise ValueError("Financial step missing action")
            intent = self.profile.create_intent(
                context=context,
                action=action,
                asset_id=str(step.params.get("assetId", "UNKNOWN")),
                amount=step.params.get("amount"),
                chain_id=step.params.get("chainId"),
                recipient=step.params.get("recipient"),
                venue=step.params.get("venue"),
                purpose=str(step.params.get("purpose", step.description)),
                spent_in_window=spent_in_window,
            )
            submit_response = self.gateway_client.submit_intent(intent)
            return {
                "type": "financial_intent",
                "stepId": step.id,
                "intent": intent.to_dict(),
                "submitResponse": submit_response,
            }

        raise ValueError(f"Unsupported step kind: {step.kind}")
