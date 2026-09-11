# Agent Loop

1. Receive task and runtime context.
2. Apply prompt safety checks.
3. Poll gateway agent status (`ACTIVE`, `SUSPENDED`, `REVOKED`).
4. Build deterministic plan via planner.
5. Execute step-by-step:
   - Non-financial tools: local allowed tool execution only.
   - Financial actions: generate canonical `FinancialIntent`, submit through gateway client.
6. Persist trace and action metadata in runtime tables.
7. Evaluate run and persist structured evaluation record.
8. Halt immediately if gateway status changes to suspended/revoked or kill-switch equivalent.
