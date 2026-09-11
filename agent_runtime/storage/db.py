from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class RuntimeStore:
    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                profile_type TEXT,
                autonomy_level TEXT,
                model_provider TEXT,
                model_name TEXT,
                status TEXT,
                terminal_reason TEXT,
                safety_flags TEXT,
                escalation_state TEXT,
                run_metrics TEXT,
                audit_metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agent_tasks (
                task_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_text TEXT NOT NULL,
                objective_hash TEXT,
                profile_type TEXT,
                plan_json TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS agent_actions (
                action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_payload TEXT NOT NULL,
                profile_type TEXT,
                autonomy_level TEXT,
                safety_flags TEXT,
                escalation_state TEXT,
                gateway_ref TEXT,
                gateway_refs TEXT,
                reason_code TEXT,
                downstream_refs TEXT,
                run_metrics TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id),
                FOREIGN KEY (task_id) REFERENCES agent_tasks(task_id)
            );

            CREATE TABLE IF NOT EXISTS runtime_run_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                run_trace_json TEXT NOT NULL,
                evaluation_json TEXT NOT NULL,
                blocked_unsafe_attempts INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()

    def upsert_session(
        self,
        *,
        session_id: str,
        actor_id: str,
        profile_type: str | None = None,
        autonomy_level: str | None = None,
        model_provider: str,
        model_name: str,
        status: str,
        terminal_reason: str | None = None,
        safety_flags: list[str] | None = None,
        escalation_state: str | None = None,
        run_metrics: dict[str, Any] | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO agent_sessions (
                session_id, actor_id, profile_type, autonomy_level, model_provider, model_name, status,
                terminal_reason, safety_flags, escalation_state, run_metrics, audit_metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                actor_id=excluded.actor_id,
                profile_type=excluded.profile_type,
                autonomy_level=excluded.autonomy_level,
                model_provider=excluded.model_provider,
                model_name=excluded.model_name,
                status=excluded.status,
                terminal_reason=excluded.terminal_reason,
                safety_flags=excluded.safety_flags,
                escalation_state=excluded.escalation_state,
                run_metrics=excluded.run_metrics,
                audit_metadata=excluded.audit_metadata
            """,
            (
                session_id,
                actor_id,
                profile_type,
                autonomy_level,
                model_provider,
                model_name,
                status,
                terminal_reason,
                json.dumps(safety_flags or []),
                escalation_state,
                json.dumps(run_metrics or {}),
                json.dumps(audit_metadata or {}),
            ),
        )
        self.conn.commit()

    def save_task(
        self,
        task_id: str,
        session_id: str,
        task_text: str,
        plan: list[dict[str, Any]],
        *,
        objective_hash: str | None = None,
        profile_type: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO agent_tasks (task_id, session_id, task_text, objective_hash, profile_type, plan_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, session_id, task_text, objective_hash, profile_type, json.dumps(plan)),
        )
        self.conn.commit()

    def save_action(
        self,
        *,
        session_id: str,
        task_id: str,
        step_id: str,
        action_type: str,
        payload: dict[str, Any],
        profile_type: str | None = None,
        autonomy_level: str | None = None,
        safety_flags: list[str] | None = None,
        escalation_state: str | None = None,
        gateway_ref: str | None = None,
        gateway_refs: dict[str, Any] | None = None,
        reason_code: str | None = None,
        downstream_refs: dict[str, Any] | None = None,
        run_metrics: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO agent_actions (
                session_id, task_id, step_id, action_type, action_payload, profile_type, autonomy_level,
                safety_flags, escalation_state, gateway_ref, gateway_refs, reason_code, downstream_refs, run_metrics
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                task_id,
                step_id,
                action_type,
                json.dumps(payload),
                profile_type,
                autonomy_level,
                json.dumps(safety_flags or []),
                escalation_state,
                gateway_ref,
                json.dumps(gateway_refs or {}),
                reason_code,
                json.dumps(downstream_refs or {}),
                json.dumps(run_metrics or {}),
            ),
        )
        self.conn.commit()

    def save_run_record(
        self,
        *,
        session_id: str,
        task_id: str,
        run_trace: list[dict[str, Any]],
        evaluation: dict[str, Any],
        blocked_unsafe_attempts: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO runtime_run_records (session_id, task_id, run_trace_json, evaluation_json, blocked_unsafe_attempts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, task_id, json.dumps(run_trace), json.dumps(evaluation), blocked_unsafe_attempts),
        )
        self.conn.commit()

    def get_run_records(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM runtime_run_records ORDER BY id ASC"))

    def get_actions_by_correlation_id(self, correlation_id: str) -> list[sqlite3.Row]:
        query = """
            SELECT * FROM agent_actions
            WHERE json_extract(action_payload, '$.correlationId') = ?
               OR json_extract(action_payload, '$.intent.correlationId') = ?
               OR json_extract(action_payload, '$.approvalPayload.correlationId') = ?
            ORDER BY action_id ASC
        """
        return list(self.conn.execute(query, (correlation_id, correlation_id, correlation_id)))
