#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF ELITE BOTS v4
================
Zero external libraries.  Standard library only.

  Windows CMD:   python run.py
  Mac / Linux:   python3 run.py

DATA SOURCES (tried in order per symbol, first success wins):
  1. Yahoo Finance v8 API  query1  (direct HTTP, no key)
  2. Yahoo Finance v8 API  query2  (load-balanced mirror)
  3. Stooq intraday CSV           (free, no key)

All 4 contracts (ES / MES / NQ / MNQ) fetched independently.
No mirroring.  No simulation.  Standard library only.

PRICING:
  Entry  = snap(bar.close, 0.25 pt)  -- exact close of signal bar
  SL/TP  = entry +/- ATR(14) x mult, snapped to 0.25 pt
  Exit   = SL or TP triggered by real bar High / Low
  P&L    = (exit - entry) x ptVal    -- verify by hand
"""

# ── Windows CMD: force UTF-8 stdout so Unicode chars don't crash ──────────────
import sys, io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except AttributeError:
    pass   # already wrapped (e.g. pytest), ignore

import json, time, threading, webbrowser, http.server, urllib.parse
import urllib.request, urllib.error, csv, io as _io, datetime, gzip, socket

PORT = 7432

# ── Interval config ───────────────────────────────────────────────────────────
# key -> (yf_interval, yf_range, stooq_minutes)
IV_CFG = {
    "1m":  ("1m",  "1d",   "5"),
    "5m":  ("5m",  "5d",   "5"),
    "15m": ("15m", "60d",  "15"),
    "1H":  ("1h",  "180d", "60"),
}

# Contract -> data-source symbols
CONTRACTS = {
    "ES":  {"yf": "ES=F",  "stooq": "es.f"},
    "MES": {"yf": "MES=F", "stooq": "mes.f"},
    "NQ":  {"yf": "NQ=F",  "stooq": "nq.f"},
    "MNQ": {"yf": "MNQ=F", "stooq": "mnq.f"},
}

YF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://finance.yahoo.com/",
}


# ── helpers ───────────────────────────────────────────────────────────────────
def _safe_print(msg):
    """Print with Unicode error replacement so CMD never crashes."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def _http_get(url, headers, timeout=20):
    """GET url, return raw bytes or raise.  Handles gzip transparently."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass
    return raw


def _parse_yf_json(raw, yf_sym):
    """Parse raw Yahoo Finance v8 JSON bytes -> list of OHLC dicts."""
    data   = json.loads(raw)
    result = data["chart"]["result"][0]
    ts     = result["timestamp"]
    q      = result["indicators"]["quote"][0]
    opens, highs, lows, closes = q["open"], q["high"], q["low"], q["close"]
    rows = []
    for i, t in enumerate(ts):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        if any(v is None or (v != v) for v in (o, h, l, c)):
            continue
        rows.append({"t": int(t) * 1000,
                     "o": round(o, 2), "h": round(h, 2),
                     "l": round(l, 2), "c": round(c, 2)})
    if not rows:
        raise ValueError("all rows were NaN")
    # patch last bar with regularMarketPrice if present
    try:
        rt = float(result["meta"].get("regularMarketPrice") or 0)
        if rt > 0:
            rows[-1]["c"] = round(rt, 2)
            if rt > rows[-1]["h"]: rows[-1]["h"] = round(rt, 2)
            if rt < rows[-1]["l"]: rows[-1]["l"] = round(rt, 2)
    except Exception:
        pass
    return rows


# ── Source 1 & 2: Yahoo Finance v8 (query1 then query2) ──────────────────────
def _fetch_yf(yf_sym, yf_interval, yf_range, host="query1"):
    url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(yf_sym)}"
           f"?interval={yf_interval}&range={yf_range}"
           f"&includePrePost=false&corsDomain=finance.yahoo.com")
    raw  = _http_get(url, YF_HEADERS)
    rows = _parse_yf_json(raw, yf_sym)
    return rows


# ── Source 3: Stooq intraday CSV ──────────────────────────────────────────────
def _fetch_stooq(stooq_sym, stooq_minutes):
    url = (f"https://stooq.com/q/d/l/?s={urllib.parse.quote(stooq_sym)}"
           f"&i={stooq_minutes}")
    raw  = _http_get(url, {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
    text = raw.decode("utf-8", errors="replace")
    rows = []
    reader = csv.DictReader(_io.StringIO(text))
    for row in reader:
        try:
            date_s = row.get("Date", "").strip()
            time_s = row.get("Time", "000000").strip()
            if not date_s or date_s.lower() in ("date", "no data", ""):
                continue
            dt_str = f"{date_s} {time_s[:2]}:{time_s[2:4]}:{time_s[4:6]}"
            try:
                dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt = datetime.datetime.strptime(date_s, "%Y-%m-%d")
            o = float(row.get("Open",  0) or 0)
            h = float(row.get("High",  0) or 0)
            l = float(row.get("Low",   0) or 0)
            c = float(row.get("Close", 0) or 0)
            if o == 0 and c == 0:
                continue
            rows.append({"t": int(dt.timestamp() * 1000),
                         "o": round(o,2), "h": round(h,2),
                         "l": round(l,2), "c": round(c,2)})
        except (ValueError, KeyError, TypeError):
            continue
    if not rows:
        raise ValueError("no valid rows")
    rows.sort(key=lambda r: r["t"])
    return rows


# ── Main fetch: 3 sources, first success wins ─────────────────────────────────
def fetch_candles(code, iv):
    """
    Returns (rows, source_label) or raises RuntimeError if all 3 sources fail.
    """
    cfg      = IV_CFG.get(iv, IV_CFG["5m"])
    yf_int   = cfg[0]
    yf_range = cfg[1]
    stooq_m  = cfg[2]
    yf_sym   = CONTRACTS[code]["yf"]
    stooq_s  = CONTRACTS[code]["stooq"]

    errors = []

    # 1. Yahoo Finance v8 query1
    try:
        rows = _fetch_yf(yf_sym, yf_int, yf_range, host="query1")
        _safe_print(f"  [OK] {code:4s}  YF/query1  {len(rows):4d} bars  last={rows[-1]['c']}")
        return rows, "Yahoo Finance"
    except Exception as e:
        errors.append(f"YF/q1: {e}")

    # 2. Yahoo Finance v8 query2  (load-balanced mirror)
    try:
        rows = _fetch_yf(yf_sym, yf_int, yf_range, host="query2")
        _safe_print(f"  [OK] {code:4s}  YF/query2  {len(rows):4d} bars  last={rows[-1]['c']}")
        return rows, "Yahoo Finance (q2)"
    except Exception as e:
        errors.append(f"YF/q2: {e}")

    # 3. Stooq CSV
    try:
        rows = _fetch_stooq(stooq_s, stooq_m)
        _safe_print(f"  [OK] {code:4s}  Stooq      {len(rows):4d} bars  last={rows[-1]['c']}")
        return rows, "Stooq"
    except Exception as e:
        errors.append(f"Stooq: {e}")

    raise RuntimeError(" | ".join(errors))


# ── Server-side cache (20 s TTL) ──────────────────────────────────────────────
_cache = {}
_lock  = threading.Lock()
TTL    = 20

def get_candles(code, iv):
    key = f"{code}|{iv}"
    with _lock:
        e = _cache.get(key)
        if e and time.time() - e["ts"] < TTL:
            return e["data"]
    try:
        rows, source = fetch_candles(code, iv)
        out = {"live": True,  "candles": rows, "source": source}
    except RuntimeError as err:
        _safe_print(f"  [--] {code}: all sources failed ({err})")
        out = {"live": False, "candles": [], "source": "unavailable"}
    with _lock:
        _cache[key] = {"data": out, "ts": time.time()}
    return out


# =============================================================================
#  HTML + JAVASCRIPT  (all inline, zero external dependencies beyond fonts)
# =============================================================================
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FF Elite Bots v4</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@700;900&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#030310;--p1:#06061c;--p2:#09091f;--p3:#0c0c26;
  --b1:#141438;--b2:#1c1c44;
  --tx:#b8cce0;--tx2:#687898;--tx3:#304060;--tx4:#1e2848;
  --cy:#18d8f0;--pu:#8080ff;--or:#f09030;--pk:#f060c0;
  --g:#18c860;--r:#f03050;--yw:#f0c020;--bl:#5090ff;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--tx);
  font-family:'Share Tech Mono',monospace;font-size:11px}
#app{display:flex;flex-direction:column;height:100vh;overflow:hidden}

/* TOP */
#top{display:flex;align-items:center;height:36px;flex-shrink:0;padding:0 10px;
  background:var(--p1);border-bottom:2px solid var(--b2)}
#logo{font-family:'Orbitron',sans-serif;font-size:13px;font-weight:900;color:var(--cy);
  letter-spacing:3px;padding-right:10px;border-right:1px solid var(--b1);margin-right:8px;
  white-space:nowrap}
#ltag{padding:1px 8px;border-radius:2px;font-size:8px;font-weight:bold;letter-spacing:1px;
  background:var(--p2);color:var(--tx3);border:1px solid var(--b1);margin-right:8px;transition:all .4s}
#ltag.live{background:#04200e;color:var(--g);border-color:#18c86040}
#ltag.closed{background:#100830;color:var(--pu);border-color:#8080ff40}
.ivg{display:flex;gap:3px;margin-right:8px;padding-right:8px;border-right:1px solid var(--b1)}
.ivb{padding:2px 9px;border:1px solid var(--b2);border-radius:2px;background:transparent;
  color:var(--tx3);cursor:pointer;font-family:'Share Tech Mono',monospace;font-size:10px;transition:all .15s}
.ivb:hover{border-color:var(--cy);color:var(--cy)}
.ivb.on{background:var(--cy);color:#000;border-color:var(--cy);font-weight:bold}
.ts{color:var(--tx3);font-size:9px;margin-right:8px;white-space:nowrap}.ts b{color:var(--tx)}
.sp{flex:1}
.prices{display:flex;gap:12px;padding-left:10px;border-left:1px solid var(--b1)}
.px{font-size:10px;display:flex;align-items:baseline;gap:3px}
.px .sym{font-size:8px}
#tu{font-size:9px;color:var(--tx3);margin-left:8px}

/* BODY */
#body{display:flex;flex:1;overflow:hidden;min-height:0}

/* LEFT */
#left{width:232px;min-width:232px;flex-shrink:0;background:var(--p1);
  border-right:1px solid var(--b2);display:flex;flex-direction:column;overflow:hidden}
.ph{font-family:'Orbitron',sans-serif;font-size:8px;font-weight:700;letter-spacing:2px;
  color:var(--cy);padding:4px 9px;border-bottom:1px solid var(--b1);background:var(--p2);
  flex-shrink:0;text-transform:uppercase}
.card{padding:8px 9px;border-bottom:1px solid var(--b2)}
.r2{display:flex;justify-content:space-between;align-items:center;padding:1px 0;font-size:9px}
.r2 .k{color:var(--tx3)}
#bname{font-family:'Orbitron',sans-serif;font-size:11px;font-weight:700;color:#dce8ff;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:2px}
#btype{color:var(--tx3);font-size:8px;margin-bottom:4px}
svg#spark{display:block;width:100%;height:26px;margin-top:5px;overflow:hidden}
#openbox{flex-shrink:0;overflow-y:auto;max-height:120px;border-bottom:1px solid var(--b2)}
.ti{padding:4px 9px;border-bottom:1px solid var(--b1);font-size:9px}
#histbox{flex-shrink:0;overflow-y:auto;max-height:108px;border-bottom:1px solid var(--b2)}
.hi{display:flex;justify-content:space-between;padding:2px 9px;font-size:8.5px;
  border-bottom:1px solid var(--b1)}
#stratbox{flex:1;overflow-y:auto;padding:7px 9px;font-size:9px;line-height:1.8}

/* CENTER */
#center{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
#cgrid{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;
  flex:1;gap:2px;padding:2px;background:var(--bg);min-height:0;overflow:hidden}
.cc{background:var(--p2);border:1px solid var(--b1);border-radius:3px;
  display:flex;flex-direction:column;overflow:hidden;min-height:0}
.ch{display:flex;justify-content:space-between;align-items:center;
  padding:3px 8px;border-bottom:1px solid var(--b1);flex-shrink:0;height:26px}
.csym{font-family:'Orbitron',sans-serif;font-size:10px;font-weight:700}
.cpx{font-family:'Orbitron',sans-serif;font-size:11px;font-weight:700}
.cw{flex:1;position:relative;overflow:hidden;min-height:0}
.cw canvas{display:block;position:absolute;top:0;left:0}
.sb{flex-shrink:0;border-top:1px solid var(--b1);padding:2px 6px;
  min-height:18px;display:flex;gap:4px;flex-wrap:wrap;align-items:center;background:var(--bg)}
.chip{padding:1px 6px;border-radius:2px;font-size:8px}
.cl{background:#04200e30;color:var(--g);border:1px solid #18c86020}
.cs{background:#20040a30;color:var(--r);border:1px solid #f0305020}
#tradepane{height:148px;flex-shrink:0;display:flex;flex-direction:column;border-top:2px solid var(--b2)}
.tscroll{flex:1;overflow-y:auto}

/* RIGHT */
#right{width:212px;min-width:212px;flex-shrink:0;background:var(--p1);
  border-left:1px solid var(--b2);display:flex;flex-direction:column;overflow:hidden}
#blist{flex:1;overflow-y:auto}
.brow{display:flex;align-items:center;gap:4px;padding:2px 7px;
  border-bottom:1px solid var(--b1);font-size:9px}
.brow.dead{opacity:.22}
.bdot{width:5px;height:5px;border-radius:50%;flex-shrink:0}
.bbar{flex:1;height:3px;background:var(--b1);border-radius:2px}
.bfill{height:100%;border-radius:2px;transition:width .7s}
.rsect{flex-shrink:0;padding:6px 9px;border-top:1px solid var(--b2);
  font-size:8.5px;line-height:2;color:var(--tx3)}

/* LOG */
#log{height:36px;flex-shrink:0;background:#02020a;border-top:1px solid var(--b2);
  overflow-x:auto;overflow-y:hidden;display:flex;align-items:center;
  padding:0 6px;gap:4px;white-space:nowrap}
.lc{display:inline-flex;align-items:center;padding:1px 7px;border-radius:2px;
  font-size:8px;border:1px solid var(--b1);flex-shrink:0}
.lc.win{background:#04200e;color:var(--g);border-color:#18c86020}
.lc.loss{background:#20040a;color:var(--r);border-color:#f0305020}
.lc.kill{background:#200404;color:#f07878;border-color:#f0305030}
.lc.wave{background:#080828;color:var(--pu);border-color:#8080ff20}
.lc.info{background:var(--p2);color:var(--tx3)}
table.mt{width:100%;border-collapse:collapse}
table.mt th{font-size:7px;color:var(--tx3);padding:2px 5px;border-bottom:1px solid var(--b2);
  position:sticky;top:0;background:var(--p3);white-space:nowrap;text-align:left}
table.mt td{font-size:8.5px;padding:2px 5px;border-bottom:1px solid var(--b1);white-space:nowrap}
table.mt tr:hover td{background:var(--p2)}
::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--b2)}
</style>
</head>
<body>
<div id="app">

<div id="top">
  <div id="logo">FF ELITE BOTS</div>
  <div id="ltag">LOADING</div>
  <div class="ivg">
    <button class="ivb" data-iv="1m">1m</button>
    <button class="ivb on" data-iv="5m">5m</button>
    <button class="ivb" data-iv="15m">15m</button>
    <button class="ivb" data-iv="1H">1H</button>
  </div>
  <span class="ts">Active:<b id="ta">10</b></span>
  <span class="ts">Wave:<b id="tw" style="color:var(--pu)">1</b></span>
  <span class="ts">Closed:<b id="tcl" style="color:var(--g)">0</b></span>
  <span class="ts">Bars:<b id="tbars" style="color:var(--tx2)">--</b></span>
  <div class="sp"></div>
  <div class="prices">
    <span class="px"><span class="sym" style="color:var(--cy)">ES</span><b id="pES" style="color:var(--cy)">--</b></span>
    <span class="px"><span class="sym" style="color:var(--pu)">MES</span><b id="pMES" style="color:var(--pu)">--</b></span>
    <span class="px"><span class="sym" style="color:var(--or)">NQ</span><b id="pNQ" style="color:var(--or)">--</b></span>
    <span class="px"><span class="sym" style="color:var(--pk)">MNQ</span><b id="pMNQ" style="color:var(--pk)">--</b></span>
  </div>
  <div id="tu">--</div>
</div>

<div id="body">
  <div id="left">
    <div class="ph">Best Bot  (WR x50% + PnL x50%)</div>
    <div class="card">
      <div id="bname">Waiting for live data...</div>
      <div id="btype">--</div>
      <div class="r2"><span class="k">Balance</span><b id="bbal">$50,000.00</b></div>
      <div class="r2"><span class="k">Net P&amp;L</span><b id="bpnl">+$0.00</b></div>
      <div class="r2"><span class="k">Win Rate</span><b id="bwr" style="color:var(--cy)">0.0%</b></div>
      <div class="r2"><span class="k">W / L / Total</span><b id="bwl" style="color:var(--tx2)">0/0/0</b></div>
      <div class="r2"><span class="k">Score</span><b id="bsc" style="color:var(--yw)">--</b></div>
      <svg id="spark" viewBox="0 0 200 26" preserveAspectRatio="none"></svg>
    </div>
    <div class="ph">Open Positions</div>
    <div id="openbox"><div style="padding:5px 9px;color:var(--tx3)">No open trades</div></div>
    <div class="ph">Last 8 Closed</div>
    <div id="histbox"><div style="padding:5px 9px;color:var(--tx3)">No trades yet</div></div>
    <div class="ph">Strategy</div>
    <div id="stratbox"><span style="color:var(--tx3)">--</span></div>
  </div>

  <div id="center">
    <div id="cgrid"></div>
    <div id="tradepane">
      <div class="ph" style="font-size:7.5px">ALL BOTS -- CLOSED TRADES
        <span style="font-size:7px;color:var(--tx3);font-family:'Share Tech Mono',monospace;
          letter-spacing:0;text-transform:none;font-weight:normal;margin-left:8px">
          Entry and exit = exact candle close &middot; P&amp;L = (exit-entry) x ptVal
        </span>
      </div>
      <div class="tscroll">
        <table class="mt">
          <thead><tr>
            <th>MKT</th><th>BOT</th><th>DIR</th>
            <th>ENTRY</th><th>EXIT</th><th>PTS</th><th>P&amp;L $</th><th>RES</th>
          </tr></thead>
          <tbody id="atbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <div id="right">
    <div class="ph">Leaderboard</div>
    <div id="blist"></div>
    <div class="ph" style="border-top:1px solid var(--b2)">Data Sources</div>
    <div id="srcsect" class="rsect"></div>
    <div class="ph" style="border-top:1px solid var(--b2)">Correlation</div>
    <div id="corrsect" class="rsect"></div>
    <div class="ph" style="border-top:1px solid var(--b2)">Contract Specs</div>
    <div class="rsect">
      <span style="color:var(--cy)">ES </span>$50/pt &middot; $12.50/tick<br>
      <span style="color:var(--pu)">MES</span> $5/pt  &middot; $1.25/tick<br>
      <span style="color:var(--or)">NQ </span>$20/pt &middot; $5.00/tick<br>
      <span style="color:var(--pk)">MNQ</span> $2/pt  &middot; $0.50/tick<br>
      <span style="color:var(--tx4)">0.25pt tick &middot; all independent data</span>
    </div>
    <div class="ph" style="border-top:1px solid var(--b2)">Kill / Wave</div>
    <div class="rsect">
      Balance &lt; $48k -- killed<br>
      WR &lt; 25% after 20 trades -- killed<br>
      5 or fewer active -- +10 bots spawned
    </div>
  </div>
</div>

<div id="log">
  <span class="lc info">FF Elite Bots v4 -- authentic paper trading -- Yahoo Finance / Stooq -- all 4 contracts independent</span>
</div>
</div>

<script>
/* ================================================================
   FF ELITE BOTS v4
   All 4 contracts fully independent -- no mirroring.
   Data: Python fetches Yahoo Finance v8 (query1 -> query2) -> Stooq.
   Charts: ResizeObserver + DPR scaling + gap-based candle X.
   Element IDs: cv-ES, cv-MES, cv-NQ, cv-MNQ (no = in IDs).
================================================================ */

const MKTS = [
  {id:"ES",  code:"ES",  name:"E-Mini S&P 500",   ptVal:50, tick:0.25, col:"#18d8f0"},
  {id:"MES", code:"MES", name:"Micro E-Mini S&P",  ptVal:5,  tick:0.25, col:"#8080ff"},
  {id:"NQ",  code:"NQ",  name:"E-Mini Nasdaq-100", ptVal:20, tick:0.25, col:"#f09030"},
  {id:"MNQ", code:"MNQ", name:"Micro E-Mini NQ",   ptVal:2,  tick:0.25, col:"#f060c0"},
];

const snap = p => Math.round(p * 4) / 4;

let candles      = {};
let sources      = {};
let processedIdx = {};
let iv           = "5m";
let isLive       = false;
let wave = 1, uid = 0, totalClosed = 0;
let bots = [], allClosed = [], logEvents = [];
let startupDone  = false;

const bars = code => candles[code] ?? [];

// ── Indicators ──────────────────────────────────────────────────
function ema(arr, p) {
  if (!arr || arr.length < p) return (arr||[]).map(()=>null);
  const k = 2/(p+1), out = Array(arr.length).fill(null);
  out[p-1] = arr.slice(0,p).reduce((a,b)=>a+b,0)/p;
  for (let i=p;i<arr.length;i++) out[i]=arr[i]*k+out[i-1]*(1-k);
  return out;
}
function sma(arr,p){
  return arr.map((_,i)=>i<p-1?null:arr.slice(i-p+1,i+1).reduce((a,b)=>a+b,0)/p);
}
function atrArr(bs,p=14){
  if(!bs?.length)return[];
  const tr=bs.map((c,i)=>i===0?c.h-c.l:
    Math.max(c.h-c.l,Math.abs(c.h-bs[i-1].c),Math.abs(c.l-bs[i-1].c)));
  return tr.map((_,i)=>i<p?null:tr.slice(i-p+1,i+1).reduce((a,b)=>a+b)/p);
}
function rsiArr(c,p=14){
  const r=Array(c.length).fill(null);
  if(c.length<p+1)return r;
  let g=0,l=0;
  for(let i=1;i<=p;i++){const d=c[i]-c[i-1];d>0?g+=d:l-=d;}
  let ag=g/p,al=l/p;
  r[p]=100-100/(1+ag/Math.max(al,1e-10));
  for(let i=p+1;i<c.length;i++){
    const d=c[i]-c[i-1];
    ag=(ag*(p-1)+(d>0?d:0))/p;al=(al*(p-1)+(d<0?-d:0))/p;
    r[i]=100-100/(1+ag/Math.max(al,1e-10));
  }
  return r;
}
function macdArr(c){
  const f=ema(c,12),s=ema(c,26);
  const line=c.map((_,i)=>f[i]!=null&&s[i]!=null?f[i]-s[i]:null);
  const vals=line.filter(v=>v!=null),sigR=ema(vals,9);let si=0;
  const sig=line.map(v=>v==null?null:(sigR[si++]??null));
  return{hist:line.map((v,i)=>v!=null&&sig[i]!=null?v-sig[i]:null)};
}
function bbArr(c,p=20,m=2){
  const sm=sma(c,p);
  return c.map((_,i)=>{
    if(sm[i]==null)return{u:null,l:null};
    const sl=c.slice(i-p+1,i+1),mn=sm[i];
    const std=Math.sqrt(sl.reduce((a,v)=>a+(v-mn)**2,0)/p);
    return{u:mn+m*std,l:mn-m*std};
  });
}
function stochArr(bs,p=9){
  return bs.map((_,i)=>{
    if(i<p-1)return null;
    const sl=bs.slice(i-p+1,i+1);
    const hi=Math.max(...sl.map(c=>c.h)),lo=Math.min(...sl.map(c=>c.l));
    return hi===lo?50:((bs[i].c-lo)/(hi-lo))*100;
  });
}
function cciArr(bs,p=14){
  return bs.map((_,i)=>{
    if(i<p-1)return null;
    const sl=bs.slice(i-p+1,i+1),tp=sl.map(c=>(c.h+c.l+c.c)/3);
    const mn=tp.reduce((a,b)=>a+b)/p,md=tp.reduce((a,v)=>a+Math.abs(v-mn),0)/p;
    return md?((bs[i].h+bs[i].l+bs[i].c)/3-mn)/(0.015*md):0;
  });
}

// ── Strategies ───────────────────────────────────────────────────
const STRATS = [
  {id:"TrendFollow_A",name:"TrendFollow A",type:"EMA 21/55 Cross",rr:3.0,atrMult:1.5,
   desc:"Long on EMA21 cross above EMA55. Short on cross below. 3:1 R:R.",
   signal(bs){
     if(bs.length<62)return null;
     const c=bs.map(x=>x.c),n=c.length-1,f=ema(c,21),s=ema(c,55);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";
     if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;
   }},
  {id:"Stoch_Master",name:"Stoch Master",type:"Stoch %K(9) 20/80",rr:1.5,atrMult:1.2,
   desc:"Long on %K cross above 20. Short on cross below 80. Fast cyclic reversal.",
   signal(bs){
     if(bs.length<15)return null;
     const k=stochArr(bs,9),n=k.length-1;
     if(k[n]==null||k[n-1]==null)return null;
     if(k[n-1]<=20&&k[n]>20)return"long";
     if(k[n-1]>=80&&k[n]<80)return"short";
     return null;
   }},
  {id:"FF_Top_Trader",name:"FF Top Trader",type:"EMA 8/34 Cross",rr:2.5,atrMult:1.5,
   desc:"EMA8/EMA34 golden/death cross. Higher frequency than 21/55.",
   signal(bs){
     if(bs.length<40)return null;
     const c=bs.map(x=>x.c),n=c.length-1,f=ema(c,8),s=ema(c,34);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";
     if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;
   }},
  {id:"GoldPatrol99",name:"Gold Patrol 99",type:"ROC(5) +/-0.25% Cross",rr:1.5,atrMult:1.2,
   desc:"Long when 5-bar ROC crosses above +0.25%. Short below -0.25%.",
   signal(bs){
     if(bs.length<12)return null;
     const c=bs.map(x=>x.c),n=c.length-1;
     if(!c[n-5]||!c[n-6])return null;
     const r=(c[n]-c[n-5])/c[n-5]*100,rp=(c[n-1]-c[n-6])/c[n-6]*100;
     if(rp<0.25&&r>=0.25)return"long";if(rp>-0.25&&r<=-0.25)return"short";
     return null;
   }},
  {id:"VelocityTrader",name:"Velocity Trader",type:"ROC(10) +/-0.4% Cross",rr:2.0,atrMult:1.5,
   desc:"Long when 10-bar ROC crosses above +0.4%. Balanced scalp/trend.",
   signal(bs){
     if(bs.length<15)return null;
     const c=bs.map(x=>x.c),n=c.length-1;
     if(!c[n-10]||!c[n-11])return null;
     const r=(c[n]-c[n-10])/c[n-10]*100,rp=(c[n-1]-c[n-11])/c[n-11]*100;
     if(rp<0.4&&r>=0.4)return"long";if(rp>-0.4&&r<=-0.4)return"short";
     return null;
   }},
  {id:"BollingerBreak",name:"Bollinger Break",type:"BB(20,2) Outside Band",rr:2.5,atrMult:1.5,
   desc:"Long on close above upper BB. Short below lower BB. Volatility expansion.",
   signal(bs){
     if(bs.length<25)return null;
     const c=bs.map(x=>x.c),b=bbArr(c,20,2),n=c.length-1;
     if(!b[n].u||!b[n-1].u)return null;
     if(c[n-1]<=b[n-1].u&&c[n]>b[n].u)return"long";
     if(c[n-1]>=b[n-1].l&&c[n]<b[n].l)return"short";
     return null;
   }},
  {id:"MACD_Wave",name:"MACD Wave",type:"MACD(12,26,9) Hist Zero",rr:2.0,atrMult:1.5,
   desc:"Long on MACD histogram cross above zero. Short on cross below.",
   signal(bs){
     if(bs.length<35)return null;
     const c=bs.map(x=>x.c),{hist}=macdArr(c),n=hist.length-1;
     if(hist[n]==null||hist[n-1]==null)return null;
     if(hist[n-1]<=0&&hist[n]>0)return"long";
     if(hist[n-1]>=0&&hist[n]<0)return"short";
     return null;
   }},
  {id:"ATR_Channel",name:"ATR Channel",type:"SMA20 +/- 2xATR(14)",rr:2.5,atrMult:1.5,
   desc:"Long on break above SMA20+2xATR. Short below SMA20-2xATR.",
   signal(bs){
     if(bs.length<30)return null;
     const c=bs.map(x=>x.c),at=atrArr(bs,14),sm=sma(c,20),n=c.length-1;
     if(!at[n]||!sm[n]||!at[n-1]||!sm[n-1])return null;
     if(c[n-1]<=sm[n-1]+2*at[n-1]&&c[n]>sm[n]+2*at[n])return"long";
     if(c[n-1]>=sm[n-1]-2*at[n-1]&&c[n]<sm[n]-2*at[n])return"short";
     return null;
   }},
  {id:"CCI_Reversal",name:"CCI Reversal",type:"CCI(14) Cross +/-100",rr:2.0,atrMult:1.2,
   desc:"Long on CCI cross above -100. Short on cross below +100. Mean reversion.",
   signal(bs){
     if(bs.length<20)return null;
     const ci=cciArr(bs,14),n=ci.length-1;
     if(ci[n]==null||ci[n-1]==null)return null;
     if(ci[n-1]<=-100&&ci[n]>-100)return"long";
     if(ci[n-1]>=100&&ci[n]<100)return"short";
     return null;
   }},
  {id:"RSI_Momentum",name:"RSI Momentum",type:"RSI(14) Cross 30/70",rr:2.0,atrMult:1.2,
   desc:"Long on RSI cross above 30. Short on cross below 70.",
   signal(bs){
     if(bs.length<20)return null;
     const c=bs.map(x=>x.c),ri=rsiArr(c,14),n=ri.length-1;
     if(ri[n]==null||ri[n-1]==null)return null;
     if(ri[n-1]<=30&&ri[n]>30)return"long";
     if(ri[n-1]>=70&&ri[n]<70)return"short";
     return null;
   }},
];

// ── Bot factory ───────────────────────────────────────────────────
function mkBot(strat,wv){
  return{uid:++uid,name:`${strat.name} W${wv}`,strat,wave:wv,
    balance:50000,openTrades:{},closedTrades:[],wins:0,losses:0,killed:false,killReason:""};
}
bots = STRATS.map(s=>mkBot(s,1));

const getPnl = b => b.balance-50000;
const getWR  = b => {const t=b.wins+b.losses;return t?b.wins/t:0;};
function score(b,all){
  const ps=all.map(x=>getPnl(x));
  const mn=Math.min(...ps),mx=Math.max(...ps),rng=mx-mn||1;
  return getWR(b)*0.5+((getPnl(b)-mn)/rng)*0.5;
}
const live    = ()=>bots.filter(b=>!b.killed);
const bestBot = ()=>{const ab=live();return ab.length?ab.reduce((b,x)=>score(x,ab)>score(b,ab)?x:b,ab[0]):null;};

// ── Bot engine ────────────────────────────────────────────────────
function processBots(){
  if(!startupDone)return;
  MKTS.forEach(mkt=>{
    const bs=bars(mkt.code);
    if(!bs||bs.length<35)return;
    const atr=atrArr(bs,14);
    const startI=(processedIdx[mkt.code]??bs.length-2)+1;
    const endI  =bs.length-2;
    if(startI>endI)return;
    for(let i=startI;i<=endI;i++){
      const bar=bs[i];
      bots.forEach(bot=>{
        if(bot.killed)return;
        const trade=bot.openTrades[mkt.code];
        if(trade){
          let closed=false,exitPx=0,won=false;
          if(trade.dir==="long"){
            if(bar.h>=trade.tp&&bar.l<=trade.sl){exitPx=trade.sl;closed=true;won=false;}
            else if(bar.h>=trade.tp){exitPx=trade.tp;closed=true;won=true;}
            else if(bar.l<=trade.sl){exitPx=trade.sl;closed=true;won=false;}
          }else{
            if(bar.l<=trade.tp&&bar.h>=trade.sl){exitPx=trade.sl;closed=true;won=false;}
            else if(bar.l<=trade.tp){exitPx=trade.tp;closed=true;won=true;}
            else if(bar.h>=trade.sl){exitPx=trade.sl;closed=true;won=false;}
          }
          if(closed){
            exitPx=snap(exitPx);
            const pts=trade.dir==="long"?exitPx-trade.entry:trade.entry-exitPx;
            const pnlUSD=Math.round(pts*mkt.ptVal*100)/100;
            bot.balance=Math.round((bot.balance+pnlUSD)*100)/100;
            won?bot.wins++:bot.losses++;totalClosed++;
            const rec={code:mkt.code,col:mkt.col,botName:bot.name,dir:trade.dir,
              entry:trade.entry,exitPx,pts:Math.round(pts*100)/100,pnlUSD,won,
              sl:trade.sl,tp:trade.tp,openT:trade.openT,closeT:bar.t,atr:trade.atr};
            bot.closedTrades=[...bot.closedTrades.slice(-49),rec];
            allClosed=[rec,...allClosed].slice(0,60);
            delete bot.openTrades[mkt.code];
            document.getElementById("tcl").textContent=totalClosed;
            addLog(`${mkt.code} ${bot.name} ${won?"WIN":"LOSS"} ${f$(pnlUSD)} (${fPts(pts)})`,won?"win":"loss");
          }
        }else{
          const sig=bot.strat.signal(bs.slice(0,i+1));
          if(sig&&atr[i]!=null){
            const entry=snap(bar.c);
            const dist=snap(Math.max(atr[i]*bot.strat.atrMult,2*mkt.tick));
            const sl=snap(sig==="long"?entry-dist:entry+dist);
            const tp=snap(sig==="long"?entry+dist*bot.strat.rr:entry-dist*bot.strat.rr);
            bot.openTrades[mkt.code]={dir:sig,entry,sl,tp,openT:bar.t,atr:atr[i]};
          }
        }
      });
      processedIdx[mkt.code]=i;
    }
    bots.forEach(bot=>{
      if(bot.killed)return;
      if(bot.balance<48000){bot.killed=true;bot.killReason="Bal<$48k";bot.openTrades={};
        addLog(`${bot.name} KILLED -- balance below $48k`,"kill");}
      const tot=bot.wins+bot.losses;
      if(tot>=20&&bot.wins/tot<0.25){bot.killed=true;bot.killReason="WR<25%";bot.openTrades={};
        addLog(`${bot.name} KILLED -- WR<25% after ${tot} trades`,"kill");}
    });
  });
  if(live().length<=5){
    wave++;bots=[...bots,...STRATS.map(s=>mkBot(s,wave))];
    document.getElementById("tw").textContent=wave;
    addLog(`Wave ${wave} spawned -- 10 new bots`,"wave");
  }
  document.getElementById("ta").textContent=live().length;
}

// ── Fetch from Python backend ─────────────────────────────────────
async function loadAll(){
  const tag=document.getElementById("ltag");
  tag.textContent="FETCHING";tag.className="";
  let liveN=0;
  await Promise.allSettled(MKTS.map(async mkt=>{
    try{
      const r=await fetch(`/api/candles?code=${mkt.code}&iv=${iv}`,
                          {signal:AbortSignal.timeout(30000)});
      const d=await r.json();
      if(d.live&&d.candles?.length>10){
        candles[mkt.code]=d.candles;sources[mkt.code]=d.source||"?";liveN++;
      }
    }catch(e){console.warn(mkt.code,e.message);}
  }));
  isLive=liveN>0;
  tag.textContent=isLive?`LIVE (${liveN}/4)`:Object.keys(candles).length?"STALE":"CLOSED";
  tag.className=isLive?"live":!Object.keys(candles).length?"closed":"";
  document.getElementById("tu").textContent=new Date().toLocaleTimeString();
  document.getElementById("tbars").textContent=candles["ES"]?.length||"--";
  MKTS.forEach(m=>{
    const last=bars(m.code).at(-1)?.c;
    if(last!=null){const el=document.getElementById("p"+m.id);if(el)el.textContent=last.toFixed(2);}
  });
  if(!startupDone&&isLive){
    MKTS.forEach(m=>{const bs=bars(m.code);if(bs?.length)processedIdx[m.code]=bs.length-2;});
    startupDone=true;
    addLog("Live data loaded -- bots watching for signals on new completed bars","info");
  }
}

// ── Chart renderer ────────────────────────────────────────────────
const cvMap={};
function buildGrid(){
  document.getElementById("cgrid").innerHTML=MKTS.map(m=>`
    <div class="cc">
      <div class="ch">
        <div style="display:flex;align-items:baseline;gap:6px">
          <span class="csym" style="color:${m.col}">${m.code}</span>
          <span style="font-size:8px;color:var(--tx3)">${m.name} &middot; $${m.ptVal}/pt</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <span style="font-size:8px;color:var(--tx3)">
            <span style="color:#f0c020">-</span>E9
            <span style="color:#5090ff">-</span>E21
          </span>
          <span class="cpx" id="cpx-${m.id}" style="color:${m.col}">--</span>
        </div>
      </div>
      <div class="cw" id="cw-${m.id}"><canvas id="cv-${m.id}"></canvas></div>
      <div class="sb" id="sb-${m.id}">
        <span style="color:var(--tx4);font-size:8px">watching for signal...</span>
      </div>
    </div>`).join("");
  MKTS.forEach(m=>{
    cvMap[m.id]=document.getElementById("cv-"+m.id);
    new ResizeObserver(()=>drawChart(m)).observe(document.getElementById("cw-"+m.id));
  });
}

function drawChart(mkt){
  const cv=cvMap[mkt.id];if(!cv)return;
  const wrap=document.getElementById("cw-"+mkt.id);if(!wrap)return;
  const dpr=window.devicePixelRatio||1;
  const W=wrap.clientWidth,H=wrap.clientHeight;
  if(W<20||H<20)return;
  cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);
  cv.style.width=W+"px";cv.style.height=H+"px";
  const ctx=cv.getContext("2d");
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle="#030310";ctx.fillRect(0,0,W,H);

  const bs=bars(mkt.code);
  if(!bs?.length){
    ctx.fillStyle="#1a1a40";ctx.font="10px 'Share Tech Mono'";ctx.textAlign="center";
    ctx.fillText("Fetching "+mkt.code+" data...",W/2,H/2-8);
    ctx.fillStyle="#101030";ctx.font="8px 'Share Tech Mono'";
    ctx.fillText(sources[mkt.code]?"source: "+sources[mkt.code]:"trying Yahoo Finance then Stooq...",W/2,H/2+8);
    return;
  }

  const PL=4,PR=65,PT=8,PB=19;
  const CW=W-PL-PR,CH=H-PT-PB;
  const maxC=Math.max(14,Math.floor(CW/8));
  const vis=bs.slice(-maxC),n=vis.length;
  if(n<2)return;

  /* gap-based X -- candle i occupies slot [i*gap, (i+1)*gap], centre = i*gap+gap/2 */
  const gap=CW/n,bw=Math.max(2,gap*0.68);
  const toX=i=>PL+i*gap+gap/2;

  let hiP=Math.max(...vis.map(c=>c.h)),loP=Math.min(...vis.map(c=>c.l));
  const pad=(hiP-loP)*0.04||hiP*0.001;hiP+=pad;loP-=pad;
  const rng=hiP-loP||1;
  const toY=p=>PT+CH*(1-(p-loP)/rng);

  /* grid */
  ctx.font="7px 'Share Tech Mono'";ctx.textAlign="left";
  for(let gi=0;gi<=4;gi++){
    const pv=hiP-(rng/4)*gi,y=toY(pv);
    ctx.strokeStyle="#0c0c28";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();
    ctx.fillStyle="#26265a";ctx.fillText(pv.toFixed(2),PL+CW+4,y+3);
  }

  /* EMA 9 + EMA 21 */
  const closes=vis.map(c=>c.c);
  [[9,"#f0c02099",1.3],[21,"#5090ff88",1.3]].forEach(([p,col,lw])=>{
    const vals=ema(closes,p);
    ctx.strokeStyle=col;ctx.lineWidth=lw;ctx.beginPath();let st=false;
    vals.forEach((v,i)=>{
      if(v==null)return;
      st?ctx.lineTo(toX(i),toY(v)):(ctx.moveTo(toX(i),toY(v)),st=true);
    });
    ctx.stroke();
  });

  /* candles */
  vis.forEach((c,i)=>{
    const x=toX(i),isUp=c.c>=c.o,col=isUp?"#18c860":"#f03050";
    ctx.globalAlpha=i===n-1?0.55:1;
    ctx.strokeStyle=col;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,toY(c.h));ctx.lineTo(x,toY(c.l));ctx.stroke();
    const by=toY(Math.max(c.o,c.c)),bh=Math.max(1.5,toY(Math.min(c.o,c.c))-by);
    ctx.fillStyle=isUp?"#18c86038":"#f0305038";ctx.fillRect(x-bw/2,by,bw,bh);
    ctx.strokeStyle=col;ctx.strokeRect(x-bw/2,by,bw,bh);
    ctx.globalAlpha=1;
  });

  /* best bot SL/Entry/TP lines */
  const bb=bestBot();
  if(bb){const tr=bb.openTrades[mkt.code];if(tr){
    const lvl=(price,col,dash,lbl)=>{
      if(price<loP||price>hiP)return;
      const y=toY(price);
      ctx.setLineDash(dash);ctx.strokeStyle=col;ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=col;ctx.font="bold 7.5px 'Share Tech Mono'";ctx.textAlign="left";
      ctx.fillText(lbl+" "+price.toFixed(2),PL+CW+4,y+3);
    };
    lvl(tr.tp,"#18c860",[5,3],"TP");
    lvl(tr.entry,"#808080",[2,5],"E ");
    lvl(tr.sl,"#f03050",[5,3],"SL");
  }}

  /* current price label */
  const last=closes.at(-1);
  if(last!=null){
    const y=toY(last),bx=PL+CW+2,bxw=PR-4,byy=y-9;
    ctx.setLineDash([3,5]);ctx.strokeStyle="#ffffff10";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle=mkt.col+"25";ctx.strokeStyle=mkt.col+"cc";ctx.lineWidth=1.5;
    ctx.beginPath();
    if(ctx.roundRect){ctx.roundRect(bx,byy,bxw,18,3);}
    else{
      const r=3;
      ctx.moveTo(bx+r,byy);ctx.lineTo(bx+bxw-r,byy);ctx.arcTo(bx+bxw,byy,bx+bxw,byy+r,r);
      ctx.lineTo(bx+bxw,byy+18-r);ctx.arcTo(bx+bxw,byy+18,bx+bxw-r,byy+18,r);
      ctx.lineTo(bx+r,byy+18);ctx.arcTo(bx,byy+18,bx,byy+18-r,r);
      ctx.lineTo(bx,byy+r);ctx.arcTo(bx,byy,bx+r,byy,r);ctx.closePath();
    }
    ctx.fill();ctx.stroke();
    ctx.fillStyle=mkt.col;ctx.font="bold 9px 'Share Tech Mono'";ctx.textAlign="center";
    ctx.fillText(last.toFixed(2),bx+bxw/2,y+3.5);
  }

  /* time axis */
  ctx.fillStyle="#22225a";ctx.font="7px 'Share Tech Mono'";ctx.textAlign="center";
  const fmtT=ts=>new Date(ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
  [0,Math.floor(n/4),Math.floor(n/2),Math.floor(3*n/4),n-1].forEach(i=>{
    if(i<0||i>=n||!vis[i])return;
    ctx.fillText(fmtT(vis[i].t),toX(i),H-3);
  });
}

// ── Render helpers ────────────────────────────────────────────────
const f$  =v=>(v>=0?"+":"-")+"$"+Math.abs(v).toFixed(2);
const fPts=v=>(v>=0?"+":"")+v.toFixed(2)+"pts";
const fPct=v=>(v*100).toFixed(1)+"%";
const clr =v=>v>0?"#18c860":v<0?"#f03050":"#687898";
const fTs =ts=>new Date(ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});

function renderLeft(){
  const bb=bestBot();if(!bb)return;
  document.getElementById("bname").textContent="* "+bb.name;
  document.getElementById("btype").textContent=`${bb.strat.type} | RR ${bb.strat.rr}:1 | ATRx${bb.strat.atrMult}`;
  const p=getPnl(bb);
  document.getElementById("bbal").textContent="$"+bb.balance.toFixed(2);
  const pe=document.getElementById("bpnl");pe.textContent=f$(p);pe.style.color=clr(p);
  document.getElementById("bwr").textContent=fPct(getWR(bb));
  document.getElementById("bwl").textContent=`${bb.wins}/${bb.losses}/${bb.wins+bb.losses}`;
  document.getElementById("bsc").textContent=(score(bb,live())*100).toFixed(1)+"/100";
  if(bb.closedTrades.length>1){
    const cum=bb.closedTrades.map((_,i,a)=>a.slice(0,i+1).reduce((s,t)=>s+t.pnlUSD,0));
    const mn=Math.min(...cum),mx=Math.max(...cum),rng=mx-mn||1;
    const pts=cum.map((v,i)=>`${(i/(cum.length-1))*200},${25-((v-mn)/rng)*23}`).join(" ");
    const zy=25-((0-mn)/rng)*23;
    document.getElementById("spark").innerHTML=
      `<line x1="0" y1="${zy}" x2="200" y2="${zy}" stroke="#181840" stroke-width="1" stroke-dasharray="3,4"/>` +
      `<polyline points="${pts}" fill="none" stroke="${p>=0?"#18c860":"#f03050"}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
  }
  const ents=Object.entries(bb.openTrades);
  document.getElementById("openbox").innerHTML=ents.length
    ?ents.map(([code,t])=>{
        const mkt=MKTS.find(m=>m.code===code);
        const cur=bars(code).at(-1)?.c??t.entry;
        const pts=t.dir==="long"?cur-t.entry:t.entry-cur;
        const unr=Math.round(pts*mkt.ptVal*100)/100;
        return`<div class="ti">
          <div style="display:flex;justify-content:space-between;margin-bottom:2px">
            <b style="color:${mkt.col}">${mkt.code}</b>
            <b style="color:${t.dir==="long"?"#18c860":"#f03050"}">${t.dir.toUpperCase()}</b>
          </div>
          <div class="r2"><span class="k">Entry (bar close)</span><b>${t.entry.toFixed(2)}</b></div>
          <div class="r2"><span style="color:#f03050">SL</span>
            <span style="color:#f03050">${t.sl.toFixed(2)} <span style="color:var(--tx3)">(${Math.abs(t.entry-t.sl).toFixed(2)}pt)</span></span></div>
          <div class="r2"><span style="color:#18c860">TP</span>
            <span style="color:#18c860">${t.tp.toFixed(2)} <span style="color:var(--tx3)">(${Math.abs(t.tp-t.entry).toFixed(2)}pt)</span></span></div>
          <div class="r2"><span class="k">Unrealized</span>
            <b style="color:${clr(unr)}">${f$(unr)} (${fPts(pts)})</b></div>
          <div style="display:flex;justify-content:space-between;font-size:8px;color:var(--tx3);margin-top:2px">
            <span>ATR: ${t.atr?.toFixed(2)}</span><span>Open: ${fTs(t.openT)}</span>
          </div>
        </div>`;
      }).join("")
    :`<div style="padding:5px 9px;color:var(--tx3)">No open trades</div>`;
  document.getElementById("histbox").innerHTML=bb.closedTrades.length
    ?bb.closedTrades.slice(-8).reverse().map(t=>{
        const mkt=MKTS.find(m=>m.code===t.code);
        return`<div class="hi" style="background:${t.won?"#18c86008":"#f0305008"}">
          <span style="color:${mkt?.col||'#fff'}">${t.code}</span>
          <span style="color:${t.dir==="long"?"#18c86060":"#f0305060"}">${t.dir==="long"?"L":"S"}</span>
          <span style="color:var(--tx2)">E:${t.entry?.toFixed(2)}</span>
          <span style="color:var(--tx2)">X:${t.exitPx?.toFixed(2)}</span>
          <b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b>
          <b style="color:${t.won?"#14a046":"#b01828"}">${t.won?"W":"L"}</b>
        </div>`;
      }).join("")
    :`<div style="padding:5px 9px;color:var(--tx3)">No trades yet</div>`;
  document.getElementById("stratbox").innerHTML=
    `<b style="color:var(--pu)">${bb.strat.type}</b><br>
     <span style="color:var(--tx2)">${bb.strat.desc}</span><br><br>
     <span class="k">R:R </span><b>${bb.strat.rr}:1</b>&nbsp;
     <span class="k">ATRx </span><b>${bb.strat.atrMult}</b>&nbsp;
     <span class="k">Wave </span><b style="color:var(--pu)">${bb.wave}</b><br>
     <span class="k">Trades </span><b>${bb.wins+bb.losses}</b>&nbsp;
     <span class="k">WR </span><b>${fPct(getWR(bb))}</b>`;
}

function renderCharts(){
  MKTS.forEach(m=>{
    drawChart(m);
    const last=bars(m.code).at(-1)?.c;
    if(last!=null){
      const cp=document.getElementById("cpx-"+m.id);if(cp)cp.textContent=last.toFixed(2);
      const pp=document.getElementById("p"+m.id);if(pp)pp.textContent=last.toFixed(2);
    }
    const sb=document.getElementById("sb-"+m.id);if(!sb)return;
    const open=live().filter(b=>b.openTrades[m.code]);
    if(open.length){
      sb.innerHTML=open.slice(0,5).map(b=>{
        const t=b.openTrades[m.code];
        const cur=bars(m.code).at(-1)?.c??t.entry;
        const pts=t.dir==="long"?cur-t.entry:t.entry-cur;
        const unr=Math.round(pts*m.ptVal*100)/100;
        return`<span class="chip ${t.dir==="long"?"cl":"cs"}">
          ${b.name.split(" W")[0]} ${t.dir==="long"?"L":"S"}
          E:${t.entry.toFixed(2)} TP:${t.tp.toFixed(2)} SL:${t.sl.toFixed(2)}
          <span style="color:${clr(unr)}">${f$(unr)}</span>
        </span>`;
      }).join("");
    }else{
      sb.innerHTML=`<span style="color:var(--tx4);font-size:8px">watching for crossover signal...</span>`;
    }
  });
}

function renderAllTrades(){
  document.getElementById("atbody").innerHTML=allClosed.length
    ?allClosed.map(t=>{
        const mkt=MKTS.find(m=>m.code===t.code);
        return`<tr style="background:${t.won?"#18c86008":"#f0305008"}">
          <td><b style="color:${mkt?.col||'#fff'}">${t.code}</b></td>
          <td style="color:var(--pu);max-width:90px;overflow:hidden;text-overflow:ellipsis">${t.botName}</td>
          <td style="color:${t.dir==="long"?"#18c86060":"#f0305060"}">${t.dir==="long"?"L":"S"}</td>
          <td style="color:var(--tx2)">${t.entry?.toFixed(2)}</td>
          <td style="color:var(--tx2)">${t.exitPx?.toFixed(2)}</td>
          <td style="color:${clr(t.pts)}">${fPts(t.pts??0)}</td>
          <td><b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b></td>
          <td style="color:${t.won?"#14a046":"#b01828"}">${t.won?"WIN":"LOSS"}</td>
        </tr>`;
      }).join("")
    :`<tr><td colspan="8" style="text-align:center;color:var(--tx3);padding:16px">
       Bots fire on crossover signals -- trades appear when real bar crosses SL or TP.
     </td></tr>`;
}

function renderRight(){
  const ab=live(),bb=bestBot();
  document.getElementById("blist").innerHTML=[...bots]
    .sort((a,b2)=>score(b2,ab)-score(a,ab)).slice(0,26)
    .map((b,i)=>{
      const sc=score(b,ab)*100,p=getPnl(b);
      const bc=b.killed?"#1e1e3a":sc>60?"#18c860":sc>35?"#f0c020":"#f03050";
      const isBest=b===bb;
      return`<div class="brow${b.killed?" dead":""}">
        <span class="bdot" style="background:${b.killed?"#1e1e3a":bc}"></span>
        <div style="flex:1;min-width:0">
          <div style="display:flex;justify-content:space-between;gap:2px">
            <span style="color:${isBest?"#18d8f0":b.killed?"#282840":"#4a6080"};
              font-size:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">
              ${isBest?"* ":""}${b.name}</span>
            <b style="color:${clr(p)};font-size:8px;flex-shrink:0">${f$(p)}</b>
          </div>
          <div style="display:flex;align-items:center;gap:3px">
            <div class="bbar"><div class="bfill" style="width:${Math.max(0,Math.min(100,sc))}%;background:${bc}"></div></div>
            <span style="color:${bc};font-size:7.5px;flex-shrink:0">${fPct(getWR(b))}</span>
          </div>
          ${b.killed?`<div style="color:#3a1a1a;font-size:7px">${b.killReason}</div>`:""}
        </div></div>`;
    }).join("");

  document.getElementById("srcsect").innerHTML=MKTS.map(m=>{
    const src=sources[m.code]||"--";
    const ok=!!candles[m.code]?.length;
    return`<div style="display:flex;justify-content:space-between">
      <span style="color:${m.col}">${m.code}</span>
      <span style="color:${ok?"var(--g)":"var(--r)"};font-size:8px">${src}</span>
    </div>`;
  }).join("");

  const pairs=[["ES","MES"],["NQ","MNQ"],["ES","NQ"]];
  document.getElementById("corrsect").innerHTML=pairs.map(([a,b2])=>{
    const ca=candles[a]?.map(c=>c.c)??[],cb=candles[b2]?.map(c=>c.c)??[];
    let r=0;
    if(ca.length>10&&cb.length>10){
      const nn=Math.min(ca.length,cb.length,300);
      const ax=ca.slice(-nn),bx=cb.slice(-nn);
      const ma=ax.reduce((s,v)=>s+v)/nn,mb=bx.reduce((s,v)=>s+v)/nn;
      const num=ax.reduce((s,v,i)=>s+(v-ma)*(bx[i]-mb),0);
      const da=Math.sqrt(ax.reduce((s,v)=>s+(v-ma)**2,0));
      const db=Math.sqrt(bx.reduce((s,v)=>s+(v-mb)**2,0));
      r=da&&db?num/(da*db):0;
    }
    const rc=r>0.8?"#18c860":r>0.5?"#f0c020":"#8080ff";
    return`<div style="margin-bottom:5px">
      <div style="display:flex;justify-content:space-between;margin-bottom:2px">
        <span>${a} / ${b2}</span><span style="color:${rc}">${(r*100).toFixed(0)}%</span>
      </div>
      <div style="height:3px;background:var(--b1);border-radius:2px">
        <div style="height:100%;border-radius:2px;width:${Math.abs(r)*100}%;background:${rc}"></div>
      </div></div>`;
  }).join("");
}

function addLog(msg,type="info"){
  logEvents.unshift({msg,type,ts:Date.now()});logEvents=logEvents.slice(0,80);
  document.getElementById("log").innerHTML=logEvents.map(e=>
    `<span class="lc ${e.type}">
       ${new Date(e.ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"})}
       ${e.msg}
     </span>`).join("");
}

document.querySelectorAll(".ivb").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".ivb").forEach(b=>b.classList.remove("on"));
    btn.classList.add("on");iv=btn.dataset.iv;
    candles={};sources={};processedIdx={};startupDone=false;
    allClosed=[];totalClosed=0;wave=1;uid=0;
    bots=STRATS.map(s=>mkBot(s,1));
    document.getElementById("tcl").textContent="0";
    document.getElementById("tw").textContent="1";
    addLog("Interval -> "+iv+" -- fetching fresh data...","info");
    refresh();
  });
});
window.addEventListener("resize",()=>MKTS.forEach(m=>drawChart(m)));

buildGrid();

async function refresh(){
  await loadAll();processBots();
  renderCharts();renderLeft();renderAllTrades();renderRight();
}
refresh();
setInterval(refresh,30000);
setInterval(()=>{renderCharts();renderLeft();renderRight();},4000);
</script>
</body>
</html>"""


