from __future__ import annotations

import json
import fcntl
import os
import select
import subprocess
import time
from pathlib import Path
from typing import Any
from contextlib import contextmanager


def default_state_file() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return root / "codex-window-primer/state.json"


def load_auth(path: Path | None = None) -> tuple[str, str, str | None]:
    path = path or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    tokens = data.get("tokens") or {}
    access = tokens.get("access_token")
    account = tokens.get("account_id")
    if not access or not account:
        raise RuntimeError(f"Codex login tokens not found in {path}; run `codex login`")
    return access, account, data.get("chatgpt_plan_type")


def read_rate_limits(codex: str = "codex", timeout: int = 20) -> dict[str, Any]:
    access, account, plan = load_auth()
    proc = subprocess.Popen([codex, "app-server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, bufsize=1)
    def send(payload: dict[str, Any]) -> None:
        assert proc.stdin
        proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        proc.stdin.flush()
    send({"id": 1, "method": "initialize", "params": {
        "clientInfo": {"name": "codex-window-primer", "version": "0.1.0"},
        "capabilities": {"experimentalApi": True}}})
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            assert proc.stdout
            readable, _, _ = select.select([proc.stdout], [], [], 1)
            if not readable:
                continue
            line = proc.stdout.readline()
            if not line:
                break
            payload = json.loads(line)
            if payload.get("id") == 1:
                send({"method": "initialized", "params": {}})
                params = {"type": "chatgptAuthTokens", "accessToken": access,
                          "chatgptAccountId": account}
                if plan:
                    params["chatgptPlanType"] = plan
                send({"id": 2, "method": "account/login/start", "params": params})
            elif payload.get("id") == 2:
                if payload.get("error"):
                    raise RuntimeError(payload["error"].get("message", "Codex login failed"))
                send({"id": 3, "method": "account/rateLimits/read", "params": {}})
            elif payload.get("id") == 3:
                if payload.get("error"):
                    raise RuntimeError(payload["error"].get("message", "rate-limit read failed"))
                return payload["result"]["rateLimits"]
        raise TimeoutError("Codex rate-limit query timed out")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


@contextmanager
def single_instance(state_path: Path):
    lock_path = state_path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another primer check is already running") from exc
        yield


def decision(used_percent: float, state: dict[str, Any], now: int,
             min_prime_interval: int = 4 * 3600) -> tuple[bool, str]:
    if used_percent > 0:
        return False, "window-active"
    last = int(state.get("last_primed_at") or 0)
    if last and now - last < min_prime_interval:
        return False, "recently-primed"
    return True, "fresh-window"


def prime(codex: str = "codex", timeout: int = 120,
          model: str | None = None) -> None:
    command = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only"]
    if model:
        command.extend(["--model", model])
    command.append("Reply with exactly OK.")
    result = subprocess.run(command, text=True, capture_output=True,
                            timeout=timeout)
    if result.returncode:
        # Provider output can contain account details; keep scheduled-task logs terse.
        raise RuntimeError(f"primer request failed (Codex exit status {result.returncode})")


def verify_primed(codex: str = "codex", attempts: int = 3,
                  delay: float = 2, query_timeout: int = 20) -> dict[str, Any]:
    """Return refreshed limits once the primary window reports non-zero usage.

    Each query and the number of retries are bounded so callers used by cron or
    systemd cannot wait indefinitely.  A zero reading is retried because quota
    accounting may lag slightly behind the primer request.
    """
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            limits = read_rate_limits(codex, timeout=query_timeout)
            primary = limits.get("primary") or {}
            if float(primary.get("usedPercent") or 0) > 0:
                return limits
            last_error = RuntimeError("primary usage is still 0%")
        except (OSError, RuntimeError, TimeoutError, ValueError, KeyError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(delay)
    detail = str(last_error) if last_error else "no verification attempts made"
    raise RuntimeError(f"primer could not be verified after {attempts} attempts: {detail}")
