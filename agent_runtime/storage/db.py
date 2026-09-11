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
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                model_provider TEXT,
                model_name TEXT,
                status TEXT,
                terminal_reason TEXT,
                audit_metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agent_tasks (
                task_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_text TEXT NOT NULL,
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
                gateway_ref TEXT,
                reason_code TEXT,
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
        model_provider: str,
        model_name: str,
        status: str,
        terminal_reason: str | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO agent_sessions (session_id, actor_id, model_provider, model_name, status, terminal_reason, audit_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                status=excluded.status,
                terminal_reason=excluded.terminal_reason,
                audit_metadata=excluded.audit_metadata
            """,
            (
                session_id,
                actor_id,
                model_provider,
                model_name,
                status,
                terminal_reason,
                json.dumps(audit_metadata or {}),
            ),
        )
        self.conn.commit()

    def save_task(self, task_id: str, session_id: str, task_text: str, plan: list[dict[str, Any]]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO agent_tasks (task_id, session_id, task_text, plan_json) VALUES (?, ?, ?, ?)",
            (task_id, session_id, task_text, json.dumps(plan)),
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
        gateway_ref: str | None = None,
        reason_code: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO agent_actions (session_id, task_id, step_id, action_type, action_payload, gateway_ref, reason_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, task_id, step_id, action_type, json.dumps(payload), gateway_ref, reason_code),
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