# =============================================================================
#  HTTP SERVER
# =============================================================================
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type",   "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control",  "no-cache, no-store")
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
            iv_  = params.get("iv",   "5m")
            d    = get_candles(code, iv_)
            body = json.dumps(d).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type",   "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass   # silence per-request log noise


def serve():
    srv = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    srv.serve_forever()


# =============================================================================
#  ENTRY POINT
# =============================================================================
if __name__ == "__main__":

    # ── Windows: enable UTF-8 in the console if possible ─────────────────────
    if sys.platform == "win32":
        try:
            import subprocess
            subprocess.run(["chcp", "65001"], capture_output=True, shell=True)
        except Exception:
            pass

    _safe_print("")
    _safe_print("  FF ELITE BOTS v4")
    _safe_print("  ================")
    _safe_print("  Data : Yahoo Finance v8 API (query1 -> query2) -> Stooq CSV")
    _safe_print("  Auth : none -- standard library only -- no pip install needed")
    _safe_print("  Mode : all 4 contracts fetched independently, no mirroring")
    _safe_print("")
    _safe_print("  Pre-flight data check...")
    _safe_print("")

    ok = 0
    for code in ("ES", "MES", "NQ", "MNQ"):
        try:
            rows, source = fetch_candles(code, "5m")
            ok += 1
        except RuntimeError as e:
            _safe_print(f"  [--] {code}: {e}")

    _safe_print("")
    if ok:
        _safe_print(f"  {ok}/4 contracts fetched OK")
        _safe_print("  Entry  = snap(bar.close, 0.25pt tick)")
        _safe_print("  SL/TP  = entry +/- ATR(14) x mult, snapped to 0.25pt")
        _safe_print("  Exit   = real bar High or Low crosses SL / TP")
        _safe_print("  P&L    = (exit - entry) x ptVal  -- verify by hand")
    else:
        _safe_print("  No data -- market may be closed or no internet access.")
        _safe_print("  CME Globex hours: Sun 6pm - Fri 5pm ET")
        _safe_print("  The dashboard will retry automatically every 30 seconds.")

    _safe_print("")

    # Check port is free
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            _safe_print(f"  WARNING: port {PORT} is already in use.")
            _safe_print(f"  Close whatever is using it, then re-run.")
            _safe_print("")
            sys.exit(1)

    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.4)
    url = f"http://localhost:{PORT}"
    _safe_print(f"  Running at  {url}")
    _safe_print("")
    _safe_print("  Press Ctrl+C to stop.")
    _safe_print("")
    webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _safe_print("")
        _safe_print("  Stopped.")
        _safe_print("")
        sys.exit(0)