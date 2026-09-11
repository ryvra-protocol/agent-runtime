# Agent Runtime

Phase 7 implementation for RFC-0010 in `agent-runtime`.

## Runtime architecture

- `agent_runtime/adapters`: provider-agnostic model adapter contract and config-driven stub adapter.
- `agent_runtime/planner`: deterministic task decomposition to structured plan steps.
- `agent_runtime/tools`: tool registry with per-profile allowlist, argument validation, and sanitized outputs.
- `agent_runtime/executor`: local execution for non-financial tools; financial operations emit canonical `FinancialIntent` and submit only through gateway client.
- `agent_runtime/memory`: short-term in-session memory and optional long-term summaries.
- `agent_runtime/safety`: prompt injection guards, policy/mutate-at-runtime defenses, and output sanitization.
- `agent_runtime/evaluation`: post-run checks and scoring (intent validity, policy linkage, blocked unsafe attempts).
- `agent_runtime/storage`: runtime-owned persistence for `agent_sessions`, `agent_tasks`, `agent_actions`, and additive run-record table.
- `agent_runtime/gateway`: gateway-only execution client abstraction and in-memory implementation.

## Gateway-only execution rule

Mandatory path:

`Agent Runtime -> Agent Gateway -> Ryvra Authorization -> Deterministic Execution`

The runtime blocks direct execution routes (`chain_rpc_execute`, `accounts_direct_execute`, `pay_direct_execute`, `markets_direct_execute`) and never emits transaction payloads as final execution.

## Bounded Treasury/Payment agent profile

`TreasuryPaymentAgent` supports configurable intent actions (`PAY`, `TRANSFER`, `COLLECT`, `REBALANCE`) and requires:

- runtime `mandate_id`
- runtime `capability_ids`
- bounded autonomy (`A1`/`A2` by default)
- hard limits for per-transaction, per-window, and optional per-counterparty controls

If thresholds are exceeded, intents are marked `reviewRequired=true` with explicit reason code.

## Autonomy levels (A0-A3)

- `A0`: no autonomous financial action generation.
- `A1`: bounded autonomous proposal mode (default allowed).
- `A2`: bounded delegated operation mode (default allowed).
- `A3`: unrestricted/high-autonomy mode (blocked by default for Treasury/Payment profile).

`TreasuryPaymentAgent` currently permits only `A1` and `A2` unless reconfigured; `A0` and `A3` are rejected by default policy.

## Safety model

- prompt-level blocking for gateway bypass / policy mutation attempts
- immutable mandate/capability/limit posture enforced by profile and runtime checks
- strict per-profile tool allowlists
- tool argument validation and output sanitization
- runtime halt on `SUSPENDED`/`REVOKED` gateway status with terminal reason persisted

## RFC mapping

- RFC-0010: runtime architecture, bounded agent operation, safety, observability
- RFC-0005: canonical `FinancialIntent` generation and submission path
- RFC-0007: capability/mandate linkage and policy propagation
- RFC-0009: gateway authorization, review flows, and deterministic execution control plane

## Documentation

- `docs/agent-loop.md`
- `docs/safety-controls.md`
- `docs/treasury-payment-agent.md`

## Running tests

```bash
python -m pytest
```
