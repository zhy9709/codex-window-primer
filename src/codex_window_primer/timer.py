from __future__ import annotations

import re
import time
from pathlib import Path


MAX_FOLLOW_UP_SECONDS = 7 * 24 * 3600


def parse_interval(value: str) -> int:
    match = re.fullmatch(r"(\d+)([mh])", value.strip().lower())
    if not match:
        raise ValueError("interval must look like 15m, 30m, 1h, or 2h")
    amount = int(match.group(1))
    seconds = amount * (60 if match.group(2) == "m" else 3600)
    if seconds < 300:
        raise ValueError("interval must be at least 5 minutes")
    return seconds


def render_timer(interval: str) -> str:
    parse_interval(interval)
    return ("[Unit]\nDescription=Check for a fresh Codex usage window\n\n"
            f"[Timer]\nOnBootSec=2m\nOnUnitActiveSec={interval}\nPersistent=true\n"
            "RandomizedDelaySec=30\n\n[Install]\nWantedBy=timers.target\n")


def follow_up_at(resets_at: int, safety_delay: int, now: int | None = None) -> int | None:
    """Return a safe reset follow-up epoch, or None for stale/implausible input."""
    current = int(time.time()) if now is None else now
    target = resets_at + safety_delay
    if safety_delay < 0 or target <= current or target - current > MAX_FOLLOW_UP_SECONDS:
        return None
    return target


def render_reset_timer(run_at: int) -> str:
    return ("[Unit]\nDescription=Follow up at the next Codex window reset\n\n"
            f"[Timer]\nOnCalendar=@{run_at}\nAccuracySec=1s\nPersistent=true\n\n"
            "[Install]\nWantedBy=timers.target\n")


def schedule_reset_follow_up(resets_at: int, safety_delay: int,
                             unit_dir: Path | None = None,
                             now: int | None = None) -> Path | None:
    """Write one idempotent reset timer. The caller activates it with systemctl."""
    run_at = follow_up_at(resets_at, safety_delay, now)
    if run_at is None:
        return None
    directory = unit_dir or Path.home() / ".config/systemd/user"
    directory.mkdir(parents=True, exist_ok=True)
    timer = directory / "codex-window-primer-reset.timer"
    content = render_reset_timer(run_at)
    if not timer.exists() or timer.read_text(encoding="utf-8") != content:
        timer.write_text(content, encoding="utf-8")
    return timer


def install(interval: str, executable: str, reset_follow_up: bool = False,
            reset_delay: int = 30, model: str | None = None) -> tuple[Path, Path]:
    if reset_delay < 0:
        raise ValueError("reset delay must not be negative")
    if model and not re.fullmatch(r"[A-Za-z0-9._:-]+", model):
        raise ValueError("model contains unsupported characters")
    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = unit_dir / "codex-window-primer.service"
    timer = unit_dir / "codex-window-primer.timer"
    check_args = ""
    if reset_follow_up:
        check_args = f" --schedule-reset-follow-up --reset-delay {reset_delay}"
    if model:
        check_args += f" --model {model}"
    service.write_text("[Unit]\nDescription=Prime fresh Codex usage window\n\n[Service]\n"
                       f"Type=oneshot\nExecStart={executable} check{check_args}\n",
                       encoding="utf-8")
    reset_service = unit_dir / "codex-window-primer-reset.service"
    reset_service.write_text("[Unit]\nDescription=Prime Codex after window reset\n\n[Service]\n"
                             f"Type=oneshot\nExecStart={executable} check{check_args}\n",
                             encoding="utf-8")
    timer.write_text(render_timer(interval), encoding="utf-8")
    return service, timer
