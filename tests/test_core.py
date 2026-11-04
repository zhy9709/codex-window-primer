import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from codex_window_primer.cli import main
from codex_window_primer.core import decision, load_state, verify_primed
from codex_window_primer.timer import parse_interval, render_timer


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
        primer.assert_called_once()

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
        primer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
