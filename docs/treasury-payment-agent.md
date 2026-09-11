# TreasuryPaymentAgent

## Profile

`TreasuryPaymentAgent` and `TreasuryPaymentLimits` are compatibility aliases for the Phase 10 `TreasuryAgentProfile` and `TreasuryAgentControls` bounded production profile types.

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
