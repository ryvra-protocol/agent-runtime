# Escalation Runbook

## Trigger conditions

Escalation is automatic for:

- `REVIEW`
- `CHALLENGE`
- `DELAY`
- `QUARANTINE`

## Approval payload

Approval payloads include:

- session ID
- task ID
- step ID
- profile name and version
- intent ID
- correlation ID
- idempotency key
- gateway reference
- reason code
- safety flags

## Runtime behavior

### Review, challenge, delay

1. Persist the action and gateway references.
2. Persist an escalation event with the approval payload.
3. Pause the session.
4. Resume only through explicit runtime/gateway resume flow.

### Quarantine

1. Persist the action and escalation payload.
2. Mark safety intervention.
3. Halt the session immediately.
4. Route to manual investigation.

## Audit trail

All pause, resume, escalation, and gateway-reference events are stored in runtime-owned tables so the full trace can be reconstructed by correlation ID.
