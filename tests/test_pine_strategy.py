import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pine_strategy as ps


def make_bars(closes, t0=1700000000000, iv_ms=300000):
    """Build bar dicts from a list of closes; small symmetric wiggle."""
    bars = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        h = max(o, c) + 0.5
        l = min(o, c) - 0.5
        bars.append({"t": t0 + i * iv_ms, "o": o, "h": h, "l": l, "c": c, "v": 100})
        prev = c
    return bars


def find_signal(closes, cfg, position=None):
    """Scan prefixes of the series for the first bar where evaluate fires."""
    bars = make_bars(closes)
    for i in range(ps.min_bars(cfg), len(bars) + 1):
        sig = ps.evaluate(bars[:i], cfg, position)
        if sig is not None:
            return i, sig
    return None, None


class TestIndicators(unittest.TestCase):
    def test_rma_hand_computed(self):
        # n=2: seed = SMA(first 2) = 15, then (prev*(n-1)+x)/n
        out = ps.rma([10.0, 20.0, 30.0, 40.0], 2)
        self.assertIsNone(out[0])
        self.assertAlmostEqual(out[1], 15.0)
        self.assertAlmostEqual(out[2], 22.5)
        self.assertAlmostEqual(out[3], 31.25)

    def test_atr_hand_computed(self):
        bars = [
            {"t": 0, "o": 9.0, "h": 10.0, "l": 8.0, "c": 9.0, "v": 1},   # tr=2
            {"t": 1, "o": 9.0, "h": 11.0, "l": 9.0, "c": 10.0, "v": 1},  # tr=2
            {"t": 2, "o": 10.0, "h": 12.0, "l": 9.0, "c": 11.0, "v": 1}, # tr=3
        ]
        out = ps.atr(bars, 2)
        self.assertIsNone(out[0])
        self.assertAlmostEqual(out[1], 2.0)
        self.assertAlmostEqual(out[2], 2.5)

    def test_session_wraparound(self):
        # 13 -> 1 UTC: wraps midnight
        self.assertTrue(ps.session_in(23, 13, 1))
        self.assertTrue(ps.session_in(13, 13, 1))
        self.assertTrue(ps.session_in(0, 13, 1))
        self.assertFalse(ps.session_in(5, 13, 1))
        self.assertFalse(ps.session_in(1, 13, 1))
        # non-wrapping
        self.assertTrue(ps.session_in(15, 13, 18))
        self.assertFalse(ps.session_in(20, 13, 18))


class TestEvaluate(unittest.TestCase):
    def test_long_signal(self):
        # ~230 bars of mild downtrend, then a sharp rally crossing ema50 over ema100
        closes = [6000 - i * 1.0 for i in range(230)]
        base = closes[-1]
        closes += [base + i * 6.0 for i in range(1, 71)]
        cfg = ps.PineConfig()
        idx, sig = find_signal(closes, cfg)
        self.assertIsNotNone(sig, "expected a long signal somewhere in the series")
        self.assertEqual(sig.side, "long")
        self.assertEqual(len(sig.tps), cfg.qty_per_trade)
        self.assertLess(sig.stop, sig.entry)
        for a, b in zip(sig.tps, sig.tps[1:]):
            self.assertLess(a, b)
        self.assertGreater(sig.tps[0], sig.entry)
        for v in [sig.entry, sig.stop] + sig.tps:
            self.assertAlmostEqual(v / 0.25, round(v / 0.25), places=9)

    def test_short_signal(self):
        closes = [5000 + i * 1.0 for i in range(230)]
        base = closes[-1]
        closes += [base - i * 6.0 for i in range(1, 71)]
        cfg = ps.PineConfig()
        idx, sig = find_signal(closes, cfg)
        self.assertIsNotNone(sig, "expected a short signal somewhere in the series")
        self.assertEqual(sig.side, "short")
        self.assertEqual(len(sig.tps), cfg.qty_per_trade)
        self.assertGreater(sig.stop, sig.entry)
        for a, b in zip(sig.tps, sig.tps[1:]):
            self.assertGreater(a, b)
        self.assertLess(sig.tps[0], sig.entry)
        for v in [sig.entry, sig.stop] + sig.tps:
            self.assertAlmostEqual(v / 0.25, round(v / 0.25), places=9)

    def test_reverse_disabled(self):
        # Same data as short test; position long + allow_reverse=False -> None,
        # and with exit_on_opposite -> "flat".
        closes = [5000 + i * 1.0 for i in range(230)]
        base = closes[-1]
        closes += [base - i * 6.0 for i in range(1, 71)]

        cfg = ps.PineConfig(allow_reverse=False)
        idx, sig = find_signal(closes, cfg, position="long")
        self.assertIsNone(sig)

        cfg2 = ps.PineConfig(allow_reverse=False, exit_on_opposite=True)
        idx, sig = find_signal(closes, cfg2, position="long")
        self.assertEqual(sig, "flat")

    def test_smc_bias_v_shape(self):
        # decline, rally, small pullback, rally higher: the pullback makes the
        # prior rally peak a new internal high; the final rally crosses it -> +1
        closes = [6000 - i * 3.0 for i in range(40)]
        p = closes[-1]
        closes += [p + i * 3.0 for i in range(1, 41)]
        p = closes[-1]
        closes += [p - i * 2.0 for i in range(1, 8)]
        p = closes[-1]
        closes += [p + i * 3.0 for i in range(1, 41)]
        bias = ps._smc_bias_series(make_bars(closes), 5)
        self.assertEqual(bias[-1], 1)

    def test_smc_bias_inverted_v(self):
        closes = [5000 + i * 3.0 for i in range(40)]
        p = closes[-1]
        closes += [p - i * 3.0 for i in range(1, 41)]
        p = closes[-1]
        closes += [p + i * 2.0 for i in range(1, 8)]
        p = closes[-1]
        closes += [p - i * 3.0 for i in range(1, 41)]
        bias = ps._smc_bias_series(make_bars(closes), 5)
        self.assertEqual(bias[-1], -1)

    def test_too_few_bars(self):
        bars = make_bars([100.0] * 50)
        self.assertIsNone(ps.evaluate(bars, ps.PineConfig()))


if __name__ == "__main__":
    unittest.main()
