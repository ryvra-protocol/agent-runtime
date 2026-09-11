# Agent Runtime

Phase 10 autonomous agent expansion for `agent-runtime`.

## Runtime architecture

- `agent_runtime/adapters`: provider-agnostic model adapter contract and deterministic stub adapter.
- `agent_runtime/planner`: task decomposition to structured plan steps.
- `agent_runtime/tools`: tool registry with per-profile allowlists, validation, and sanitized outputs.
- `agent_runtime/executor`: non-financial local execution only; all financial actions emit canonical `FinancialIntent` objects and submit through the gateway client.
- `agent_runtime/agents`: bounded production profiles for Treasury, Portfolio, Procurement, Market, and Settlement workloads.
- `agent_runtime/safety`: prompt-injection blocking, malicious tool-output sanitization, anti-escalation controls, and runaway loop defenses.
- `agent_runtime/storage`: runtime-owned persistence for `agent_sessions`, `agent_tasks`, `agent_actions`, and run records.
- `agent_runtime/gateway`: gateway-only execution client abstraction with approval, pause, and resume hooks.

## Gateway-only authority boundary

Mandatory path:

`Agent Runtime -> Agent Gateway -> Ryvra Authorization -> Deterministic Execution`

The runtime is intelligence and orchestration only. It never executes financial side effects directly and always blocks direct execution routes such as `chain_rpc_execute`, `accounts_direct_execute`, `pay_direct_execute`, and `markets_direct_execute`.

## Autonomous profile architecture

Each profile declares:

- allowed actions
- allowed tools
- autonomy level cap (`A0`-`A3`)
- mandatory approval conditions
- forbidden self-escalation operations
- bounded runaway limits for actions, retries, denials, and duration

### Capability matrix

| Profile | Actions | Autonomy cap | Key controls |
| --- | --- | --- | --- |
| Treasury Agent | `PAY`, `TRANSFER`, `REBALANCE`, `COLLECT` | `A2` | treasury policy binding, per-counterparty limits, cash-balance floor checks |
| Portfolio Agent | `REBALANCE`, `TRADE`, `COLLECT` | `A2` | drift band, concentration limits, risk budget checks |
| Procurement Agent | `PAY`, `TRANSFER` | `A1` | vendor allowlist, invoice reference requirement, approval for exceptions |
| Market Agent | `TRADE`, `OPEN_POSITION`, `CLOSE_POSITION` | `A1` | venue/instrument allowlists, exposure and leverage limits, privacy and execution constraints |
| Settlement Agent | `COLLECT`, `TRANSFER` | `A1` | ops-restricted transfers, reconciliation mismatch thresholds, manual review escalation |

## Shared orchestration loop

1. Read objective and runtime context.
2. Apply prompt-injection and anti-escalation checks.
3. Verify gateway agent status and halt on `SUSPENDED` or `REVOKED`.
4. Build the plan.
5. Execute non-financial tools within the profile allowlist.
6. Generate canonical `FinancialIntent` payloads for financial steps.
7. Submit intents through `agent-gateway`.
8. Process gateway responses:
   - `APPROVED`: continue
   - `REVIEW`, `CHALLENGE`, `DELAY`: pause and escalate to approval flow
   - `QUARANTINE`: halt and escalate
   - `KILLSWITCH`: halt immediately
9. Persist provenance, safety interventions, and run metrics.

## Threat-model controls (RFC-0017)

- prompt-level blocking for gateway bypass, policy mutation, approval override, and autonomy escalation attempts
- malicious tool-output sanitization before model/runtime reuse
- anti-escalation guard so an agent cannot alter its own limits, profile, policy, or mandate
- runaway loop defense with max actions, max retries, repeated denial halts, and max duration
- compromised-model assumption: safety is enforced by runtime and gateway checks, not model compliance

## Human approval and escalation flow

- review-bearing intents produce structured approval payloads with session, task, profile, gateway, correlation, and reason references
- `REVIEW`, `CHALLENGE`, `DELAY`, and `QUARANTINE` always trigger escalation handling
- pause/resume is supported through immutable audit events

## Provenance and observability

Runtime-owned records persist:

- session, task, run, and step identifiers
- profile type and autonomy level
- objective hash
- selected tools
- `intentId`, `correlationId`, `idempotencyKey`, and `gatewayRef`
- gateway decision and reason code
- downstream audit timeline references
- safety flags, escalation state, and run metrics

## Data model

Additive fields on runtime-owned records include:

- `profile_type`
- `autonomy_level`
- `safety_flags`
- `escalation_state`
- `gateway_refs`
- `run_metrics`

## RFC mapping

- RFC-0016: autonomous financial-agent profile framework
- RFC-0017: threat-model controls and bounded safety enforcement
- RFC-0010: runtime architecture and observability base
- RFC-0009: gateway authorization, review flows, and deterministic execution
- RFC-0007: mandate and capability linkage
- RFC-0005: canonical `FinancialIntent` submission path

## Documentation

- `docs/agent-profiles.md`
- `docs/threat-model-controls.md`
- `docs/escalation-runbook.md`
- `docs/agent-loop.md`

## Running tests

```bash
python -m pytest
```
