# Threat Model Controls

## RFC-0017 posture

Safety must hold even if the model output is wrong, compromised, or adversarial.

## Controls

### Prompt injection detection

The runtime rejects instructions that attempt to:

- bypass the gateway
- disable safety or policy
- change mandate, capability, limits, profile, or autonomy
- override review or self-approve actions

### Malicious tool output sanitization

Tool outputs are sanitized before re-entry into the runtime:

- tokens, secrets, and API keys are redacted
- escalation phrases are blocked

### Anti-escalation guard

Profiles carry immutable authority limits for the run:

- allowed actions
- allowed tools
- autonomy cap
- mandatory approval conditions
- forbidden operations

The runtime refuses attempts to mutate these controls from the task or tool output.

### Runaway loop protection

The runtime enforces:

- max actions per run
- max retries
- max duration
- halt on repeated gateway denials

### Gateway and kill-switch handling

- `APPROVED` continues
- `REVIEW`, `CHALLENGE`, `DELAY` escalate to human approval and pause the run
- `QUARANTINE` halts and escalates
- `KILLSWITCH`, `SUSPENDED`, and `REVOKED` halt immediately
