# Plan: Precision priming and observable results

## Technical Context

Python 3.10+, standard library, Codex CLI app-server, systemd user units.

## File Structure / Interfaces

- `core.py`: model-aware primer and verified result.
- `cli.py`: flags and JSON output.
- `timer.py`: optional reset follow-up scheduling.
- `tests/`: deterministic mocked tests.
- README files: usage and compatibility notes.

## Reuse and Selection

Keep the existing small CLI instead of adopting larger quota schedulers such as redline/shunt; the product value is single-purpose setup and auditability.

## Validation Plan

Run unittest discovery, compileall, diff check, CLI help/status dry run, and inspect generated systemd units without installing them during tests.
