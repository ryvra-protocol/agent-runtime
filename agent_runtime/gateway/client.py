from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_runtime.types import AgentStatus, FinancialIntent, IntentState


@dataclass
class GatewayIntentRecord:
    intent: FinancialIntent
    state: IntentState
    response: dict[str, Any]
    timeline: list[dict[str, Any]] = field(default_factory=list)


class GatewayClient:
    def submit_intent(self, intent: FinancialIntent) -> dict[str, Any]:
        raise NotImplementedError

    def get_intent(self, intent_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def approve_intent(self, intent_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def cancel_intent(self, intent_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def get_audit_timeline(self, intent_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_agent_status(self, actor_id: str) -> AgentStatus:
        raise NotImplementedError

    def pause_session(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def resume_session(self, session_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def record_escalation(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class InMemoryGatewayClient(GatewayClient):
    def __init__(self) -> None:
        self._intents: dict[str, GatewayIntentRecord] = {}
        self._status: dict[str, AgentStatus] = {}
        self._paused_sessions: dict[str, dict[str, Any]] = {}
        self._escalations: dict[str, list[dict[str, Any]]] = {}

    def set_agent_status(self, actor_id: str, status: AgentStatus) -> None:
        self._status[actor_id] = status

    def get_agent_status(self, actor_id: str) -> AgentStatus:
        return self._status.get(actor_id, AgentStatus.ACTIVE)

    def submit_intent(self, intent: FinancialIntent) -> dict[str, Any]:
        state = IntentState.REVIEW if intent.reviewRequired else IntentState.APPROVED
        response = {
            "intentId": intent.intentId,
            "state": state.value,
            "gatewayRef": f"gw-{intent.intentId}",
            "reason": intent.reviewReason,
        }
        self._intents[intent.intentId] = GatewayIntentRecord(
            intent=intent,
            state=state,
            response=response,
            timeline=[self._event("SUBMIT", intent.intentId, state.value)],
        )
        return response

    def mark_intent_state(self, intent_id: str, state: IntentState, reason: str | None = None) -> None:
        record = self._intents[intent_id]
        record.state = state
        record.response["state"] = state.value
        if reason:
            record.response["reason"] = reason
        record.timeline.append(self._event("STATE_CHANGE", intent_id, state.value, reason))

    def get_intent(self, intent_id: str) -> dict[str, Any]:
        record = self._intents[intent_id]
        return {
            "intentId": intent_id,
            "state": record.state.value,
            **record.response,
        }

    def approve_intent(self, intent_id: str) -> dict[str, Any]:
        self.mark_intent_state(intent_id, IntentState.APPROVED, reason="HUMAN_APPROVED")
        return self.get_intent(intent_id)

    def cancel_intent(self, intent_id: str) -> dict[str, Any]:
        self.mark_intent_state(intent_id, IntentState.DENIED, reason="HUMAN_CANCELLED")
        return self.get_intent(intent_id)

    def get_audit_timeline(self, intent_id: str) -> list[dict[str, Any]]:
        return list(self._intents[intent_id].timeline)

    def pause_session(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "sessionId": session_id,
            "state": "PAUSED",
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._paused_sessions[session_id] = record
        return record

    def resume_session(self, session_id: str) -> dict[str, Any]:
        payload = self._paused_sessions.pop(session_id, None)
        if payload is None:
            return {
                "sessionId": session_id,
                "state": "NOT_PAUSED",
                "payload": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "sessionId": session_id,
            "state": "RESUMED",
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def record_escalation(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "sessionId": session_id,
            "state": "ESCALATED",
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._escalations.setdefault(session_id, []).append(event)
        return event

    @staticmethod
    def _event(event_type: str, intent_id: str, state: str, reason: str | None = None) -> dict[str, Any]:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "eventType": event_type,
            "intentId": intent_id,
            "state": state,
        }
        if reason:
            event["reason"] = reason
        return event
