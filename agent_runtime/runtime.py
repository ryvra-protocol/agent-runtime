from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_runtime.agents.treasury_payment import AgentPolicyError, TreasuryPaymentAgent
from agent_runtime.evaluation import RunEvaluator
from agent_runtime.executor import DirectExecutionBlockedError, RuntimeExecutor
from agent_runtime.gateway.client import GatewayClient
from agent_runtime.memory import SessionMemory
from agent_runtime.planner import TaskPlanner
from agent_runtime.safety import PromptDefense
from agent_runtime.storage import RuntimeStore
from agent_runtime.tools.registry import ToolValidationError
from agent_runtime.types import AgentStatus, RuntimeContext


@dataclass
class RuntimeResult:
    plan: list[dict[str, Any]]
    run_trace: list[dict[str, Any]]
    evaluation: dict[str, Any]
    terminal_reason: str | None


class AgentRuntime:
    def __init__(
        self,
        *,
        planner: TaskPlanner,
        executor: RuntimeExecutor,
        gateway_client: GatewayClient,
        store: RuntimeStore,
        memory: SessionMemory | None = None,
        evaluator: RunEvaluator | None = None,
        prompt_defense: PromptDefense | None = None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.gateway_client = gateway_client
        self.store = store
        self.memory = memory or SessionMemory()
        self.evaluator = evaluator or RunEvaluator()
        self.prompt_defense = prompt_defense or PromptDefense()

    def run(self, *, context: RuntimeContext, task_text: str) -> RuntimeResult:
        blocked_unsafe_attempts = 0
        terminal_reason: str | None = None

        prompt_result = self.prompt_defense.check(task_text)
        if not prompt_result.allowed:
            blocked_unsafe_attempts += 1
            terminal_reason = prompt_result.reason
            self._save_terminal_session(context, terminal_reason)
            return RuntimeResult(plan=[], run_trace=[], evaluation=self.evaluator.evaluate([], blocked_unsafe_attempts).to_dict(), terminal_reason=terminal_reason)

        try:
            self._ensure_active(context)
        except PermissionError as exc:
            terminal_reason = str(exc)
            return RuntimeResult(
                plan=[],
                run_trace=[],
                evaluation=self.evaluator.evaluate([], blocked_unsafe_attempts).to_dict(),
                terminal_reason=terminal_reason,
            )
        plan_steps = self.planner.create_plan(task_text)
        plan_serialized = [step.__dict__ for step in plan_steps]

        self.store.upsert_session(
            session_id=context.session_id,
            actor_id=context.actor_id,
            model_provider="stub",
            model_name="stub-model",
            status=AgentStatus.ACTIVE.value,
        )
        self.store.save_task(context.task_id, context.session_id, task_text, plan_serialized)

        run_trace: list[dict[str, Any]] = []
        spent_in_window = 0.0

        for step in plan_steps:
            try:
                self._ensure_active(context)
                result = self.executor.execute_step(context, step, spent_in_window=spent_in_window)
                run_trace.append(result)
                self.memory.add_event(result)
                if result["type"] == "financial_intent":
                    amount = result["intent"].get("amount")
                    if amount:
                        spent_in_window += float(amount)
                    self.store.save_action(
                        session_id=context.session_id,
                        task_id=context.task_id,
                        step_id=step.id,
                        action_type="financial_intent",
                        payload=result["intent"],
                        gateway_ref=result["submitResponse"].get("gatewayRef"),
                        reason_code=result["submitResponse"].get("state"),
                    )
                else:
                    self.store.save_action(
                        session_id=context.session_id,
                        task_id=context.task_id,
                        step_id=step.id,
                        action_type="tool",
                        payload=result,
                    )
            except (ToolValidationError, DirectExecutionBlockedError, AgentPolicyError, PermissionError, ValueError) as exc:
                blocked_unsafe_attempts += 1
                reason = str(exc)
                run_trace.append({"type": "blocked", "stepId": step.id, "reason": reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="blocked",
                    payload={"reason": reason},
                    reason_code=reason,
                )

        evaluation = self.evaluator.evaluate(run_trace, blocked_unsafe_attempts).to_dict()
        self.store.save_run_record(
            session_id=context.session_id,
            task_id=context.task_id,
            run_trace=run_trace,
            evaluation=evaluation,
            blocked_unsafe_attempts=blocked_unsafe_attempts,
        )

        self.store.upsert_session(
            session_id=context.session_id,
            actor_id=context.actor_id,
            model_provider="stub",
            model_name="stub-model",
            status=AgentStatus.ACTIVE.value,
            terminal_reason=terminal_reason,
            audit_metadata={"blockedUnsafeAttempts": blocked_unsafe_attempts},
        )
        return RuntimeResult(plan=plan_serialized, run_trace=run_trace, evaluation=evaluation, terminal_reason=terminal_reason)

    def _ensure_active(self, context: RuntimeContext) -> None:
        status = self.gateway_client.get_agent_status(context.actor_id)
        if status in {AgentStatus.SUSPENDED, AgentStatus.REVOKED}:
            reason = f"AGENT_{status.value}"
            self._save_terminal_session(context, reason)
            raise PermissionError(reason)

    def _save_terminal_session(self, context: RuntimeContext, reason: str) -> None:
        self.store.upsert_session(
            session_id=context.session_id,
            actor_id=context.actor_id,
            model_provider="stub",
            model_name="stub-model",
            status="HALTED",
            terminal_reason=reason,
            audit_metadata={"reason": reason},
        )
