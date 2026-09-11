# Agent Profiles

## Purpose

Phase 10 expands the runtime from a single bounded treasury profile to five bounded production profiles. All profiles remain intent-based and gateway-routed.

## Profile framework

Each profile defines:

- allowed financial actions
- allowed non-financial tools
- autonomy cap
- mandatory approval conditions
- forbidden self-escalation operations
- bounded runaway limits

## Profiles

### Treasury Agent

- actions: `PAY`, `TRANSFER`, `REBALANCE`, `COLLECT`
- controls: treasury policy binding, per-counterparty limits, cash-balance floor checks

### Portfolio Agent

- actions: `REBALANCE`, `TRADE`, `COLLECT`
- controls: drift band, concentration limits, risk budget checks

### Procurement Agent

- actions: `PAY`, `TRANSFER`
- controls: vendor allowlist, invoice reference requirement, approval for exceptions

### Market Agent

- actions: `TRADE`, `OPEN_POSITION`, `CLOSE_POSITION`
- controls: venue allowlist, instrument allowlist, exposure limits, leverage limits, execution/privacy constraints

### Settlement Agent

- actions: `COLLECT`, `TRANSFER`
- controls: ops-restricted transfer handling, reconciliation mismatch thresholds, manual-review escalation

## Authority boundary

- runtime plans and orchestrates
- runtime may use only profile-approved non-financial tools
- runtime emits canonical `FinancialIntent` records for financial actions
- gateway decides execution, review, delay, challenge, quarantine, or halt
