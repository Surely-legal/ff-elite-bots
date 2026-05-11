#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF ELITE BOTS v7.0  --  8 Markets  --  4 Index Pairs  --  Auto-Save
===================================================================
  python run.py   (Windows CMD, PowerShell, Mac, Linux -- no pip needed)

  Markets    : ES/MES  NQ/MNQ  YM/MYM  RTY/M2K
  Strategies : 34 session-aware bots (Asia / London / NY / Sydney)
               25 standalone (Apex-eligible) + 9 combo (apexExclude)
  Data       : Yahoo Finance v8 OHLC + v7 quotes  ->  Stooq fallback
  State file : ff_bots_state_v7.json

===============================================================================
  VERSION HISTORY
===============================================================================

  v7.0  2026-05-11   17 new strategies + apexExclude flag
    + STRATS expanded 17 -> 34 (8 standalone + 9 combo strategies):
        Standalone (Apex-eligible):
          S1  OpenRangeBreak     NY only — first 12 NY bars define range
          S2  EMATripleStack     EMA 5/13/34 stack + pullback re-cross
          S3  SuperTrend         HL2 +/- mult*ATR band-flip
          S4  DonchianBreak      N-period high/low break (sess-tuned)
          S5  KeltnerBreak       EMA20 +/- mult*ATR outer break
          S6  VWAPDeviation      VWAP +/- sigma (NY+LONDON only)
          S7  AsiaOpenFade       RSI 20/80 fade, first 2 ASIA hours
          S8  EMACrossATRExpand  EMA 8/21 cross gated on ATR expansion
        Combo (apexExclude:true — regular bots only, NOT in Apex):
          C1  GoldenDeathMACD    SMA 50/200 cross + MACD histogram gate
          C2  IchimokuMACD       Kumo break + MACD zero-cross within 2 bars
          C3  ATRChannelMACD     ATR channel break + MACD direction gate
          C4  SARAdx             SAR flip + ADX trend strength gate
          C5  BBMacd             Bollinger outer break + MACD gate
          C6  MACDRsiFilter      MACD zero-cross + RSI mid-zone gate
          C7  EMAStochCombo      EMA 8/21 cross + Stoch %K extreme filter
          C8  VelocityMACD       ROC threshold break + MACD gate
          C9  ADXDonchian        Donchian break + ADX trend strength gate
    + apexExclude flag: STRATS entries with apexExclude:true are filtered
      out of getTop2BySession(), so combo strats never enter Apex AI
      consensus ranking. They still run as standalone bots and write
      sessionTally/perfMatrix entries (visible in the PF Ranking section
      as "no rank, combo strat" once they accumulate trades). This keeps
      Apex picking from single-indicator strats only and avoids two
      MACD-dependent combos voting together.
    ~ getTop2BySession() gains a single filter line:
        if(s.apexExclude)return;
      placed immediately after the liveIds.has(s.id) check. No other
      function or behavior changed.
    Note: this is a pure additive release. All v6.0-v6.9 strats and
          their behavior are untouched.
    * State file bumped to ff_bots_state_v7.json so v7 starts with a
      clean slate for all 34 strats. The v6 state file
      (ff_bots_state_v6.json) is left untouched on disk; renaming the
      v7 STATE_FILE constant back to v6 is enough to roll back
      cleanly. Empty per-session tallies will fill in as v7 strats
      fire and trades close.

  v6.9  2026-05-04   Fix recordPerfAll multi-session credit fanout
    Fix: recordPerfAll() previously called getActiveSessions(openTs) and
         credited every active session at open time. During NY/LONDON or
         ASIA/SYDNEY overlap windows that doubled the perfMatrix tally
         for any trade -- a single LONDON-overlap-of-NY trade inflated
         BOTH the LONDON|stratId|code and NY|stratId|code buckets, even
         though only one of those is the strategy's "home" session.
    ~ recordPerfAll now uses getSessionET(openTs) -- the single primary
      session priority order (MAINT > NY > LONDON > ASIA > SYDNEY) --
      so credits land in exactly one bucket: the same session stamped
      on the trade record (t.sess) at open time. perfMatrix fanout is
      gone, perfMatrix totals match sessionTally totals.
    Note: sessionTally was already correct (always credited via
          _sessTallyAdd(t.sess, ...) using the single primary session).
          PF ranking visualization is unaffected by this fix.
    + fullscreen Apex now shows a per-session PF ranking grid (added
      in the v6.8 series) so live PF rankings are visible across all
      four sessions side-by-side.

  v6.8  2026-05-04   Strict revert: drop v6.2 + v6.5 entirely
    - STRAT_FAMILY map and _familyOf() helper removed (no family logic).
    - REGIME_ALLOW / ADX_TREND_MIN / ADX_RANGE_MAX constants removed.
    - _computeApexRegime() helper removed.
    - 'regime' arg dropped from getTop2BySession / getApexBest /
      getApexConsensusSig / getApexFallbackSig.
    - 'regime' field no longer stamped on Apex trade records.
    ~ getApexConsensusSig reverted to pre-v6.2 strict consensus:
      both top-1 AND top-2 must have same-direction signals within
      lookback. Cross-family fallback is gone -- single-strat fires only
      via the FALLBACK MODE path (20-bar timeout + 5-bar duration).
    ~ Per-trade apexMode reverts to session-mode label (was vote-based
      in v6.2). Trades will be quieter overall (~80-90% rate drop).
    Kept : v6.0 baseline, v6.1 (no SL/TP averaging), v6.6 (PF ranking,
           min trades 10, PF>=1.0 floor), v6.7 (exit-on-touch).
    Why  : CCIReversal-on-NY firings traced to v6.2's immediate
           cross-family fallback path. User chose strict removal over
           surgical mitigation.

  v6.7  2026-05-04   Exit-on-touch  (live SL/TP retroactive scan)
    + checkLiveExits() now scans cumulative max-H / min-L across every bar
      since openT, plus dayHigh/dayLow as a ceiling/floor backstop. Any
      source reporting a wick at SL/TP triggers exit immediately.
    + checkLiveExits() also runs at end of refreshFull(), so retroactive
      chart-endpoint corrections book the exit before any new entry.
    Fix : trades whose TP/SL was breached on a wick missed by the live-
          quote sampler no longer remain open indefinitely.

  v6.6  2026-05-04   Profit-factor ranking + tighter eligibility
    ~ Strategy ranking swapped from expectancy to profit factor
      (PF = totalWinPts / totalLossPts).
    ~ APEX_MIN_TRADES bumped 5 -> 10  (seasoned strats only).
    + APEX_PF_MIN = 1.0 floor; strats with PF < 1.0 excluded entirely.
    ~ UI shows "PF X.XX" in place of "E X.XX"; PF=infinity when no losses.

  v6.5  2026-05-04   ADX(14) regime filter   [REVERTED in v6.8]
    Originally added an ADX-based regime classifier and family-gated the
    eligible strat pool. Reverted in v6.8 because the strict consensus
    revert (also v6.8) makes the regime filter redundant -- without
    cross-family fallback, the only firing path is same-family CONSENSUS
    or 20-bar-timeout FALLBACK, neither of which benefits from family
    gating.

  v6.4  --           Veto-with-window     (no-op vs v6.2; void after v6.8)
    Same semantics were briefly implemented by v6.2 -- top-1 trades alone
    unless top-2 (same family) agrees in the same direction within
    apexLookbackBars(). No code change at the time. Behavior gone after
    v6.8 strict revert.

  v6.3  --           Per-trade max-loss cap   (skipped per design discussion)

  v6.2  2026-05-04   Family map + cross-family fallback   [REVERTED in v6.8]
    Originally added STRAT_FAMILY / _familyOf and made cross-family
    top-2 pairs collapse to immediate top-1-only firing. This change
    was traced as the proximate cause of CCIReversal-on-NY firings in
    low-ADX periods (and other unwanted single-strat trades), so the
    behavior was strict-reverted in v6.8.

  v6.1  2026-05-04   SL/TP averaging removed
    ~ Both CONSENSUS and FALLBACK now use the higher-PF strat's own SL/TP.
      Synthetic averaged levels removed -- they had no backtest basis and
      were the root cause of consensus losses on cross-family pairs.

  v6.0  baseline     Per-strategy expectancy tally, 20-bar fallback timeout,
                     getLiveStratIds() filter, ff_bots_state_v6.json save
                     (fully isolated from v3/v4/v5 saves), live-bar
                     re-evaluation each processBots cycle, _barClosedCodes
                     within-cycle dedup guard.

