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
        final_status = AgentStatus.ACTIVE.value

        prompt_result = self.prompt_defense.check(task_text)
        if not prompt_result.allowed:
            blocked_unsafe_attempts += 1
            terminal_reason = prompt_result.reason
            return self._terminal_exit(
                context=context,
                reason=terminal_reason or "PROMPT_BLOCKED",
                blocked_unsafe_attempts=blocked_unsafe_attempts,
                task_text=task_text,
            )

        try:
            self._ensure_active(context)
        except PermissionError as exc:
            terminal_reason = str(exc)
            return self._terminal_exit(
                context=context,
                reason=terminal_reason,
                blocked_unsafe_attempts=blocked_unsafe_attempts,
                task_text=task_text,
            )
        self.store.upsert_session(
            session_id=context.session_id,
            actor_id=context.actor_id,
            model_provider="stub",
            model_name="stub-model",
            status=AgentStatus.ACTIVE.value,
        )
        try:
            self.executor.profile.validate_context(context)
        except AgentPolicyError as exc:
            return self._terminal_exit(
                context=context,
                reason=str(exc),
                blocked_unsafe_attempts=blocked_unsafe_attempts,
                task_text=task_text,
            )
        plan_steps = self.planner.create_plan(task_text)
        plan_serialized = [step.__dict__ for step in plan_steps]
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
            except PermissionError as exc:
                terminal_reason = str(exc)
                final_status = "HALTED"
                run_trace.append({"type": "blocked", "stepId": step.id, "reason": terminal_reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="blocked",
                    payload={"reason": terminal_reason},
                    reason_code=terminal_reason,
                )
                break
            except AgentPolicyError as exc:
                terminal_reason = str(exc)
                final_status = "HALTED"
                run_trace.append({"type": "blocked", "stepId": step.id, "reason": terminal_reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="blocked",
                    payload={"reason": terminal_reason},
                    reason_code=terminal_reason,
                )
                break
            except (ToolValidationError, DirectExecutionBlockedError) as exc:
                blocked_unsafe_attempts += 1
                reason = str(exc)
                terminal_reason = reason
                final_status = "HALTED"
                run_trace.append({"type": "blocked", "stepId": step.id, "reason": reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="blocked",
                    payload={"reason": reason},
                    reason_code=reason,
                )
                break
            except ValueError as exc:
                reason = str(exc)
                terminal_reason = reason
                final_status = "HALTED"
                run_trace.append({"type": "validation_error", "stepId": step.id, "reason": reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="validation_error",
                    payload={"reason": reason},
                    reason_code=reason,
                )
                break

        if final_status == AgentStatus.ACTIVE.value and terminal_reason is None:
            final_status = "COMPLETED"

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
            status=final_status,
            terminal_reason=terminal_reason,
            audit_metadata={"blockedUnsafeAttempts": blocked_unsafe_attempts},
        )
        return RuntimeResult(plan=plan_serialized, run_trace=run_trace, evaluation=evaluation, terminal_reason=terminal_reason)

    def _ensure_active(self, context: RuntimeContext) -> None:
        status = self.gateway_client.get_agent_status(context.actor_id)
        if status in {AgentStatus.SUSPENDED, AgentStatus.REVOKED}:
            reason = f"AGENT_{status.value}"
            raise PermissionError(reason)

    def _terminal_exit(
        self,
        *,
        context: RuntimeContext,
        reason: str,
        blocked_unsafe_attempts: int,
        task_text: str,
    ) -> RuntimeResult:
        evaluation = self.evaluator.evaluate([], blocked_unsafe_attempts).to_dict()
        self.memory.add_event({"type": "terminal", "reason": reason})
        self.store.upsert_session(
            session_id=context.session_id,
            actor_id=context.actor_id,
            model_provider="stub",
            model_name="stub-model",
            status="HALTED",
            terminal_reason=reason,
            audit_metadata={"reason": reason, "blockedUnsafeAttempts": blocked_unsafe_attempts},
        )
        self.store.save_task(context.task_id, context.session_id, task_text, [])
        self.store.save_run_record(
            session_id=context.session_id,
            task_id=context.task_id,
            run_trace=[],
            evaluation=evaluation,
            blocked_unsafe_attempts=blocked_unsafe_attempts,
        )
        return RuntimeResult(plan=[], run_trace=[], evaluation=evaluation, terminal_reason=reason)
