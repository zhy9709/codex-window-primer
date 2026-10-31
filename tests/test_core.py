import unittest

from codex_window_primer.core import decision
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


if __name__ == "__main__":
    unittest.main()

