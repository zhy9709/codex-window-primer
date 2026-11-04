from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .core import (decision, default_state_file, load_state, prime,
                   read_rate_limits, save_state, single_instance, verify_primed)
from .timer import install, schedule_reset_follow_up


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-window-primer")
    parser.add_argument("--codex", default=os.environ.get("CODEX_BIN", "codex"))
    parser.add_argument("--state-file", type=Path, default=default_state_file())
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check usage and prime a fresh window")
    check.add_argument("--dry-run", action="store_true")
    check.add_argument("--min-prime-interval", type=int, default=4 * 3600,
                       help="duplicate guard in seconds (default: 14400)")
    check.add_argument("--model", help="Codex model for the primer request (default: CLI default)")
    check.add_argument("--schedule-reset-follow-up", action="store_true",
                       help="schedule one systemd run just after the reported reset")
    check.add_argument("--reset-delay", type=int, default=30,
                       help="seconds to wait after reset (default: 30)")
    sub.add_parser("status", help="show usage without priming")
    timer = sub.add_parser("install-timer", help="install a systemd user timer")
    timer.add_argument("--interval", default="1h", help="15m, 30m, 1h, etc. (default: 1h)")
    timer.add_argument("--reset-follow-up", action="store_true",
                       help="also schedule a precise one-shot run after each reset")
    timer.add_argument("--reset-delay", type=int, default=30,
                       help="seconds to wait after reset (default: 30)")
    timer.add_argument("--model", help="Codex model for scheduled primer requests")
    args = parser.parse_args(argv)

    if args.command == "install-timer":
        executable = shutil.which("codex-window-primer") or str(Path(sys.argv[0]).resolve())
        service, timer_path = install(args.interval, executable, args.reset_follow_up,
                                      args.reset_delay, args.model)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", timer_path.name], check=True)
        print(json.dumps({"service": str(service), "timer": str(timer_path),
                          "interval": args.interval,
                          "resetFollowUp": args.reset_follow_up,
                          "resetDelay": args.reset_delay,
                          "modelRequested": args.model or None}))
        return 0

    with single_instance(args.state_file):
        limits = read_rate_limits(args.codex)
        primary = limits.get("primary") or {}
        used = float(primary.get("usedPercent", 100))
        reset = int(primary.get("resetsAt") or 0)
        payload = {"usedPercent": used, "leftPercent": 100 - used, "resetsAt": reset}
        if args.command == "status":
            print(json.dumps(payload))
            return 0

        state = load_state(args.state_file)
        now = int(time.time())
        if args.reset_delay < 0:
            parser.error("--reset-delay must not be negative")
        should_prime, reason = decision(used, state, now, args.min_prime_interval)
        payload.update({"wouldPrime": should_prime, "reason": reason,
                        "modelRequested": args.model or None,
                        "before": {"usedPercent": used, "leftPercent": 100 - used,
                                   "resetsAt": reset}})
        if should_prime and not args.dry_run:
            prime(args.codex, model=args.model)
            verified_limits = verify_primed(args.codex)
            verified_primary = verified_limits.get("primary") or {}
            after_used = float(verified_primary.get("usedPercent") or 0)
            after_reset = int(verified_primary.get("resetsAt") or 0)
            payload.update({
                "usedPercent": after_used,
                "leftPercent": 100 - after_used,
                "resetsAt": after_reset,
                "after": {"usedPercent": after_used, "leftPercent": 100 - after_used,
                          "resetsAt": after_reset},
            })
            save_state(args.state_file, {"version": 1, "last_primed_at": now,
                                         "last_reset_at": payload["resetsAt"]})
            payload["primed"] = True
        if args.schedule_reset_follow_up:
            scheduled_reset = int(payload["resetsAt"])
            reset_timer = schedule_reset_follow_up(scheduled_reset, args.reset_delay, now=now)
            payload["resetFollowUpAt"] = (scheduled_reset + args.reset_delay
                                           if reset_timer else None)
            if reset_timer:
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                subprocess.run(["systemctl", "--user", "enable", reset_timer.name], check=True)
                subprocess.run(["systemctl", "--user", "restart", reset_timer.name], check=True)
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