===============================================================================
"""

import sys, io as _io
try:
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except AttributeError:
    pass

import json, time, threading, webbrowser, http.server, urllib.parse
import urllib.request, csv, io, datetime, gzip, socket
import os  # ── AUTO-SAVE ──

PORT  = 7432
CODES = ("ES","MES","NQ","MNQ","YM","MYM","RTY","M2K")

# ── AUTO-SAVE ────────────────────────────────────────────────────────────────
STATE_FILE     = "ff_bots_state_v7.json"
AUTOSAVE_EVERY = 30 * 60   # seconds
# ─────────────────────────────────────────────────────────────────────────────

IV_CFG = {
    "1m":  ("1m",  "2d",   "5"),
    "5m":  ("5m",  "10d",  "5"),
    "15m": ("15m", "60d",  "15"),
    "1H":  ("1h",  "180d", "60"),
}

CONTRACTS = {
    "ES":  {"yf": "ES=F",   "stooq": "es.f"},
    "MES": {"yf": "MES=F",  "stooq": "mes.f"},
    "NQ":  {"yf": "NQ=F",   "stooq": "nq.f"},
    "MNQ": {"yf": "MNQ=F",  "stooq": "mnq.f"},
    "YM":  {"yf": "YM=F",   "stooq": "ym.f"},
    "MYM": {"yf": "MYM=F",  "stooq": "mym.f"},
    "RTY": {"yf": "RTY=F",  "stooq": "rty.f"},
    "M2K": {"yf": "M2K=F",  "stooq": "m2k.f"},
}

YF_HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
}


def _safe(msg):
    try: print(msg)
    except UnicodeEncodeError: print(msg.encode("ascii","replace").decode("ascii"))


def _get(url, hdrs=None, timeout=12):
    req = urllib.request.Request(url, headers=hdrs or YF_HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try: raw = gzip.decompress(raw)
    except: pass
    return raw


def _yf_ohlc(yf_sym, yf_iv, yf_range, host="query1"):
    url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(yf_sym)}?interval={yf_iv}&range={yf_range}"
           f"&includePrePost=true&corsDomain=finance.yahoo.com")
    d = json.loads(_get(url))
    res = d["chart"]["result"][0]
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        o,h,l,c = q["open"][i],q["high"][i],q["low"][i],q["close"][i]
        if any(v is None or v!=v for v in (o,h,l,c)): continue
        rows.append({"t":int(t)*1000,"o":round(o,2),"h":round(h,2),"l":round(l,2),"c":round(c,2)})
    if not rows: raise ValueError("all NaN")
    try:
        rt = float(res["meta"].get("regularMarketPrice") or 0)
        if rt > 0:
            rows[-1]["c"] = round(rt,2)
            if rt > rows[-1]["h"]: rows[-1]["h"] = round(rt,2)
            if rt < rows[-1]["l"]: rows[-1]["l"] = round(rt,2)
    except: pass
    return rows


def _stooq_ohlc(stooq_sym, stooq_min):
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(stooq_sym)}&i={stooq_min}"
    raw = _get(url, {"User-Agent":"Mozilla/5.0","Accept":"text/csv,*/*"})
    rows = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8","replace"))):
        try:
            ds = row.get("Date","").strip(); ts2 = row.get("Time","000000").strip()
            if not ds or ds.lower() in ("date","no data"): continue
            dts = f"{ds} {ts2[:2]}:{ts2[2:4]}:{ts2[4:6]}"
            try: dt = datetime.datetime.strptime(dts,"%Y-%m-%d %H:%M:%S")
            except: dt = datetime.datetime.strptime(ds,"%Y-%m-%d")
            o=float(row.get("Open",0) or 0); h=float(row.get("High",0) or 0)
            l=float(row.get("Low",0) or 0);  c=float(row.get("Close",0) or 0)
            if o==0 and c==0: continue
            rows.append({"t":int(dt.timestamp()*1000),"o":round(o,2),"h":round(h,2),"l":round(l,2),"c":round(c,2)})
        except: continue
    if not rows: raise ValueError("no rows")
    rows.sort(key=lambda r: r["t"])
    return rows


def fetch_ohlc(code, iv):
    cfg = IV_CFG.get(iv, IV_CFG["5m"])
    yf_sym = CONTRACTS[code]["yf"]; stooq_s = CONTRACTS[code]["stooq"]
    errs = []
    for host in ("query1","query2"):
        try:
            rows = _yf_ohlc(yf_sym, cfg[0], cfg[1], host)
            _safe(f"  [OK] {code:4s}  YF/{host}  {len(rows):4d} bars  last={rows[-1]['c']}")
            return rows, f"Yahoo Finance ({host})"
        except Exception as e: errs.append(f"YF/{host}: {e}")
    try:
        rows = _stooq_ohlc(stooq_s, cfg[2])
        _safe(f"  [OK] {code:4s}  Stooq  {len(rows):4d} bars  last={rows[-1]['c']}")
        return rows, "Stooq"
    except Exception as e: errs.append(f"Stooq: {e}")
    raise RuntimeError(" | ".join(errs))


def fetch_quotes_batch():
    syms = ",".join(urllib.parse.quote(CONTRACTS[c]["yf"]) for c in CODES)
    fields = ("regularMarketPrice,regularMarketTime,regularMarketDayHigh,"
              "regularMarketDayLow,regularMarketChange,regularMarketChangePercent,"
              "regularMarketPreviousClose")
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}&fields={fields}"
    data = json.loads(_get(url))
    out = {}
    for r in data["quoteResponse"]["result"]:
        price = r.get("regularMarketPrice")
        if not price: continue
        for code, cfg in CONTRACTS.items():
            if cfg["yf"] == r.get("symbol",""):
                out[code] = {
                    "price":     round(float(price),2),
                    "ts_ms":     int(r.get("regularMarketTime",time.time()))*1000,
                    "dayHigh":   round(float(r.get("regularMarketDayHigh") or price),2),
                    "dayLow":    round(float(r.get("regularMarketDayLow")  or price),2),
                    "change":    round(float(r.get("regularMarketChange")  or 0),2),
                    "changePct": round(float(r.get("regularMarketChangePercent") or 0),4),
                }
    return out


_ohlc_cache  = {}
_quote_cache = {"data": {}, "ts": 0}
_lock = threading.Lock()

def get_ohlc(code, iv):
    key = f"{code}|{iv}"
    with _lock:
        e = _ohlc_cache.get(key)
        if e and time.time()-e["ts"] < 30: return e["data"]
    try:
        rows, src = fetch_ohlc(code, iv)
        out = {"live":True,"candles":rows,"source":src}
    except RuntimeError as e:
        _safe(f"  [--] {code}: {e}")
        with _lock: e2 = _ohlc_cache.get(key)
        out = e2["data"] if e2 else {"live":False,"candles":[],"source":"unavailable"}
    with _lock: _ohlc_cache[key] = {"data":out,"ts":time.time()}
    return out

def get_quotes():
    with _lock:
        if time.time()-_quote_cache["ts"] < 0.75: return _quote_cache["data"]
    try:
        data = fetch_quotes_batch()
        with _lock: _quote_cache["data"]=data; _quote_cache["ts"]=time.time()
        return data
    except Exception as e:
        _safe(f"  [--] quotes: {e}")
        with _lock: return dict(_quote_cache["data"])


# ── AUTO-SAVE: direct file I/O only ──────────────────────────────────────────
def _save_state_to_disk(data):
    """Write bot state JSON to disk atomically (temp file + rename)."""
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, STATE_FILE)
        _safe(f"  [SAVE] State saved -> {STATE_FILE}  ({len(json.dumps(data))//1024} KB)")
    except Exception as e:
        _safe(f"  [--] Auto-save failed: {e}")


def _load_state_from_disk():
    """Return saved state dict or None if file missing / corrupt."""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        age_min = (time.time() - data.get("savedAt", 0) / 1000) / 60
        _safe(f"  [LOAD] Restored state from {STATE_FILE}  (saved {age_min:.0f} min ago)")
        return data
    except Exception as e:
        _safe(f"  [--] State load failed: {e}")
        return None
# ─────────────────────────────────────────────────────────────────────────────


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FF Elite Bots v7</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@700;900&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#131722;--p1:#1e222d;--p2:#1e222d;--p3:#2a2e39;
  --b1:#2a2e39;--b2:#363a45;
  --tx:#d1d4dc;--tx2:#787b86;--tx3:#4c525e;--tx4:#2f3241;
  --cy:#2962ff;--pu:#9c27b0;--or:#ff9800;--pk:#e91e63;
  --gr:#00bfa5;--rd:#f44336;--bl:#42a5f5;--lm:#cddc39;
  --up:#26a69a;--dn:#ef5350;--yw:#f5a623;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--tx);
  font-family:'Share Tech Mono',monospace;font-size:11px}
#app{display:flex;flex-direction:column;height:100vh;overflow:hidden}
#top{display:flex;align-items:center;height:46px;flex-shrink:0;padding:0 10px;
  background:var(--p1);border-bottom:1px solid var(--b2);gap:0;overflow:hidden}
#logo{font-family:'Orbitron',sans-serif;font-size:11px;font-weight:900;color:var(--cy);
  letter-spacing:2px;padding-right:10px;border-right:1px solid var(--b1);margin-right:8px;white-space:nowrap}
#ltag{padding:2px 7px;border-radius:3px;font-size:7.5px;font-weight:bold;
  background:var(--p2);color:var(--tx3);border:1px solid var(--b1);margin-right:8px;
  transition:all .3s;min-width:62px;text-align:center;white-space:nowrap}
#ltag.live{background:#1a2e1a;color:var(--up);border-color:#26a69a40}
#ltag.closed{background:#1a1a2e;color:var(--pu);border-color:#9c27b040}
.ivg{display:flex;gap:2px;margin-right:8px;padding-right:8px;border-right:1px solid var(--b1)}
.ivb{padding:2px 8px;border:1px solid transparent;border-radius:3px;background:transparent;
  color:var(--tx3);cursor:pointer;font-family:'Share Tech Mono',monospace;font-size:9.5px;transition:all .15s}
.ivb:hover{color:var(--tx);background:var(--b1)}
.ivb.on{background:var(--cy);color:#fff;border-color:var(--cy)}
.ts{color:var(--tx3);font-size:8.5px;margin-right:8px;white-space:nowrap}.ts b{color:var(--tx)}
.sp{flex:1}
#tu{font-size:7.5px;color:var(--tx3);margin-left:8px;white-space:nowrap}
#qtag{font-size:7px;color:var(--tx3);margin-left:5px;padding:2px 5px;
  border-radius:2px;background:var(--b1);white-space:nowrap}
.sess-chip{padding:2px 6px;border-radius:3px;font-size:7px;font-weight:700;
  letter-spacing:1px;color:var(--tx3);background:var(--b1);border:1px solid transparent;transition:all .3s}
#sess-asia.active{color:#8080ff;background:#8080ff18;border-color:#8080ff50}
#sess-london.active{color:#f09030;background:#f0903018;border-color:#f0903050}
#sess-ny.active{color:#18c860;background:#18c86018;border-color:#18c86050}
#sess-sydney.active{color:#ffd700;background:#ffd70018;border-color:#ffd70050}
#body{display:flex;flex:1;overflow:hidden;min-height:0}
#left{width:232px;min-width:232px;flex-shrink:0;background:var(--p1);
  border-right:1px solid var(--b2);display:flex;flex-direction:column;overflow:hidden}
.ph{font-size:7.5px;font-weight:700;letter-spacing:1.5px;color:var(--tx3);
  padding:4px 10px;border-bottom:1px solid var(--b1);background:var(--p3);
  flex-shrink:0;text-transform:uppercase;display:flex;align-items:center;justify-content:space-between}
.card{padding:7px 10px;border-bottom:1px solid var(--b2)}
.r2{display:flex;justify-content:space-between;align-items:center;padding:1px 0;font-size:8.5px}
.r2 .k{color:var(--tx3)}
#bname{font-family:'Orbitron',sans-serif;font-size:9.5px;font-weight:700;color:var(--tx);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:2px}
#btype{color:var(--tx3);font-size:7.5px;margin-bottom:4px}
svg#spark{display:block;width:100%;height:22px;margin-top:4px;overflow:hidden}
#openbox{flex-shrink:0;overflow-y:auto;flex:1;border-bottom:1px solid var(--b2)}
.pos-card{border-bottom:1px solid var(--b1);padding:6px 9px 5px}
.pos-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.pos-mkt{font-family:'Orbitron',sans-serif;font-size:14px;font-weight:900;line-height:1}
.pos-strat{font-size:7px;color:var(--tx2);margin-top:1px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pos-dir{font-family:'Orbitron',sans-serif;font-size:9.5px;font-weight:700;
  padding:2px 7px;border-radius:3px;letter-spacing:1px}
.pos-dir.long{color:#26a69a;background:#26a69a18;border:1px solid #26a69a40}
.pos-dir.short{color:#ef5350;background:#ef535018;border:1px solid #ef535040}
.pos-sess{font-size:6.5px;font-weight:700;letter-spacing:1px;padding:1px 5px;border-radius:2px}
.pos-levels{display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;margin-bottom:4px}
.pos-lv{background:var(--p3);border-radius:3px;padding:3px 2px;text-align:center}
.pos-lv-label{font-size:6px;letter-spacing:1px;font-weight:700;margin-bottom:2px}
.pos-lv-val{font-family:'Orbitron',sans-serif;font-size:11px;font-weight:700;line-height:1}
.pos-lv-dist{font-size:5.5px;margin-top:2px;opacity:.65}
.pos-footer{display:flex;justify-content:space-between;align-items:center}
.pos-unr{font-family:'Orbitron',sans-serif;font-size:10px;font-weight:700}
.pos-meta{font-size:6.5px;color:var(--tx3);text-align:right;line-height:1.5}
#stratbox{flex-shrink:0;padding:6px 10px;font-size:8.5px;line-height:1.8;border-bottom:1px solid var(--b2)}
#ai-panel-left{flex-shrink:0;overflow-y:auto;max-height:200px;border-bottom:1px solid var(--b2)}
#center{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
#cgrid{display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:1fr 1fr;
  flex:1;gap:1px;padding:1px;background:var(--b1);min-height:0;overflow:hidden}
.cc{background:var(--bg);display:flex;flex-direction:column;overflow:hidden;min-height:0}
.ch{display:flex;justify-content:space-between;align-items:center;
  padding:3px 8px;border-bottom:1px solid var(--b2);flex-shrink:0;height:26px;background:var(--p1)}
.csym{font-family:'Orbitron',sans-serif;font-size:9.5px;font-weight:700}
.clive{font-family:'Orbitron',sans-serif;font-size:11px;font-weight:700;transition:color .3s}
.cw{flex:1;position:relative;overflow:hidden;min-height:0}
.cw canvas{display:block;position:absolute;top:0;left:0}
.sb{flex-shrink:0;border-top:1px solid var(--b2);padding:2px 6px;min-height:18px;
  display:flex;gap:3px;flex-wrap:nowrap;align-items:center;background:var(--p1);
  overflow-x:auto;overflow-y:hidden}
.sb::-webkit-scrollbar{height:2px}.sb::-webkit-scrollbar-thumb{background:var(--b2)}
.chip{padding:1px 5px;border-radius:2px;font-size:7.5px;display:inline-flex;flex-direction:row;gap:2px;align-items:center}
.cl{background:#26a69a18;color:var(--up);border:1px solid #26a69a30}
.cs{background:#ef535018;color:var(--dn);border:1px solid #ef535030}
#tradepane{height:130px;flex-shrink:0;display:flex;flex-direction:column;border-top:1px solid var(--b2)}
.tscroll{flex:1;overflow-y:auto}
#right{width:196px;min-width:196px;flex-shrink:0;background:var(--p1);
  border-left:1px solid var(--b2);display:flex;flex-direction:column;overflow:hidden}
#blist{flex:1;overflow-y:auto}
.brow{display:flex;align-items:center;gap:4px;padding:3px 7px;border-bottom:1px solid var(--b1);font-size:8.5px}
.brow.dead{opacity:.2}
.bdot{width:5px;height:5px;border-radius:50%;flex-shrink:0}
.bbar{flex:1;height:2px;background:var(--b2);border-radius:1px}
.bfill{height:100%;border-radius:1px;transition:width .8s}
.rsect{flex-shrink:0;padding:5px 9px;border-top:1px solid var(--b2);font-size:8px;line-height:1.9;color:var(--tx3)}
#log{height:30px;flex-shrink:0;background:var(--p3);border-top:1px solid var(--b2);
  overflow-x:auto;overflow-y:hidden;display:flex;align-items:center;padding:0 8px;gap:4px;white-space:nowrap}
.lc{display:inline-flex;align-items:center;padding:1px 7px;border-radius:2px;
  font-size:7.5px;border:1px solid var(--b1);flex-shrink:0}
.lc.win{background:#26a69a18;color:var(--up);border-color:#26a69a30}
.lc.loss{background:#ef535018;color:var(--dn);border-color:#ef535030}
.lc.kill{background:#3e1c1c;color:#f87171}
.lc.wave{background:#1e1a2e;color:var(--pu)}
.lc.info{background:var(--b1);color:var(--tx3)}
.lc.open{background:#1a2040;color:#7eb8ff;border-color:#2962ff40}
.lc.save{background:#1a2e1a;color:#26a69a;border-color:#26a69a30}
table.mt{width:100%;border-collapse:collapse}
table.mt th{font-size:6.5px;color:var(--tx3);padding:2px 4px;border-bottom:1px solid var(--b2);
  position:sticky;top:0;background:var(--p3);white-space:nowrap;text-align:left}
table.mt td{font-size:8px;padding:2px 4px;border-bottom:1px solid var(--b1);white-space:nowrap}
table.mt tr:hover td{background:var(--p2)}
::-webkit-scrollbar{width:3px;height:3px}::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--b2);border-radius:2px}
#chart-tooltip{position:fixed;pointer-events:none;z-index:100;display:none;
  background:#1e222d;border:1px solid #363a45;border-radius:4px;
  padding:7px 10px;font-family:'Share Tech Mono',monospace;font-size:8px;
  color:var(--tx);line-height:1.8;box-shadow:0 4px 20px #00000070;}
#chart-tooltip .tt-sym{font-family:'Orbitron',sans-serif;font-size:9px;font-weight:700;
  margin-bottom:3px;padding-bottom:3px;border-bottom:1px solid var(--b1);}
#chart-tooltip .tt-row{display:flex;justify-content:space-between;gap:12px;}
#chart-tooltip .tt-k{color:var(--tx3);}
#fs-overlay{display:none;position:fixed;inset:0;z-index:200;background:#131722;
  flex-direction:column;}
#fs-overlay.open{display:flex;}
#fs-header{display:flex;align-items:center;justify-content:space-between;height:44px;
  padding:0 16px;background:var(--p1);border-bottom:1px solid var(--b2);flex-shrink:0;}
#fs-meta{display:flex;align-items:center;gap:10px;}
#fs-sym{font-family:'Orbitron',sans-serif;font-size:14px;font-weight:900;}
#fs-price{font-family:'Orbitron',sans-serif;font-size:12px;font-weight:700;}
#fs-chg{font-size:9px;}
#fs-close{cursor:pointer;color:var(--tx3);font-size:11px;padding:4px 10px;
  border-radius:3px;border:1px solid var(--b1);transition:all .15s;letter-spacing:1px;}
#fs-close:hover{color:var(--tx);background:var(--b2);border-color:var(--b2);}
#fs-canvas-wrap{flex:1;position:relative;overflow:hidden;}
#fs-canvas-wrap canvas{display:block;position:absolute;top:0;left:0;}
#fs-positions{flex-shrink:0;background:var(--p1);border-top:1px solid var(--b2);
  display:none;overflow-x:auto;overflow-y:hidden;padding:6px 8px;
  gap:6px;align-items:stretch;min-height:0;max-height:140px;white-space:nowrap;}
#fs-positions.has-trades{display:flex;}
#fs-positions::-webkit-scrollbar{height:3px;}
#fs-positions::-webkit-scrollbar-thumb{background:var(--b2);}
.fs-pos-card{display:inline-flex;flex-direction:column;gap:3px;min-width:160px;max-width:200px;
  background:var(--p3);border-radius:4px;padding:7px 9px;border:1px solid var(--b2);
  flex-shrink:0;vertical-align:top;white-space:normal;}
.fs-pos-card.long-card{border-color:#26a69a40;}
.fs-pos-card.short-card{border-color:#ef535040;}
.fs-pos-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;}
.fs-pos-bot{font-size:7px;color:var(--tx3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.fs-pos-dir{font-family:'Orbitron',sans-serif;font-size:8px;font-weight:700;
  padding:1px 6px;border-radius:2px;letter-spacing:1px;}
.fs-pos-dir.long{color:#26a69a;background:#26a69a18;border:1px solid #26a69a40;}
.fs-pos-dir.short{color:#ef5350;background:#ef535018;border:1px solid #ef535040;}
.fs-pos-levels{display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px;margin-bottom:3px;}
.fs-pos-lv{background:var(--p2);border-radius:2px;padding:2px 3px;text-align:center;}
.fs-pos-lv-lbl{font-size:5.5px;letter-spacing:1px;font-weight:700;color:var(--tx3);}
.fs-pos-lv-val{font-family:'Orbitron',sans-serif;font-size:9px;font-weight:700;line-height:1.2;}
.fs-pos-unr{font-family:'Orbitron',sans-serif;font-size:11px;font-weight:700;text-align:center;}
.fs-pos-meta{display:flex;justify-content:space-between;font-size:6px;color:var(--tx3);}
#strat-modal{display:none;position:fixed;inset:0;z-index:300;
  background:#00000090;align-items:center;justify-content:center;}
#strat-modal.open{display:flex;}
#strat-modal-inner{background:var(--p1);border:1px solid var(--b2);border-radius:6px;
  width:600px;max-width:95vw;max-height:82vh;display:flex;flex-direction:column;
  overflow:hidden;box-shadow:0 8px 40px #00000090;}
#strat-modal-header{padding:10px 14px;background:var(--p3);border-bottom:1px solid var(--b2);
  flex-shrink:0;display:flex;align-items:center;justify-content:space-between;}
#strat-modal-title{font-family:'Orbitron',sans-serif;font-size:10px;font-weight:700;color:var(--tx);}
#strat-modal-sub{font-size:7px;color:var(--tx3);margin-top:2px;}
#strat-modal-close{cursor:pointer;color:var(--tx3);font-size:13px;padding:3px 8px;
  border-radius:3px;border:1px solid var(--b1);transition:all .15s;}
#strat-modal-close:hover{color:var(--tx);background:var(--b2);}
#strat-modal-body{flex:1;overflow-y:auto;}
#strat-modal-stats{display:flex;gap:1px;background:var(--b1);flex-shrink:0;}
.sm-stat{flex:1;background:var(--p2);padding:5px 10px;font-size:7px;color:var(--tx3);line-height:1.6;}
.sm-stat b{display:block;font-size:10px;font-family:'Orbitron',sans-serif;font-weight:700;}
.brow{cursor:pointer;transition:background .15s;}
.brow:hover{background:var(--p3)!important;}
</style>
</head>
<body>
<div id="app">
<div id="top">
  <div id="logo">FF BOTS</div>
  <div id="ltag">LOADING</div>
  <div class="ivg">
    <button class="ivb" data-iv="1m">1m</button>
    <button class="ivb on" data-iv="5m">5m</button>
    <button class="ivb" data-iv="15m">15m</button>
    <button class="ivb" data-iv="1H">1H</button>
  </div>
  <span class="ts">Active:<b id="ta">17</b></span>
  <span class="ts">Closed:<b id="tcl" style="color:var(--up)">0</b></span>
  <span class="ts">Bars:<b id="tbars" style="color:var(--tx2)">--</b></span>
  <span id="qtag">QUOTE --</span>
  <div class="sp"></div>
  <div id="tu">--</div>
  <div id="sess-bar" style="display:flex;gap:3px;margin-left:8px;padding-left:8px;border-left:1px solid var(--b1)">
    <span id="sess-ny"     class="sess-chip">NY</span>
    <span id="sess-sydney" class="sess-chip">SYD</span>
    <span id="sess-asia"   class="sess-chip">ASIA</span>
    <span id="sess-london" class="sess-chip">LON</span>
    <span id="sess-et" style="font-size:7px;color:var(--tx3);align-self:center;margin-left:3px;white-space:nowrap"></span>
  </div>
</div>
<div id="body">
  <div id="left">
    <div class="ph">Best Bot</div>
    <div class="card">
      <div id="bname">Waiting...</div><div id="btype">--</div>
      <div class="r2"><span class="k">Balance</span><b id="bbal">$50,000.00</b></div>
      <div class="r2"><span class="k">Net P&amp;L</span><b id="bpnl">+$0.00</b></div>
      <div class="r2"><span class="k">Win Rate</span><b id="bwr" style="color:var(--up)">0.0%</b></div>
      <div class="r2"><span class="k">W/L/Total</span><b id="bwl" style="color:var(--tx2)">0/0/0</b></div>
      <div class="r2"><span class="k">Score</span><b id="bsc" style="color:var(--yw)">--</b></div>
      <svg id="spark" viewBox="0 0 200 22" preserveAspectRatio="none"></svg>
    </div>
    <div class="ph">
      <span>Open Positions</span>
      <span id="open-count" style="color:var(--up);font-size:7px"></span>
    </div>
    <div id="openbox"><div style="padding:8px 10px;color:var(--tx3);font-size:8.5px">Waiting for signals...</div></div>
    <div class="ph" id="apex-header" style="border-top:1px solid var(--b2);display:flex;align-items:center;gap:6px">
      <span style="color:#7eb8ff">&#x2B21; APEX AI</span>
      <span id="ai-wr-badge" style="font-size:6.5px;color:var(--tx3);font-weight:normal;text-transform:none;letter-spacing:0"></span>
      <span id="apex-expand-btn" onclick="openApexFullscreen()" title="Open Apex fullscreen view" style="margin-left:auto;cursor:pointer;font-size:11px;line-height:1;color:#7eb8ff;padding:3px 7px;border:1px solid #7eb8ff60;background:#7eb8ff12;border-radius:2px;letter-spacing:0">&#x26F6;</span>
    </div>
    <div id="ai-panel-left"><div style="padding:8px 10px;color:var(--tx3);font-size:8px">Learning... needs WR&gt;50% strategy per session</div></div>
    <div id="ai-trades-panel" style="flex-shrink:0;overflow-y:auto;max-height:130px;border-bottom:1px solid var(--b2);display:none"></div>
  </div>
  <!-- ── Apex AI fullscreen overlay ─────────────────────────── -->
  <div id="apex-fs" style="display:none;position:fixed;inset:0;background:#0c0e15f2;z-index:9999;flex-direction:column;font-family:inherit">
    <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--b2);background:#0a0c12">
      <span style="font-size:11px;color:#7eb8ff;font-weight:700;letter-spacing:2px;flex:1">&#x2B21; APEX AI &mdash; FULLSCREEN</span>
      <span id="apex-fs-tabs" style="display:flex;gap:6px"></span>
      <span onclick="closeApexFullscreen()" style="cursor:pointer;color:var(--tx2);padding:3px 10px;border:1px solid var(--b2);font-size:9px" title="Close">&#x2715; CLOSE</span>
    </div>
    <div id="apex-fs-stats" style="padding:10px 14px;border-bottom:1px solid var(--b2)"></div>
    <div id="apex-fs-pf-rank" style="padding:8px 14px;border-bottom:1px solid var(--b2);background:#f5a62308"></div>
    <div id="apex-fs-open" style="padding:8px 14px;border-bottom:1px solid var(--b2);background:#7eb8ff08"></div>
    <div id="apex-fs-chart-wrap" style="padding:8px 14px;border-bottom:1px solid var(--b2)">
      <div style="font-size:7px;color:var(--tx3);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Cumulative P&amp;L</div>
      <div id="apex-fs-chart" style="height:160px"></div>
    </div>
    <div id="apex-fs-trades" style="flex:1;overflow-y:auto;padding:0 14px 10px"></div>
  </div>
  <!-- ── Win Rate fullscreen overlay (3 columns: standalones / combos / leaderboard) ── -->
  <div id="wr-fs" style="display:none;position:fixed;inset:0;background:#0c0e15f2;z-index:9999;flex-direction:column;font-family:inherit">
    <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--b2);background:#0a0c12">
      <span style="font-size:11px;color:#26a69a;font-weight:700;letter-spacing:2px;flex:1">&#x2696; WIN RATE &mdash; FULLSCREEN</span>
      <span style="font-size:8px;color:var(--tx3);letter-spacing:1px">STANDALONE &nbsp;|&nbsp; COMBO &nbsp;|&nbsp; LEADERBOARD</span>
      <span onclick="closeWRFullscreen()" style="cursor:pointer;color:var(--tx2);padding:3px 10px;border:1px solid var(--b2);font-size:9px" title="Close">&#x2715; CLOSE</span>
    </div>
    <div style="flex:1;display:flex;overflow:hidden">
      <div style="flex:1;display:flex;flex-direction:column;border-right:1px solid var(--b2);min-width:0">
        <div class="ph" style="padding:6px 12px;border-bottom:1px solid var(--b2);background:#1a2e1a08">Standalone &mdash; Apex-eligible <span id="wr-fs-std-count" style="margin-left:auto;color:var(--tx3);font-weight:normal"></span></div>
        <div id="wr-fs-standalones" style="flex:1;overflow-y:auto"></div>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;border-right:1px solid var(--b2);min-width:0">
        <div class="ph" style="padding:6px 12px;border-bottom:1px solid var(--b2);background:#7eb8ff08">Combo &mdash; apexExclude <span id="wr-fs-combo-count" style="margin-left:auto;color:var(--tx3);font-weight:normal"></span></div>
        <div id="wr-fs-combos" style="flex:1;overflow-y:auto"></div>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;min-width:0">
        <div class="ph" style="padding:6px 12px;border-bottom:1px solid var(--b2);background:#f5a62308">Leaderboard &mdash; Score Rank</div>
        <div id="wr-fs-leaderboard" style="flex:1;overflow-y:auto"></div>
      </div>
    </div>
  </div>
  <div id="center">
    <div id="cgrid"></div>
    <div id="tradepane">
      <div class="ph">All Bots &mdash; Closed Trades
        <span style="font-size:6.5px;color:var(--tx3);font-weight:normal;text-transform:none;letter-spacing:0;margin-left:8px">
          P&amp;L=(exit-entry)&times;ptVal
        </span>
      </div>
      <div class="tscroll">
        <table class="mt"><thead><tr>
          <th>MKT</th><th>BOT</th><th>SESS</th><th>DIR</th><th>ENTRY</th><th>EXIT</th><th>PTS</th><th>P&amp;L</th><th>RES</th>
        </tr></thead><tbody id="atbody"></tbody></table>
      </div>
    </div>
  </div>
  <div id="right">
    <div class="ph" style="display:flex;align-items:center;gap:6px">
      <span>Win Rate</span>
      <span id="wr-expand-btn" onclick="openWRFullscreen()" title="Open Win Rate fullscreen view" style="margin-left:auto;cursor:pointer;font-size:11px;line-height:1;color:#7eb8ff;padding:3px 7px;border:1px solid #7eb8ff60;background:#7eb8ff12;border-radius:2px;letter-spacing:0">&#x26F6;</span>
    </div>
    <div id="sess-best-sect" style="border-bottom:1px solid var(--b2)"></div>
    <div id="blist"></div>
    <div class="ph" style="border-top:1px solid var(--b2)">Sources</div>
    <div id="srcsect" class="rsect"></div>
    <div class="ph" style="border-top:1px solid var(--b2)">Contract Specs</div>
    <div class="rsect" style="font-size:7.5px;line-height:1.75">
      <b style="color:var(--tx2)">S&amp;P 500</b><br>
      <span style="color:#2962ff">ES </span>$50/pt &middot; 0.25 tick<br>
      <span style="color:#5585ff">MES</span> $5/pt &middot; 0.25 tick<br>
      <b style="color:var(--tx2)">Nasdaq 100</b><br>
      <span style="color:#ff9800">NQ </span>$20/pt &middot; 0.25 tick<br>
      <span style="color:#ffb74d">MNQ</span> $2/pt &middot; 0.25 tick<br>
      <b style="color:var(--tx2)">Dow Jones</b><br>
      <span style="color:#00bfa5">YM </span>$5/pt &middot; 1pt tick<br>
      <span style="color:#4dd0c4">MYM</span> $0.50/pt &middot; 1pt tick<br>
      <b style="color:var(--tx2)">Russell 2000</b><br>
      <span style="color:#e91e63">RTY</span> $50/pt &middot; 0.10 tick<br>
      <span style="color:#f06292">M2K</span> $5/pt &middot; 0.10 tick<br>
    </div>
    <div class="ph" style="border-top:1px solid var(--b2)">Suspend / Revive</div>
    <div class="rsect" style="font-size:7.5px">WR &lt;25% after 20 &rarr; suspended<br>Revives fresh at each new session<br>No wave spawning &mdash; all 34 run always</div>
  </div>
</div>
<div id="log"><span class="lc info">FF Elite Bots v7 &mdash; 8 markets &mdash; 4 index pairs &mdash; 34 session-aware strategies (25 Apex-eligible + 9 combo)</span></div>
</div>

<div id="chart-tooltip"></div>

<div id="fs-overlay">
  <div id="fs-header">
    <div id="fs-meta">
      <span id="fs-sym"></span>
      <span id="fs-price">--</span>
      <span id="fs-chg"></span>
    </div>
    <span id="fs-close">&#x2715; &nbsp;ESC</span>
  </div>
  <div id="fs-canvas-wrap"></div>
  <div id="fs-positions"></div>
</div>

<div id="strat-modal">
  <div id="strat-modal-inner">
    <div id="strat-modal-header">
      <div>
        <div id="strat-modal-title"></div>
        <div id="strat-modal-sub"></div>
      </div>
      <span id="strat-modal-close">&#x2715;</span>
    </div>
    <div id="strat-modal-stats"></div>
    <div id="strat-modal-body">
      <table class="mt"><thead><tr>
        <th>MKT</th><th>SESS</th><th>DIR</th><th>ENTRY</th><th>EXIT</th><th>PTS</th><th>P&amp;L</th><th>RESULT</th>
      </tr></thead><tbody id="strat-modal-tbody"></tbody></table>
    </div>
  </div>
</div>

<script>
const MKTS=[
  {id:"NQ", code:"NQ", name:"E-Mini Nasdaq-100",   ptVal:20,  tick:0.25, col:"#ff9800", pair:"NDX", tier:1, conf:1.00, tierLabel:"T1\u00b7MAX"},
  {id:"MNQ",code:"MNQ",name:"Micro E-Mini NQ",     ptVal:2,   tick:0.25, col:"#ffb74d", pair:"NDX", tier:1, conf:1.00, tierLabel:"T1\u00b7MAX"},
  {id:"ES", code:"ES", name:"E-Mini S&P 500",      ptVal:50,  tick:0.25, col:"#2962ff", pair:"SPX", tier:2, conf:0.85, tierLabel:"T2\u00b7HIGH"},
  {id:"MES",code:"MES",name:"Micro E-Mini S&P",    ptVal:5,   tick:0.25, col:"#5585ff", pair:"SPX", tier:2, conf:0.85, tierLabel:"T2\u00b7HIGH"},
  {id:"YM", code:"YM", name:"E-Mini Dow Jones",    ptVal:5,   tick:1.00, col:"#00bfa5", pair:"DJI", tier:3, conf:0.65, tierLabel:"T3\u00b7MOD"},
  {id:"MYM",code:"MYM",name:"Micro E-Mini Dow",    ptVal:0.5, tick:1.00, col:"#4dd0c4", pair:"DJI", tier:3, conf:0.65, tierLabel:"T3\u00b7MOD"},
  {id:"RTY",code:"RTY",name:"E-Mini Russell 2000",  ptVal:50,  tick:0.10, col:"#e91e63", pair:"RUT", tier:4, conf:0.45, tierLabel:"T4\u00b7LOW"},
  {id:"M2K",code:"M2K",name:"Micro E-Mini Russell", ptVal:5,   tick:0.10, col:"#f06292", pair:"RUT", tier:4, conf:0.45, tierLabel:"T4\u00b7LOW"},
];
const snap=(p,tick)=>Math.round(p/tick)*tick;
let candles={},liveQ={},sources={},prevPx={},dirty={};
let processedTs={},iv="5m",isLive=false;
let wave=1,uid=0,totalClosed=0,bots=[],allClosed=[],logE=[];
let startupDone=false;
let prevBestTradeKeys=new Set();
let prevBestBotUid=null;
let soundSeeded=false;
const bs=code=>candles[code]??[];
let hoverState={};
const pendingSignals={};

// ── Performance matrix ─────────────────────────────────────────
const perfMatrix={};
function recordPerf(stratId,sess,code,won,pnl,openTs){
  const k=`${stratId}|${sess}|${code}`;
  if(!perfMatrix[k])perfMatrix[k]={w:0,l:0,pnl:0,bestWin:0,trades:[]};
  won?perfMatrix[k].w++:perfMatrix[k].l++;
  perfMatrix[k].pnl=Math.round((perfMatrix[k].pnl+(pnl||0))*100)/100;
  if(won&&pnl>0)perfMatrix[k].bestWin=Math.max(perfMatrix[k].bestWin,pnl);
  perfMatrix[k].trades.push({ts:openTs||Date.now(),won,pnl:pnl||0});
  if(perfMatrix[k].trades.length>200)perfMatrix[k].trades=perfMatrix[k].trades.slice(-200);
}

function recordPerfAll(stratId,openTs,code,won,pnl){
  // v6.9 fix: credit only the single primary session at open time.
  // getActiveSessions() returns every active session during overlap
  // windows (e.g. ["NY","LONDON"]), which used to fan tally credits
  // across both buckets and inflate perfMatrix totals. getSessionET()
  // returns one session via priority order (MAINT > NY > LONDON >
  // ASIA > SYDNEY), matching the t.sess stamped on the trade record.
  const sess=getSessionET(openTs);
  if(!sess)return;
  recordPerf(stratId,sess,code,won,pnl,openTs);
}
function perfWR(stratId,sess,code){
  const k=`${stratId}|${sess}|${code}`;
  const p=perfMatrix[k];
  return p&&(p.w+p.l)>=3 ? p.w/(p.w+p.l) : null;
}

function getBestStratForSession(sess){
  let best=null;
  STRATS.forEach(s=>{
    MKTS.forEach(m=>{
      const k=`${s.id}|${sess}|${m.code}`;
      const p=perfMatrix[k];
      if(!p)return;
      const n=p.w+p.l; if(n<3)return;
      const wr=p.w/n;
      if(!best||wr>best.wr)best={strat:s,wr,mktCode:m.code,mktCol:m.col,n,wins:p.w,pnl:p.pnl};
    });
  });
  return best;
}

function comboScore(p){
  if(!p)return 0;
  const n=p.w+p.l; if(n===0)return 0;
  const wr=p.w/n;
  const avgPnl=p.pnl/n;
  const pnlScore=Math.max(0,Math.min(1,avgPnl/500));
  return wr*0.80+pnlScore*0.20;
}

// ── Adaptive (AI) bot state ───────────────────────────────────
// _barClosedCodes: initialized here, reset each processBots cycle
// sessionTally: per-session per-strategy expectancy data, persists across iv
//   shape: {NY:{stratId:{wins,losses,totalWinPts,totalLossPts}}, LONDON:{...}, ...}
// apexMode: per-session CONSENSUS / FALLBACK timeout state
const adaptiveBot={
  uid:-1,name:"Apex AI",openTrades:{},closedTrades:[],wins:0,losses:0,
  _barClosedCodes:new Set(),
  sessionTally:{NY:{},LONDON:{},ASIA:{},SYDNEY:{}},
  apexMode:{NY:"CONSENSUS",LONDON:"CONSENSUS",ASIA:"CONSENSUS",SYDNEY:"CONSENSUS"},
  barsSinceLastTrade:{NY:0,LONDON:0,ASIA:0,SYDNEY:0},
  fallbackBarsRemaining:{NY:0,LONDON:0,ASIA:0,SYDNEY:0},
  // ── per-session Apex W/L (Apex's own combined trades, NOT per-strat) ──
  apexSessWL:{NY:{w:0,l:0},LONDON:{w:0,l:0},ASIA:{w:0,l:0},SYDNEY:{w:0,l:0}},
  // ── per-strategy per-market last raw signal cache (lookback consensus) ──
  // shape: {`${stratId}|${code}`: {dir, barT}} — overwritten on flip (auto-discard)
  _lastSig:{},
  // ── last bar.t we ticked Apex counters for, per market ──
  // prevents over-counting when the live bar is re-evaluated each cycle
  _lastApexTickT:{},
  // ── preserved placeholder fields (kept across save/restore) ──
  apexPaused:false,consecLosses:0,_lastDomId:null
};

// ── Only allow Apex to learn from non-suspended strategies ────
function getLiveStratIds(){
  return new Set(bots.filter(b=>!b.killed).map(b=>b.strat.id));
}

// ── Apex expectancy: per-session per-strategy tally ──────────
// Slot shape: {wins,losses,totalWinPts,totalLossPts}
// Recorded from regular bot trade closes (each bot runs one strategy);
// Apex's own combined trades are NOT tallied here (kept clean for selection).
// STEP 6: bumped from 5 -> 10 to require seasoned strats before they can rank.
const APEX_MIN_TRADES=10;
// STEP 6: profit-factor floor. Strats with PF < 1.0 are net-losers and are
// excluded from ranking entirely.
const APEX_PF_MIN=1.0;
const APEX_FALLBACK_BARS_THRESHOLD=20;
const APEX_FALLBACK_DURATION=5;
// v6.8 strict revert: ADX_TREND_MIN / ADX_RANGE_MAX / REGIME_ALLOW removed.
function _ensureSessSlot(sess,stratId){
  const t=adaptiveBot.sessionTally;
  if(!t[sess])t[sess]={};
  if(!t[sess][stratId])t[sess][stratId]={wins:0,losses:0,totalWinPts:0,totalLossPts:0};
  return t[sess][stratId];
}
// Strict whitelist for valid session keys — anything else is rejected.
const VALID_SESSIONS=new Set(["NY","LONDON","ASIA","SYDNEY"]);
function _sessTallyAdd(sess,stratId,won,pts){
  // ── strict scoping: only tally for whitelisted sessions and known strats ──
  if(!VALID_SESSIONS.has(sess))return;
  if(!stratId||!STRATS.some(s=>s.id===stratId))return;
  if(!adaptiveBot.sessionTally[sess])adaptiveBot.sessionTally[sess]={};
  const slot=_ensureSessSlot(sess,stratId);
  const p=Math.abs(pts||0);
  if(won){slot.wins++;slot.totalWinPts+=p;}
  else   {slot.losses++;slot.totalLossPts+=p;}
}
// STEP 6: also computes profit factor (totalWinPts / totalLossPts).
// PF is more stable than expectancy for ranking small-sample strats because
// it isn't distorted by a single tail trade.
function expectancy(sess,stratId){
  const z={exp:0,n:0,wr:0,avgWin:0,avgLoss:0,pf:0,totalWin:0,totalLoss:0};
  const slot=adaptiveBot.sessionTally?.[sess]?.[stratId];
  if(!slot)return z;
  const n=slot.wins+slot.losses;
  if(n===0)return z;
  const wr=slot.wins/n;
  const avgWin =slot.wins  >0?slot.totalWinPts /slot.wins  :0;
  const avgLoss=slot.losses>0?slot.totalLossPts/slot.losses:0;
  const totalWin =slot.totalWinPts ||0;
  const totalLoss=slot.totalLossPts||0;
  // PF undefined/inf if no losses; treat 0-loss-with-wins as Infinity, 0-loss-no-wins as 0.
  const pf=totalLoss>0?totalWin/totalLoss:(totalWin>0?Infinity:0);
  return{exp:wr*avgWin-(1-wr)*avgLoss,n,wr,avgWin,avgLoss,pf,totalWin,totalLoss};
}
// v6.8 strict revert: STRAT_FAMILY map, _familyOf(), and _computeApexRegime()
// all removed. No family logic and no regime classification.
// Top-2 non-suspended strategies by profit factor (≥APEX_MIN_TRADES each,
// PF ≥ APEX_PF_MIN). Tie-broken by expectancy.
// STEP 6: ranking is PF-based and gates on PF ≥ 1.0; min-trades 5 -> 10.
function getTop2BySession(sess){
  if(!sess||sess==="MAINT")return[];
  const liveIds=getLiveStratIds();
  const ranked=[];
  STRATS.forEach(s=>{
    if(!liveIds.has(s.id))return;
    if(s.apexExclude)return;
    const e=expectancy(sess,s.id);
    if(e.n<APEX_MIN_TRADES)return;
    if(!(e.pf>=APEX_PF_MIN))return; // also rejects NaN
    ranked.push({strat:s,exp:e.exp,n:e.n,wr:e.wr,avgWin:e.avgWin,
                 avgLoss:e.avgLoss,pf:e.pf});
  });
  // Sort by PF desc; Infinity (no-loss) sorts to top; expectancy as tiebreaker.
  ranked.sort((a,b)=>{
    if(a.pf===b.pf)return b.exp-a.exp;
    if(a.pf===Infinity)return -1;
    if(b.pf===Infinity)return 1;
    return b.pf-a.pf;
  });
  return ranked.slice(0,2);
}
// Best single (highest PF) — used for fallback / banner.
function getApexBest(sess){
  const top=getTop2BySession(sess);
  return top[0]||null;
}
// Compute SL/TP for a given strat at a given bar (mirrors bot-loop math)
function _stratLevels(strat,sig,entry,atrV,sessRRMult,mkConf,mkt){
  const c=mkConf??1.0;
  const rrMult=Math.max(1.0,strat.rr*sessRRMult);
  const dist=snap(Math.max(atrV*strat.atrMult*c,2*mkt.tick),mkt.tick);
  const sl=snap(sig==="long"?entry-dist:entry+dist,mkt.tick);
  const tp=snap(sig==="long"?entry+dist*rrMult:entry-dist*rrMult,mkt.tick);
  return{sl,tp,dist,rrMult};
}
// Interval-aware lookback for consensus
function _ivBarMs(){
  return iv==="1m"?60000:iv==="15m"?900000:iv==="1H"?3600000:300000;
}
function apexLookbackBars(){
  return iv==="1m"?5:iv==="5m"?4:iv==="15m"?3:iv==="1H"?3:2;
}
// Record a raw signal for a strategy on a market (lookback cache).
// Always overwrites the previous entry — flips auto-discard the older signal.
function _recordStratSig(stratId,code,dir,barT){
  if(!stratId||!code||!dir)return;
  adaptiveBot._lastSig[`${stratId}|${code}`]={dir,barT};
}
// Consensus signal with lookback window: both top-2 strategies must have a
// recorded signal in the same direction within `apexLookbackBars()` bars on
// this market. Only the most recent signal per strategy is consulted.
// v6.8 strict revert: requires top.length>=2 and r1.dir===r2.dir; no family
// gate, no cross-family fallback, no regime filter. Single-strat trades only
// happen via the FALLBACK MODE path (20-bar timeout + 5-bar duration).
function getApexConsensusSig(bars,sess,code,curBarT){
  const top=getTop2BySession(sess);
  if(top.length<2)return null;
  const lbMs=apexLookbackBars()*_ivBarMs();
  const r1=adaptiveBot._lastSig[`${top[0].strat.id}|${code}`];
  const r2=adaptiveBot._lastSig[`${top[1].strat.id}|${code}`];
  if(!r1||!r2)return null;
  if(curBarT-r1.barT>lbMs)return null;
  if(curBarT-r2.barT>lbMs)return null;
  if(r1.dir!==r2.dir)return null;
  return{sig:r1.dir,strats:top,strat1:top[0],strat2:top[1],
         lookbackBars:apexLookbackBars()};
}
// Fallback signal: single highest-PF strategy.
function getApexFallbackSig(bars,sess){
  const best=getApexBest(sess);
  if(!best)return null;
  const sig=best.strat.signal(bars);
  if(!sig)return null;
  return{sig,strats:[best],strat1:best,strat2:null};
}

let t1Consensus=null;

// ── Technical helpers ─────────────────────────────────────────
function ema(arr,p){
  if(!arr||arr.length<p)return(arr||[]).map(()=>null);
  const k=2/(p+1),out=Array(arr.length).fill(null);
  out[p-1]=arr.slice(0,p).reduce((a,b)=>a+b,0)/p;
  for(let i=p;i<arr.length;i++)out[i]=arr[i]*k+out[i-1]*(1-k);
  return out;
}
function sma(arr,p){return arr.map((_,i)=>i<p-1?null:arr.slice(i-p+1,i+1).reduce((a,b)=>a+b,0)/p);}
function atrArr(b,p=14){
  if(!b?.length)return[];
  const tr=b.map((c,i)=>i===0?c.h-c.l:Math.max(c.h-c.l,Math.abs(c.h-b[i-1].c),Math.abs(c.l-b[i-1].c)));
  return tr.map((_,i)=>i<p?null:tr.slice(i-p+1,i+1).reduce((a,b)=>a+b)/p);
}
function rsiArr(c,p=14){
  const r=Array(c.length).fill(null);if(c.length<p+1)return r;
  let g=0,l=0;for(let i=1;i<=p;i++){const d=c[i]-c[i-1];d>0?g+=d:l-=d;}
  let ag=g/p,al=l/p;r[p]=100-100/(1+ag/Math.max(al,1e-10));
  for(let i=p+1;i<c.length;i++){const d=c[i]-c[i-1];
    ag=(ag*(p-1)+(d>0?d:0))/p;al=(al*(p-1)+(d<0?-d:0))/p;
    r[i]=100-100/(1+ag/Math.max(al,1e-10));}
  return r;
}
function macdArr(c){
  const f=ema(c,12),s=ema(c,26);
  const line=c.map((_,i)=>f[i]!=null&&s[i]!=null?f[i]-s[i]:null);
  const vals=line.filter(v=>v!=null),sg=ema(vals,9);let si=0;
  const sig=line.map(v=>v==null?null:(sg[si++]??null));
  return{hist:line.map((v,i)=>v!=null&&sig[i]!=null?v-sig[i]:null)};
}
function bbArr(c,p=20,m=2){
  const sm=sma(c,p);
  return c.map((_,i)=>{if(sm[i]==null)return{u:null,l:null};
    const sl=c.slice(i-p+1,i+1),mn=sm[i],std=Math.sqrt(sl.reduce((a,v)=>a+(v-mn)**2,0)/p);
    return{u:mn+m*std,l:mn-m*std};});
}
function stochArr(b,p=9){
  return b.map((_,i)=>{if(i<p-1)return null;
    const sl=b.slice(i-p+1,i+1),hi=Math.max(...sl.map(c=>c.h)),lo=Math.min(...sl.map(c=>c.l));
    return hi===lo?50:((b[i].c-lo)/(hi-lo))*100;});
}
function cciArr(b,p=14){
  return b.map((_,i)=>{if(i<p-1)return null;
    const sl=b.slice(i-p+1,i+1),tp=sl.map(c=>(c.h+c.l+c.c)/3),mn=tp.reduce((a,b)=>a+b)/p;
    const md=tp.reduce((a,v)=>a+Math.abs(v-mn),0)/p;
    return md?((b[i].h+b[i].l+b[i].c)/3-mn)/(0.015*md):0;});
}
function sarArr(b,af=0.02,maxAF=0.2){
  if(b.length<2)return b.map(()=>null);
  const out=Array(b.length).fill(null);
  let bull=true,sar=b[0].l,ep=b[0].h,curAF=af;
  out[0]=sar;
  for(let i=1;i<b.length;i++){
    let nsar=sar+curAF*(ep-sar);
    if(bull){
      nsar=Math.min(nsar,b[i-1].l,i>=2?b[i-2].l:b[i-1].l);
      if(b[i].l<nsar){bull=false;sar=ep;ep=b[i].l;curAF=af;
        nsar=sar+curAF*(ep-sar);nsar=Math.max(nsar,b[i-1].h,i>=2?b[i-2].h:b[i-1].h);}
      else{if(b[i].h>ep){ep=b[i].h;curAF=Math.min(curAF+af,maxAF);}}
    }else{
      nsar=Math.max(nsar,b[i-1].h,i>=2?b[i-2].h:b[i-1].h);
      if(b[i].h>nsar){bull=true;sar=ep;ep=b[i].h;curAF=af;
        nsar=sar+curAF*(ep-sar);nsar=Math.min(nsar,b[i-1].l,i>=2?b[i-2].l:b[i-1].l);}
      else{if(b[i].l<ep){ep=b[i].l;curAF=Math.min(curAF+af,maxAF);}}
    }
    sar=nsar;out[i]=Math.round(sar*10000)/10000;
  }
  return out;
}
function adxArr(b,p=14){
  if(b.length<p*2)return b.map(()=>null);
  const out=Array(b.length).fill(null);
  const tr=[],pdm=[],ndm=[];
  for(let i=1;i<b.length;i++){
    const hi=b[i].h,lo=b[i].l,ph=b[i-1].h,pl=b[i-1].l,pc=b[i-1].c;
    tr.push(Math.max(hi-lo,Math.abs(hi-pc),Math.abs(lo-pc)));
    pdm.push(hi-ph>pl-lo&&hi-ph>0?hi-ph:0);
    ndm.push(pl-lo>hi-ph&&pl-lo>0?pl-lo:0);
  }
  let atr=tr.slice(0,p).reduce((a,v)=>a+v,0);
  let apdm=pdm.slice(0,p).reduce((a,v)=>a+v,0);
  let andm=ndm.slice(0,p).reduce((a,v)=>a+v,0);
  const dxArr=[];
  for(let i=p;i<tr.length;i++){
    atr=atr-atr/p+tr[i];apdm=apdm-apdm/p+pdm[i];andm=andm-andm/p+ndm[i];
    const pdi=atr>0?100*apdm/atr:0,ndi=atr>0?100*andm/atr:0;
    const dx=(pdi+ndi>0)?100*Math.abs(pdi-ndi)/(pdi+ndi):0;
    dxArr.push(dx);
  }
  if(dxArr.length<p)return out;
  let adx=dxArr.slice(0,p).reduce((a,v)=>a+v,0)/p;
  const adxStart=p+p;out[adxStart]=adx;
  for(let i=1;i<dxArr.length-p+1;i++){
    adx=(adx*(p-1)+dxArr[p-1+i])/p;
    if(adxStart+i<out.length)out[adxStart+i]=Math.round(adx*100)/100;
  }
  return out;
}
function ichimokuArr(b,t=9,k=26,sb=52){
  const midVal=(bars,p,i)=>{
    if(i<p-1)return null;
    const sl=bars.slice(i-p+1,i+1);
    return(Math.max(...sl.map(x=>x.h))+Math.min(...sl.map(x=>x.l)))/2;
  };
  return b.map((_,i)=>{
    const tenkan=midVal(b,t,i),kijun=midVal(b,k,i);
    const senkouA=tenkan!=null&&kijun!=null?(tenkan+kijun)/2:null;
    const senkouB=midVal(b,sb,i);
    return{tenkan,kijun,senkouA,senkouB,chikou:b[i].c};
  });
}

// ── Adaptive signal helpers ───────────────────────────────────
function sessScore(p){
  if(!p)return 0;
  const n=p.w+p.l; if(n===0)return 0;
  const wr=p.w/n,avgPnl=p.pnl/n,bestW=p.bestWin||0;
  return wr*0.50+Math.max(0,Math.min(1,avgPnl/500))*0.30+Math.max(0,Math.min(1,bestW/1000))*0.20;
}

// ── v6: liveIds filter — only learn from non-suspended strats ──
function getQualifiedStrats(sess,code){
  const liveIds=getLiveStratIds();
  return STRATS.filter(s=>{
    if(!liveIds.has(s.id))return false;
    const k=`${s.id}|${sess}|${code}`;
    const p=perfMatrix[k];
    if(!p)return false;
    const n=p.w+p.l; if(n===0)return false;
    return(p.w/n)>0.50&&p.pnl>0;
  });
}
function aiSessionReady(sess){return MKTS.some(m=>getQualifiedStrats(sess,m.code).length>0);}
function aiFullyUnlocked(){return["NY","LONDON","ASIA","SYDNEY"].filter(s=>aiSessionReady(s)).length>=2;}

// ── getBestForSession (v3 port) ────────────────────────────────
function getBestForSession(sess){
  const liveIds=getLiveStratIds();
  let best=null;
  STRATS.forEach(s=>{
    if(!liveIds.has(s.id))return;
    MKTS.forEach(m=>{
      const k=`${s.id}|${sess}|${m.code}`;
      const p=perfMatrix[k];
      if(!p)return;
      const n=p.w+p.l; if(n===0)return;
      if((p.w/n)<=0.50||p.pnl<=0)return;
      const sc=sessScore(p);
      if(!best||sc>best.sc)
        best={strat:s,sc,wr:p.w/n,avgPnl:p.pnl/n,bestWin:p.bestWin||0,
              n,wins:p.w,mktCode:m.code,mktCol:m.col,pnl:p.pnl};
    });
  });
  return best;
}

// ── getDominantStrat (v3 port — simple, no min-trades/decay/pause) ──
function getDominantStrat(sess){
  const liveIds=getLiveStratIds();
  const totals={};
  STRATS.forEach(s=>{
    if(!liveIds.has(s.id))return;
    MKTS.forEach(m=>{
      const k=`${s.id}|${sess}|${m.code}`;
      const p=perfMatrix[k];
      if(!p||p.w===0)return;
      if(!totals[s.id])totals[s.id]={strat:s,w:0,l:0,pnl:0,bestWin:0};
      totals[s.id].w   +=p.w;totals[s.id].l   +=p.l;totals[s.id].pnl +=p.pnl;
      if(p.bestWin>totals[s.id].bestWin)totals[s.id].bestWin=p.bestWin;
    });
  });
  let best=null;
  Object.values(totals).forEach(t=>{
    const n=t.w+t.l; if(n===0)return;
    const wr=t.w/n; if(wr<=0.50||t.pnl<=0)return;
    if(!best||t.w>best.w)best=t;
  });
  if(!best)return null;
  const n=best.w+best.l,wr=best.w/n;
  return{strat:best.strat,wins:best.w,n,wr,pnl:best.pnl,sc:sessScore(best)};
}

function getAdaptiveSig(code,bars,sess,atrVal){
  if(!atrVal||atrVal<=0)return null;
  const dom=getDominantStrat(sess);
  if(!dom)return null;
  const sig=dom.strat.signal(bars);
  if(!sig)return null;
  return{sig,conf:dom.sc,strat:{s:dom.strat,sc:dom.sc,wr:dom.wr,n:dom.n},
         votes:1,stratName:dom.strat.name,wins:dom.wins};
}

function computeT1Consensus(bars_ES,bars_NQ){
  if(!bars_ES||bars_ES.length<22||!bars_NQ||bars_NQ.length<22){t1Consensus=null;return;}
  const esC=bars_ES.map(c=>c.c),nqC=bars_NQ.map(c=>c.c);
  const esE=ema(esC,21),nqE=ema(nqC,21);
  const n=esC.length-1;
  const esUp=esC[n]>esE[n],nqUp=nqC[n]>nqE[n];
  const esMom=esC[n]>esC[n-3],nqMom=nqC[n]>nqC[n-3];
  const esLong=esUp&&esMom,esShort=!esUp&&!esMom;
  const nqLong=nqUp&&nqMom,nqShort=!nqUp&&!nqMom;
  if(esLong&&nqLong)t1Consensus="long";
  else if(esShort&&nqShort)t1Consensus="short";
  else t1Consensus="mixed";
}

// ── Session detector ──────────────────────────────────────────
function etHour(ts){
  const d=new Date(ts??Date.now());
  const y=d.getUTCFullYear();
  const dstStart=new Date(Date.UTC(y,2,8-(new Date(Date.UTC(y,2,1)).getUTCDay()+7)%7,7));
  const dstEnd  =new Date(Date.UTC(y,10,1+(7-(new Date(Date.UTC(y,10,1)).getUTCDay()))%7,6));
  const off=d>=dstStart&&d<dstEnd?-4:-5;
  return((d.getUTCHours()+off)+24)%24+d.getUTCMinutes()/60;
}
function _inSydney(h){return(h>=18||h<2);}
function _inAsia(h)  {return(h>=19||h<4);}
function _inLondon(h){return(h>=3 &&h<12);}
function _inNY(h)    {return(h>=8 &&h<17);}
function _inMaint(h) {return(h>=17&&h<18);}

function getActiveSessions(ts){
  const h=etHour(ts);
  if(_inMaint(h))return["MAINT"];
  const a=[];
  if(_inNY(h))     a.push("NY");
  if(_inLondon(h)) a.push("LONDON");
  if(_inAsia(h))   a.push("ASIA");
  if(_inSydney(h)) a.push("SYDNEY");
  return a.length?a:["SYDNEY"];
}
const _SESS_SHORT={NY:"NY",LONDON:"LON",ASIA:"ASIA",SYDNEY:"SYD",MAINT:"BREAK"};
function getSessionLabel(ts){return getActiveSessions(ts).map(s=>_SESS_SHORT[s]||s).join("+");}
function getSessionET(ts){
  const h=etHour(ts);
  if(_inMaint(h))  return"MAINT";
  if(_inNY(h))     return"NY";
  if(_inLondon(h)) return"LONDON";
  if(_inAsia(h))   return"ASIA";
  return"SYDNEY";
}
function primarySess(label){
  if(!label)return"NY";
  const first=label.split("+")[0];
  const map={NY:"NY",LON:"LONDON",ASIA:"ASIA",SYD:"SYDNEY",BREAK:"MAINT"};
  return map[first]||first;
}
const SESS_STYLE={
  ASIA:  {col:"#8080ff",bg:"#8080ff22",border:"#8080ff60"},
  LONDON:{col:"#f09030",bg:"#f0903022",border:"#f0903060"},
  NY:    {col:"#18c860",bg:"#18c86022",border:"#18c86060"},
  SYDNEY:{col:"#ffd700",bg:"#ffd70022",border:"#ffd70060"},
  MAINT: {col:"#4c525e",bg:"#4c525e22",border:"#4c525e60"},
};

// ── 17 Session-aware strategies ────────────────────────────────
const STRATS=[
  {id:"AsiaRangeFade",name:"Asia Fade",type:"RSI Fade / EMA Break",rr:2.0,atrMult:1.2,confirm:true,
   sess:{ASIA:"RSI 25/75",LONDON:"EMA 8/21",NY:"EMA 8/21"},
   desc:"ASIA: fade RSI extremes (25/75). LONDON/NY: EMA 8/21 golden-death cross.",
   signal(b){
     if(b.length<25)return null;
     const sess=getSessionET(b[b.length-1].t),c=b.map(x=>x.c),n=c.length-1;
     if(sess==="ASIA"){
       const ri=rsiArr(c,14);if(ri[n]==null||ri[n-1]==null)return null;
       if(ri[n-1]<=25&&ri[n]>25)return"long";if(ri[n-1]>=75&&ri[n]<75)return"short";
     }else{
       const f=ema(c,8),s=ema(c,21);if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
       if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     }
     return null;}},
  {id:"StochMaster",name:"Stoch Master",type:"Stoch %K Session",rr:1.5,atrMult:1.2,confirm:true,
   sess:{ASIA:"15/85",LONDON:"18/82",NY:"20/80"},
   desc:"Stochastic %K crossover tuned per session.",
   signal(b){
     if(b.length<15)return null;
     const sess=getSessionET(b[b.length-1].t),lo=sess==="ASIA"?15:sess==="LONDON"?18:20;
     const k=stochArr(b,9),n=k.length-1;if(k[n]==null||k[n-1]==null)return null;
     if(k[n-1]<=lo&&k[n]>lo)return"long";if(k[n-1]>=(100-lo)&&k[n]<(100-lo))return"short";
     return null;}},
  {id:"FFTopTrader",name:"FF Top Trader",type:"EMA Cross Session",rr:2.5,atrMult:1.5,
   sess:{ASIA:"EMA 5/13",LONDON:"EMA 8/21",NY:"EMA 8/34"},
   desc:"Golden/death cross with faster EMAs in quiet Asia, slower momentum in NY.",
   signal(b){
     if(b.length<40)return null;
     const sess=getSessionET(b[b.length-1].t),c=b.map(x=>x.c),n=c.length-1;
     const [fp,sp]=sess==="ASIA"?[5,13]:sess==="LONDON"?[8,21]:[8,34];
     const f=ema(c,fp),s=ema(c,sp);if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;}},
  {id:"VelocityBreak",name:"Velocity Break",type:"ROC Session",rr:2.0,atrMult:1.5,
   sess:{ASIA:"ROC 0.15%",LONDON:"ROC 0.25%",NY:"ROC 0.40%"},
   desc:"Rate-of-change momentum. Low threshold in quiet Asia, high in NY volume.",
   signal(b){
     if(b.length<16)return null;
     const sess=getSessionET(b[b.length-1].t),thresh=sess==="ASIA"?0.15:sess==="LONDON"?0.25:0.40;
     const c=b.map(x=>x.c),n=c.length-1;if(!c[n-10]||!c[n-11])return null;
     const r=(c[n]-c[n-10])/c[n-10]*100,rp=(c[n-1]-c[n-11])/c[n-11]*100;
     if(rp<thresh&&r>=thresh)return"long";if(rp>-thresh&&r<=-thresh)return"short";
     return null;}},
  {id:"BollingerBreak",name:"BB Squeeze",type:"Bollinger Session",rr:2.5,atrMult:1.5,
   sess:{ASIA:"BB(20,1.5)",LONDON:"BB(20,2.0)",NY:"BB(20,2.0)"},
   desc:"Close outside Bollinger Bands. Tighter 1.5x in slow Asia, 2.0x in London/NY.",
   signal(b){
     if(b.length<25)return null;
     const sess=getSessionET(b[b.length-1].t),mult=sess==="ASIA"?1.5:2.0;
     const c=b.map(x=>x.c),bb2=bbArr(c,20,mult),n=c.length-1;
     if(!bb2[n].u||!bb2[n-1].u)return null;
     if(c[n-1]<=bb2[n-1].u&&c[n]>bb2[n].u)return"long";
     if(c[n-1]>=bb2[n-1].l&&c[n]<bb2[n].l)return"short";
     return null;}},
  {id:"MACDWave",name:"MACD Wave",type:"MACD Hist Zero Cross",rr:2.0,atrMult:1.5,confirm:true,
   sess:{ASIA:"MACD",LONDON:"MACD",NY:"MACD"},
   desc:"MACD histogram crosses zero. Universal -- fires in all sessions.",
   signal(b){
     if(b.length<35)return null;
     const c=b.map(x=>x.c),{hist}=macdArr(c),n=hist.length-1;
     if(hist[n]==null||hist[n-1]==null)return null;
     if(hist[n-1]<=0&&hist[n]>0)return"long";if(hist[n-1]>=0&&hist[n]<0)return"short";
     return null;}},
  {id:"ATRChannel",name:"ATR Channel",type:"SMA+ATR Session",rr:2.5,atrMult:1.5,
   sess:{ASIA:"SMA20+1.5xATR",LONDON:"SMA20+2xATR",NY:"SMA20+2.5xATR"},
   desc:"Break above/below SMA20 +/- ATR channel. Channel widens from Asia to NY.",
   signal(b){
     if(b.length<30)return null;
     const sess=getSessionET(b[b.length-1].t),mult=sess==="ASIA"?1.5:sess==="LONDON"?2.0:2.5;
     const c=b.map(x=>x.c),at=atrArr(b,14),sm=sma(c,20),n=c.length-1;
     if(!at[n]||!sm[n]||!at[n-1]||!sm[n-1])return null;
     if(c[n-1]<=sm[n-1]+mult*at[n-1]&&c[n]>sm[n]+mult*at[n])return"long";
     if(c[n-1]>=sm[n-1]-mult*at[n-1]&&c[n]<sm[n]-mult*at[n])return"short";
     return null;}},
  {id:"CCIReversal",name:"CCI Reversal",type:"CCI Session",rr:2.0,atrMult:1.2,confirm:true,
   sess:{ASIA:"CCI \u00b180",LONDON:"CCI \u00b1100",NY:"CCI \u00b1100"},
   desc:"CCI crosses extreme. +/-80 in tight Asia range, +/-100 in London/NY.",
   signal(b){
     if(b.length<20)return null;
     const sess=getSessionET(b[b.length-1].t),lev=sess==="ASIA"?80:100;
     const ci=cciArr(b,14),n=ci.length-1;if(ci[n]==null||ci[n-1]==null)return null;
     if(ci[n-1]<=-lev&&ci[n]>-lev)return"long";if(ci[n-1]>=lev&&ci[n]<lev)return"short";
     return null;}},
  {id:"RSIMomentum",name:"RSI Momentum",type:"RSI Session",rr:2.0,atrMult:1.2,confirm:true,
   sess:{ASIA:"RSI 25/75",LONDON:"RSI 28/72",NY:"RSI 30/70"},
   desc:"RSI oversold/overbought crossover. Wider for Asia fade, tighter for NY.",
   signal(b){
     if(b.length<20)return null;
     const sess=getSessionET(b[b.length-1].t),lo=sess==="ASIA"?25:sess==="LONDON"?28:30;
     const c=b.map(x=>x.c),ri=rsiArr(c,14),n=ri.length-1;
     if(ri[n]==null||ri[n-1]==null)return null;
     if(ri[n-1]<=lo&&ri[n]>lo)return"long";if(ri[n-1]>=(100-lo)&&ri[n]<(100-lo))return"short";
     return null;}},
  {id:"OvernightMom",name:"Overnight Mom",type:"EMA 8/55 Session",rr:3.5,atrMult:1.5,trend:true,
   sess:{ASIA:"EMA 8/55",LONDON:"EMA 8/55",NY:"EMA 21/55"},
   desc:"ASIA/LONDON: fast 8/55 catches overnight momentum. NY: 21/55 rides session trend.",
   signal(b){
     if(b.length<62)return null;
     const sess=getSessionET(b[b.length-1].t),c=b.map(x=>x.c),n=c.length-1;
     const fp=sess==="NY"?21:8,f=ema(c,fp),s=ema(c,55);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;}},
  {id:"GoldenDeath",name:"Golden Death",type:"SMA 50/200 Cross",rr:3.5,atrMult:2.0,trend:true,
   sess:{ASIA:"SMA 50/200",LONDON:"SMA 50/200",NY:"SMA 50/200"},
   desc:"Classic Golden Cross (50 over 200) = long. Death Cross (50 under 200) = short.",
   signal(b){
     if(b.length<205)return null;
     const c=b.map(x=>x.c),n=c.length-1,f=sma(c,50),s=sma(c,200);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;}},
  {id:"RSI3070",name:"RSI 30/70",type:"RSI Overbought/Oversold",rr:2.0,atrMult:1.2,confirm:true,
   sess:{ASIA:"RSI 30/70",LONDON:"RSI 30/70",NY:"RSI 30/70"},
   desc:"Buy when RSI crosses up through 30. Sell when it crosses down through 70.",
   signal(b){
     if(b.length<20)return null;
     const c=b.map(x=>x.c),ri=rsiArr(c,14),n=ri.length-1;
     if(ri[n]==null||ri[n-1]==null)return null;
     if(ri[n-1]<=30&&ri[n]>30)return"long";if(ri[n-1]>=70&&ri[n]<70)return"short";
     return null;}},
  {id:"BBSqueeze",name:"BB Squeeze X",type:"Bollinger Squeeze Breakout",rr:2.5,atrMult:1.5,
   sess:{ASIA:"Squeeze+break",LONDON:"Squeeze+break",NY:"Squeeze+break"},
   desc:"Waits for bands to tighten to 50% of 20-bar average width, then trades the expansion breakout.",
   signal(b){
     if(b.length<30)return null;
     const c=b.map(x=>x.c),n=c.length-1,bb=bbArr(c,20,2);
     if(!bb[n].u||!bb[n-1].u)return null;
     const bw=bb.map(v=>v.u!=null?v.u-v.l:null);
     const recentBW=bw.slice(-20).filter(v=>v!=null);if(recentBW.length<10)return null;
     const avgBW=recentBW.reduce((a,v)=>a+v,0)/recentBW.length,curBW=bw[n];
     if(curBW>=avgBW*0.5)return null;
     if(c[n-1]<=bb[n-1].u&&c[n]>bb[n].u)return"long";
     if(c[n-1]>=bb[n-1].l&&c[n]<bb[n].l)return"short";
     return null;}},
  {id:"StochDivergence",name:"Stoch Divergence",type:"Stochastic Hidden Divergence",rr:2.5,atrMult:1.3,confirm:true,
   sess:{ASIA:"Stoch Div",LONDON:"Stoch Div",NY:"Stoch Div"},
   desc:"Price makes lower low but Stochastic makes higher low = hidden bullish divergence (and inverse).",
   signal(b){
     if(b.length<20)return null;
     const n=b.length-1,k=stochArr(b,9);if(k[n]==null||k[n-5]==null)return null;
     const priceLow5=Math.min(...b.slice(n-4,n+1).map(x=>x.l));
     const priceHigh5=Math.max(...b.slice(n-4,n+1).map(x=>x.h));
     const priceLow10=Math.min(...b.slice(n-9,n-4).map(x=>x.l));
     const priceHigh10=Math.max(...b.slice(n-9,n-4).map(x=>x.h));
     const kNow=k.slice(n-4,n+1).filter(v=>v!=null),kPrev=k.slice(n-9,n-4).filter(v=>v!=null);
     if(!kNow.length||!kPrev.length)return null;
     const kLowNow=Math.min(...kNow),kLowPrev=Math.min(...kPrev);
     const kHighNow=Math.max(...kNow),kHighPrev=Math.max(...kPrev);
     if(priceLow5<priceLow10&&kLowNow>kLowPrev&&kLowNow<30)return"long";
     if(priceHigh5>priceHigh10&&kHighNow<kHighPrev&&kHighNow>70)return"short";
     return null;}},
  {id:"ParabolicSAR",name:"Parabolic SAR",type:"SAR Trend Reversal",rr:2.0,atrMult:1.5,confirm:true,
   sess:{ASIA:"SAR 0.02/0.2",LONDON:"SAR 0.02/0.2",NY:"SAR 0.02/0.2"},
   desc:"Trades the dot flip -- when SAR flips from above to below price (long) or below to above (short).",
   signal(b){
     if(b.length<10)return null;
     const n=b.length-1,sar=sarArr(b,0.02,0.2);
     if(sar[n]==null||sar[n-1]==null)return null;
     if(sar[n-1]>b[n-1].c&&sar[n]<b[n].c)return"long";
     if(sar[n-1]<b[n-1].c&&sar[n]>b[n].c)return"short";
     return null;}},
  {id:"ADXTrend",name:"ADX Trend",type:"ADX+EMA Filter",rr:3.5,atrMult:1.5,trend:true,
   sess:{ASIA:"ADX>20+EMA",LONDON:"ADX>25+EMA",NY:"ADX>25+EMA"},
   desc:"Only trades EMA 8/21 crosses when ADX confirms a real trend.",
   signal(b){
     if(b.length<30)return null;
     const sess=getSessionET(b[b.length-1].t),threshold=sess==="ASIA"?20:25;
     const c=b.map(x=>x.c),n=c.length-1,adx=adxArr(b,14);
     if(adx[n]==null||adx[n]<threshold)return null;
     const f=ema(c,8),s=ema(c,21);if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;}},
  {id:"IchimokuCloud",name:"Ichimoku Cloud",type:"Kumo Breakout",rr:4.0,atrMult:1.5,trend:true,
   sess:{ASIA:"Kumo break",LONDON:"Kumo break",NY:"Kumo break"},
   desc:"Price breaks out of the Ichimoku cloud (Senkou A/B).",
   signal(b){
     if(b.length<60)return null;
     const n=b.length-1,ich=ichimokuArr(b);
     if(!ich[n]||ich[n].senkouA==null||ich[n].senkouB==null)return null;
     const top=Math.max(ich[n].senkouA,ich[n].senkouB),bot=Math.min(ich[n].senkouA,ich[n].senkouB);
     const prev=ich[n-1];if(!prev||prev.senkouA==null)return null;
     const prevTop=Math.max(prev.senkouA,prev.senkouB),prevBot=Math.min(prev.senkouA,prev.senkouB);
     const c=b[n].c,cp=b[n-1].c;
     if(cp<=prevTop&&c>top)return"long";if(cp>=prevBot&&c<bot)return"short";
     return null;}},
  // ── v7 additions ──────────────────────────────────────────────
  // S1: Opening Range Break — NY only. First 12 bars of current NY
  //     session define the range; close-confirmed breakout fires.
  {id:"OpenRangeBreak",name:"Open Range Break",type:"NY Opening Range",rr:2.5,atrMult:1.5,
   sess:{NY:"ORB 9:30-10:00"},
   desc:"NY only. Uses the first 2 bars after NY open (08:00-09:00 ET on 5m = first ~12 bars of session) to define the range high/low. Trades the breakout of that range on close confirmation.",
   confirm:false,
   signal(b){
     if(b.length<14)return null;
     const n=b.length-1;
     if(getSessionET(b[n].t)!=="NY")return null;
     // Walk back to the start of the current contiguous NY run.
     let startIdx=n;
     while(startIdx>0&&getSessionET(b[startIdx-1].t)==="NY")startIdx--;
     const nySess=b.slice(startIdx);
     if(nySess.length<14)return null;
     const range=nySess.slice(0,12);
     const rangeHigh=Math.max(...range.map(x=>x.h));
     const rangeLow =Math.min(...range.map(x=>x.l));
     const cc=b[n].c,pc=b[n-1].c;
     if(cc>rangeHigh&&pc<=rangeHigh)return"long";
     if(cc<rangeLow &&pc>=rangeLow )return"short";
     return null;
   }},
  // S2: EMA Triple Stack — full 5/13/34 stack + pullback re-cross.
  {id:"EMATripleStack",name:"EMA Triple Stack",type:"EMA 5/13/34 Alignment",rr:2.5,atrMult:1.5,
   sess:{ASIA:"EMA 5/13/34",LONDON:"EMA 5/13/34",NY:"EMA 5/13/34",SYDNEY:"EMA 5/13/34"},
   desc:"Long when EMA5 > EMA13 > EMA34 and price crosses back above EMA5 after a pullback. Short inverse. Full stack alignment eliminates weak crossovers.",
   confirm:true,
   signal(b){
     if(b.length<40)return null;
     const c=b.map(x=>x.c),n=c.length-1;
     const e5=ema(c,5),e13=ema(c,13),e34=ema(c,34);
     if(e5[n]==null||e13[n]==null||e34[n]==null||e5[n-1]==null)return null;
     const longStack =e5[n]>e13[n]&&e13[n]>e34[n];
     const shortStack=e5[n]<e13[n]&&e13[n]<e34[n];
     if(longStack &&c[n-1]<=e5[n-1]&&c[n]>e5[n])return"long";
     if(shortStack&&c[n-1]>=e5[n-1]&&c[n]<e5[n])return"short";
     return null;
   }},
  // S3: SuperTrend — band flip on HL2 +/- mult*ATR(14). Mult tightens
  //     in ASIA, widens in NY. Running-direction loop over last 30 bars.
  {id:"SuperTrend",name:"Super Trend",type:"ATR Trailing Band",rr:2.5,atrMult:1.5,
   sess:{ASIA:"ST 1.5x ATR",LONDON:"ST 2.5x ATR",NY:"ST 3.0x ATR",SYDNEY:"ST 2.0x ATR"},
   desc:"SuperTrend indicator. Upper/lower bands = HL2 +/- multiplier*ATR. Trade the band flip. Multiplier tightens for ASIA, widens for NY.",
   confirm:false,
   signal(b){
     if(b.length<20)return null;
     const sess=getSessionET(b[b.length-1].t);
     const mult=sess==="ASIA"?1.5:sess==="LONDON"?2.5:sess==="NY"?3.0:2.0;
     const at=atrArr(b,14);
     const n=b.length-1;
     if(at[n-1]==null)return null;
     // Run direction state up to the prev bar over a 30-bar window.
     let dir=1;
     const startIdx=Math.max(15,n-30);
     for(let i=startIdx;i<n;i++){
       if(at[i]==null)continue;
       const hl2=(b[i].h+b[i].l)/2;
       const upper=hl2+mult*at[i];
       const lower=hl2-mult*at[i];
       if(b[i].c>upper)dir=1;
       else if(b[i].c<lower)dir=-1;
     }
     const hl2p=(b[n-1].h+b[n-1].l)/2;
     const upperP=hl2p+mult*at[n-1];
     const lowerP=hl2p-mult*at[n-1];
     if(dir=== 1&&b[n].c<lowerP)return"short";
     if(dir===-1&&b[n].c>upperP)return"long";
     return null;
   }},
  // S4: Donchian Channel Break — close breaks N-period high/low.
  //     Period tightens for ASIA, widens for NY.
  {id:"DonchianBreak",name:"Donchian Break",type:"N-Period High/Low Breakout",rr:2.5,atrMult:1.5,
   sess:{ASIA:"DC 10-bar",LONDON:"DC 20-bar",NY:"DC 25-bar",SYDNEY:"DC 15-bar"},
   desc:"Close breaks above N-period high (long) or below N-period low (short). Period tightens in quiet ASIA, widens in NY.",
   confirm:false,
   signal(b){
     const sess=getSessionET(b[b.length-1].t);
     const period=sess==="ASIA"?10:sess==="LONDON"?20:sess==="NY"?25:15;
     if(b.length<period+2)return null;
     const n=b.length-1;
     const slc=b.slice(n-period,n);
     const dcHigh=Math.max(...slc.map(x=>x.h));
     const dcLow =Math.min(...slc.map(x=>x.l));
     if(b[n-1].c<=dcHigh&&b[n].c>dcHigh)return"long";
     if(b[n-1].c>=dcLow &&b[n].c<dcLow )return"short";
     return null;
   }},
  // S5: Keltner Channel Break — EMA20 +/- mult*ATR14 outer break.
  {id:"KeltnerBreak",name:"Keltner Break",type:"EMA + ATR Channel",rr:2.5,atrMult:1.5,
   sess:{ASIA:"KC 1.5x",LONDON:"KC 2.0x",NY:"KC 2.5x",SYDNEY:"KC 2.0x"},
   desc:"Price closes outside EMA20 +/- mult*ATR14 Keltner band. Complementary to BBSqueeze — fires on momentum expansion.",
   confirm:false,
   signal(b){
     if(b.length<25)return null;
     const sess=getSessionET(b[b.length-1].t);
     const mult=sess==="ASIA"?1.5:sess==="LONDON"?2.0:sess==="NY"?2.5:2.0;
     const c=b.map(x=>x.c),n=c.length-1;
     const basis=ema(c,20),at=atrArr(b,14);
     if(basis[n]==null||basis[n-1]==null||at[n]==null||at[n-1]==null)return null;
     const upper =basis[n]  +mult*at[n];
     const upperP=basis[n-1]+mult*at[n-1];
     const lower =basis[n]  -mult*at[n];
     const lowerP=basis[n-1]-mult*at[n-1];
     if(b[n-1].c<=upperP&&b[n].c>upper)return"long";
     if(b[n-1].c>=lowerP&&b[n].c<lower)return"short";
     return null;
   }},
  // S6: VWAP Deviation Break — session-bar VWAP (volume-proxy = simple
  //     mean of typical prices) +/- sigma band. NY + LONDON only.
  {id:"VWAPDeviation",name:"VWAP Dev Break",type:"VWAP + Std Dev",rr:2.0,atrMult:1.3,
   sess:{LONDON:"VWAP +/-1.5\u03c3",NY:"VWAP +/-2\u03c3"},
   desc:"NY and LONDON only. Approximates VWAP using cumulative close*vol divided by cumulative vol for current session bars. Trades break of VWAP +/- 1 standard deviation band.",
   confirm:true,
   signal(b){
     if(b.length<15)return null;
     const sess=getSessionET(b[b.length-1].t);
     if(sess!=="NY"&&sess!=="LONDON")return null;
     const mult=sess==="NY"?2.0:1.5;
     // Use current contiguous session run (walk back).
     const n=b.length-1;
     let startIdx=n;
     while(startIdx>0&&getSessionET(b[startIdx-1].t)===sess)startIdx--;
     const sessBars=b.slice(startIdx);
     if(sessBars.length<10)return null;
     const tps=sessBars.map(x=>(x.h+x.l+x.c)/3);
     const vwap=tps.reduce((a,v)=>a+v,0)/tps.length;
     const variance=tps.reduce((a,v)=>a+(v-vwap)*(v-vwap),0)/tps.length;
     const sd=Math.sqrt(variance);
     const upper=vwap+mult*sd;
     const lower=vwap-mult*sd;
     if(b[n-1].c<=upper&&b[n].c>upper)return"long";
     if(b[n-1].c>=lower&&b[n].c<lower)return"short";
     return null;
   }},
  // S7: Asia Opening Fade — RSI 20/80 cross in first 2 ASIA hours (19-21 ET).
  {id:"AsiaOpenFade",name:"Asia Open Fade",type:"ASIA Session RSI Fade",rr:2.0,atrMult:1.2,
   sess:{ASIA:"RSI fade 19:00-21:00 ET"},
   desc:"ASIA only. Fades extreme RSI moves in the first 2 hours of Asia session (19:00-21:00 ET). After that window returns null \u2014 avoids the mid-Asia trend that forms after opening volatility.",
   confirm:true,
   signal(b){
     if(b.length<20)return null;
     const n=b.length-1;
     if(getSessionET(b[n].t)!=="ASIA")return null;
     const etH=etHour(b[n].t);
     if(!(etH>=19&&etH<21))return null;
     const c=b.map(x=>x.c),ri=rsiArr(c,14);
     if(ri[n]==null||ri[n-1]==null)return null;
     if(ri[n-1]<=20&&ri[n]>20)return"long";
     if(ri[n-1]>=80&&ri[n]<80)return"short";
     return null;
   }},
  // S8: EMA 8/21 Cross with ATR expansion gate (atr > 10-bar avg).
  {id:"EMACrossATRExpand",name:"EMA Cross ATR Exp",type:"EMA 8/21 + Expanding ATR",rr:2.5,atrMult:1.5,
   sess:{ASIA:"EMA+ATR",LONDON:"EMA+ATR",NY:"EMA+ATR",SYDNEY:"EMA+ATR"},
   desc:"EMA 8/21 crossover only valid when current ATR is above its 10-bar average. Removes low-energy crosses in compression.",
   confirm:true,
   signal(b){
     if(b.length<30)return null;
     const c=b.map(x=>x.c),n=c.length-1;
     const e8=ema(c,8),e21=ema(c,21),at=atrArr(b,14);
     if(e8[n]==null||e21[n]==null||at[n]==null)return null;
     const atrSlice=at.slice(-10).filter(v=>v!=null);
     if(!atrSlice.length)return null;
     const avgATR=atrSlice.reduce((a,v)=>a+v,0)/atrSlice.length;
     const atrExpanding=at[n]>avgATR;
     if(!atrExpanding)return null;
     if(e8[n-1]<=e21[n-1]&&e8[n]>e21[n])return"long";
     if(e8[n-1]>=e21[n-1]&&e8[n]<e21[n])return"short";
     return null;
   }},
  // ── COMBO strats (apexExclude: true — run as regular bots only) ──
  // C1: Golden/Death cross gated by MACD histogram in same direction.
  {id:"GoldenDeathMACD",name:"Golden+MACD",type:"SMA 50/200 + MACD Confirm",rr:4.0,atrMult:2.0,
   apexExclude:true,
   sess:{ASIA:"SMA+MACD",LONDON:"SMA+MACD",NY:"SMA+MACD"},
   desc:"Golden/Death cross confirmed by MACD histogram in same direction. MACD must be positive for longs, negative for shorts, on same or previous bar.",
   signal(b){
     if(b.length<210)return null;
     const c=b.map(x=>x.c),n=c.length-1;
     const s50=sma(c,50),s200=sma(c,200);
     if(s50[n]==null||s200[n]==null||s50[n-1]==null||s200[n-1]==null)return null;
     const {hist}=macdArr(c);
     const smaLong =s50[n-1]<=s200[n-1]&&s50[n]>s200[n];
     const smaShort=s50[n-1]>=s200[n-1]&&s50[n]<s200[n];
     const macdLong =(hist[n]!=null&&hist[n]>0)||(hist[n-1]!=null&&hist[n-1]>0);
     const macdShort=(hist[n]!=null&&hist[n]<0)||(hist[n-1]!=null&&hist[n-1]<0);
     if(smaLong &&macdLong )return"long";
     if(smaShort&&macdShort)return"short";
     return null;
   }},
  // C2: Kumo (Ichimoku cloud) break gated by MACD histogram zero-cross
  //     within 2 bars. Two independent momentum signals required.
  {id:"IchimokuMACD",name:"Ichi+MACD",type:"Kumo Break + MACD Confirm",rr:4.5,atrMult:1.5,
   apexExclude:true,
   sess:{ASIA:"Kumo+MACD",LONDON:"Kumo+MACD",NY:"Kumo+MACD"},
   desc:"Kumo cloud breakout confirmed by MACD histogram crossing zero within 2 bars. Highest conviction combo \u2014 two independent momentum signals required.",
   signal(b){
     if(b.length<65)return null;
     const n=b.length-1;
     const ich=ichimokuArr(b);
     if(!ich[n]||ich[n].senkouA==null||ich[n].senkouB==null)return null;
     if(!ich[n-1]||ich[n-1].senkouA==null||ich[n-1].senkouB==null)return null;
     const kumoTop=Math.max(ich[n].senkouA,ich[n].senkouB);
     const kumoBot=Math.min(ich[n].senkouA,ich[n].senkouB);
     const prevTop=Math.max(ich[n-1].senkouA,ich[n-1].senkouB);
     const prevBot=Math.min(ich[n-1].senkouA,ich[n-1].senkouB);
     const c=b.map(x=>x.c),{hist}=macdArr(c);
     const kumoLong =b[n-1].c<=prevTop&&b[n].c>kumoTop;
     const kumoShort=b[n-1].c>=prevBot&&b[n].c<kumoBot;
     const macdLong =(hist[n]!=null&&hist[n]>0)||
                     (hist[n-1]!=null&&hist[n-1]>0&&hist[n-2]!=null&&hist[n-2]>0);
     const macdShort=(hist[n]!=null&&hist[n]<0)||
                     (hist[n-1]!=null&&hist[n-1]<0&&hist[n-2]!=null&&hist[n-2]<0);
     if(kumoLong &&macdLong )return"long";
     if(kumoShort&&macdShort)return"short";
     return null;
   }},
  // C3: ATR Channel breakout gated by MACD histogram direction.
  {id:"ATRChannelMACD",name:"ATR Chan+MACD",type:"SMA+ATR Break + MACD Confirm",rr:3.0,atrMult:1.5,
   apexExclude:true,
   sess:{ASIA:"ATR+MACD 1.5x",LONDON:"ATR+MACD 2x",NY:"ATR+MACD 2.5x"},
   desc:"ATR channel breakout confirmed by MACD histogram direction. ATR Channel is #1 in LONDON at PF 5.27 \u2014 MACD gate removes false breaks.",
   signal(b){
     if(b.length<35)return null;
     const sess=getSessionET(b[b.length-1].t);
     const mult=sess==="ASIA"?1.5:sess==="LONDON"?2.0:2.5;
     const c=b.map(x=>x.c),n=c.length-1;
     const sm=sma(c,20),at=atrArr(b,14),{hist}=macdArr(c);
     if(sm[n]==null||sm[n-1]==null||at[n]==null||at[n-1]==null)return null;
     const atrLong =b[n-1].c<=sm[n-1]+mult*at[n-1]&&b[n].c>sm[n]+mult*at[n];
     const atrShort=b[n-1].c>=sm[n-1]-mult*at[n-1]&&b[n].c<sm[n]-mult*at[n];
     const macdLong =hist[n]!=null&&hist[n]>0;
     const macdShort=hist[n]!=null&&hist[n]<0;
     if(atrLong &&macdLong )return"long";
     if(atrShort&&macdShort)return"short";
     return null;
   }},
  // C4: Parabolic SAR flip gated by ADX trend strength.
  {id:"SARAdx",name:"SAR+ADX",type:"SAR Flip + ADX Trend Confirm",rr:2.5,atrMult:1.5,
   apexExclude:true,
   sess:{ASIA:"SAR+ADX>20",LONDON:"SAR+ADX>22",NY:"SAR+ADX>25"},
   desc:"Parabolic SAR dot flip only valid when ADX confirms a real trend. Eliminates the majority of false SAR flips in choppy conditions. SAR is #2 in LONDON \u2014 ADX gate pushes PF higher.",
   signal(b){
     if(b.length<30)return null;
     const sess=getSessionET(b[b.length-1].t);
     const threshold=sess==="ASIA"?20:sess==="LONDON"?22:25;
     const sar=sarArr(b,0.02,0.2),adx=adxArr(b,14);
     const n=b.length-1;
     if(adx[n]==null||adx[n]<threshold)return null;
     if(sar[n-1]==null||sar[n]==null)return null;
     const sarLong =sar[n-1]>b[n-1].c&&sar[n]<b[n].c;
     const sarShort=sar[n-1]<b[n-1].c&&sar[n]>b[n].c;
     if(sarLong )return"long";
     if(sarShort)return"short";
     return null;
   }},
  // C5: Bollinger outer break gated by MACD histogram direction.
  {id:"BBMacd",name:"BB+MACD",type:"Bollinger Break + MACD Confirm",rr:3.0,atrMult:1.5,
   apexExclude:true,
   sess:{ASIA:"BB(20,1.5)+MACD",LONDON:"BB(20,2.0)+MACD",NY:"BB(20,2.0)+MACD"},
   desc:"Bollinger Band outer break confirmed by MACD histogram in same direction. Removes BB false breaks where momentum hasn't fired.",
   signal(b){
     if(b.length<35)return null;
     const sess=getSessionET(b[b.length-1].t);
     const mult=sess==="ASIA"?1.5:2.0;
     const c=b.map(x=>x.c),n=c.length-1;
     const bb=bbArr(c,20,mult),{hist}=macdArr(c);
     if(bb[n].u==null||bb[n-1].u==null||bb[n].l==null||bb[n-1].l==null)return null;
     const bbLong =b[n-1].c<=bb[n-1].u&&b[n].c>bb[n].u;
     const bbShort=b[n-1].c>=bb[n-1].l&&b[n].c<bb[n].l;
     const macdLong =hist[n]!=null&&hist[n]>0;
     const macdShort=hist[n]!=null&&hist[n]<0;
     if(bbLong &&macdLong )return"long";
     if(bbShort&&macdShort)return"short";
     return null;
   }},
  // C6: MACD histogram zero-cross filtered by RSI being in the
  //     momentum-build zone (long 40-65, short 35-60). LONDON+NY only.
  {id:"MACDRsiFilter",name:"MACD+RSI Filter",type:"MACD Hist + RSI Zone",rr:2.5,atrMult:1.5,
   apexExclude:true,
   sess:{LONDON:"MACD+RSI 40-65",NY:"MACD+RSI 40-65"},
   desc:"MACD histogram zero cross only fires when RSI is in the momentum build zone (40-65 for longs, 35-60 for shorts). Filters out weak MACD crosses at extremes. LONDON and NY only.",
   signal(b){
     if(b.length<35)return null;
     const sess=getSessionET(b[b.length-1].t);
     if(sess!=="LONDON"&&sess!=="NY")return null;
     const c=b.map(x=>x.c),n=c.length-1;
     const {hist}=macdArr(c);
     const ri=rsiArr(c,14);
     if(hist[n]==null||hist[n-1]==null||ri[n]==null)return null;
     const macdLong =hist[n-1]<=0&&hist[n]>0;
     const macdShort=hist[n-1]>=0&&hist[n]<0;
     const rsiLong =ri[n]>=40&&ri[n]<=65;
     const rsiShort=ri[n]>=35&&ri[n]<=60;
     if(macdLong &&rsiLong )return"long";
     if(macdShort&&rsiShort)return"short";
     return null;
   }},
  // C7: EMA 8/21 cross gated by Stoch %K not being at the wrong extreme.
  {id:"EMAStochCombo",name:"EMA+Stoch",type:"EMA Cross + Stoch Confirm",rr:2.5,atrMult:1.3,
   apexExclude:true,
   sess:{ASIA:"EMA+Stoch 20/80",LONDON:"EMA+Stoch 25/75",NY:"EMA+Stoch 30/70"},
   desc:"EMA 8/21 cross confirmed by Stochastic %K agreeing with direction. Long only when Stoch is not overbought, short only when not oversold.",
   signal(b){
     if(b.length<25)return null;
     const sess=getSessionET(b[b.length-1].t);
     const ob=sess==="ASIA"?80:sess==="LONDON"?75:70;
     const os=sess==="ASIA"?20:sess==="LONDON"?25:30;
     const c=b.map(x=>x.c),n=c.length-1;
     const e8=ema(c,8),e21=ema(c,21),k=stochArr(b,9);
     if(e8[n]==null||e21[n]==null||e8[n-1]==null||e21[n-1]==null||k[n]==null)return null;
     const crossLong =e8[n-1]<=e21[n-1]&&e8[n]>e21[n];
     const crossShort=e8[n-1]>=e21[n-1]&&e8[n]<e21[n];
     const stochLong =k[n]<ob; // not overbought
     const stochShort=k[n]>os; // not oversold
     if(crossLong &&stochLong )return"long";
     if(crossShort&&stochShort)return"short";
     return null;
   }},
  // C8: ROC(10) threshold break gated by MACD histogram direction.
  {id:"VelocityMACD",name:"Velocity+MACD",type:"ROC Momentum + MACD Confirm",rr:2.5,atrMult:1.5,
   apexExclude:true,
   sess:{ASIA:"ROC 0.15%+MACD",LONDON:"ROC 0.25%+MACD",NY:"ROC 0.40%+MACD"},
   desc:"Rate-of-change momentum threshold break confirmed by MACD histogram in same direction. Eliminates low-conviction ROC signals.",
   signal(b){
     if(b.length<35)return null;
     const sess=getSessionET(b[b.length-1].t);
     const thresh=sess==="ASIA"?0.15:sess==="LONDON"?0.25:0.40;
     const c=b.map(x=>x.c),n=c.length-1;
     if(c[n-10]==null||c[n-11]==null||c[n-10]===0||c[n-11]===0)return null;
     const roc =(c[n]  -c[n-10])/c[n-10]*100;
     const rocP=(c[n-1]-c[n-11])/c[n-11]*100;
     const {hist}=macdArr(c);
     const rocLong = rocP< thresh&&roc>= thresh;
     const rocShort=rocP>-thresh&&roc<=-thresh;
     const macdLong =hist[n]!=null&&hist[n]>0;
     const macdShort=hist[n]!=null&&hist[n]<0;
     if(rocLong &&macdLong )return"long";
     if(rocShort&&macdShort)return"short";
     return null;
   }},
  // C9: Donchian channel break gated by ADX trend strength.
  {id:"ADXDonchian",name:"ADX+Donchian",type:"Donchian Break + ADX Trend Gate",rr:3.0,atrMult:1.5,
   apexExclude:true,
   sess:{ASIA:"DC 10+ADX>20",LONDON:"DC 20+ADX>22",NY:"DC 25+ADX>25"},
   desc:"Donchian channel breakout only fires when ADX confirms a real trend. Eliminates false breakouts in choppy low-ADX conditions.",
   signal(b){
     if(b.length<30)return null;
     const sess=getSessionET(b[b.length-1].t);
     const period   =sess==="ASIA"?10:sess==="LONDON"?20:25;
     const threshold=sess==="ASIA"?20:sess==="LONDON"?22:25;
     const adx=adxArr(b,14);
     const n=b.length-1;
     if(adx[n]==null||adx[n]<threshold)return null;
     if(b.length<period+2)return null;
     const slc=b.slice(n-period,n);
     const dcHigh=Math.max(...slc.map(x=>x.h));
     const dcLow =Math.min(...slc.map(x=>x.l));
     if(b[n-1].c<=dcHigh&&b[n].c>dcHigh)return"long";
     if(b[n-1].c>=dcLow &&b[n].c<dcLow )return"short";
     return null;
   }},
];

function mkBot(s,wv){return{uid:++uid,name:`${s.name} W${wv}`,strat:s,wave:wv,balance:50000,
  openTrades:{},closedTrades:[],wins:0,losses:0,killed:false,killReason:"",
  _sessWins:0,_sessLosses:0};}
bots=STRATS.map(s=>mkBot(s,1));
const getPnl=b=>b.balance-50000;
const getWR=b=>{const t=b.wins+b.losses;return t?b.wins/t:0;};
function score(b){
  const tot=b.wins+b.losses;if(tot===0)return 0;
  const wr=getWR(b),avgPnl=getPnl(b)/tot,pnlScore=Math.max(0,Math.min(1,avgPnl/500));
  return wr*0.80+pnlScore*0.20;
}
const live=()=>bots.filter(b=>!b.killed);
const bestBot=()=>{const ab=live();return ab.length?ab.reduce((b,x)=>score(x)>score(b)?x:b,ab[0]):null;};

function processBots(){
  if(!startupDone)return;
  // ── v6: reset _barClosedCodes for all bots AND adaptiveBot ──
  bots.forEach(b=>{b._barClosedCodes=new Set();});
  adaptiveBot._barClosedCodes=new Set();

  computeT1Consensus(bs("ES"),bs("NQ"));
  const orderedMkts=[...MKTS].sort((a,b)=>a.tier-b.tier);

  orderedMkts.forEach(mkt=>{
    const b=bs(mkt.code);if(!b||b.length<35)return;
    const atr=atrArr(b,14);
    const lastTs=processedTs[mkt.code]??0;
    let si=b.findIndex(bar=>bar.t>lastTs);
    // ── live-bar fix: process up to b.length-1 (was b.length-2)
    // so SL/TP and signals reflect the current forming bar, not the
    // last fully-closed bar. processedTs is only advanced on closed bars
    // below so the live bar gets re-evaluated each cycle.
    if(si===-1||si>b.length-1)return;
    const ei=b.length-1;

    for(let i=si;i<=ei;i++){
      const bar=b[i];
      const sess=getSessionET(bar.t),sessLabel=getSessionLabel(bar.t);
      if(sess==="MAINT"){if(i<b.length-1)processedTs[mkt.code]=bar.t;continue;}

      if(!mkt._lastSess)mkt._lastSess=sess;
      if(mkt._lastSess!==sess){
        mkt._lastSess=sess;
        const revived=[];
        bots.forEach(bot=>{
          if(!bot.killed)return;
          bot.wave=(bot.wave||1)+1;bot.name=`${bot.strat.name} W${bot.wave}`;
          bot.killed=false;bot.killReason="";bot.balance=50000;
          bot.openTrades={};bot._sessWins=0;bot._sessLosses=0;
          revived.push(bot.name);
        });
        if(revived.length)addLog(`Session ${sess} \u2014 ${revived.length} bots revived (new wave)`,"wave");
      }

      const atr20slice=atr.slice(Math.max(0,i-19),i+1).filter(v=>v!=null);
      const avgATR=atr20slice.length?atr20slice.reduce((a,v)=>a+v,0)/atr20slice.length:0;
      const atrOK=atr[i]!=null&&(avgATR===0||atr[i]>=avgATR*0.5);
      const sessRRMult=sess==="NY"?1.0:sess==="LONDON"?0.9:sess==="ASIA"?0.75:0.70;

      bots.forEach(bot=>{
        if(bot.killed)return;
        const t=bot.openTrades[mkt.code];
        if(t){
          let closed=false,ex=0,won=false;
          if(t.dir==="long"){
            if(bar.h>=t.tp&&bar.l<=t.sl){ex=t.sl;closed=true;won=false;}
            else if(bar.h>=t.tp){ex=t.tp;closed=true;won=true;}
            else if(bar.l<=t.sl){ex=t.sl;closed=true;won=false;}
          }else{
            if(bar.l<=t.tp&&bar.h>=t.sl){ex=t.sl;closed=true;won=false;}
            else if(bar.l<=t.tp){ex=t.tp;closed=true;won=true;}
            else if(bar.h>=t.sl){ex=t.sl;closed=true;won=false;}
          }
          if(closed){
            ex=snap(ex,mkt.tick);
            const pts=t.dir==="long"?ex-t.entry:t.entry-ex;
            const pnl=Math.round(pts*mkt.ptVal*100)/100;
            bot.balance=Math.round((bot.balance+pnl)*100)/100;
            won?bot.wins++:bot.losses++;won?bot._sessWins++:bot._sessLosses++;totalClosed++;
            // ── per-strategy expectancy tally for Apex selection ──
            // (idempotent: a trade is tallied at most once, in its open-session bucket)
            if(!t._tallied){_sessTallyAdd(t.sess,bot.strat.id,won,pts);t._tallied=true;}
            const rec={code:mkt.code,col:mkt.col,botName:bot.name,stratId:bot.strat.id,
              dir:t.dir,entry:t.entry,exitPx:ex,pts:Math.round(pts*100)/100,
              pnlUSD:pnl,won,sl:t.sl,tp:t.tp,openT:t.openT,closeT:bar.t,atr:t.atr,
              sess:t.sess,sessLabel:t.sessLabel||t.sess};
            bot.closedTrades=[...bot.closedTrades.slice(-199),rec];
            allClosed=[rec,...allClosed].slice(0,5000);
            delete bot.openTrades[mkt.code];
            recordPerfAll(bot.strat.id,t.openT,mkt.code,won,pnl);
            document.getElementById("tcl").textContent=totalClosed;
            addLog(`${mkt.code} ${bot.name} ${won?"WIN":"LOSS"} ${f$(pnl)} (${fPts(pts)}) [${t.sessLabel||t.sess}]`,won?"win":"loss");
            if(!bot._barClosedCodes)bot._barClosedCodes=new Set();
            bot._barClosedCodes.add(mkt.code);
            delete pendingSignals[`${bot.uid}_${mkt.code}`];
          }
        }else if(atrOK){
          const pKey=`${bot.uid}_${mkt.code}`;
          const rawSig=bot.strat.signal(b.slice(0,i+1));
          // ── lookback cache: record latest non-null signal per (strat,market) ──
          if(rawSig)_recordStratSig(bot.strat.id,mkt.code,rawSig,bar.t);
          let sig=null;
          if(bot.strat.confirm){
            const pending=pendingSignals[pKey];
            // confirm: only apply pending sig if it was queued on an
            // EARLIER bar (live-bar re-evaluation must not fire confirm)
            if(pending&&pending.barT!==bar.t){sig=pending.sig;delete pendingSignals[pKey];}
            if(rawSig&&(!pending||pending.barT!==bar.t))pendingSignals[pKey]={sig:rawSig,barT:bar.t};
          }else{sig=rawSig;}
          if(sig&&atr[i]!=null){
            const entry=snap(bar.c,mkt.tick),c=mkt.conf??1.0;
            const rrMult=Math.max(1.0,bot.strat.rr*sessRRMult);
            const dist=snap(Math.max(atr[i]*bot.strat.atrMult*c,2*mkt.tick),mkt.tick);
            const sl=snap(sig==="long"?entry-dist:entry+dist,mkt.tick);
            const tp=snap(sig==="long"?entry+dist*rrMult:entry-dist*rrMult,mkt.tick);
            bot.openTrades[mkt.code]={dir:sig,entry,sl,tp,openT:bar.t,atr:atr[i],sess,sessLabel,rr:rrMult,conf:c};
          }
        }
      });

      // ── Adaptive bot: close existing position ──────────────────
      const at=adaptiveBot.openTrades[mkt.code];
      if(at){
        let closed=false,ex=0,won=false;
        if(at.dir==="long"){
          if(bar.h>=at.tp&&bar.l<=at.sl){ex=at.sl;closed=true;won=false;}
          else if(bar.h>=at.tp){ex=at.tp;closed=true;won=true;}
          else if(bar.l<=at.sl){ex=at.sl;closed=true;won=false;}
        }else{
          if(bar.l<=at.tp&&bar.h>=at.sl){ex=at.sl;closed=true;won=false;}
          else if(bar.l<=at.tp){ex=at.tp;closed=true;won=true;}
          else if(bar.h>=at.sl){ex=at.sl;closed=true;won=false;}
        }
        if(closed){
          ex=snap(ex,mkt.tick);
          const pts=at.dir==="long"?ex-at.entry:at.entry-ex;
          const pnl=Math.round(pts*mkt.ptVal*100)/100;
          won?adaptiveBot.wins++:adaptiveBot.losses++;totalClosed++;
          const rec={code:mkt.code,col:mkt.col,botName:"Apex AI",stratId:"ADAPTIVE",
            dir:at.dir,entry:at.entry,exitPx:ex,pts:Math.round(pts*100)/100,
            pnlUSD:pnl,won,sl:at.sl,tp:at.tp,openT:at.openT,closeT:bar.t,
            atr:at.atr,sess:at.sess,sessLabel:at.sessLabel||at.sess,conf:at.conf,
            apexMode:at.apexMode||"CONSENSUS",stratUsed:at.stratUsed};
          // ── per-session Apex W/L (Apex's own trades only) ──
          if(adaptiveBot.apexSessWL?.[at.sess]){
            won?adaptiveBot.apexSessWL[at.sess].w++:adaptiveBot.apexSessWL[at.sess].l++;
          }
          adaptiveBot.closedTrades=[...adaptiveBot.closedTrades.slice(-199),rec];
          allClosed=[rec,...allClosed].slice(0,5000);
          delete adaptiveBot.openTrades[mkt.code];
          // ── v6: mark bar-closed (Apex own trade — no sessionTally tally) ──
          adaptiveBot._barClosedCodes.add(mkt.code);
          recordPerfAll("ADAPTIVE",at.openT,mkt.code,won,pnl);
          document.getElementById("tcl").textContent=totalClosed;
          addLog(`AI ${mkt.code} ${won?"WIN":"LOSS"} ${f$(pnl)} [${at.sessLabel||at.sess}] conf:${((at.conf||0)*100).toFixed(0)}%`,won?"win":"loss");
        }
      }else if(atr[i]!=null){
        // ── Apex: enter new position (consensus / fallback) ───────
        const aiHasPos=Object.keys(adaptiveBot.openTrades).length>0;
        const sessOk=sess&&sess!=="MAINT"&&adaptiveBot.barsSinceLastTrade.hasOwnProperty(sess);
        if(!aiHasPos&&aiFullyUnlocked()&&sessOk){
          // ── tick guard: only advance bar-counters on a NEW bar per market.
          // The live bar is re-evaluated each cycle; its counters must not
          // burn the consensus timeout or fallback duration.
          const tickKey=mkt.code;
          const isNewBar=bar.t>(adaptiveBot._lastApexTickT[tickKey]||0);
          if(isNewBar){
            adaptiveBot.barsSinceLastTrade[sess]=(adaptiveBot.barsSinceLastTrade[sess]||0)+1;
            adaptiveBot._lastApexTickT[tickKey]=bar.t;
          }
          const mode=adaptiveBot.apexMode[sess]||"CONSENSUS";
          let res=null;
          if(mode==="FALLBACK"){
            res=getApexFallbackSig(b.slice(0,i+1),sess);
            // decrement fallback duration only on a new bar
            if(isNewBar){
              const rem=(adaptiveBot.fallbackBarsRemaining[sess]||0)-1;
              adaptiveBot.fallbackBarsRemaining[sess]=Math.max(0,rem);
              if(adaptiveBot.fallbackBarsRemaining[sess]===0){
                adaptiveBot.apexMode[sess]="CONSENSUS";
                adaptiveBot.barsSinceLastTrade[sess]=0;
              }
            }
          }else{
            res=getApexConsensusSig(b.slice(0,i+1),sess,mkt.code,bar.t);
            // if no consensus and timeout exceeded, switch to FALLBACK mode
            if(!res&&adaptiveBot.barsSinceLastTrade[sess]>=APEX_FALLBACK_BARS_THRESHOLD){
              adaptiveBot.apexMode[sess]="FALLBACK";
              adaptiveBot.fallbackBarsRemaining[sess]=APEX_FALLBACK_DURATION;
            }
          }
          if(res){
            const entry=snap(bar.c,mkt.tick),mkConf=mkt.conf??1.0;
            const sessRRMult=sess==="NY"?1.0:sess==="LONDON"?0.9:sess==="ASIA"?0.75:0.70;
            // STEP 1: always use the higher-expectancy strat's own SL/TP.
            // res.strat1 is top-1 by expectancy (getTop2BySession sorts desc),
            // so its levels are the "higher-expectancy" levels for both
            // CONSENSUS and FALLBACK. Averaging removed (synthetic levels had
            // no backtest behind them and were the cause of consensus losses).
            const lv1=_stratLevels(res.strat1.strat,res.sig,entry,atr[i],sessRRMult,mkConf,mkt);
            const sl=lv1.sl,tp=lv1.tp,rrFinal=lv1.rrMult;
            const stratUsed=res.strat2
              ?`${res.strat1.strat.id}+${res.strat2.strat.id}`
              :res.strat1.strat.id;
            adaptiveBot._lastDomId=res.strat1.strat.id;
            // v6.8 strict revert: apexMode follows session mode (was
            // vote-based in v6.2). No regime stamp on the trade record.
            adaptiveBot.openTrades[mkt.code]={dir:res.sig,entry,sl,tp,openT:bar.t,
              atr:atr[i],sess,sessLabel,conf:Math.min(1.0,mkConf),
              rr:rrFinal,votes:res.strat2?2:1,stratUsed,
              apexMode:mode}; 
            // reset bars-since-last-trade for this session on entry
            adaptiveBot.barsSinceLastTrade[sess]=0;
          }
        }
      }
      // only mark CLOSED bars as processed; live bar must be re-evaluated
      if(i<b.length-1)processedTs[mkt.code]=bar.t;
    }
  });

  bots.forEach(bot=>{
    if(bot.killed)return;
    const sw=bot._sessWins??bot.wins,sl=bot._sessLosses??bot.losses,tot=sw+sl;
    if(tot>=20&&sw/tot<0.25){
      Object.entries(bot.openTrades).forEach(([code,t])=>{
        const mkt=MKTS.find(m=>m.code===code);if(!mkt)return;
        const ex=snap(liveQ[code]?.price||bs(code).at(-1)?.c||t.entry,mkt.tick);
        const pts=t.dir==="long"?ex-t.entry:t.entry-ex,pnl=Math.round(pts*mkt.ptVal*100)/100,won=pts>0;
        won?bot.wins++:bot.losses++;won?bot._sessWins++:bot._sessLosses++;totalClosed++;
        const rec={code,col:mkt.col,botName:bot.name,stratId:bot.strat.id,
          dir:t.dir,entry:t.entry,exitPx:ex,pts:Math.round(pts*100)/100,
          pnlUSD:pnl,won,sl:t.sl,tp:t.tp,openT:t.openT,closeT:Date.now(),atr:t.atr,sess:t.sess,sessLabel:t.sessLabel||t.sess};
        bot.closedTrades=[...bot.closedTrades.slice(-199),rec];
        allClosed=[rec,...allClosed].slice(0,5000);
        recordPerfAll(bot.strat.id,t.openT,code,won,pnl);
      });
      bot.openTrades={};bot.killed=true;bot.killReason="WR<25% (revives next session)";
      addLog(`${bot.name} SUSPENDED (WR<25%) \u2014 revives at next session`,"kill");
    }
  });
  document.getElementById("ta").textContent=live().length;
}

// ── FAST LOOP: live quotes ────────────────────────────────────
async function refreshQuote(){
  try{
    const r=await fetch("/api/quote",{signal:AbortSignal.timeout(5000)});
    const d=await r.json();
    const now=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
    document.getElementById("qtag").textContent="Q "+now;
    MKTS.forEach(m=>{
      const q=d[m.code];if(!q)return;
      liveQ[m.code]=q;
      const b=candles[m.code];
      if(b?.length){
        const last=b[b.length-1];
        if(q.price!==last.c||q.price>last.h||q.price<last.l){
          last.c=q.price;if(q.price>last.h)last.h=q.price;if(q.price<last.l)last.l=q.price;dirty[m.id]=true;
        }
      }
      const prev=prevPx[m.id],pel=document.getElementById("p"+m.id);
      if(pel){
        pel.textContent=q.price.toFixed(2);
        if(prev!=null&&q.price!==prev){
          pel.style.color=q.price>prev?"var(--up)":"var(--dn)";
          clearTimeout(pel._ft);pel._ft=setTimeout(()=>{pel.style.color="var(--tx)";},500);
        }
      }
      prevPx[m.id]=q.price;
      const cel=document.getElementById("c"+m.id);
      if(cel){const s=q.change>=0?"+":"";cel.textContent=`${s}${q.change.toFixed(2)} (${s}${q.changePct.toFixed(2)}%)`;cel.style.color=q.change>=0?"var(--up)":"var(--dn)";}
      const hlel=document.getElementById("hl"+m.id);
      if(hlel&&q.dayHigh)hlel.innerHTML=`<span style="color:#26a69a70">H:${q.dayHigh.toFixed(2)}</span> <span style="color:#ef535070">L:${q.dayLow.toFixed(2)}</span>`;
      const bars=bs(m.code);
      if(bars.length){const lb=bars[bars.length-1];if(q.price>lb.h)lb.h=q.price;if(q.price<lb.l)lb.l=q.price;dirty[m.id]=true;}
      const cpx=document.getElementById("cpx-"+m.id);
      if(cpx){
        const p2=cpx._prev;cpx.textContent=q.price.toFixed(2);
        if(p2!=null&&q.price!==p2){cpx.style.color=q.price>p2?"var(--up)":"var(--dn)";clearTimeout(cpx._ft);cpx._ft=setTimeout(()=>{cpx.style.color="var(--tx)";},500);}
        cpx._prev=q.price;
      }
    });
    checkLiveExits();
  }catch(e){console.warn("quote:",e.message);}
}

function checkLiveExits(){
  [...bots.filter(b=>!b.killed),adaptiveBot].forEach(bot=>{
    Object.entries(bot.openTrades).forEach(([code,t])=>{
      const q=liveQ[code];if(!q)return;
      const mkt=MKTS.find(m=>m.code===code);if(!mkt)return;
      const p=q.price,bars=bs(code);
      // ── STEP 7: cumulative high/low since openT ─────────────────────────
      // Was: only the live bar's H/L + current tick. That missed wicks the
      // live-quote sampler skipped over and chart-endpoint corrections to
      // earlier bars. Now: scan every bar with t >= openT, take the running
      // max-H / min-L, then fold in the latest tick. If any bar at any point
      // showed price hitting SL/TP, exit fires.
      let barH=p,barL=p;
      for(let bi=bars.length-1;bi>=0;bi--){
        const bb=bars[bi];if(bb.t<t.openT)break;
        if(bb.h>barH)barH=bb.h;
        if(bb.l<barL)barL=bb.l;
      }
      // STEP 7: also factor in dayHigh/dayLow if they were set after the
      // trade opened today (Yahoo's day-extremes update faster than per-bar
      // aggregations sometimes; this catches asymmetric latency).
      if(q.dayHigh||q.dayLow){
        const todayMs=86400000;
        if(Date.now()-t.openT<todayMs){
          if(q.dayHigh&&q.dayHigh>barH)barH=q.dayHigh;
          if(q.dayLow &&q.dayLow <barL)barL=q.dayLow ;
        }
      }
      let closed=false,ex=0,won=false,closeReason="";
      if(t.dir==="long"){
        if(barH>=t.tp&&barL<=t.sl){ex=t.sl;closed=true;won=false;closeReason="sl";}
        else if(barH>=t.tp){ex=t.tp;closed=true;won=true;closeReason="tp";}
        else if(barL<=t.sl){ex=t.sl;closed=true;won=false;closeReason="sl";}
      }else{
        if(barL<=t.tp&&barH>=t.sl){ex=t.sl;closed=true;won=false;closeReason="sl";}
        else if(barL<=t.tp){ex=t.tp;closed=true;won=true;closeReason="tp";}
        else if(barH>=t.sl){ex=t.sl;closed=true;won=false;closeReason="sl";}
      }
      // ── HARD SL OVERRIDE ────────────────────────────────────────────────
      // If live price has blown through SL by >1 tick, bypass the
      // _barClosedCodes guard. Applies to SL only — TP closes still respect
      // the within-cycle dedup guard.
      const slBreach=closeReason==="sl"&&(t.dir==="long"
        ? p<(t.sl-mkt.tick)
        : p>(t.sl+mkt.tick));
      if(closed&&bot._barClosedCodes?.has(code)&&!slBreach)closed=false;
      if(slBreach&&closed){ex=t.sl;}
      if(closed){
        ex=snap(ex,mkt.tick);
        const pts=t.dir==="long"?ex-t.entry:t.entry-ex,pnl=Math.round(pts*mkt.ptVal*100)/100;
        const isAI=bot===adaptiveBot;
        if(!isAI)bot.balance=Math.round((bot.balance+pnl)*100)/100;
        won?bot.wins++:bot.losses++;totalClosed++;
        const rec={code,col:mkt.col,botName:bot.name,stratId:bot.strat?.id||"ADAPTIVE",
          dir:t.dir,entry:t.entry,exitPx:ex,pts:Math.round(pts*100)/100,
          pnlUSD:pnl,won,sl:t.sl,tp:t.tp,openT:t.openT,closeT:Date.now(),
          atr:t.atr,sess:t.sess,sessLabel:t.sessLabel||t.sess,live:true,
          apexMode:isAI?(t.apexMode||"CONSENSUS"):undefined,
          stratUsed:isAI?t.stratUsed:undefined};
        // ── per-session Apex W/L on live exit ──
        if(isAI&&adaptiveBot.apexSessWL?.[t.sess]){
          won?adaptiveBot.apexSessWL[t.sess].w++:adaptiveBot.apexSessWL[t.sess].l++;
        }
        bot.closedTrades=[...bot.closedTrades.slice(-199),rec];
        allClosed=[rec,...allClosed].slice(0,5000);
        delete bot.openTrades[code];
        recordPerfAll(rec.stratId,t.openT,code,won,pnl);
        // ── per-strategy expectancy tally for Apex selection (skip Apex's own combined trades) ──
        // (idempotent: a trade is tallied at most once, in its open-session bucket)
        if(!isAI&&!t._tallied){_sessTallyAdd(t.sess,rec.stratId,won,rec.pts);t._tallied=true;}
        document.getElementById("tcl").textContent=totalClosed;
        const tag=isAI?"AI ":"";
        addLog(`${tag}${code} ${bot.name} ${won?"WIN":"LOSS"} ${f$(pnl)} [live]`,won?"win":"loss");
        const mktObj=MKTS.find(m=>m.code===code);if(mktObj)dirty[mktObj.id]=true;
      }
    });
  });
}

// ── SLOW LOOP: full OHLC ──────────────────────────────────────
async function refreshFull(){
  const tag=document.getElementById("ltag");tag.textContent="FETCHING";tag.className="";
  let liveN=0;
  await Promise.allSettled(MKTS.map(async mkt=>{
    try{
      const r=await fetch(`/api/candles?code=${mkt.code}&iv=${iv}`,{signal:AbortSignal.timeout(30000)});
      const d=await r.json();
      if(d.live&&d.candles?.length>10){candles[mkt.code]=d.candles;sources[mkt.code]=d.source||"?";liveN++;dirty[mkt.id]=true;}
    }catch(e){console.warn(mkt.code,e.message);}
  }));
  isLive=liveN>0;
  tag.textContent=isLive?`LIVE ${liveN}/8`:Object.keys(candles).length?"STALE":"CLOSED";
  tag.className=isLive?"live":!Object.keys(candles).length?"closed":"";
  document.getElementById("tu").textContent=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
  document.getElementById("tbars").textContent=candles["ES"]?.length||"--";
  if(!startupDone&&isLive){
    MKTS.forEach(m=>{const b=bs(m.code);if(b?.length)processedTs[m.code]=b[b.length-1].t;});
    startupDone=true;
    addLog("Live data loaded -- bots watching from NOW across all 8 markets","info");
  }
  // STEP 7: re-run live-exit check the moment fresh OHLC arrives. The
  // cumulative scan in checkLiveExits picks up any bar whose H/L was
  // corrected upstream (chart endpoint catching a wick the live tick
  // sampler missed). Runs before processBots so any retroactive exit
  // is booked before the bot opens new positions on stale state.
  checkLiveExits();
  processBots();renderLeft();renderAllTrades();renderRight();
}

// ── Sound ─────────────────────────────────────────────────────
const _audioCtx={ctx:null};
function _getACtx(){if(!_audioCtx.ctx)try{_audioCtx.ctx=new(window.AudioContext||window.webkitAudioContext)();}catch(e){}return _audioCtx.ctx;}
function playOpenSound(idx){
  const ctx=_getACtx();if(!ctx)return;
  const freqs=[[880,660],[1046,784],[1318,987],[1568,1174],[698,523],[932,698],[1109,831],[784,587]];
  const[hi,lo]=freqs[idx%freqs.length];
  [[hi,0,0.10],[lo,0.11,0.24]].forEach(([freq,start,end])=>{
    try{
      const o=ctx.createOscillator(),g=ctx.createGain();
      o.connect(g);g.connect(ctx.destination);o.type="sine";o.frequency.setValueAtTime(freq,ctx.currentTime+start);
      g.gain.setValueAtTime(0,ctx.currentTime+start);g.gain.linearRampToValueAtTime(0.18,ctx.currentTime+start+0.02);
      g.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+end);o.start(ctx.currentTime+start);o.stop(ctx.currentTime+end);
    }catch(e){}
  });
}

// ── RAF chart grid ────────────────────────────────────────────
const cvMap={};
function buildGrid(){
  document.getElementById("cgrid").innerHTML=MKTS.map(m=>`
    <div class="cc">
      <div class="ch">
        <div style="display:flex;align-items:center;gap:4px">
          <span class="csym" style="color:${m.col}">${m.code}</span>
          <span style="font-size:5.5px;padding:0 3px;border-radius:2px;
            background:${m.tier===1?"#ff980022":m.tier===2?"#2962ff22":m.tier===3?"#00bfa522":"#e91e6322"};
            color:${m.tier===1?"#ff9800":m.tier===2?"#5585ff":m.tier===3?"#00bfa5":"#f06292"};
            border:1px solid ${m.tier===1?"#ff980040":m.tier===2?"#2962ff40":m.tier===3?"#00bfa540":"#e91e6340"}">
            ${m.tierLabel||("T"+m.tier)}</span>
        </div>
        <div style="display:flex;align-items:center;gap:4px">
          <span class="clive" id="cpx-${m.id}" style="color:var(--tx)">--</span>
          <span style="font-size:8px" id="cchg-${m.id}"></span>
          <span id="fs-btn-${m.id}" title="Expand fullscreen"
            style="cursor:pointer;color:var(--tx4);font-size:12px;line-height:1;padding:0 1px;
            transition:color .15s;user-select:none">&#x2922;</span>
        </div>
      </div>
      <div class="cw" id="cw-${m.id}"><canvas id="cv-${m.id}"></canvas></div>
      <div class="sb" id="sb-${m.id}"><span style="color:var(--tx3);font-size:7px">watching...</span></div>
    </div>`).join("");
  MKTS.forEach(m=>{
    cvMap[m.id]=document.getElementById("cv-"+m.id);
    new ResizeObserver(()=>{dirty[m.id]=true;}).observe(document.getElementById("cw-"+m.id));
  });
  const ttEl=document.getElementById("chart-tooltip");
  MKTS.forEach(m=>{
    const cw=document.getElementById("cw-"+m.id);if(!cw)return;
    cw.addEventListener("mousemove",e=>{
      const b=bs(m.code);if(!b?.length){ttEl.style.display="none";return;}
      const rect=cw.getBoundingClientRect(),mx=e.clientX-rect.left,W=rect.width;
      const PL=2,PR=62,CW2=W-PL-PR,maxC=Math.max(20,Math.floor(CW2/7));
      const vis=b.slice(-maxC),n=vis.length,gap=CW2/n;
      const idx=Math.max(0,Math.min(n-1,Math.round((mx-PL-gap/2)/gap)));
      if(hoverState[m.id]!==idx){hoverState[m.id]=idx;dirty[m.id]=true;}
      const bar=vis[idx],dec=m.tick<1?2:0;
      const dt=new Date(bar.t);
      const ts2=iv==="1H"?dt.toLocaleDateString([],{month:"short",day:"numeric",year:"2-digit"}):dt.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
      const chg=bar.c-bar.o,chgPct=(chg/bar.o*100).toFixed(2);
      ttEl.innerHTML=`
        <div class="tt-sym" style="color:${m.col}">${m.code} <span style="font-size:7px;font-family:'Share Tech Mono';color:var(--tx3);font-weight:normal">${ts2}</span></div>
        <div class="tt-row"><span class="tt-k">O</span><b>${bar.o.toFixed(dec)}</b></div>
        <div class="tt-row"><span class="tt-k">H</span><b style="color:#26a69a">${bar.h.toFixed(dec)}</b></div>
        <div class="tt-row"><span class="tt-k">L</span><b style="color:#ef5350">${bar.l.toFixed(dec)}</b></div>
        <div class="tt-row"><span class="tt-k">C</span><b style="color:${bar.c>=bar.o?"#26a69a":"#ef5350"}">${bar.c.toFixed(dec)}</b></div>
        <div class="tt-row" style="margin-top:2px;border-top:1px solid var(--b1);padding-top:2px">
          <span class="tt-k">Chg</span>
          <b style="color:${chg>=0?"#26a69a":"#ef5350"}">${chg>=0?"+":""}${chg.toFixed(dec)} (${chg>=0?"+":""}${chgPct}%)</b>
        </div>`;
      ttEl.style.display="block";
      let tx=e.clientX+16,ty=e.clientY-10;
      if(tx+150>window.innerWidth)tx=e.clientX-166;if(ty+160>window.innerHeight)ty=e.clientY-160;
      ttEl.style.left=tx+"px";ttEl.style.top=ty+"px";
    });
    cw.addEventListener("mouseleave",()=>{ttEl.style.display="none";hoverState[m.id]=null;dirty[m.id]=true;});
    const fsBtn=document.getElementById("fs-btn-"+m.id);
    if(fsBtn){
      fsBtn.addEventListener("click",e=>{e.stopPropagation();openFullscreen(m);});
      fsBtn.addEventListener("mouseover",()=>{fsBtn.style.color="var(--tx)";});
      fsBtn.addEventListener("mouseout",()=>{fsBtn.style.color="var(--tx4)";});
    }
  });
}

function drawChart(mkt,_cv,_W,_H){
  const cv=_cv||cvMap[mkt.id];if(!cv)return;
  const dpr=window.devicePixelRatio||1;
  let W,H;
  if(_W&&_H){W=_W;H=_H;}else{
    const wrap=document.getElementById("cw-"+mkt.id);if(!wrap)return;
    W=wrap.clientWidth;H=wrap.clientHeight;
  }
  if(W<20||H<20)return;
  cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);
  cv.style.width=W+"px";cv.style.height=H+"px";
  const ctx=cv.getContext("2d");
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle="#131722";ctx.fillRect(0,0,W,H);
  const b=bs(mkt.code);
  if(!b?.length){
    ctx.fillStyle="#2a2e39";ctx.font="10px 'Share Tech Mono'";ctx.textAlign="center";
    ctx.fillText("Fetching "+mkt.code+"...",W/2,H/2-6);
    ctx.fillStyle="#1e222d";ctx.font="8px 'Share Tech Mono'";
    ctx.fillText(sources[mkt.code]||"Yahoo Finance",W/2,H/2+8);return;
  }
  const PL=2,PR=62,PT=6,PB=14,CW=W-PL-PR,VOLH=Math.round((H-PT-PB)*0.16),CH=H-PT-PB-VOLH-2;
  const maxC=Math.max(20,Math.floor(CW/7)),vis=b.slice(-maxC),n=vis.length;if(n<2)return;
  const gap=CW/n,bw=Math.max(1.2,gap*0.72),toX=i=>PL+i*gap+gap/2;
  let hiP=Math.max(...vis.map(c=>c.h)),loP=Math.min(...vis.map(c=>c.l));
  const rawRng=hiP-loP||hiP*0.01;hiP+=rawRng*0.08;loP-=rawRng*0.04;
  const rng=hiP-loP||1,toY=p=>PT+CH*(1-(p-loP)/rng);
  const rawStep=rawRng/5,mag=Math.pow(10,Math.floor(Math.log10(rawStep)));
  let step=mag;for(const ns of[1,2,2.5,5,10]){if(mag*ns>=rawStep){step=mag*ns;break;}}
  ctx.font="7px 'Share Tech Mono'";ctx.textAlign="left";
  for(let pv=Math.ceil(loP/step)*step;pv<=hiP;pv=Math.round((pv+step)*1e6)/1e6){
    const y=toY(pv);if(y<PT||y>PT+CH)continue;
    ctx.strokeStyle="#1e222d";ctx.lineWidth=1;ctx.setLineDash([]);
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();
    ctx.fillStyle="#131722";ctx.fillRect(PL+CW+1,y-7,PR-2,12);
    ctx.fillStyle="#787b86";ctx.fillText(pv.toFixed(mkt.tick<1?2:0),PL+CW+4,y+3);
  }
  const SESSION_DEFS=[
    {name:"SYD",startH:18,endH:2,wrap:true,col:"#ffd70010",lbl:"#ffd70055"},
    {name:"ASIA",startH:19,endH:4,wrap:true,col:"#8080ff13",lbl:"#8080ff70"},
    {name:"LON",startH:3,endH:12,wrap:false,col:"#f0903013",lbl:"#f0903070"},
    {name:"NY",startH:8,endH:17,wrap:false,col:"#18c86013",lbl:"#18c86070"},
    {name:"MAINT",startH:17,endH:18,wrap:false,col:"#4c525e18",lbl:"#4c525e80"},
  ];
  const barSess=vis.map(c=>{const h=etHour(c.t);return SESSION_DEFS.filter(s=>s.wrap?(h>=s.startH||h<s.endH):(h>=s.startH&&h<s.endH));});
  SESSION_DEFS.forEach(s=>{vis.forEach((c,i)=>{
    if(!barSess[i].includes(s))return;
    const x0=Math.max(PL,toX(i)-gap/2),w=Math.min(gap,PL+CW-x0);if(w<=0)return;
    ctx.fillStyle=s.col;ctx.fillRect(x0,PT,w,CH);
  });});
  const drawnLabel=new Set();
  vis.forEach((c,i)=>{barSess[i].forEach((s,si)=>{
    if(i>0&&barSess[i-1].includes(s))return;if(drawnLabel.has(s.name+"@"+i))return;
    drawnLabel.add(s.name+"@"+i);const x0=Math.max(PL,toX(i)-gap/2)+2;
    ctx.fillStyle=s.lbl;ctx.font="bold 6px 'Share Tech Mono'";ctx.textAlign="left";
    ctx.fillText(s.name,x0,PT+7+si*8);
  });});
  const closes=vis.map(c=>c.c);
  [[9,"#f5a62380",1.2],[21,"#2962ff60",1.2]].forEach(([p,col,lw])=>{
    const vals=ema(closes,p);ctx.strokeStyle=col;ctx.lineWidth=lw;ctx.beginPath();let st=false;
    vals.forEach((v,i)=>{if(v==null)return;const x=toX(i),y=toY(v);st?ctx.lineTo(x,y):(ctx.moveTo(x,y),st=true);});
    ctx.stroke();
  });
  const volBase=PT+CH+2,maxVol=Math.max(...vis.map(c=>c.v||0))||1;
  vis.forEach((c,i)=>{
    const x=toX(i),vPct=(c.v||0)/maxVol,vh=Math.max(1,vPct*VOLH);
    ctx.fillStyle=c.c>=c.o?"#26a69a22":"#ef535022";ctx.fillRect(x-bw/2,volBase+VOLH-vh,bw,vh);
  });
  vis.forEach((c,i)=>{
    const x=toX(i),col=c.c>=c.o?"#26a69a":"#ef5350";
    ctx.globalAlpha=i===n-1?0.75:1;
    ctx.strokeStyle=col;ctx.lineWidth=1;ctx.setLineDash([]);
    ctx.beginPath();ctx.moveTo(x,toY(c.h));ctx.lineTo(x,toY(c.l));ctx.stroke();
    const bt=toY(Math.max(c.o,c.c)),bb2=toY(Math.min(c.o,c.c)),bh=Math.max(1.2,bb2-bt);
    if(bh<=1.2){ctx.strokeStyle=col;ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(x-bw/2,toY(c.c));ctx.lineTo(x+bw/2,toY(c.c));ctx.stroke();}
    else{ctx.fillStyle=col;ctx.fillRect(x-bw/2,bt,bw,bh);}
    ctx.globalAlpha=1;
  });
  const hIdx=hoverState[mkt.id];
  if(hIdx!=null&&hIdx>=0&&hIdx<n){
    const hx=toX(hIdx);
    ctx.setLineDash([2,3]);ctx.strokeStyle="#d1d4dc28";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(hx,PT);ctx.lineTo(hx,PT+CH);ctx.stroke();ctx.setLineDash([]);
    const hc=vis[hIdx],hbt=toY(Math.max(hc.o,hc.c)),hbb=toY(Math.min(hc.o,hc.c)),hhh=Math.max(2,hbb-hbt);
    ctx.strokeStyle="#ffffff30";ctx.lineWidth=1;ctx.strokeRect(hx-bw/2,hbt,bw,hhh);
  }
  const bb=bestBot();
  if(bb){const tr=bb.openTrades[mkt.code];if(tr){
    const lvl=(price,col,dash,lbl)=>{
      if(price<loP||price>hiP)return;const y=toY(price);
      ctx.setLineDash(dash);ctx.strokeStyle=col;ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=col;ctx.font="bold 6.5px 'Share Tech Mono'";ctx.textAlign="left";
      const dec=mkt.tick<1?2:0;ctx.fillText(lbl+" "+price.toFixed(dec),PL+CW+4,y+2.5);
    };
    lvl(tr.tp,"#26a69a",[5,3],"TP");lvl(tr.entry,"#787b86",[2,4],"E");lvl(tr.sl,"#ef5350",[5,3],"SL");
  }}
  const last=closes.at(-1);
  if(last!=null){
    const y=toY(last),isUp=(liveQ[mkt.code]?.change??0)>=0,tagCol=isUp?"#26a69a":"#ef5350";
    ctx.setLineDash([3,4]);ctx.strokeStyle="#2a2e3960";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();ctx.setLineDash([]);
    const bx=PL+CW+1,bxw=PR-2,byy=y-8;ctx.fillStyle=tagCol;
    if(ctx.roundRect){ctx.beginPath();ctx.roundRect(bx,byy,bxw,16,2);ctx.fill();}else ctx.fillRect(bx,byy,bxw,16);
    ctx.fillStyle="#fff";ctx.font="bold 8px 'Share Tech Mono'";ctx.textAlign="center";
    const dec=mkt.tick<1?2:0;ctx.fillText(last.toFixed(dec),bx+bxw/2,y+3);
  }
  ctx.fillStyle="#4c525e";ctx.font="6.5px 'Share Tech Mono'";ctx.textAlign="center";
  const fmtT=ts=>{const d=new Date(ts);return iv==="1H"?d.toLocaleDateString([],{month:"short",day:"numeric"}):d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});};
  const timeY=H-2,usedX=[];
  [0,Math.floor(n*.25),Math.floor(n*.5),Math.floor(n*.75),n-1].forEach(i=>{
    if(i<0||i>=n||!vis[i])return;const x=toX(i);
    if(usedX.some(ux=>Math.abs(ux-x)<44))return;usedX.push(x);
    ctx.strokeStyle="#1e222d30";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,PT);ctx.lineTo(x,volBase+VOLH);ctx.stroke();
    ctx.fillStyle="#4c525e";ctx.fillText(fmtT(vis[i].t),x,timeY);
  });
}

function updateSessionClock(){
  const h=etHour(),etH=Math.floor(h),etM=new Date().getUTCMinutes();
  const isMaint=_inMaint(h),inNY=_inNY(h),inLondon=_inLondon(h),inAsia=_inAsia(h),inSydney=_inSydney(h);
  document.getElementById("sess-ny").classList.toggle("active",inNY);
  document.getElementById("sess-london").classList.toggle("active",inLondon);
  document.getElementById("sess-asia").classList.toggle("active",inAsia);
  const syd=document.getElementById("sess-sydney");if(syd)syd.classList.toggle("active",inSydney);
  const dH=(etH%12)||12,dM=String(etM).padStart(2,"0"),ampm=etH<12?"AM":"PM";
  const activeSess=[];
  if(isMaint)activeSess.push("BREAK");
  else{if(inNY)activeSess.push("NY");if(inLondon)activeSess.push("LON");if(inAsia)activeSess.push("ASIA");if(inSydney)activeSess.push("SYD");}
  if(!activeSess.length)activeSess.push("--");
  const el=document.getElementById("sess-et");if(el)el.textContent=`ET ${dH}:${dM}${ampm} \u00b7 ${activeSess.join("+")}`;
}

function rafLoop(){MKTS.forEach(m=>{if(dirty[m.id]){drawChart(m);dirty[m.id]=false;}});requestAnimationFrame(rafLoop);}

// ── FULLSCREEN CHART ──────────────────────────────────────────
let fsMkt=null,fsRafId=null,fsCanvas=null;
const fsOverlay=()=>document.getElementById("fs-overlay");
const fsWrap=()=>document.getElementById("fs-canvas-wrap");
function openFullscreen(mkt){
  fsMkt=mkt;const ov=fsOverlay();ov.classList.add("open");
  document.getElementById("fs-sym").textContent=mkt.code;document.getElementById("fs-sym").style.color=mkt.col;
  if(!fsCanvas){fsCanvas=document.createElement("canvas");fsWrap().appendChild(fsCanvas);}
  new ResizeObserver(drawFsChart).observe(fsWrap());drawFsChart();
  if(fsRafId)cancelAnimationFrame(fsRafId);
  (function loop(){if(!fsMkt)return;drawFsChart();fsRafId=requestAnimationFrame(loop);})();
}
function closeFullscreen(){fsMkt=null;fsOverlay().classList.remove("open");if(fsRafId){cancelAnimationFrame(fsRafId);fsRafId=null;}}
function drawFsChart(){
  if(!fsMkt||!fsCanvas)return;
  const wrap=fsWrap(),dpr=window.devicePixelRatio||1,W=wrap.clientWidth,H=wrap.clientHeight;
  if(W<20||H<20)return;
  fsCanvas.width=Math.round(W*dpr);fsCanvas.height=Math.round(H*dpr);fsCanvas.style.width=W+"px";fsCanvas.style.height=H+"px";
  drawChart(fsMkt,fsCanvas,W,H);
  const q=liveQ[fsMkt.code];
  if(q){
    const dec=fsMkt.tick<1?2:0,px=document.getElementById("fs-price");
    px.textContent=q.price.toFixed(dec);px.style.color=q.change>=0?"#26a69a":"#ef5350";
    const chg=document.getElementById("fs-chg"),s=q.change>=0?"+":"";
    chg.textContent=`${s}${q.change.toFixed(dec)} (${s}${q.changePct.toFixed(2)}%)`;chg.style.color=q.change>=0?"#26a69a":"#ef5350";
  }
  renderFsPositions();
}
function renderFsPositions(){
  if(!fsMkt)return;const bar=document.getElementById("fs-positions");if(!bar)return;
  const m=fsMkt,dec=m.tick<1?2:0,trades=[];
  [...bots.filter(b=>!b.killed),adaptiveBot].forEach(bot=>{
    const t=bot.openTrades[m.code];if(!t)return;
    const rawCur=bs(m.code).at(-1)?.c??t.entry;
    const cur=t.dir==="long"?Math.max(t.sl,Math.min(t.tp,rawCur)):Math.min(t.sl,Math.max(t.tp,rawCur));
    const pts=t.dir==="long"?cur-t.entry:t.entry-cur,unr=Math.round(pts*m.ptVal*100)/100;
    trades.push({bot,t,unr,isAI:bot===adaptiveBot,cur});
  });
  if(!trades.length){bar.classList.remove("has-trades");bar.innerHTML="";return;}
  bar.classList.add("has-trades");trades.sort((a,b2)=>b2.unr-a.unr);
  bar.innerHTML=trades.map(({bot,t,unr,isAI})=>{
    const sess=t.sessLabel||t.sess||"--",ss=SESS_STYLE[primarySess(sess)]||SESS_STYLE.NY;
    const slDist=Math.abs(t.entry-t.sl).toFixed(dec),tpDist=Math.abs(t.tp-t.entry).toFixed(dec);
    const isLong=t.dir==="long",botLabel=isAI?"\u2b21 Apex AI":bot.name;
    const stratLabel=isAI?(STRATS.find(s=>s.id===t.stratUsed)?.name||"dominant"):bot.strat.name;
    return`<div class="fs-pos-card ${isLong?"long-card":"short-card"}">
      <div class="fs-pos-top">
        <span class="fs-pos-dir ${isLong?"long":"short"}">${isLong?"LONG \u25b2":"SHORT \u25bc"}</span>
        <span style="font-size:6px;padding:1px 5px;border-radius:2px;color:${ss.col};background:${ss.bg};border:1px solid ${ss.border}">${sess}</span>
      </div>
      <div class="fs-pos-bot">${botLabel} \u00b7 ${stratLabel}</div>
      <div class="fs-pos-levels">
        <div class="fs-pos-lv" style="border:1px solid #26a69a30"><div class="fs-pos-lv-lbl" style="color:#26a69a">TP</div><div class="fs-pos-lv-val" style="color:#26a69a">${t.tp.toFixed(dec)}</div><div style="font-size:5px;color:#26a69a60">+${tpDist}</div></div>
        <div class="fs-pos-lv" style="border:1px solid #d0e0ff20"><div class="fs-pos-lv-lbl" style="color:var(--tx2)">ENTRY</div><div class="fs-pos-lv-val" style="color:#dce8ff">${t.entry.toFixed(dec)}</div><div style="font-size:5px;color:var(--tx4)">${fTs(t.openT)}</div></div>
        <div class="fs-pos-lv" style="border:1px solid #ef535030"><div class="fs-pos-lv-lbl" style="color:#ef5350">SL</div><div class="fs-pos-lv-val" style="color:#ef5350">${t.sl.toFixed(dec)}</div><div style="font-size:5px;color:#ef535060">-${slDist}</div></div>
      </div>
      <div class="fs-pos-unr" style="color:${clr(unr)}">${f$(unr)}</div>
      <div class="fs-pos-meta"><span>RR ${(t.rr||2).toFixed(1)}:1</span><span>ATR ${t.atr?.toFixed(2)??'--'}</span><span>conf ${((t.conf||0)*100).toFixed(0)}%</span></div>
    </div>`;
  }).join("")+
  (trades.length>1?`<div style="display:inline-flex;flex-direction:column;justify-content:center;align-items:center;min-width:80px;padding:0 12px;gap:4px;flex-shrink:0">
    <div style="font-size:7px;color:var(--tx3)">${trades.length} positions</div>
    <div style="font-family:'Orbitron',sans-serif;font-size:12px;font-weight:700;color:${clr(trades.reduce((s,x)=>s+x.unr,0))}">${f$(trades.reduce((s,x)=>s+x.unr,0))}</div>
    <div style="font-size:6px;color:var(--tx3)">total unrealized</div>
  </div>`:"");
}
document.getElementById("fs-close").addEventListener("click",closeFullscreen);
document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeFullscreen();closeStratModal();}});

// ── STRATEGY TRADES MODAL ─────────────────────────────────────
function openStratModal(bot){
  if(!bot)return;
  document.getElementById("strat-modal-title").textContent=bot.name;
  const tot=bot.wins+bot.losses,wr=tot?(bot.wins/tot*100).toFixed(1)+"%":"--";
  const pnl=bot.closedTrades.reduce((s,t)=>s+(t.pnlUSD||0),0),avgPnl=tot?pnl/tot:0;
  document.getElementById("strat-modal-sub").textContent=`${bot.strat.type} \u00b7 RR ${bot.strat.rr}:1 \u00b7 Wave ${bot.wave}`;
  document.getElementById("strat-modal-stats").innerHTML=`
    <div class="sm-stat"><span>Trades</span><b style="color:var(--tx)">${tot}</b></div>
    <div class="sm-stat"><span>Win Rate</span><b style="color:${bot.wins/Math.max(tot,1)>=0.5?"#26a69a":"#ef5350"}">${wr}</b></div>
    <div class="sm-stat"><span>W / L</span><b style="color:var(--tx2)">${bot.wins} / ${bot.losses}</b></div>
    <div class="sm-stat"><span>Net P&L</span><b style="color:${clr(pnl)}">${f$(pnl)}</b></div>
    <div class="sm-stat"><span>Avg/Trade</span><b style="color:${clr(avgPnl)}">${f$(avgPnl)}</b></div>
    <div class="sm-stat"><span>Balance</span><b style="color:${clr(bot.balance-50000)}">${"$"+bot.balance.toFixed(2)}</b></div>`;
  const seen=new Set(),trades=[];
  const addT=t=>{const k=`${t.openT??0}|${t.entry??0}|${t.code}`;if(!seen.has(k)){seen.add(k);trades.push(t);}};
  bot.closedTrades.forEach(addT);allClosed.filter(t=>t.botName===bot.name).forEach(addT);
  trades.sort((a,b2)=>(b2.closeT||b2.openT)-(a.closeT||a.openT));
  document.getElementById("strat-modal-tbody").innerHTML=trades.length
    ?trades.map(t=>{
        const mkt=MKTS.find(m=>m.code===t.code),dec=mkt?.tick<1?2:0;
        const _sl=t.sessLabel||t.sess||"NY",ss2=SESS_STYLE[primarySess(_sl)]||SESS_STYLE.NY;
        return`<tr style="background:${t.won?"#26a69a08":"#ef535008"}">
          <td><b style="color:${mkt?.col||"#fff"}">${t.code}</b></td>
          <td style="color:${ss2?.col||"var(--tx3)"};font-size:7px">${t.sessLabel||t.sess||"--"}</td>
          <td style="color:${t.dir==="long"?"#26a69a80":"#ef535080"}">${t.dir==="long"?"\u25b2 L":"\u25bc S"}</td>
          <td style="color:var(--tx2)">${t.entry?.toFixed(dec)}</td>
          <td style="color:var(--tx2)">${(t.exitPx??t.ex)?.toFixed(dec)??"--"}</td>
          <td style="color:${clr(t.pts)}">${fPts(t.pts??0)}</td>
          <td><b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b></td>
          <td style="color:${t.won?"#26a69a":"#ef5350"};font-weight:700">${t.won?"WIN":"LOSS"}</td>
        </tr>`;}).join("")
    :`<tr><td colspan="8" style="text-align:center;color:var(--tx3);padding:20px;font-size:8px">No closed trades yet for this bot</td></tr>`;
  document.getElementById("strat-modal").classList.add("open");
}
function closeStratModal(){document.getElementById("strat-modal").classList.remove("open");}
document.getElementById("strat-modal-close").addEventListener("click",closeStratModal);
document.getElementById("strat-modal").addEventListener("click",e=>{if(e.target===document.getElementById("strat-modal"))closeStratModal();});

const f$=v=>(v>=0?"+":"-")+"$"+Math.abs(v).toFixed(2);
const fPts=v=>(v>=0?"+":"")+v.toFixed(2)+"pts";
const fPct=v=>(v*100).toFixed(1)+"%";
const clr=v=>v>0?"#26a69a":v<0?"#ef5350":"#787b86";
const fTs=ts=>new Date(ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});

function renderLeft(){
  const bb=bestBot();if(!bb)return;
  document.getElementById("bname").textContent=bb.name;
  document.getElementById("btype").textContent=`${bb.strat.type} | RR${bb.strat.rr}:1 | ATRx${bb.strat.atrMult}`;
  const p=getPnl(bb);
  document.getElementById("bbal").textContent="$"+bb.balance.toFixed(2);
  const pe=document.getElementById("bpnl");pe.textContent=f$(p);pe.style.color=clr(p);
  document.getElementById("bwr").textContent=fPct(getWR(bb));
  document.getElementById("bwl").textContent=`${bb.wins}/${bb.losses}/${bb.wins+bb.losses}`;
  document.getElementById("bsc").textContent=(score(bb)*100).toFixed(1)+"/100";
  if(bb.closedTrades.length>1){
    const cum=bb.closedTrades.map((_,i,a)=>a.slice(0,i+1).reduce((s,t)=>s+t.pnlUSD,0));
    const mn=Math.min(...cum),mx=Math.max(...cum),rng=mx-mn||1;
    const pts=cum.map((v,i)=>`${(i/(cum.length-1))*200},${21-((v-mn)/rng)*19}`).join(" ");
    const zy=21-((0-mn)/rng)*19;
    document.getElementById("spark").innerHTML=
      `<line x1="0" y1="${zy}" x2="200" y2="${zy}" stroke="#2a2e39" stroke-width="1" stroke-dasharray="3,4"/>` +
      `<polyline points="${pts}" fill="none" stroke="${p>=0?"#26a69a":"#ef5350"}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
  }
  const bbTrades=Object.entries(bb.openTrades).map(([code,t])=>({code,t}));
  bbTrades.sort((a,b2)=>{
    const mA=MKTS.find(m=>m.code===a.code),mB=MKTS.find(m=>m.code===b2.code);
    const cA=bs(a.code).at(-1)?.c??a.t.entry,cB=bs(b2.code).at(-1)?.c??b2.t.entry;
    const uA=(a.t.dir==="long"?cA-a.t.entry:a.t.entry-cA)*mA.ptVal;
    const uB=(b2.t.dir==="long"?cB-b2.t.entry:b2.t.entry-cB)*mB.ptVal;
    return uB-uA;
  });
  const curKeys=new Set(bbTrades.map(({code,t})=>`${code}|${t.openT}`));
  const bestBotChanged=bb.uid!==prevBestBotUid;
  if(!soundSeeded||bestBotChanged){prevBestTradeKeys=curKeys;prevBestBotUid=bb.uid;soundSeeded=true;}
  else{
    let newIdx=0;
    curKeys.forEach(k=>{
      if(!prevBestTradeKeys.has(k)){
        playOpenSound(newIdx++);
        const code=k.split("|")[0],trd=bb.openTrades[code];
        if(trd)addLog(`${bb.name} OPENED ${code} ${trd.dir.toUpperCase()} @ ${trd.entry} (${trd.sess??'--'})`,"open");
      }
    });
    prevBestTradeKeys=curKeys;
  }
  const oc=document.getElementById("open-count");if(oc)oc.textContent=bbTrades.length?`${bbTrades.length} active`:"";
  document.getElementById("openbox").innerHTML=bbTrades.length
    ?bbTrades.map(({code,t})=>{
        const mkt=MKTS.find(m=>m.code===code);
        const rawCur=bs(code).at(-1)?.c??t.entry;
        const cur=t.dir==="long"?Math.max(t.sl,Math.min(t.tp,rawCur)):Math.min(t.sl,Math.max(t.tp,rawCur));
        const pts=t.dir==="long"?cur-t.entry:t.entry-cur,unr=Math.round(pts*mkt.ptVal*100)/100;
        const sess=t.sess||"NY",ss=SESS_STYLE[sess]||SESS_STYLE.NY,dec=mkt.tick<1?2:0;
        const slDist=Math.abs(t.entry-t.sl).toFixed(dec),tpDist=Math.abs(t.tp-t.entry).toFixed(dec);
        const sigName=bb.strat.sess?.[sess]||bb.strat.type;
        return`<div class="pos-card">
          <div class="pos-header">
            <div>
              <div style="display:flex;align-items:center;gap:5px;margin-bottom:2px">
                <span class="pos-mkt" style="color:${mkt.col}">${mkt.code}</span>
                <span class="pos-sess" style="color:${ss.col};background:${ss.bg};border:1px solid ${ss.border}">${sess}</span>
              </div>
              <div class="pos-strat">${mkt.name} \u00b7 ${sigName}</div>
            </div>
            <span class="pos-dir ${t.dir}">${t.dir==="long"?"LONG \u25b2":"SHORT \u25bc"}</span>
          </div>
          <div class="pos-levels">
            <div class="pos-lv" style="border:1px solid #26a69a30"><div class="pos-lv-label" style="color:#26a69a">TARGET</div><div class="pos-lv-val" style="color:#26a69a">${t.tp.toFixed(dec)}</div><div class="pos-lv-dist" style="color:#26a69a">+${tpDist}pt</div></div>
            <div class="pos-lv" style="border:1px solid #d0e0ff20"><div class="pos-lv-label" style="color:var(--tx2)">ENTRY</div><div class="pos-lv-val" style="color:#dce8ff">${t.entry.toFixed(dec)}</div><div class="pos-lv-dist" style="color:var(--tx3)">${fTs(t.openT)}</div></div>
            <div class="pos-lv" style="border:1px solid #ef535030"><div class="pos-lv-label" style="color:#ef5350">STOP</div><div class="pos-lv-val" style="color:#ef5350">${t.sl.toFixed(dec)}</div><div class="pos-lv-dist" style="color:#ef5350">-${slDist}pt</div></div>
          </div>
          <div class="pos-footer">
            <div><div class="pos-unr" style="color:${clr(unr)}">${f$(unr)}</div><div style="font-size:6px;color:var(--tx3)">unrealized \u00b7 ATR ${t.atr?.toFixed(2)}</div></div>
            <div class="pos-meta"><div style="color:var(--tx2)">RR ${bb.strat.rr}:1</div><div>Score ${(score(bb)*100).toFixed(0)}/100</div></div>
          </div>
        </div>`;}).join("")
    :`<div style="padding:10px;color:var(--tx3);font-size:8.5px;text-align:center">No open positions<br><span style="font-size:7.5px;color:var(--tx4)">Watching ${MKTS.length} markets for signals</span></div>`;
  renderAILeft();
}

function renderAILeft(){
  const el=document.getElementById("ai-panel-left");if(!el)return;
  const ab=adaptiveBot,tot=ab.wins+ab.losses,wr=tot?ab.wins/tot:0;
  const currSess=getSessionET(),unlocked=aiFullyUnlocked();
  const foundCount=["NY","LONDON","ASIA","SYDNEY"].filter(s=>aiSessionReady(s)).length;
  const badge=document.getElementById("ai-wr-badge");
  if(badge){
    const allAI=allClosed.filter(t=>t.botName==="Apex AI");
    const allAITot=allAI.length,allAIWins=allAI.filter(t=>t.won).length,allAIWR=allAITot?allAIWins/allAITot:0;
    if(unlocked)badge.innerHTML=`<span style="color:#26a69a">\u25cf LIVE \u00b7 ${allAITot>0?(allAIWR*100).toFixed(0)+"%WR \u00b7 "+allAITot+"t":"watching"}</span>`;
    else badge.innerHTML=`<span style="color:#f5a623">\u29d7 SCANNING \u00b7 ${foundCount}/4 sessions \u00b7 need 2</span>`;
  }
  const aiTrades=Object.entries(ab.openTrades).map(([code,t])=>({code,t}));
  // ── sessRows: per-session expectancy + top-2 dominant strategies ─────
  const sessRows=["NY","LONDON","ASIA","SYDNEY"].map(sess=>{
    const sst=SESS_STYLE[sess]||SESS_STYLE.NY,isNow=sess===currSess;
    const top=getTop2BySession(sess);
    const ready=top.length>0;
    const pfVal=ready?top[0].pf:0;
    const expCol=pfVal>=1?"#26a69a":pfVal>0?"#ef5350":"var(--tx4)";
    const dualLabel=top.length>=2
      ?`${top[0].strat.name} + ${top[1].strat.name}`
      :top.length===1?top[0].strat.name:"";
    const modeLabel=ready?(adaptiveBot.apexMode[sess]||"CONSENSUS"):"";
    // per-session Apex W/L (separate from per-strat expectancy)
    const wl=adaptiveBot.apexSessWL?.[sess]||{w:0,l:0};
    const wlTot=wl.w+wl.l;
    const wlCol=wlTot===0?"var(--tx4)":wl.w/wlTot>=0.5?"#26a69a":"#ef5350";
    // dominant strats stacked vertically (no truncation)
    const stratList=top.length
      ?top.map((s,i)=>`<div style="font-size:6.5px;color:var(--tx2);line-height:1.45;padding:1px 0;word-break:break-word${i>0?';border-top:1px dotted var(--b1);margin-top:2px;padding-top:3px':''}">${s.strat.name}</div>`).join("")
      :`<div style="font-size:6px;color:var(--tx4);padding:2px 0">need ${APEX_MIN_TRADES}+ trades / PF≥1.0 per strategy</div>`;
    return`<div style="display:flex;align-items:flex-start;gap:4px;padding:3px 6px;border-bottom:1px solid var(--b1);${isNow?"background:"+sst.bg+"20;border-left:2px solid "+sst.col+";":""}">
      <span style="font-size:8.5px;line-height:1;color:${ready?"#26a69a":"#4c525e"};margin-top:1px">${ready?"\u2713":"\u25cb"}</span>
      <span style="font-size:6px;color:${sst.col};min-width:38px;font-weight:${isNow?"700":"400"};margin-top:1px">${sess}</span>
      <div style="flex:1;display:flex;flex-direction:column;gap:1px;min-width:0">${stratList}</div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:1px;flex-shrink:0;border-left:1px solid var(--b2);padding-left:4px">
        ${ready?`<span style="font-size:5.5px;color:${expCol};white-space:nowrap">PF ${(top[0].pf===Infinity?"∞":top[0].pf.toFixed(2))} \u00b7 ${top[0].n}t</span>`:''}
        <span style="font-size:5.5px;color:${wlCol};white-space:nowrap">${wlTot>0?"AI "+wl.w+"W/"+wl.l+"L":"AI --"}</span>
        <span style="font-size:5.5px;color:${modeLabel==="FALLBACK"?"#f5a623":"#7eb8ff"};white-space:nowrap;font-weight:700">${modeLabel||"--"}</span>
      </div>
    </div>`;
  }).join("");
  // ── Top banner: show both dominant strats + current mode for active session ─
  const topNow=getTop2BySession(currSess);
  const modeNow=adaptiveBot.apexMode[currSess]||"CONSENSUS";
  const fbRem=adaptiveBot.fallbackBarsRemaining[currSess]||0;
  const modeText=modeNow==="FALLBACK"
    ?`MODE: FALLBACK (${fbRem}b remaining)`
    :"MODE: CONSENSUS";
  const modeCol=modeNow==="FALLBACK"?"#f5a623":"#7eb8ff";
  const domBanner=topNow.length?`
    <div style="padding:5px 8px;background:#7eb8ff12;border-bottom:1px solid var(--b1);display:flex;flex-direction:column;gap:3px;align-items:flex-start;text-align:left">
      <div style="display:flex;align-items:center;gap:6px;justify-content:flex-start">
        <span style="font-size:7px;color:#7eb8ff;font-weight:700;letter-spacing:1px">DOMINANT</span>
        <span style="font-size:6.5px;color:var(--tx3)">${currSess}</span>
        <span style="font-size:6.5px;color:${topNow[0].pf>=1?"#26a69a":"#ef5350"};white-space:nowrap">PF ${(topNow[0].pf===Infinity?"∞":topNow[0].pf.toFixed(2))} \u00b7 ${topNow[0].n}t</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;padding:2px 0 2px 6px;border-left:2px solid #7eb8ff40;align-self:stretch">
        ${topNow.map(s=>`<span style=\"font-size:8px;color:var(--tx);font-weight:700;line-height:1.35;word-break:break-word;text-align:left\">\u00b7 ${s.strat.name}</span>`).join("")}
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-start">
        <span style="font-size:6.5px;color:${modeCol};font-weight:700;letter-spacing:0.5px">${modeText}</span>
        <span style="font-size:6px;color:var(--tx3)">lookback ${apexLookbackBars()}b \u00b7 iv ${iv}</span>
        ${topNow.length<2?'<span style="font-size:6px;color:var(--tx3)">single-strategy fallback (need 2 to qualify)</span>':''}
      </div>
    </div>`:"";
  let html=`${domBanner}
  <div style="font-size:6px;font-weight:700;color:${unlocked?"#26a69a":"#f5a623"};padding:3px 8px;border-bottom:1px solid var(--b1)">
    ${unlocked?"\u2713 AI LIVE \u2014 dominant strategy active (conf&gt;50%)":"\u29d7 SCANNING \u2014 need 2 sessions to unlock"}
  </div><div>${sessRows}</div>`;
  if(aiTrades.length){
    html+=aiTrades.map(({code,t})=>{
      const mkt=MKTS.find(m=>m.code===code);if(!mkt)return"";
      const rawCur=bs(code).at(-1)?.c??t.entry;
      const cur=t.dir==="long"?Math.max(t.sl,Math.min(t.tp,rawCur)):Math.min(t.sl,Math.max(t.tp,rawCur));
      const pts=t.dir==="long"?cur-t.entry:t.entry-cur,unr=Math.round(pts*mkt.ptVal*100)/100;
      const sess=t.sess||"NY",ss=SESS_STYLE[sess]||SESS_STYLE.NY,dec=mkt.tick<1?2:0;
      const slDist=Math.abs(t.entry-t.sl).toFixed(dec),tpDist=Math.abs(t.tp-t.entry).toFixed(dec);
      const rrDisp=(t.rr||2).toFixed(1),strat=STRATS.find(s=>s.id===t.stratUsed);
      // ── show top-strategy PF summary in AI position footer ──
      const topF=getTop2BySession(sess);
      const pfF=topF.length?topF[0].pf:0;
      const tallyTot=topF.length?topF[0].n:0;
      return`<div class="pos-card">
        <div class="pos-header">
          <div><div style="display:flex;align-items:center;gap:5px;margin-bottom:2px"><span class="pos-mkt" style="color:${mkt.col}">${mkt.code}</span><span class="pos-sess" style="color:${ss.col};background:${ss.bg};border:1px solid ${ss.border}">${sess}</span></div><div class="pos-strat">AI \u00b7 ${strat?.name||t.stratUsed||"dominant"} \u00b7 conf${((t.conf||0)*100).toFixed(0)}%</div></div>
          <span class="pos-dir ${t.dir}">${t.dir==="long"?"LONG \u25b2":"SHORT \u25bc"}</span>
        </div>
        <div class="pos-levels">
          <div class="pos-lv" style="border:1px solid #26a69a30"><div class="pos-lv-label" style="color:#26a69a">TARGET</div><div class="pos-lv-val" style="color:#26a69a">${t.tp.toFixed(dec)}</div><div class="pos-lv-dist" style="color:#26a69a">+${tpDist}pt</div></div>
          <div class="pos-lv" style="border:1px solid #d0e0ff20"><div class="pos-lv-label" style="color:var(--tx2)">ENTRY</div><div class="pos-lv-val" style="color:#dce8ff">${t.entry.toFixed(dec)}</div><div class="pos-lv-dist" style="color:var(--tx3)">${fTs(t.openT)}</div></div>
          <div class="pos-lv" style="border:1px solid #ef535030"><div class="pos-lv-label" style="color:#ef5350">STOP</div><div class="pos-lv-val" style="color:#ef5350">${t.sl.toFixed(dec)}</div><div class="pos-lv-dist" style="color:#ef5350">-${slDist}pt</div></div>
        </div>
        <div class="pos-footer">
          <div><div class="pos-unr" style="color:${clr(unr)}">${f$(unr)}</div><div style="font-size:6px;color:var(--tx3)">${tallyTot>0?"PF "+(pfF===Infinity?"\u221e":pfF.toFixed(2))+" \u00b7 "+tallyTot+"t in "+sess:"no "+sess+" history yet"}</div></div>
          <div class="pos-meta"><div style="color:var(--tx2)">RR ${rrDisp}:1</div></div>
        </div>
      </div>`;}).join("");
  }else{
    html+=`<div style="padding:6px 10px;color:var(--tx4);font-size:7px;text-align:center">${unlocked?"Watching "+currSess+" \u2014 conf&gt;50% required to fire":"Need "+Math.max(0,2-foundCount)+" more session"+(2-foundCount===1?"":"s")+" \u00b7 "+foundCount+"/4 ready"}</div>`;
  }
  el.innerHTML=html;
  const tp=document.getElementById("ai-trades-panel");if(!tp)return;
  if(!unlocked){tp.style.display="none";return;}
  const aiSeen=new Set(),aiClosedTrades=[];
  const addAI=t=>{const k=`${t.openT??0}|${t.entry??0}|${t.code}`;if(!aiSeen.has(k)){aiSeen.add(k);aiClosedTrades.push(t);}};
  allClosed.filter(t=>t.botName==="Apex AI").forEach(addAI);
  ab.closedTrades.forEach(t=>{const k=`${t.openT??0}|${t.entry??0}|${t.code}`;if(!aiSeen.has(k)){aiSeen.add(k);aiClosedTrades.push(t);}});
  aiClosedTrades.sort((a,b2)=>(b2.closeT||b2.openT)-(a.closeT||a.openT));
  if(!aiClosedTrades.length){tp.style.display="none";return;}
  tp.style.display="block";
  const aiWins=aiClosedTrades.filter(t=>t.won).length,aiLosses=aiClosedTrades.filter(t=>!t.won).length;
  const aiTot=aiClosedTrades.length,aiWR=aiTot?aiWins/aiTot:0,aiPnl=aiClosedTrades.reduce((s,t)=>s+(t.pnlUSD||0),0);
  tp.innerHTML=`
    <div style="padding:4px 8px;background:var(--p3);border-bottom:1px solid var(--b1);display:flex;gap:1px">
      <div style="flex:1;text-align:center;font-size:6px;color:var(--tx3);line-height:1.7">Trades<br><b style="font-size:9px;font-family:'Orbitron',sans-serif;color:var(--tx)">${aiTot}</b></div>
      <div style="flex:1;text-align:center;font-size:6px;color:var(--tx3);line-height:1.7">Win Rate<br><b style="font-size:9px;font-family:'Orbitron',sans-serif;color:${aiWR>=0.5?"#26a69a":"#ef5350"}">${(aiWR*100).toFixed(0)}%</b></div>
      <div style="flex:1;text-align:center;font-size:6px;color:var(--tx3);line-height:1.7">W / L<br><b style="font-size:9px;font-family:'Orbitron',sans-serif;color:var(--tx2)">${aiWins}/${aiLosses}</b></div>
      <div style="flex:1;text-align:center;font-size:6px;color:var(--tx3);line-height:1.7">Net P&amp;L<br><b style="font-size:9px;font-family:'Orbitron',sans-serif;color:${clr(aiPnl)}">${f$(aiPnl)}</b></div>
    </div>
    <table class="mt"><thead><tr><th>MKT</th><th>SESS</th><th>DIR</th><th>MODE</th><th>PTS</th><th>P&amp;L</th><th>RES</th></tr></thead><tbody>${
    aiClosedTrades.slice(0,30).map(t=>{
      const mkt=MKTS.find(m=>m.code===t.code),_sl=t.sessLabel||t.sess||"NY",ss2=SESS_STYLE[primarySess(_sl)]||SESS_STYLE.NY;
      const _mode=t.apexMode||"--";
      const _modeCol=_mode==="FALLBACK"?"#f5a623":_mode==="CONSENSUS"?"#7eb8ff":"var(--tx4)";
      return`<tr style="background:${t.won?"#26a69a08":"#ef535008"}">
        <td><b style="color:${mkt?.col||"#fff"}">${t.code}</b></td>
        <td style="color:${ss2?.col||"var(--tx3)"};font-size:6.5px">${_sl}</td>
        <td style="color:${t.dir==="long"?"#26a69a80":"#ef535080"}">${t.dir==="long"?"\u25b2":"\u25bc"}</td>
        <td style="color:${_modeCol};font-size:6px;font-weight:700">${_mode}</td>
        <td style="color:${clr(t.pts)}">${fPts(t.pts??0)}</td>
        <td><b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b></td>
        <td style="color:${t.won?"#26a69a":"#ef5350"};font-weight:700">${t.won?"W":"L"}</td>
      </tr>`;}).join("")
    }</tbody></table>`;
}

// ── Apex fullscreen overlay ──────────────────────────────────
let _apexFsSess=null;
const APEX_FS_TABS=["ALL","NY","LONDON","ASIA","SYDNEY"];
function openApexFullscreen(){
  if(!_apexFsSess)_apexFsSess="ALL";
  if(APEX_FS_TABS.indexOf(_apexFsSess)===-1)_apexFsSess="ALL";
  const fs=document.getElementById("apex-fs");if(!fs)return;
  fs.style.display="flex";
  renderApexFullscreen();
}
function closeApexFullscreen(){
  const fs=document.getElementById("apex-fs");if(!fs)return;
  fs.style.display="none";
}
// v6.8 PF ranking column for the fullscreen overlay -- one per session.
// Lists every strat that has at least 1 trade on this session, sorted by PF.
// Eligible strats (n >= APEX_MIN_TRADES, PF >= APEX_PF_MIN) appear at top in
// full color; ineligible strats are dimmed with the reason badge attached.
function _renderApexFsPFCol(sess){
  const sty=SESS_STYLE[sess]||SESS_STYLE.NY;
  const liveIds=getLiveStratIds();
  const all=[];
  STRATS.forEach(s=>{
    if(!liveIds.has(s.id))return;
    const e=expectancy(sess,s.id);
    if(e.n===0)return;
    const eligible=e.n>=APEX_MIN_TRADES&&e.pf>=APEX_PF_MIN;
    all.push({strat:s,pf:e.pf,n:e.n,exp:e.exp,eligible});
  });
  // Eligible first (by PF desc, exp tiebreak); then ineligible (also by PF desc).
  all.sort((a,b)=>{
    if(a.eligible!==b.eligible)return a.eligible?-1:1;
    if(a.pf===b.pf)return b.exp-a.exp;
    if(a.pf===Infinity)return -1;
    if(b.pf===Infinity)return 1;
    return b.pf-a.pf;
  });
  // Track top-1/top-2 among eligible only.
  let elIx=0;
  const rows=all.map(r=>{
    const slot=adaptiveBot.sessionTally?.[sess]?.[r.strat.id]||{wins:0,losses:0};
    const pfStr=r.pf===Infinity?"\u221e":r.pf.toFixed(2);
    let rankBadge="",rankCol="var(--tx4)";
    if(r.eligible){
      if(elIx===0){rankBadge="#1";rankCol="#ffd54f";}
      else if(elIx===1){rankBadge="#2";rankCol="#a0a8b8";}
      else{rankBadge="#"+(elIx+1);rankCol="var(--tx3)";}
      elIx++;
    }
    const opacity=r.eligible?"1":"0.45";
    const reason=!r.eligible?(r.n<APEX_MIN_TRADES?`n<${APEX_MIN_TRADES}`:"PF<"+APEX_PF_MIN.toFixed(1)):"";
    const pfCol=r.eligible?(r.pf>=2?"#26a69a":r.pf===Infinity?"#26a69a":"#dce8ff"):"var(--tx4)";
    return`<div style="display:grid;grid-template-columns:20px 1fr auto;gap:4px;align-items:center;font-size:7.5px;padding:2px 0;opacity:${opacity};border-bottom:1px solid var(--b1)">
      <span style="color:${rankCol};font-weight:700;font-size:7px">${rankBadge}</span>
      <span style="color:${r.eligible?"var(--tx)":"var(--tx3)"};white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${r.strat.name}">${r.strat.name}</span>
      <span style="text-align:right;white-space:nowrap">
        <b style="color:${pfCol}">PF ${pfStr}</b>
        <span style="color:var(--tx3);margin-left:4px">${slot.wins}W/${slot.losses}L</span>
        ${reason?`<span style="color:#ef5350;margin-left:4px">${reason}</span>`:""}
      </span>
    </div>`;
  }).join("")||`<div style="font-size:7px;color:var(--tx4);padding:6px 0;text-align:center">No trades yet</div>`;
  const eligCount=all.filter(r=>r.eligible).length;
  return`<div style="border:1px solid ${sty.border};background:${sty.bg};padding:5px 8px;border-radius:2px">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;border-bottom:1px solid ${sty.border};padding-bottom:3px">
      <span style="color:${sty.col};font-size:8px;font-weight:700;letter-spacing:1px">${sess}</span>
      <span style="font-size:6.5px;color:var(--tx3);margin-left:auto">${eligCount} eligible / ${all.length} traded</span>
    </div>
    ${rows}
  </div>`;
}
function _apexTradesForSess(sess){
  const seen=new Set(),out=[];
  const add=t=>{const k=`${t.openT??0}|${t.entry??0}|${t.code}`;if(!seen.has(k)){seen.add(k);out.push(t);}};
  allClosed.filter(t=>t.botName==="Apex AI").forEach(add);
  adaptiveBot.closedTrades.forEach(add);
  const filtered=sess==="ALL"?out:out.filter(t=>(t.sess||"NY")===sess);
  return filtered.sort((a,b)=>(a.closeT||a.openT)-(b.closeT||b.openT));
}
function renderApexFullscreen(){
  const fs=document.getElementById("apex-fs");
  if(!fs||fs.style.display==="none")return;
  const sess=_apexFsSess||"NY";
  // ── tabs
  const tabsEl=document.getElementById("apex-fs-tabs");
  tabsEl.innerHTML=APEX_FS_TABS.map(s=>{
    const on=s===sess;
    const accent=s==="ALL"?"#d0e0ff":"#7eb8ff";
    const col=on?accent:"var(--tx2)",bg=on?accent+"18":"transparent";
    return`<span class="apex-fs-tab" data-sess="${s}" style="cursor:pointer;padding:3px 12px;font-size:9px;font-weight:700;letter-spacing:1px;border:1px solid ${on?accent:"var(--b2)"};color:${col};background:${bg}">${s}</span>`;
  }).join("");
  tabsEl.querySelectorAll(".apex-fs-tab").forEach(b=>{
    b.onclick=()=>{_apexFsSess=b.dataset.sess;renderApexFullscreen();};
  });
  // ── trades + stats
  const trades=_apexTradesForSess(sess);
  const wins=trades.filter(t=>t.won).length,losses=trades.length-wins;
  const tot=trades.length,wr=tot?wins/tot:0;
  const pnl=trades.reduce((s,t)=>s+(t.pnlUSD||0),0);
  let ssWL;
  if(sess==="ALL"){
    ssWL={w:0,l:0};
    Object.values(adaptiveBot.apexSessWL||{}).forEach(v=>{
      ssWL.w+=v?.w||0;ssWL.l+=v?.l||0;
    });
  }else{
    ssWL=adaptiveBot.apexSessWL?.[sess]||{w:0,l:0};
  }
  const consTrades=trades.filter(t=>t.apexMode==="CONSENSUS");
  const fbTrades  =trades.filter(t=>t.apexMode==="FALLBACK");
  const _wr=ts=>{const w=ts.filter(x=>x.won).length;return ts.length?w/ts.length:0;};
  const _pnl=ts=>ts.reduce((s,x)=>s+(x.pnlUSD||0),0);
  document.getElementById("apex-fs-stats").innerHTML=`
    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:10px;font-size:9px">
      <div><div style="color:var(--tx3);font-size:7px;text-transform:uppercase;letter-spacing:1px">Trades</div><b style="font-size:14px">${tot}</b></div>
      <div><div style="color:var(--tx3);font-size:7px;text-transform:uppercase;letter-spacing:1px">Win Rate</div><b style="font-size:14px;color:${wr>=0.5?"#26a69a":"#ef5350"}">${(wr*100).toFixed(1)}%</b></div>
      <div><div style="color:var(--tx3);font-size:7px;text-transform:uppercase;letter-spacing:1px">W / L</div><b style="font-size:14px"><span style="color:#26a69a">${wins}</span> / <span style="color:#ef5350">${losses}</span></b></div>
      <div><div style="color:var(--tx3);font-size:7px;text-transform:uppercase;letter-spacing:1px">Lifetime W/L</div><b style="font-size:14px;color:var(--tx2)">${ssWL.w}/${ssWL.l}</b></div>
      <div><div style="color:var(--tx3);font-size:7px;text-transform:uppercase;letter-spacing:1px">Net P&amp;L</div><b style="font-size:14px;color:${clr(pnl)}">${f$(pnl)}</b></div>
      <div><div style="color:var(--tx3);font-size:7px;text-transform:uppercase;letter-spacing:1px">Consensus / Fallback</div><b style="font-size:11px;color:#7eb8ff">${consTrades.length} (${(_wr(consTrades)*100).toFixed(0)}%)</b> / <b style="font-size:11px;color:#f5a623">${fbTrades.length} (${(_wr(fbTrades)*100).toFixed(0)}%)</b></div>
    </div>
    <div style="margin-top:6px;font-size:7px;color:var(--tx3)">Net P&amp;L by mode: <span style="color:${clr(_pnl(consTrades))}">CONSENSUS ${f$(_pnl(consTrades))}</span> \u00b7 <span style="color:${clr(_pnl(fbTrades))}">FALLBACK ${f$(_pnl(fbTrades))}</span></div>`;
  // ── PF ranking by session (always shows all 4 sessions side-by-side)
  const pfEl=document.getElementById("apex-fs-pf-rank");
  if(pfEl){
    const sessions=["NY","LONDON","ASIA","SYDNEY"];
    pfEl.innerHTML=`
      <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">
        <span style="font-size:7px;color:#f5a623;text-transform:uppercase;letter-spacing:1.5px;font-weight:700">PF Ranking by Session</span>
        <span style="font-size:6.5px;color:var(--tx3)">eligibility: PF \u2265 ${APEX_PF_MIN.toFixed(1)} \u00b7 n \u2265 ${APEX_MIN_TRADES} trades \u00b7 ranks among eligible only</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px">
        ${sessions.map(s=>_renderApexFsPFCol(s)).join("")}
      </div>`;
  }
  // ── open Apex positions (live; filtered by selected session)
  const openEl=document.getElementById("apex-fs-open");
  if(openEl){
    const openAll=Object.entries(adaptiveBot.openTrades||{}).map(([code,t])=>({code,t}));
    const open=sess==="ALL"?openAll:openAll.filter(o=>(o.t.sess||"NY")===sess);
    if(!open.length){
      openEl.innerHTML=`<div style="font-size:8px;color:var(--tx3);text-align:left">No open Apex positions${sess==="ALL"?"":` in ${sess}`}</div>`;
    }else{
      openEl.innerHTML=`<div style="font-size:7px;color:#7eb8ff;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;font-weight:700">Open Positions (${open.length})</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px">${
        open.map(({code,t})=>{
          const m=MKTS.find(mk=>mk.code===code);
          const dec=m&&m.tick<1?2:0;
          const rawCur=bs(code).at(-1)?.c??t.entry;
          const cur=t.dir==="long"?Math.max(t.sl,Math.min(t.tp,rawCur)):Math.min(t.sl,Math.max(t.tp,rawCur));
          const pts=t.dir==="long"?cur-t.entry:t.entry-cur;
          const unr=m?Math.round(pts*m.ptVal*100)/100:0;
          const tSess=t.sess||"NY";
          const tSessSty=SESS_STYLE[tSess]||SESS_STYLE.NY;
          const mode=t.apexMode||"--";
          const modeCol=mode==="FALLBACK"?"#f5a623":mode==="CONSENSUS"?"#7eb8ff":"var(--tx4)";
          return`<div style="border:1px solid var(--b2);background:#0c0e15;padding:6px 8px;border-radius:2px">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
              <span style="color:${m?.col||"#fff"};font-weight:700;font-size:9px">${code}</span>
              <span style="color:${tSessSty.col};background:${tSessSty.bg};border:1px solid ${tSessSty.border};padding:1px 4px;font-size:7px;font-weight:700">${tSess}</span>
              <span style="color:${t.dir==="long"?"#26a69a":"#ef5350"};font-weight:700;font-size:9px">${t.dir==="long"?"\u25b2 LONG":"\u25bc SHORT"}</span>
              <span style="color:${modeCol};font-weight:700;font-size:7px;margin-left:auto">${mode}</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px;font-size:8px">
              <div><div style="color:var(--tx3);font-size:6px;text-transform:uppercase;letter-spacing:1px">Target</div><b style="color:#26a69a">${t.tp.toFixed(dec)}</b></div>
              <div><div style="color:var(--tx3);font-size:6px;text-transform:uppercase;letter-spacing:1px">Entry</div><b style="color:#dce8ff">${t.entry.toFixed(dec)}</b></div>
              <div><div style="color:var(--tx3);font-size:6px;text-transform:uppercase;letter-spacing:1px">Stop</div><b style="color:#ef5350">${t.sl.toFixed(dec)}</b></div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px;padding-top:4px;border-top:1px solid var(--b1)">
              <div><div style="color:var(--tx3);font-size:6px;text-transform:uppercase;letter-spacing:1px">Unrealized</div><b style="font-size:10px;color:${clr(unr)}">${f$(unr)}</b></div>
              <div style="font-size:6.5px;color:var(--tx3);margin-left:auto">cur ${rawCur.toFixed(dec)} \u00b7 RR ${(t.rr||2).toFixed(1)}:1</div>
            </div>
          </div>`;
        }).join("")
      }</div>`;
    }
  }
  // ── chart: cumulative P&L
  const chartEl=document.getElementById("apex-fs-chart");
  if(trades.length<2){
    chartEl.innerHTML=`<div style="color:var(--tx4);font-size:9px;text-align:center;padding-top:60px">No P&amp;L history${sess==="ALL"?"":` for ${sess}`}</div>`;
  }else{
    let cum=0;const pts=trades.map(t=>{cum+=t.pnlUSD||0;return{t:t.closeT||t.openT,v:cum};});
    const minV=Math.min(...pts.map(p=>p.v),0),maxV=Math.max(...pts.map(p=>p.v),0);
    const W=Math.max(400,chartEl.clientWidth||800),H=148;
    const minT=pts[0].t,maxT=pts[pts.length-1].t;
    const sx=t=>maxT===minT?W/2:8+(t-minT)/(maxT-minT)*(W-16);
    const sy=v=>maxV===minV?H/2:H-8-((v-minV)/(maxV-minV))*(H-16);
    const path=pts.map((p,i)=>`${i===0?"M":"L"}${sx(p.t).toFixed(1)},${sy(p.v).toFixed(1)}`).join(" ");
    const zero=sy(0);
    const dotPath=pts.map(p=>`<circle cx="${sx(p.t).toFixed(1)}" cy="${sy(p.v).toFixed(1)}" r="1.8" fill="${pnl>=0?"#26a69a":"#ef5350"}"/>`).join("");
    chartEl.innerHTML=`<svg width="${W}" height="${H}" style="display:block">
      <line x1="0" y1="${zero}" x2="${W}" y2="${zero}" stroke="var(--b2)" stroke-dasharray="3,3"/>
      <path d="${path}" fill="none" stroke="${pnl>=0?"#26a69a":"#ef5350"}" stroke-width="1.5"/>
      ${dotPath}
      <text x="6" y="12" font-size="9" fill="var(--tx3)">${f$(maxV)}</text>
      <text x="6" y="${H-4}" font-size="9" fill="var(--tx3)">${f$(minV)}</text>
    </svg>`;
  }
  // ── trades table with MODE column
  const tradesEl=document.getElementById("apex-fs-trades");
  if(!trades.length){
    tradesEl.innerHTML=`<div style="padding:20px;text-align:center;color:var(--tx3);font-size:9px">No closed Apex trades${sess==="ALL"?"":` in ${sess}`}</div>`;
  }else{
    const showSessCol=sess==="ALL";
    tradesEl.innerHTML=`<table class="mt" style="font-size:8.5px"><thead><tr>
      <th>WHEN</th><th>MKT</th>${showSessCol?"<th>SESS</th>":""}<th>DIR</th><th>MODE</th><th>STRAT</th>
      <th>ENTRY</th><th>EXIT</th><th>SL</th><th>TP</th><th>PTS</th><th>P&amp;L</th><th>RES</th>
    </tr></thead><tbody>${
      trades.slice().reverse().map(t=>{
        const m=MKTS.find(mk=>mk.code===t.code);const dec=m&&m.tick<1?2:0;
        const mode=t.apexMode||"--";
        const modeCol=mode==="FALLBACK"?"#f5a623":mode==="CONSENSUS"?"#7eb8ff":"var(--tx4)";
        const stratLabel=t.stratUsed||"";
        const tSess=t.sess||"NY";
        const tSessSty=SESS_STYLE[tSess]||SESS_STYLE.NY;
        return`<tr style="background:${t.won?"#26a69a08":"#ef535008"}">
          <td style="font-size:7px;color:var(--tx3);white-space:nowrap">${fTs(t.closeT||t.openT)}</td>
          <td><b style="color:${m?.col||"#fff"}">${t.code}</b></td>
          ${showSessCol?`<td style="color:${tSessSty.col};font-size:7px;font-weight:700">${tSess}</td>`:""}
          <td style="color:${t.dir==="long"?"#26a69a":"#ef5350"};font-weight:700">${t.dir==="long"?"\u25b2 LONG":"\u25bc SHORT"}</td>
          <td style="color:${modeCol};font-weight:700">${mode}</td>
          <td style="font-size:7px;color:var(--tx3);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${stratLabel}">${stratLabel}</td>
          <td>${(t.entry??0).toFixed(dec)}</td>
          <td>${(t.exitPx??0).toFixed(dec)}</td>
          <td style="color:#ef535080">${(t.sl??0).toFixed(dec)}</td>
          <td style="color:#26a69a80">${(t.tp??0).toFixed(dec)}</td>
          <td style="color:${clr(t.pts)}">${fPts(t.pts??0)}</td>
          <td><b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b></td>
          <td style="color:${t.won?"#26a69a":"#ef5350"};font-weight:700">${t.won?"W":"L"}</td>
        </tr>`;
      }).join("")
    }</tbody></table>`;
  }
}

function renderSigBars(){
  MKTS.forEach(m=>{
    const sb=document.getElementById("sb-"+m.id);if(!sb)return;
    const dec=m.tick<1?2:0,openHere=[];
    [...bots.filter(b=>!b.killed),adaptiveBot].forEach(bot=>{
      const t=bot.openTrades[m.code];if(!t)return;
      const rawCur=bs(m.code).at(-1)?.c??t.entry;
      const cur=t.dir==="long"?Math.max(t.sl,Math.min(t.tp,rawCur)):Math.min(t.sl,Math.max(t.tp,rawCur));
      const pts=t.dir==="long"?cur-t.entry:t.entry-cur,unr=Math.round(pts*m.ptVal*100)/100;
      openHere.push({bot,t,unr,isAI:bot===adaptiveBot});
    });
    if(openHere.length){
      sb.innerHTML=openHere.map(({bot,t,unr,isAI})=>
        `<span class="chip ${t.dir==="long"?"cl":"cs"}" style="flex-direction:column;align-items:flex-start;gap:0;padding:1px 4px">
          <span style="font-size:7px">${isAI?"\u2b21AI":""}${bot.name.split(" W")[0].slice(0,8)} ${t.dir==="long"?"\u25b2":"\u25bc"}</span>
          <span style="font-size:6px">E:${t.entry?.toFixed(dec)} TP:${t.tp?.toFixed(dec)}</span>
          <b style="font-size:6px;color:${clr(unr)}">${f$(unr)}</b>
        </span>`).join("");
    }else{
      sb.innerHTML=`<span style="color:var(--tx4);font-size:6.5px">${m.tierLabel||("T"+m.tier)} \u00b7 watching</span>`;
    }
    const q=liveQ[m.code];
    if(q){const cc=document.getElementById("cchg-"+m.id);if(cc){const s=q.change>=0?"+":"";cc.textContent=`${s}${q.change.toFixed(2)}(${s}${q.changePct.toFixed(2)}%)`;cc.style.color=q.change>=0?"var(--up)":"var(--dn)";}}
  });
}

function renderAllTrades(){
  const seen=new Set(),merged=[];
  const addRec=t=>{const k=`${t.code}|${t.openT??0}|${t.entry??0}|${t.botName}`;if(!seen.has(k)){seen.add(k);merged.push(t);}};
  allClosed.forEach(addRec);bots.forEach(b=>b.closedTrades.forEach(addRec));adaptiveBot.closedTrades.forEach(addRec);
  merged.sort((a,b)=>(b.closeT||b.openT)-(a.closeT||a.openT));
  document.getElementById("atbody").innerHTML=merged.length
    ?merged.map(t=>{
        const mkt=MKTS.find(m=>m.code===t.code),dec=mkt?.tick<1?2:0;
        const _sl=t.sessLabel||t.sess||"NY",ss2=SESS_STYLE[primarySess(_sl)]||SESS_STYLE.NY;
        return`<tr style="background:${t.won?"#26a69a08":"#ef535008"}">
          <td><b style="color:${mkt?.col||'#fff'}">${t.code}</b></td>
          <td style="color:#9c27b0;max-width:72px;overflow:hidden;text-overflow:ellipsis;font-size:7px">${t.botName?.replace(" W1","").replace(" W2","").replace(" W3","")}</td>
          <td style="color:${ss2?.col||'var(--tx3)'};font-size:7px">${t.sessLabel||t.sess||"--"}</td>
          <td style="color:${t.dir==="long"?"#26a69a70":"#ef535070"}">${t.dir==="long"?"L":"S"}</td>
          <td style="color:var(--tx2)">${t.entry?.toFixed(dec)}</td>
          <td style="color:var(--tx2)">${(t.exitPx??t.ex)?.toFixed(dec)}</td>
          <td style="color:${clr(t.pts)}">${fPts(t.pts??0)}</td>
          <td><b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b></td>
          <td style="color:${t.won?"#26a69a":"#ef5350"}">${t.won?"WIN":"LOSS"}</td>
        </tr>`;}).join("")
    :`<tr><td colspan="9" style="text-align:center;color:var(--tx3);padding:12px">Bots fire on crossover signals -- trades appear when SL or TP is hit on a real bar.</td></tr>`;
}

function renderRight(){
  const ab=live(),bb=bestBot();
  document.getElementById("blist").innerHTML=[...bots].sort((a,b2)=>score(b2)-score(a))
    .map(b=>{
      const tot=b.wins+b.losses,wr=getWR(b),p=getPnl(b);
      const bc=b.killed?"#2a2e39":tot===0?"#4c525e":(wr>=0.5&&p>=0)?"#26a69a":(tot>0&&p>=0)?"#f5a623":"#ef5350";
      const isBest=b===bb,wrBar=Math.round(wr*100);
      return`<div class="brow${b.killed?" dead":""}" onclick="openStratModal(bots.find(x=>x.uid===${b.uid}))" title="Click to view ${b.name} trades">
        <span class="bdot" style="background:${bc}"></span>
        <div style="flex:1;min-width:0">
          <div style="display:flex;justify-content:space-between;gap:2px">
            <span style="color:${isBest?"var(--cy)":b.killed?"#363a45":"#787b86"};font-size:7.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${isBest?"\u2605 ":""}${b.name}</span>
            <b style="color:${tot===0?"#4c525e":clr(p)};font-size:7.5px;flex-shrink:0">${tot===0?"no trades":f$(p)}</b>
          </div>
          <div style="display:flex;align-items:center;gap:3px">
            <div class="bbar"><div class="bfill" style="width:${wrBar}%;background:${bc}"></div></div>
            <span style="color:${bc};font-size:7px;flex-shrink:0">${tot===0?"--":fPct(wr)}</span>
          </div>
          ${b.killed?`<div style="color:#3e1c1c;font-size:6.5px">${b.killReason}</div>`:""}
        </div></div>`;}).join("");
  document.getElementById("srcsect").innerHTML=MKTS.map(m=>{
    const src=sources[m.code]||"--",ok=!!candles[m.code]?.length;
    return`<div style="display:flex;justify-content:space-between;margin-bottom:1px"><span style="color:${m.col}">${m.code}</span><span style="font-size:7.5px;color:${ok?"#26a69a":"#ef5350"}">${src.replace("Yahoo Finance ","YF")}</span></div>`;
  }).join("");
}

function renderAdaptive(){
  const currSess=getSessionET(),sessions=["NY","SYDNEY","ASIA","LONDON"],ssect=document.getElementById("sess-best-sect");
  if(!ssect)return;
  const sessMap=sessions.map(sess=>({sess,best:getBestStratForSession(sess)})).filter(x=>x.best);
  if(!sessMap.length){ssect.innerHTML=`<div style="padding:5px 9px;color:var(--tx4);font-size:7px">Waiting \u2014 need WR&gt;50% strategy per session</div>`;return;}
  ssect.innerHTML=sessMap.map(({sess,best})=>{
    const sst=SESS_STYLE[sess]||SESS_STYLE.NY,isNow=sess===currSess,wrPct=(best.wr*100).toFixed(0);
    const wrCol=best.wr>=0.65?"#26a69a":best.wr>=0.45?"#f5a623":"#ef5350";
    return`<div style="display:flex;align-items:center;gap:3px;padding:2px 7px;border-bottom:1px solid var(--b1);${isNow?"background:"+sst.bg+"20;border-left:2px solid "+sst.col+";":""}>
      <span style="font-size:6px;padding:1px 4px;border-radius:2px;color:${sst.col};background:${sst.bg};border:1px solid ${sst.border};min-width:28px;text-align:center">${sess}</span>
      <b style="font-size:7px;color:${best.mktCol};flex-shrink:0">${best.mktCode}</b>
      <span style="flex:1;font-size:6px;color:var(--tx2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${best.strat?.name||best.stratId}</span>
      <div style="text-align:right;flex-shrink:0;line-height:1.3">
        <b style="font-size:7px;color:${wrCol};display:block">${wrPct}% WR</b>
        <span style="font-size:5.5px;color:var(--tx3)">${best.n}t</span>
      </div>
    </div>`;}).join("");
}

// ── Win Rate fullscreen overlay (3 cols: standalones / combos / leaderboard) ──
function openWRFullscreen(){
  const fs=document.getElementById("wr-fs");if(!fs)return;
  fs.style.display="flex";
  renderWRFullscreen();
}
function closeWRFullscreen(){
  const fs=document.getElementById("wr-fs");if(!fs)return;
  fs.style.display="none";
}
function _wrFsRow(b,bb){
  const tot=b.wins+b.losses,wr=getWR(b),p=getPnl(b);
  const bc=b.killed?"#2a2e39":tot===0?"#4c525e":(wr>=0.5&&p>=0)?"#26a69a":(tot>0&&p>=0)?"#f5a623":"#ef5350";
  const isBest=b===bb,wrBar=Math.round(wr*100);
  return`<div class="brow${b.killed?" dead":""}" onclick="openStratModal(bots.find(x=>x.uid===${b.uid}))" title="Click to view ${b.name} trades" style="font-size:9px;padding:5px 11px">
    <span class="bdot" style="background:${bc};width:6px;height:6px"></span>
    <div style="flex:1;min-width:0">
      <div style="display:flex;justify-content:space-between;gap:4px">
        <span style="color:${isBest?"var(--cy)":b.killed?"#363a45":"var(--tx2)"};font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${isBest?"\u2605 ":""}${b.name}</span>
        <b style="color:${tot===0?"#4c525e":clr(p)};font-size:9px;flex-shrink:0">${tot===0?"no trades":f$(p)}</b>
      </div>
      <div style="display:flex;align-items:center;gap:4px;margin-top:1px">
        <div class="bbar" style="height:3px"><div class="bfill" style="width:${wrBar}%;background:${bc}"></div></div>
        <span style="color:${bc};font-size:8px;flex-shrink:0;min-width:38px;text-align:right">${tot===0?"--":fPct(wr)} &middot; ${tot}t</span>
      </div>
      ${b.killed?`<div style="color:#3e1c1c;font-size:7.5px;margin-top:1px">${b.killReason}</div>`:""}
    </div></div>`;
}
function renderWRFullscreen(){
  const fs=document.getElementById("wr-fs");if(!fs||fs.style.display==="none")return;
  const bb=bestBot();
  const standalones=bots.filter(b=>!b.strat.apexExclude);
  const combos     =bots.filter(b=> b.strat.apexExclude);
  const byScore    =(a,b2)=>score(b2)-score(a);
  const stdEl=document.getElementById("wr-fs-standalones");
  const cmbEl=document.getElementById("wr-fs-combos");
  const lbEl =document.getElementById("wr-fs-leaderboard");
  const stdCnt=document.getElementById("wr-fs-std-count");
  const cmbCnt=document.getElementById("wr-fs-combo-count");
  if(stdEl)stdEl.innerHTML=[...standalones].sort(byScore).map(b=>_wrFsRow(b,bb)).join("");
  if(cmbEl)cmbEl.innerHTML=[...combos     ].sort(byScore).map(b=>_wrFsRow(b,bb)).join("");
  if(lbEl) lbEl .innerHTML=[...bots       ].sort(byScore).map(b=>_wrFsRow(b,bb)).join("");
  if(stdCnt)stdCnt.textContent=`${standalones.length} strats`;
  if(cmbCnt)cmbCnt.textContent=`${combos.length} strats`;
}

function addLog(msg,type="info"){
  logE.unshift({msg,type,ts:Date.now()});logE=logE.slice(0,80);
  document.getElementById("log").innerHTML=logE.map(e=>
    `<span class="lc ${e.type}">${new Date(e.ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"})} ${e.msg}</span>`).join("");
}

document.querySelectorAll(".ivb").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".ivb").forEach(b=>b.classList.remove("on"));
    btn.classList.add("on");iv=btn.dataset.iv;
    // reset lookback signal cache on iv change (lookback window changes meaning)
    adaptiveBot._lastSig={};
    candles={};liveQ={};sources={};prevPx={};dirty={};
    processedTs={};startupDone=false;prevBestTradeKeys=new Set();prevBestBotUid=null;soundSeeded=false;
    // ── reset AI open trades on iv switch; sessionTally / W-L intentionally preserved ──
    if(adaptiveBot){adaptiveBot.openTrades={};adaptiveBot._barClosedCodes=new Set();}
    addLog("Interval \u2192 "+iv+" -- chart refreshed, all trades kept","info");
    refreshFull();
  });
});
window.addEventListener("resize",()=>MKTS.forEach(m=>{dirty[m.id]=true;}));

buildGrid();
updateSessionClock();
setInterval(updateSessionClock,5000);
refreshFull();
setInterval(refreshFull,30000);
setInterval(refreshQuote,750);
refreshQuote();
setInterval(()=>{renderLeft();renderSigBars();renderRight();renderAdaptive();if(document.getElementById("apex-fs")?.style.display!=="none")renderApexFullscreen();if(document.getElementById("wr-fs")?.style.display!=="none")renderWRFullscreen();},1500);
document.addEventListener("keydown",e=>{
  if(e.key!=="Escape")return;
  if(document.getElementById("apex-fs")?.style.display!=="none")closeApexFullscreen();
  if(document.getElementById("wr-fs")?.style.display!=="none")closeWRFullscreen();
});
requestAnimationFrame(rafLoop);

// ══════════════════════════════════════════════════════════════
// AUTO-SAVE  --  ff_bots_state_v7.json
// Reads and writes directly from/to disk on every GET/POST.
// sessionTally persists across interval changes.
// ══════════════════════════════════════════════════════════════
function _serializeState(){
  return{
    savedAt: Date.now(),
    iv,
    wave, uid, totalClosed,
    perfMatrix,
    allClosed: allClosed.slice(0,5000),
    pendingSignals,
    bots: bots.map(b=>({
      uid:b.uid, name:b.name, stratId:b.strat.id, wave:b.wave,
      balance:b.balance, wins:b.wins, losses:b.losses,
      killed:b.killed, killReason:b.killReason,
      _sessWins:b._sessWins||0, _sessLosses:b._sessLosses||0,
      closedTrades:b.closedTrades.slice(-200),
      openTrades:b.openTrades
    })),
    adaptiveBot:{
      wins:adaptiveBot.wins, losses:adaptiveBot.losses,
      sessionTally:adaptiveBot.sessionTally,
      apexMode:adaptiveBot.apexMode,
      barsSinceLastTrade:adaptiveBot.barsSinceLastTrade,
      fallbackBarsRemaining:adaptiveBot.fallbackBarsRemaining,
      apexSessWL:adaptiveBot.apexSessWL,
      _lastSig:adaptiveBot._lastSig,
      apexPaused:adaptiveBot.apexPaused,
      consecLosses:adaptiveBot.consecLosses,
      _lastDomId:adaptiveBot._lastDomId,
      closedTrades:adaptiveBot.closedTrades.slice(-200),
      openTrades:adaptiveBot.openTrades
    },
    processedTs
  };
}

async function saveState(){
  try{
    const body=JSON.stringify(_serializeState());
    await fetch("/api/state/v6",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body,
      signal:AbortSignal.timeout(8000)
    });
    const now=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
    addLog(`Auto-save complete at ${now} \u2014 ${(body.length/1024).toFixed(0)} KB written to disk`,"save");
  }catch(e){console.warn("auto-save failed:",e.message);}
}

async function restoreState(){
  try{
    const r=await fetch("/api/state/v6",{signal:AbortSignal.timeout(5000)});
    if(!r.ok)return;
    const s=await r.json();
    if(!s||!s.savedAt)return;

    wave        = s.wave        ?? wave;
    uid         = s.uid         ?? uid;
    totalClosed = s.totalClosed ?? totalClosed;
    document.getElementById("tcl").textContent = totalClosed;

    if(s.perfMatrix) Object.assign(perfMatrix, s.perfMatrix);
    if(Array.isArray(s.allClosed)) allClosed=[...s.allClosed];
    if(s.pendingSignals) Object.assign(pendingSignals, s.pendingSignals);

    if(Array.isArray(s.bots)){
      // ── group saved entries by stratId (older saves may contain duplicates
      //    from the prior wave-based bug); merge closedTrades, keep highest wave.
      const grouped={};
      s.bots.forEach(sv=>{
        if(!sv||!sv.stratId)return;
        const g=grouped[sv.stratId]||(grouped[sv.stratId]={
          stratId:sv.stratId,wave:0,uid:sv.uid,name:sv.name,balance:sv.balance,
          wins:0,losses:0,_sessWins:0,_sessLosses:0,killed:false,killReason:"",
          closedTrades:[],openTrades:{}
        });
        // pick the highest-wave entry as canonical for stats fields
        if((sv.wave||1)>=(g.wave||0)){
          g.wave=sv.wave||1;
          g.uid=sv.uid;
          g.name=sv.name||g.name;
          g.balance=sv.balance??g.balance;
          g.wins=sv.wins??g.wins;
          g.losses=sv.losses??g.losses;
          g._sessWins=sv._sessWins??g._sessWins;
          g._sessLosses=sv._sessLosses??g._sessLosses;
          g.killed=sv.killed??false;
          g.killReason=sv.killReason??"";
          g.openTrades=sv.openTrades||{};
        }
        // closedTrades: merge across all waves (history is shared per-strat)
        if(Array.isArray(sv.closedTrades))g.closedTrades=g.closedTrades.concat(sv.closedTrades);
      });
      Object.values(grouped).forEach(saved=>{
        const strat=STRATS.find(st=>st.id===saved.stratId);if(!strat)return;
        // single bot per strategy — match by stratId only, never push
        let bot=bots.find(b=>b.strat.id===saved.stratId);
        if(!bot)return; // strat no longer in STRATS — skip
        bot.uid          = saved.uid          ?? bot.uid;
        bot.wave         = saved.wave         ?? bot.wave;
        bot.name         = saved.name         ?? `${strat.name} W${bot.wave}`;
        bot.balance      = saved.balance      ?? bot.balance;
        bot.wins         = saved.wins         ?? 0;
        bot.losses       = saved.losses       ?? 0;
        bot.killed       = saved.killed       ?? false;
        bot.killReason   = saved.killReason   ?? "";
        bot._sessWins    = saved._sessWins    ?? 0;
        bot._sessLosses  = saved._sessLosses  ?? 0;
        // dedupe closedTrades by (openT|entry|code) so re-merges don't grow it
        const seen=new Set(),dedup=[];
        (saved.closedTrades||[]).forEach(t=>{
          const k=`${t.openT??0}|${t.entry??0}|${t.code}`;
          if(!seen.has(k)){seen.add(k);dedup.push(t);}
        });
        bot.closedTrades = dedup.slice(-200);
        bot.openTrades   = saved.openTrades   ?? {};
      });
      // post-restore safety: collapse any duplicate stratId entries that may
      // have crept into bots[] from older builds.
      const byStrat={};
      const keep=[];
      bots.forEach(b=>{
        const id=b.strat?.id;if(!id)return;
        if(!byStrat[id]){byStrat[id]=b;keep.push(b);return;}
        // duplicate: merge closedTrades, keep highest wave on the canonical bot
        const can=byStrat[id];
        if((b.wave||1)>(can.wave||1)){
          can.wave=b.wave;can.name=b.name;can.uid=b.uid;
          can.balance=b.balance;can.killed=b.killed;can.killReason=b.killReason;
          can._sessWins=b._sessWins;can._sessLosses=b._sessLosses;
          can.wins=b.wins;can.losses=b.losses;
        }
        const seen2=new Set();
        const merged=[...(can.closedTrades||[]),...(b.closedTrades||[])].filter(t=>{
          const k=`${t.openT??0}|${t.entry??0}|${t.code}`;
          if(seen2.has(k))return false;seen2.add(k);return true;
        });
        can.closedTrades=merged.slice(-200);
      });
      if(keep.length!==bots.length){bots.length=0;keep.forEach(b=>bots.push(b));}
      uid=Math.max(...bots.map(b=>b.uid),uid);
    }

    if(s.adaptiveBot){
      adaptiveBot.wins         = s.adaptiveBot.wins         ?? 0;
      adaptiveBot.losses       = s.adaptiveBot.losses       ?? 0;
      adaptiveBot.closedTrades = s.adaptiveBot.closedTrades ?? [];
      adaptiveBot.openTrades   = s.adaptiveBot.openTrades   ?? {};
      // ── restore per-session per-strategy expectancy tally ─────
      // tolerate old W/L shape ({NY:{w,l}}); reset such sessions to empty.
      if(s.adaptiveBot.sessionTally){
        Object.keys(adaptiveBot.sessionTally).forEach(sess=>{
          const v=s.adaptiveBot.sessionTally[sess];
          if(!v||typeof v!=="object"){adaptiveBot.sessionTally[sess]={};return;}
          // detect old shape: top-level w/l keys
          if("w" in v||"l" in v){adaptiveBot.sessionTally[sess]={};return;}
          adaptiveBot.sessionTally[sess]={};
          Object.keys(v).forEach(stratId=>{
            const slot=v[stratId];
            if(!slot||typeof slot!=="object")return;
            adaptiveBot.sessionTally[sess][stratId]={
              wins         :slot.wins         ??0,
              losses       :slot.losses       ??0,
              totalWinPts  :slot.totalWinPts  ??0,
              totalLossPts :slot.totalLossPts ??0
            };
          });
        });
      }
      // restore apex mode + counters (best-effort; defaults preserved)
      ["apexMode","barsSinceLastTrade","fallbackBarsRemaining"].forEach(key=>{
        const v=s.adaptiveBot[key];
        if(v&&typeof v==="object")Object.assign(adaptiveBot[key],v);
      });
      // restore per-session Apex W/L counters
      if(s.adaptiveBot.apexSessWL&&typeof s.adaptiveBot.apexSessWL==="object"){
        Object.keys(adaptiveBot.apexSessWL).forEach(k=>{
          const v=s.adaptiveBot.apexSessWL[k];
          if(v&&typeof v==="object"){adaptiveBot.apexSessWL[k]={w:v.w??0,l:v.l??0};}
        });
      }
      // restore lookback signal cache (may be stale; harmless — cleared on iv change)
      if(s.adaptiveBot._lastSig&&typeof s.adaptiveBot._lastSig==="object"){
        adaptiveBot._lastSig=Object.assign({},s.adaptiveBot._lastSig);
      }
      // restore preserved placeholder fields
      if("apexPaused"   in s.adaptiveBot)adaptiveBot.apexPaused   =s.adaptiveBot.apexPaused;
      if("consecLosses" in s.adaptiveBot)adaptiveBot.consecLosses =s.adaptiveBot.consecLosses;
      if("_lastDomId"   in s.adaptiveBot)adaptiveBot._lastDomId   =s.adaptiveBot._lastDomId;
    }

    if(s.processedTs) Object.assign(processedTs, s.processedTs);

    const age=Math.round((Date.now()-s.savedAt)/60000);
    addLog(`State restored from disk \u2014 saved ${age} min ago \u00b7 ${totalClosed} closed trades`,"save");
    renderLeft();renderAllTrades();renderRight();renderAdaptive();
  }catch(e){console.warn("restore failed:",e.message);}
}

restoreState();
setInterval(saveState, 30 * 60 * 1000);
// ══════════════════════════════════════════════════════════════
</script>
</body>
</html>"""


# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/candles":
            params = {}
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        params[k] = urllib.parse.unquote(v)
            code = params.get("code", "ES").upper()
            iv_  = params.get("iv", "5m")
            d    = get_ohlc(code, iv_)
            body = json.dumps(d).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/quote":
            d    = get_quotes()
            body = json.dumps(d).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        # ── AUTO-SAVE: read directly from disk ────────────────────────────────
        elif path == "/api/state/v6":
            data = _load_state_from_disk()
            if data:
                body = json.dumps(data).encode("utf-8")
                self.send_response(200)
            else:
                body = b"null"
                self.send_response(204)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        # ─────────────────────────────────────────────────────────────────────
        else:
            self.send_response(404)
            self.end_headers()

    # ── AUTO-SAVE: write directly to disk ─────────────────────────────────────
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/state/v6":
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                raw = self.rfile.read(length)
                try:
                    data = json.loads(raw.decode("utf-8"))
                    threading.Thread(
                        target=_save_state_to_disk, args=(data,), daemon=True
                    ).start()
                    self.send_response(200)
                except Exception as e:
                    _safe(f"  [--] State POST parse error: {e}")
                    self.send_response(400)
            else:
                self.send_response(400)
            self.send_header("Content-Length", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    # ─────────────────────────────────────────────────────────────────────────

    def log_message(self, *_): pass


def serve():
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


def _bg_warm():
    time.sleep(0.5)
    ok = 0
    for code in CODES:
        try:
            fetch_ohlc(code, "5m")
            ok += 1
        except RuntimeError as e:
            _safe(f"  [--] {code}: {e}")
    try:
        fetch_quotes_batch()
    except Exception:
        pass
    _safe(f"  {'[OK]' if ok else '[--]'} {ok}/8 Yahoo Finance feeds active")


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import subprocess
            subprocess.run(["chcp", "65001"], capture_output=True, shell=True)
        except Exception:
            pass
    _safe("")
    _safe("  FF ELITE BOTS v7  --  8 Markets  --  4 Index Pairs  --  Auto-Save")
    _safe("  =================================================================")
    _safe("  S&P 500  : ES  / MES   (E-mini & Micro)")
    _safe("  Nasdaq   : NQ  / MNQ   (E-mini & Micro)")
    _safe("  Dow Jones: YM  / MYM   (E-mini & Micro)")
    _safe("  Russell  : RTY / M2K   (E-mini & Micro)")
    _safe("")
    _safe("  Strategies : 34 session-aware bots (Asia/London/NY/Sydney) -- 25 standalone + 9 combo")
    _safe("  Data       : Yahoo Finance v8 OHLC + v7 quotes -> Stooq")
    _safe("")
    # ── AUTO-SAVE: report file status on startup ──────────────────────────────
    if os.path.exists(STATE_FILE):
        _safe(f"  [LOAD] Previous session found in {STATE_FILE} -- will restore on browser open")
    else:
        _safe(f"  [INFO] No saved state found -- starting fresh  (saves → {STATE_FILE})")
    _safe(f"  [INFO] Auto-save every {AUTOSAVE_EVERY//60} minutes via browser push → {STATE_FILE}")
    # ─────────────────────────────────────────────────────────────────────────
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            _safe(f"  Port {PORT} already in use -- close the old window first.")
            _safe("")
            sys.exit(1)
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.3)
    url = f"http://localhost:{PORT}"
    _safe(f"  Open   : {url}")
    _safe("  Stop   : Ctrl+C")
    _safe("")
    threading.Thread(target=_bg_warm, daemon=True).start()
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _safe("")
        _safe("  [INFO] State is persisted to disk on each auto-save interval.")
        _safe("")
        _safe("  Stopped.")
        sys.exit(0)