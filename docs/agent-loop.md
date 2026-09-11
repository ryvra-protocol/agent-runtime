# Agent Loop

1. Receive objective and bounded runtime context.
2. Apply prompt-injection and anti-escalation checks before planning.
3. Poll gateway agent status and halt on `SUSPENDED` or `REVOKED`.
4. Build the plan.
5. Execute step-by-step:
   - non-financial steps: local allowed-tool execution only
   - financial steps: generate canonical `FinancialIntent` and submit through the gateway client
6. Process gateway decisions:
   - `APPROVED` continues
   - `REVIEW`, `CHALLENGE`, and `DELAY` pause the run and emit approval payloads
   - `QUARANTINE` halts and escalates
   - `KILLSWITCH` halts immediately
7. Persist trace, provenance, safety flags, escalation state, and run metrics.
8. Evaluate run results and persist the final session/task/action records.
