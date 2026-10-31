from __future__ import annotations

import re
from pathlib import Path


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


def install(interval: str, executable: str) -> tuple[Path, Path]:
    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = unit_dir / "codex-window-primer.service"
    timer = unit_dir / "codex-window-primer.timer"
    service.write_text("[Unit]\nDescription=Prime fresh Codex usage window\n\n[Service]\n"
                       f"Type=oneshot\nExecStart={executable} check\n", encoding="utf-8")
    timer.write_text(render_timer(interval), encoding="utf-8")
    return service, timer

