# TreasuryPaymentAgent

Legacy compatibility shim documentation for the older treasury profile names. New integrations should prefer `TreasuryAgentProfile` and `TreasuryAgentControls`.

## Profile

`TreasuryPaymentAgent` is a compatibility wrapper around `TreasuryAgentProfile` that still accepts the legacy `limits=` constructor argument, and `TreasuryPaymentLimits` remains a compatibility type built on `TreasuryAgentControls`.

### Allowed actions

- PAY
- TRANSFER
- COLLECT
- REBALANCE

Action set is configurable, and unsupported actions are rejected before submission.

### Required context

- `mandate_id`
- `capability_ids`
- `policy_version`
- `actor_id`

Missing mandate/capability context causes immediate policy error.

### Limits and escalation

- hard cap per transaction
- rolling window cap
- optional per-counterparty cap

If any cap is exceeded, the runtime still emits canonical `FinancialIntent` but marks it review-required with reason codes:

- `PER_TX_LIMIT_EXCEEDED`
- `WINDOW_LIMIT_EXCEEDED`
- `COUNTERPARTY_LIMIT_EXCEEDED`
- `CASH_FLOOR_BREACH`

### Autonomy bounds

Default permitted autonomy: `A1`, `A2`.

`A0` and `A3` are blocked unless explicitly configured.
