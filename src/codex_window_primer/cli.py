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
from .timer import install


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-window-primer")
    parser.add_argument("--codex", default=os.environ.get("CODEX_BIN", "codex"))
    parser.add_argument("--state-file", type=Path, default=default_state_file())
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check usage and prime a fresh window")
    check.add_argument("--dry-run", action="store_true")
    check.add_argument("--min-prime-interval", type=int, default=4 * 3600,
                       help="duplicate guard in seconds (default: 14400)")
    sub.add_parser("status", help="show usage without priming")
    timer = sub.add_parser("install-timer", help="install a systemd user timer")
    timer.add_argument("--interval", default="1h", help="15m, 30m, 1h, etc. (default: 1h)")
    args = parser.parse_args(argv)

    if args.command == "install-timer":
        executable = shutil.which("codex-window-primer") or str(Path(sys.argv[0]).resolve())
        service, timer_path = install(args.interval, executable)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", timer_path.name], check=True)
        print(json.dumps({"service": str(service), "timer": str(timer_path),
                          "interval": args.interval}))
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
        should_prime, reason = decision(used, state, now, args.min_prime_interval)
        payload.update({"wouldPrime": should_prime, "reason": reason})
        if should_prime and not args.dry_run:
            prime(args.codex)
            verified_limits = verify_primed(args.codex)
            verified_primary = verified_limits.get("primary") or {}
            payload.update({
                "usedPercent": float(verified_primary.get("usedPercent") or 0),
                "leftPercent": 100 - float(verified_primary.get("usedPercent") or 0),
                "resetsAt": int(verified_primary.get("resetsAt") or 0),
            })
            save_state(args.state_file, {"version": 1, "last_primed_at": now,
                                         "last_reset_at": payload["resetsAt"]})
            payload["primed"] = True
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
