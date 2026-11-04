# Feature Spec: Precision priming and observable results

## User Story & Acceptance

### US1 — Prime close to reset (P1)
As a Codex user, I want an optional one-shot follow-up derived from the server reset time so a fresh window starts without waiting for the next hourly poll.

**Independent Test**: Given a future `resetsAt`, installing/updating scheduling produces one bounded follow-up at reset plus a safety delay.

### US2 — Control primer cost (P1)
As a user, I want to configure the model used by the tiny primer request and see which model was requested.

**Independent Test**: `check --model X` passes X to Codex without changing status/dry-run behavior.

### US3 — See proof (P1)
As a user, I want output that clearly shows before/after usage and the next reset time.

**Independent Test**: Verified success JSON includes before/after usage and reset timestamp; false success remains non-zero and state is unchanged.

## Edge Cases

- Missing or stale reset timestamps.
- Timer reinstall and repeated checks must stay idempotent.
- Unsupported model or CLI version must fail without saving success state.
- No credential or free-form provider error may be logged.

## Functional Requirements

- FR-001: Existing hourly timer behavior must remain compatible.
- FR-002: Dynamic follow-up must be optional, bounded and idempotent.
- FR-003: Primer model must be configurable with a safe documented default/current-default choice.
- FR-004: Machine-readable output must show verified before/after values.
- FR-005: Runtime remains Python standard-library only.

## Success Criteria

- SC-001: Fresh-window trigger delay is at most the configured safety delay when dynamic scheduling is enabled.
- SC-002: Users can verify successful priming from one JSON result.
- SC-003: All tests and compile checks pass.

## Out of Scope

- Web dashboard, telemetry, quota bypass, multi-account orchestration.

## Assumptions

- Linux/systemd is the first supported scheduler; cron remains documented fallback.
