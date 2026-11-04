import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from codex_window_primer.cli import main
from codex_window_primer.core import decision, load_state, prime, verify_primed
from codex_window_primer.timer import (follow_up_at, install, parse_interval,
                                       render_reset_timer, render_timer,
                                       schedule_reset_follow_up)


class DecisionTests(unittest.TestCase):
    def test_active_window_does_not_prime(self):
        self.assertEqual(decision(1, {}, 10_000), (False, "window-active"))

    def test_fresh_window_primes(self):
        self.assertEqual(decision(0, {}, 10_000), (True, "fresh-window"))

    def test_reset_drift_cannot_duplicate_prime(self):
        state = {"last_primed_at": 10_000, "last_reset_at": 99_999}
        self.assertEqual(decision(0, state, 13_600), (False, "recently-primed"))


class TimerTests(unittest.TestCase):
    def test_intervals(self):
        self.assertEqual(parse_interval("15m"), 900)
        self.assertEqual(parse_interval("1h"), 3600)
        self.assertIn("OnUnitActiveSec=30m", render_timer("30m"))

    def test_rejects_too_frequent(self):
        with self.assertRaises(ValueError):
            parse_interval("1m")

    def test_reset_follow_up_is_bounded(self):
        self.assertEqual(follow_up_at(2000, 30, now=1000), 2030)
        self.assertIsNone(follow_up_at(900, 30, now=1000))
        self.assertIsNone(follow_up_at(1_000_000, 30, now=1000))
        self.assertIsNone(follow_up_at(2000, -1, now=1000))

    def test_reset_timer_is_idempotent(self):
        with TemporaryDirectory() as directory:
            unit_dir = Path(directory)
            first = schedule_reset_follow_up(2000, 30, unit_dir, now=1000)
            second = schedule_reset_follow_up(2000, 30, unit_dir, now=1000)
            self.assertEqual(first, second)
            self.assertEqual(first.read_text(encoding="utf-8"), render_reset_timer(2030))

    def test_install_preserves_poll_and_configures_follow_up(self):
        with TemporaryDirectory() as directory, \
                patch("codex_window_primer.timer.Path.home", return_value=Path(directory)):
            service, timer = install("1h", "/opt/primer", True, 30, "gpt-test")
            service_text = service.read_text(encoding="utf-8")
            reset_text = service.with_name("codex-window-primer-reset.service").read_text(
                encoding="utf-8")
            self.assertIn("OnUnitActiveSec=1h", timer.read_text(encoding="utf-8"))
            self.assertIn("--schedule-reset-follow-up --reset-delay 30", service_text)
            self.assertIn("--model gpt-test", service_text)
            self.assertIn("--model gpt-test", reset_text)


class PrimerTests(unittest.TestCase):
    @patch("codex_window_primer.core.subprocess.run")
    def test_model_is_optional(self, run):
        run.return_value.returncode = 0
        prime("codex", model="gpt-test")
        command = run.call_args.args[0]
        self.assertIn("--model", command)
        self.assertIn("gpt-test", command)


class VerificationTests(unittest.TestCase):
    @patch("codex_window_primer.core.time.sleep")
    @patch("codex_window_primer.core.read_rate_limits")
    def test_verified_success(self, read_limits, sleep):
        read_limits.return_value = {"primary": {"usedPercent": 1}}
        self.assertEqual(verify_primed("codex"), read_limits.return_value)
        read_limits.assert_called_once_with("codex", timeout=20)
        sleep.assert_not_called()

    @patch("codex_window_primer.core.time.sleep")
    @patch("codex_window_primer.core.read_rate_limits")
    def test_persistent_zero_fails(self, read_limits, sleep):
        read_limits.return_value = {"primary": {"usedPercent": 0}}
        with self.assertRaisesRegex(RuntimeError, "could not be verified"):
            verify_primed("codex")
        self.assertEqual(read_limits.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("codex_window_primer.core.time.sleep")
    @patch("codex_window_primer.core.read_rate_limits")
    def test_transient_errors_are_retried(self, read_limits, sleep):
        expected = {"primary": {"usedPercent": 0.5}}
        read_limits.side_effect = [TimeoutError("late"), expected]
        self.assertEqual(verify_primed("codex"), expected)
        self.assertEqual(read_limits.call_count, 2)
        sleep.assert_called_once_with(2)


class CheckCommandTests(unittest.TestCase):
    @patch("codex_window_primer.cli.prime")
    @patch("codex_window_primer.cli.verify_primed")
    @patch("codex_window_primer.cli.read_rate_limits")
    def test_state_saved_only_after_verified_success(self, read_limits, verify, primer):
        read_limits.return_value = {"primary": {"usedPercent": 0, "resetsAt": 10}}
        verify.return_value = {"primary": {"usedPercent": 1, "resetsAt": 20}}
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            self.assertEqual(main(["--state-file", str(state_path), "check"]), 0)
            self.assertEqual(load_state(state_path)["last_reset_at"], 20)
        primer.assert_called_once_with("codex", model=None)

    @patch("codex_window_primer.cli.prime")
    @patch("codex_window_primer.cli.verify_primed")
    @patch("codex_window_primer.cli.read_rate_limits")
    def test_verification_failure_leaves_state_unchanged(self, read_limits, verify, primer):
        read_limits.return_value = {"primary": {"usedPercent": 0, "resetsAt": 10}}
        verify.side_effect = RuntimeError("still zero")
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text('{"last_primed_at": 1}\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "still zero"):
                main(["--state-file", str(state_path), "check", "--min-prime-interval", "0"])
            self.assertEqual(load_state(state_path), {"last_primed_at": 1})
        primer.assert_called_once_with("codex", model=None)

    @patch("codex_window_primer.cli.prime")
    @patch("codex_window_primer.cli.verify_primed")
    @patch("codex_window_primer.cli.read_rate_limits")
    def test_output_contains_before_after_and_model(self, read_limits, verify, primer):
        read_limits.return_value = {"primary": {"usedPercent": 0, "resetsAt": 10}}
        verify.return_value = {"primary": {"usedPercent": 2, "resetsAt": 20}}
        with TemporaryDirectory() as directory, patch("builtins.print") as output:
            state_path = Path(directory) / "state.json"
            self.assertEqual(main(["--state-file", str(state_path), "check",
                                   "--model", "gpt-test"]), 0)
            payload = __import__("json").loads(output.call_args.args[0])
        self.assertEqual(payload["before"]["usedPercent"], 0)
        self.assertEqual(payload["after"]["usedPercent"], 2)
        self.assertEqual(payload["modelRequested"], "gpt-test")
        primer.assert_called_once_with("codex", model="gpt-test")


if __name__ == "__main__":
    unittest.main()
