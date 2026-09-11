from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

from agent_runtime.agents import AgentPolicyError, AgentProfile
from agent_runtime.evaluation import RunEvaluator
from agent_runtime.executor import DirectExecutionBlockedError, RuntimeExecutor
from agent_runtime.gateway.client import GatewayClient
from agent_runtime.memory import SessionMemory
from agent_runtime.planner import TaskPlanner
from agent_runtime.safety import PromptDefense
from agent_runtime.storage import RuntimeStore
from agent_runtime.tools.registry import ToolValidationError
from agent_runtime.types import AgentStatus, EscalationState, IntentState, RuntimeContext


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
        profile = self.executor.profile
        objective_hash = hashlib.sha256(task_text.encode("utf-8")).hexdigest()
        blocked_unsafe_attempts = 0
        terminal_reason: str | None = None
        final_status = AgentStatus.ACTIVE.value
        start_time = time.monotonic()
        run_metrics = {"attempts": 0, "retries": 0, "duration_seconds": 0, "denials": 0}
        safety_flags: list[str] = []
        escalation_state = EscalationState.NONE.value

        prompt_result = self.prompt_defense.check(task_text)
        if not prompt_result.allowed:
            blocked_unsafe_attempts += 1
            terminal_reason = prompt_result.reason
            safety_flags.append("PROMPT_INJECTION_BLOCKED")
            return self._terminal_exit(
                context=context,
                reason=terminal_reason or "PROMPT_BLOCKED",
                blocked_unsafe_attempts=blocked_unsafe_attempts,
                task_text=task_text,
                profile=profile,
                objective_hash=objective_hash,
                safety_flags=safety_flags,
                escalation_state=EscalationState.HALTED.value,
                run_metrics=run_metrics,
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
                profile=profile,
                objective_hash=objective_hash,
                safety_flags=safety_flags,
                escalation_state=EscalationState.HALTED.value,
                run_metrics=run_metrics,
            )
        try:
            self.executor.profile.validate_context(context)
        except AgentPolicyError as exc:
            return self._terminal_exit(
                context=context,
                reason=str(exc),
                blocked_unsafe_attempts=blocked_unsafe_attempts,
                task_text=task_text,
                profile=profile,
                objective_hash=objective_hash,
                safety_flags=safety_flags,
                escalation_state=EscalationState.HALTED.value,
                run_metrics=run_metrics,
            )
        self.store.upsert_session(
            session_id=context.session_id,
            actor_id=context.actor_id,
            profile_type=context.profile_type.value,
            autonomy_level=context.autonomy_level.value,
            model_provider="stub",
            model_name="stub-model",
            status=AgentStatus.ACTIVE.value,
            safety_flags=safety_flags,
            escalation_state=escalation_state,
            run_metrics=run_metrics,
        )
        plan_steps = self.planner.create_plan(task_text)
        plan_serialized = [step.__dict__ for step in plan_steps]
        self.store.save_task(
            context.task_id,
            context.session_id,
            task_text,
            plan_serialized,
            objective_hash=objective_hash,
            profile_type=context.profile_type.value,
        )

        run_trace: list[dict[str, Any]] = []
        spent_in_window = 0.0
        intent_retries: dict[str, int] = {}

        for step in plan_steps:
            try:
                self._enforce_runaway_limits(
                    context=context,
                    profile=profile,
                    action_count=len(run_trace),
                    start_time=start_time,
                    retry_count=sum(intent_retries.values()),
                )
                self._ensure_active(context)
                run_metrics["attempts"] += 1
                result = self.executor.execute_step(context, step, spent_in_window=spent_in_window)
                run_trace.append(result)
                self.memory.add_event(result)
                if result["type"] == "financial_intent":
                    self.store.save_action(
                        session_id=context.session_id,
                        task_id=context.task_id,
                        step_id=step.id,
                        action_type="financial_intent",
                        payload=result["intent"],
                        profile_type=context.profile_type.value,
                        autonomy_level=context.autonomy_level.value,
                        safety_flags=list(safety_flags),
                        escalation_state=EscalationState.NONE.value,
                        gateway_ref=result["submitResponse"].get("gatewayRef"),
                        gateway_refs={
                            "intentId": result["intent"].get("intentId"),
                            "correlationId": result["intent"].get("correlationId"),
                            "idempotencyKey": result["intent"].get("idempotencyKey"),
                            "gatewayRef": result["submitResponse"].get("gatewayRef"),
                        },
                        reason_code=result["submitResponse"].get("state"),
                        downstream_refs={"auditTimeline": self.gateway_client.get_audit_timeline(result["intent"]["intentId"])},
                        run_metrics=run_metrics,
                    )
                    handled = self._handle_gateway_response(
                        context=context,
                        profile=profile,
                        step_id=step.id,
                        result=result,
                        safety_flags=safety_flags,
                        run_metrics=run_metrics,
                        intent_retries=intent_retries,
                    )
                    escalation_state = handled["escalation_state"]
                    final_status = handled["status"]
                    terminal_reason = handled["terminal_reason"]
                    if handled["count_spend"]:
                        amount = result["intent"].get("amount")
                        if amount:
                            spent_in_window += float(amount)
                    if handled["halt"]:
                        break
                else:
                    self.store.save_action(
                        session_id=context.session_id,
                        task_id=context.task_id,
                        step_id=step.id,
                        action_type="tool",
                        payload=result,
                        profile_type=context.profile_type.value,
                        autonomy_level=context.autonomy_level.value,
                        safety_flags=list(safety_flags),
                        escalation_state=EscalationState.NONE.value,
                        run_metrics=run_metrics,
                    )
            except PermissionError as exc:
                terminal_reason = str(exc)
                final_status = "HALTED"
                escalation_state = EscalationState.HALTED.value
                run_trace.append({"type": "blocked", "stepId": step.id, "reason": terminal_reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="blocked",
                    payload={"reason": terminal_reason},
                    profile_type=context.profile_type.value,
                    autonomy_level=context.autonomy_level.value,
                    safety_flags=list(safety_flags),
                    escalation_state=escalation_state,
                    reason_code=terminal_reason,
                    run_metrics=run_metrics,
                )
                break
            except AgentPolicyError as exc:
                terminal_reason = str(exc)
                final_status = "HALTED"
                escalation_state = EscalationState.HALTED.value
                run_trace.append({"type": "blocked", "stepId": step.id, "reason": terminal_reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="blocked",
                    payload={"reason": terminal_reason},
                    profile_type=context.profile_type.value,
                    autonomy_level=context.autonomy_level.value,
                    safety_flags=list(safety_flags),
                    escalation_state=escalation_state,
                    reason_code=terminal_reason,
                    run_metrics=run_metrics,
                )
                break
            except (ToolValidationError, DirectExecutionBlockedError) as exc:
                blocked_unsafe_attempts += 1
                reason = str(exc)
                terminal_reason = reason
                final_status = "HALTED"
                escalation_state = EscalationState.HALTED.value
                safety_flags.append("TOOL_GUARD_BLOCKED")
                run_trace.append({"type": "blocked", "stepId": step.id, "reason": reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="blocked",
                    payload={"reason": reason},
                    profile_type=context.profile_type.value,
                    autonomy_level=context.autonomy_level.value,
                    safety_flags=list(safety_flags),
                    escalation_state=escalation_state,
                    reason_code=reason,
                    run_metrics=run_metrics,
                )
                break
            except ValueError as exc:
                reason = str(exc)
                terminal_reason = reason
                final_status = "HALTED"
                escalation_state = EscalationState.HALTED.value
                run_trace.append({"type": "validation_error", "stepId": step.id, "reason": reason})
                self.store.save_action(
                    session_id=context.session_id,
                    task_id=context.task_id,
                    step_id=step.id,
                    action_type="validation_error",
                    payload={"reason": reason},
                    profile_type=context.profile_type.value,
                    autonomy_level=context.autonomy_level.value,
                    safety_flags=list(safety_flags),
                    escalation_state=escalation_state,
                    reason_code=reason,
                    run_metrics=run_metrics,
                )
                break

        run_metrics["duration_seconds"] = int(time.monotonic() - start_time)
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
            profile_type=context.profile_type.value,
            autonomy_level=context.autonomy_level.value,
            model_provider="stub",
            model_name="stub-model",
            status=final_status,
            terminal_reason=terminal_reason,
            safety_flags=list(safety_flags),
            escalation_state=escalation_state,
            run_metrics=run_metrics,
            audit_metadata={"blockedUnsafeAttempts": blocked_unsafe_attempts, "objectiveHash": objective_hash},
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
        profile: AgentProfile,
        objective_hash: str,
        safety_flags: list[str],
        escalation_state: str,
        run_metrics: dict[str, Any],
    ) -> RuntimeResult:
        evaluation = self.evaluator.evaluate([], blocked_unsafe_attempts).to_dict()
        self.memory.add_event({"type": "terminal", "reason": reason})
        self.store.upsert_session(
            session_id=context.session_id,
            actor_id=context.actor_id,
            profile_type=context.profile_type.value,
            autonomy_level=context.autonomy_level.value,
            model_provider="stub",
            model_name="stub-model",
            status="HALTED",
            terminal_reason=reason,
            safety_flags=list(safety_flags),
            escalation_state=escalation_state,
            run_metrics=run_metrics,
            audit_metadata={"reason": reason, "blockedUnsafeAttempts": blocked_unsafe_attempts, "objectiveHash": objective_hash},
        )
        self.store.save_task(
            context.task_id,
            context.session_id,
            task_text,
            [],
            objective_hash=objective_hash,
            profile_type=profile.config.profile_type.value,
        )
        self.store.save_run_record(
            session_id=context.session_id,
            task_id=context.task_id,
            run_trace=[],
            evaluation=evaluation,
            blocked_unsafe_attempts=blocked_unsafe_attempts,
        )
        return RuntimeResult(plan=[], run_trace=[], evaluation=evaluation, terminal_reason=reason)

    def pause_session(self, session_id: str, approval_payload: dict[str, Any]) -> dict[str, Any]:
        return self.gateway_client.pause_session(session_id, approval_payload)

    def resume_session(self, session_id: str) -> dict[str, Any]:
        result = self.gateway_client.resume_session(session_id)
        if result["state"] == "RESUMED":
            self.store.update_session_state(
                session_id=session_id,
                status=AgentStatus.ACTIVE.value,
                escalation_state=EscalationState.NONE.value,
                audit_metadata={"resumeTimestamp": result["timestamp"]},
            )
        return result

    def _enforce_runaway_limits(
        self,
        *,
        context: RuntimeContext,
        profile: AgentProfile,
        action_count: int,
        start_time: float,
        retry_count: int,
    ) -> None:
        limits = profile.config.runaway_limits
        if action_count >= limits.max_actions_per_run:
            raise PermissionError("RUNAWAY_MAX_ACTIONS_EXCEEDED")
        if retry_count > limits.max_retries:
            raise PermissionError("RUNAWAY_MAX_RETRIES_EXCEEDED")
        if time.monotonic() - start_time > limits.max_duration_seconds:
            raise PermissionError("RUNAWAY_MAX_DURATION_EXCEEDED")

    def _handle_gateway_response(
        self,
        *,
        context: RuntimeContext,
        profile: AgentProfile,
        step_id: str,
        result: dict[str, Any],
        safety_flags: list[str],
        run_metrics: dict[str, Any],
        intent_retries: dict[str, int],
    ) -> dict[str, Any]:
        response = result["submitResponse"]
        state = response.get("state")
        gateway_ref = response.get("gatewayRef")
        intent_id = result["intent"]["intentId"]
        approval_payload = {
            "sessionId": context.session_id,
            "taskId": context.task_id,
            "stepId": step_id,
            "profileName": profile.config.profile_name,
            "profileVersion": profile.config.profile_version,
            "intentId": intent_id,
            "correlationId": result["intent"]["correlationId"],
            "idempotencyKey": result["intent"]["idempotencyKey"],
            "gatewayRef": gateway_ref,
            "reasonCode": response.get("reason") or state,
            "safetyFlags": list(safety_flags),
        }
        if state == IntentState.APPROVED.value:
            return {
                "halt": False,
                "status": AgentStatus.ACTIVE.value,
                "terminal_reason": None,
                "escalation_state": EscalationState.NONE.value,
                "count_spend": True,
            }
        if state == IntentState.DENIED.value:
            run_metrics["denials"] += 1
            intent_retries[intent_id] = intent_retries.get(intent_id, 0) + 1
            run_metrics["retries"] = sum(intent_retries.values())
            threshold_met = run_metrics["denials"] >= profile.config.runaway_limits.max_denials
            terminal_reason = None
            if threshold_met:
                terminal_reason = "REPEATED_GATEWAY_DENIALS" if profile.config.runaway_limits.max_denials > 1 else "GATEWAY_DENIED"
            return {
                "halt": threshold_met,
                "status": "HALTED" if threshold_met else AgentStatus.ACTIVE.value,
                "terminal_reason": terminal_reason,
                "escalation_state": EscalationState.HALTED.value if threshold_met else EscalationState.NONE.value,
                "count_spend": False,
            }
        if state in {IntentState.REVIEW.value, IntentState.CHALLENGE.value, IntentState.DELAY.value, IntentState.QUARANTINE.value}:
            escalation_map = {
                IntentState.REVIEW.value: EscalationState.REVIEW.value,
                IntentState.CHALLENGE.value: EscalationState.CHALLENGE.value,
                IntentState.DELAY.value: EscalationState.DELAY.value,
                IntentState.QUARANTINE.value: EscalationState.QUARANTINE.value,
            }
            escalation_state = escalation_map[state]
            escalation_record = self.gateway_client.record_escalation(context.session_id, approval_payload)
            if state == IntentState.QUARANTINE.value:
                safety_flags.append("QUARANTINE_ESCALATION")
            else:
                self.pause_session(context.session_id, approval_payload)
            self.store.save_action(
                session_id=context.session_id,
                task_id=context.task_id,
                step_id=step_id,
                action_type="escalation",
                payload={"approvalPayload": approval_payload, "response": response},
                profile_type=context.profile_type.value,
                autonomy_level=context.autonomy_level.value,
                safety_flags=list(safety_flags),
                escalation_state=escalation_state,
                gateway_ref=gateway_ref,
                gateway_refs=approval_payload,
                reason_code=approval_payload["reasonCode"],
                downstream_refs={
                    "auditTimeline": self.gateway_client.get_audit_timeline(intent_id),
                    "gatewayEscalation": escalation_record,
                },
                run_metrics=run_metrics,
            )
            return {
                "halt": True,
                "status": "HALTED" if state == IntentState.QUARANTINE.value else "PAUSED",
                "terminal_reason": "QUARANTINED" if state == IntentState.QUARANTINE.value else None,
                "escalation_state": escalation_state,
                "count_spend": False,
            }
        if state == IntentState.KILLSWITCH.value:
            safety_flags.append("KILLSWITCH_TRIGGERED")
            return {
                "halt": True,
                "status": "HALTED",
                "terminal_reason": "KILLSWITCH_TRIGGERED",
                "escalation_state": EscalationState.HALTED.value,
                "count_spend": False,
            }
        return {
            "halt": False,
            "status": AgentStatus.ACTIVE.value,
            "terminal_reason": None,
            "escalation_state": EscalationState.NONE.value,
            "count_spend": False,
        }
