# codex-window-primer

Starts an idle Codex rolling usage window before you actually need it. It checks
the local Codex account's primary usage window and sends one tiny request only
when usage is still 0%.

This does **not** add quota, bypass plan limits, or make requests free. It only
starts the normal rolling window earlier. It relies on an experimental Codex
app-server method, so a future Codex release may require an update.

## Install

Prerequisites: Python 3.10+, Codex CLI on `PATH`, and `codex login` completed.

```bash
git clone <repository-url> codex-window-primer
cd codex-window-primer
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/codex-window-primer status
```

Install the recommended hourly user timer:

```bash
.venv/bin/codex-window-primer install-timer --interval 1h
```

Other useful choices are `30m` (more responsive) and `15m` (usually
unnecessary). The default `1h` means the window starts at most 59 minutes after
it becomes fresh, while making only 24 lightweight checks per day.

For cron instead:

```cron
17 * * * * /path/to/codex-window-primer/.venv/bin/codex-window-primer check
```

## Commands

```bash
codex-window-primer status
codex-window-primer check --dry-run
codex-window-primer check
codex-window-primer install-timer --interval 30m
```

State is stored in `$XDG_STATE_HOME/codex-window-primer/state.json` (normally
`~/.local/state/...`). OAuth tokens remain in Codex's own auth file and are
never copied or logged. A four-hour safety guard prevents duplicate requests
when the server's reset timestamp drifts by a few seconds.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## License

MIT

