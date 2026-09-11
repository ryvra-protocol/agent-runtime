# Safety Controls

## Prompt defenses

The runtime blocks known unsafe instruction patterns, including attempts to:

- bypass the gateway execution path
- disable policy enforcement
- self-modify mandate/capability/limits
- self-approve restricted flows

Blocked attempts are recorded and counted in evaluation outcomes.

## Tool security model

- strict allowlist per agent profile
- per-tool argument validation required before invocation
- sanitized tool outputs before re-entry into runtime context
- runtime tool self-expansion is rejected by registry policy (unknown/unallowlisted tools denied)

## Kill-switch and status enforcement

Before and during execution, runtime checks gateway status. If status is `SUSPENDED` or `REVOKED`, runtime stops immediately and persists terminal reason and audit metadata.
