#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pine_strategy.py -- Python port of the TradingView Pine v5 strategy
"50/100 Cross + 20 EMA Direction + Structure".

Only the trading logic is ported: the EMA cross entries, direction filter,
quality filters (session, EMA separation, ATR volatility, SMC internal trend,
EMA slope, EMA stack), liquidity-sweep / BOS confluence, and the multi-TP
risk model. All drawing code (LuxAlgo Liquidity Swings, SMC order blocks,
FVG/IFVG boxes, SL/TP lines) is intentionally omitted.

Bars are dicts: {"t": ms epoch, "o":, "h":, "l":, "c":, "v":} as returned by
run.py's /api/candles endpoint.
"""

from dataclasses import dataclass, field
import datetime


# -----------------------------------------------------------------------------
#  Indicator helpers (Pine semantics)
# -----------------------------------------------------------------------------

def sma(vals, n):
    out = [None] * len(vals)
    for i in range(n - 1, len(vals)):
        out[i] = sum(vals[i - n + 1:i + 1]) / n
    return out


def ema(vals, n):
    # Pine ta.ema: seeded with the SMA of the first n values, alpha = 2/(n+1)
    if len(vals) < n:
        return [None] * len(vals)
    k = 2.0 / (n + 1)
    out = [None] * len(vals)
    out[n - 1] = sum(vals[:n]) / n
    for i in range(n, len(vals)):
        out[i] = vals[i] * k + out[i - 1] * (1 - k)
    return out


def rma(vals, n):
    # Pine ta.rma (Wilder): SMA seed, then (prev*(n-1) + x) / n
    if len(vals) < n:
        return [None] * len(vals)
    out = [None] * len(vals)
    out[n - 1] = sum(vals[:n]) / n
    for i in range(n, len(vals)):
        out[i] = (out[i - 1] * (n - 1) + vals[i]) / n
    return out


def atr(bars, n):
    # Pine ta.atr uses RMA of true range (NOT the SMA-based _atr in broker.py)
    if not bars:
        return []
    tr = [bars[0]["h"] - bars[0]["l"]]
    for i in range(1, len(bars)):
        tr.append(max(bars[i]["h"] - bars[i]["l"],
                      abs(bars[i]["h"] - bars[i - 1]["c"]),
                      abs(bars[i]["l"] - bars[i - 1]["c"])))
    return rma(tr, n)


def pivot_high(highs, left, right):
    # Like ta.pivothigh(left, right): the value is returned at index i+right
    # for a pivot whose high is highs[i].
    out = [None] * len(highs)
    for i in range(left, len(highs) - right):
        v = highs[i]
        ok = all(highs[j] <= v for j in range(i - left, i)) and \
             all(highs[j] < v for j in range(i + 1, i + right + 1))
        if ok:
            out[i + right] = v
    return out


def pivot_low(lows, left, right):
    out = [None] * len(lows)
    for i in range(left, len(lows) - right):
        v = lows[i]
        ok = all(lows[j] >= v for j in range(i - left, i)) and \
             all(lows[j] > v for j in range(i + 1, i + right + 1))
        if ok:
            out[i + right] = v
    return out


def snap(p, tick):
    return round(round(p / tick) * tick, 10)


def session_in(hour, start, end):
    # Pine line 647: wrap-around when start >= end
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


# -----------------------------------------------------------------------------
#  Config / Signal
# -----------------------------------------------------------------------------

@dataclass
class PineConfig:
    dir_len: int = 20
    slow_len1: int = 50
    slow_len2: int = 100
    atr_len: int = 5
    stop_mult: float = 2.2
    qty_per_trade: int = 2
    tp_mults: tuple = (2.3, 2.95, 4.5, 9.0, 11.0)
    use_session: bool = False
    session_start: int = 13
    session_end: int = 1
    use_ema_sep: bool = False
    ema_sep_min: float = 0.05
    use_vol_filter: bool = True
    atr_ma_len: int = 50
    atr_min_mult: float = 1.2
    atr_max_mult: float = 2.1
    use_smc_align: bool = False
    smc_pivot_len: int = 5
    use_ema_slope: bool = True
    ema_slope_len: int = 9
    ema_slope_min: float = 0.01
    use_ema_stack: bool = False
    use_sweep: bool = False
    use_bos: bool = False
    sweep_len: int = 14
    sweep_recency: int = 10
    allow_long: bool = True
    allow_short: bool = True
    allow_reverse: bool = True
    exit_on_opposite: bool = False
    tick: float = 0.25


@dataclass
class Signal:
    side: str            # "long" | "short"
    entry: float
    stop: float
    tps: list = field(default_factory=list)
    qty: int = 1
    bar_t: int = 0
    reason: str = ""


# -----------------------------------------------------------------------------
#  SMC internal trend (Pine lines 288-318, 378-393 -- drawing/OB code omitted)
# -----------------------------------------------------------------------------

def _smc_bias_series(bars, size):
    """Replicates smc_leg + smc_getInternalStructure + the bias flips in
    smc_displayInternalStructure. Returns a per-bar list of trend bias
    (1 bull, -1 bear, 0 unset)."""
    n = len(bars)
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    closes = [b["c"] for b in bars]

    leg = [0] * n
    prev = 0
    for i in range(n):
        new_leg = prev
        if i >= size:
            # newLegHigh: high[size] > highest of the `size` bars after it
            if highs[i - size] > max(highs[i - size + 1:i + 1]):
                new_leg = 1  # SMC_BEARISH_LEG
            elif lows[i - size] < min(lows[i - size + 1:i + 1]):
                new_leg = 0  # SMC_BULLISH_LEG
        leg[i] = new_leg
        prev = new_leg

    int_high_level = None
    int_high_crossed = False
    int_low_level = None
    int_low_crossed = False
    bias = [0] * n
    cur_bias = 0

    for i in range(n):
        # smc_getInternalStructure(size)
        if i > 0 and leg[i] != leg[i - 1] and i >= size:
            if leg[i] - leg[i - 1] == 1:      # new bearish leg -> internal low pivot
                int_low_level = lows[i - size]
                int_low_crossed = False
            else:                             # new bullish leg -> internal high pivot
                int_high_level = highs[i - size]
                int_high_crossed = False

        # smc_displayInternalStructure bias flips (confluence filter skipped:
        # smcInternalFilterConfluence defaults to false)
        if (int_high_level is not None and not int_high_crossed and i > 0
                and closes[i - 1] <= int_high_level < closes[i]):
            int_high_crossed = True
            cur_bias = 1
        if (int_low_level is not None and not int_low_crossed and i > 0
                and closes[i - 1] >= int_low_level > closes[i]):
            int_low_crossed = True
            cur_bias = -1
        bias[i] = cur_bias
    return bias


# -----------------------------------------------------------------------------
#  compute_state -- evaluate all per-bar series, expose last-bar snapshot
# -----------------------------------------------------------------------------

def min_bars(cfg):
    return max(cfg.slow_len2, cfg.atr_ma_len + cfg.atr_len, cfg.sweep_len * 2) + 5


def compute_state(bars, cfg=None):
    cfg = cfg or PineConfig()
    n = len(bars)
    if n < min_bars(cfg):
        return {}

    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    last = n - 1

    ema20 = ema(closes, cfg.dir_len)
    ema50 = ema(closes, cfg.slow_len1)
    ema100 = ema(closes, cfg.slow_len2)
    if any(v is None for v in (ema20[last], ema50[last], ema100[last],
                               ema50[last - 1], ema100[last - 1])):
        return {}

    cross_bull = ema50[last - 1] <= ema100[last - 1] and ema50[last] > ema100[last]
    cross_bear = ema50[last - 1] >= ema100[last - 1] and ema50[last] < ema100[last]
    dir_up = closes[last] > ema20[last]
    dir_down = closes[last] < ema20[last]

    atr_vals = atr(bars, cfg.atr_len)
    atr_val = atr_vals[last]
    if atr_val is None:
        return {}
    atr_ma = sma([v if v is not None else 0.0 for v in atr_vals], cfg.atr_ma_len)[last]
    if atr_ma is None:
        return {}
    vol_ok = (not cfg.use_vol_filter) or \
             (atr_val >= atr_ma * cfg.atr_min_mult and atr_val <= atr_ma * cfg.atr_max_mult)

    ema_sep_pct = abs(ema50[last] - ema100[last]) / ema100[last] * 100
    ema_sep_ok = (not cfg.use_ema_sep) or ema_sep_pct >= cfg.ema_sep_min

    L = cfg.ema_slope_len
    ema_slope = 0.0
    if last - L >= 0 and ema20[last - L] is not None and ema20[last - L] != 0:
        ema_slope = abs(ema20[last] - ema20[last - L]) / ema20[last - L] * 100 / L
    ema_slope_ok = (not cfg.use_ema_slope) or ema_slope >= cfg.ema_slope_min

    ema_stack_long = (not cfg.use_ema_stack) or \
                     (closes[last] > ema20[last] and ema20[last] > ema50[last])
    ema_stack_short = (not cfg.use_ema_stack) or \
                      (closes[last] < ema20[last] and ema20[last] < ema50[last])

    hour = datetime.datetime.fromtimestamp(bars[last]["t"] / 1000, datetime.timezone.utc).hour
    in_session = (not cfg.use_session) or \
                 session_in(hour, cfg.session_start, cfg.session_end)

    # ── Liquidity sweep / BOS (Pine lines 592-618) ──
    ph = pivot_high(highs, cfg.sweep_len, cfg.sweep_len)
    pl = pivot_low(lows, cfg.sweep_len, cfg.sweep_len)
    last_swing_high = [None] * n
    last_swing_low = [None] * n
    sh = sl = None
    sweep_low = [False] * n
    sweep_high = [False] * n
    bull_bos = [False] * n
    bear_bos = [False] * n
    for i in range(n):
        if ph[i] is not None:
            sh = ph[i]
        if pl[i] is not None:
            sl = pl[i]
        last_swing_high[i] = sh
        last_swing_low[i] = sl
        if sl is not None and lows[i] < sl < closes[i]:
            sweep_low[i] = True
        if sh is not None and highs[i] > sh > closes[i]:
            sweep_high[i] = True
        if sh is not None and i > 0 and closes[i - 1] <= sh < closes[i]:
            bull_bos[i] = True
        if sl is not None and i > 0 and closes[i - 1] >= sl > closes[i]:
            bear_bos[i] = True

    def bars_since(flags, i):
        for k in range(i, -1, -1):
            if flags[k]:
                return i - k
        return None

    bs_low = bars_since(sweep_low, last)
    bs_high = bars_since(sweep_high, last)
    recent_sweep_low = bs_low is not None and bs_low <= cfg.sweep_recency
    recent_sweep_high = bs_high is not None and bs_high <= cfg.sweep_recency
    recent_bull_bos = any(bull_bos[last - k] for k in range(0, 3) if last - k >= 0)
    recent_bear_bos = any(bear_bos[last - k] for k in range(0, 3) if last - k >= 0)

    smc_bias = _smc_bias_series(bars, cfg.smc_pivot_len)[last]
    smc_long_ok = (not cfg.use_smc_align) or smc_bias == 1
    smc_short_ok = (not cfg.use_smc_align) or smc_bias == -1

    quality = in_session and ema_sep_ok and vol_ok and ema_slope_ok
    long_cond = (quality and cross_bull and dir_up and smc_long_ok and ema_stack_long
                 and (not cfg.use_sweep or recent_sweep_low)
                 and (not cfg.use_bos or recent_bull_bos))
    short_cond = (quality and cross_bear and dir_down and smc_short_ok and ema_stack_short
                  and (not cfg.use_sweep or recent_sweep_high)
                  and (not cfg.use_bos or recent_bear_bos))

    return {
        "ema20": ema20[last], "ema50": ema50[last], "ema100": ema100[last],
        "atr": atr_val, "atr_ma": atr_ma,
        "cross_bull": cross_bull, "cross_bear": cross_bear,
        "dir_up": dir_up, "dir_down": dir_down,
        "in_session": in_session, "ema_sep_ok": ema_sep_ok,
        "vol_ok": vol_ok, "ema_slope_ok": ema_slope_ok,
        "ema_stack_long": ema_stack_long, "ema_stack_short": ema_stack_short,
        "smc_bias": smc_bias, "smc_long_ok": smc_long_ok, "smc_short_ok": smc_short_ok,
        "recent_sweep_low": recent_sweep_low, "recent_sweep_high": recent_sweep_high,
        "recent_bull_bos": recent_bull_bos, "recent_bear_bos": recent_bear_bos,
        "long_cond": long_cond, "short_cond": short_cond,
        "close": closes[last],
    }


# -----------------------------------------------------------------------------
#  evaluate -- entry/exit decision for the last closed bar
# -----------------------------------------------------------------------------

def evaluate(bars, cfg=None, position=None):
    cfg = cfg or PineConfig()
    st = compute_state(bars, cfg)
    if not st:
        return None

    is_flat = position is None
    is_long = position == "long"
    is_short = position == "short"

    enter_long = st["long_cond"] and cfg.allow_long and \
                 (is_flat or (is_short and cfg.allow_reverse))
    enter_short = st["short_cond"] and cfg.allow_short and \
                  (is_flat or (is_long and cfg.allow_reverse))

    close = st["close"]
    qty = max(1, min(cfg.qty_per_trade, len(cfg.tp_mults)))

    def make(side):
        if side == "long":
            stop = snap(close - st["atr"] * cfg.stop_mult, cfg.tick)
            tps = [snap(close + st["atr"] * cfg.tp_mults[i], cfg.tick) for i in range(qty)]
        else:
            stop = snap(close + st["atr"] * cfg.stop_mult, cfg.tick)
            tps = [snap(close - st["atr"] * cfg.tp_mults[i], cfg.tick) for i in range(qty)]
        reasons = [k for k, on in (
            ("cross", st["cross_bull"] or st["cross_bear"]),
            ("dir", st["dir_up"] or st["dir_down"]),
            ("session", st["in_session"]), ("sep", st["ema_sep_ok"]),
            ("vol", st["vol_ok"]), ("slope", st["ema_slope_ok"])) if on]
        return Signal(side=side, entry=snap(close, cfg.tick), stop=stop, tps=tps,
                      qty=qty, bar_t=bars[-1]["t"], reason="+".join(reasons))

    if enter_long:
        return make("long")
    if enter_short:
        return make("short")

    # Opposite signal with reversing disabled -> go flat (Pine lines 752-756)
    if not cfg.allow_reverse and cfg.exit_on_opposite:
        if is_long and st["short_cond"]:
            return "flat"
        if is_short and st["long_cond"]:
            return "flat"
    return None
