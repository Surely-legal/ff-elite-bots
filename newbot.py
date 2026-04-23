#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF ELITE BOTS v4  --  8 Markets  --  4 Index Pairs
===================================================
  python run.py   (Windows CMD, PowerShell, Mac, Linux -- no pip needed)

  Markets: ES/MES  NQ/MNQ  YM/MYM  RTY/M2K
  Strategies: 10 session-aware bots (Asia / London / NY)
  Data: Yahoo Finance v8 OHLC + v7 quotes  ->  Stooq fallback
"""

import sys, io as _io
try:
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except AttributeError:
    pass

import json, time, threading, webbrowser, http.server, urllib.parse
import urllib.request, csv, io, datetime, gzip, socket

PORT  = 7432
CODES = ("ES","MES","NQ","MNQ","YM","MYM","RTY","M2K")

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


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FF Elite Bots v4</title>
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

/* ── TOP BAR ── */
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

/* Session chips */
.sess-chip{padding:2px 6px;border-radius:3px;font-size:7px;font-weight:700;
  letter-spacing:1px;color:var(--tx3);background:var(--b1);border:1px solid transparent;transition:all .3s}
#sess-asia.active{color:#8080ff;background:#8080ff18;border-color:#8080ff50}
#sess-london.active{color:#f09030;background:#f0903018;border-color:#f0903050}
#sess-ny.active{color:#18c860;background:#18c86018;border-color:#18c86050}
#sess-sydney.active{color:#ffd700;background:#ffd70018;border-color:#ffd70050}

/* ── BODY ── */
#body{display:flex;flex:1;overflow:hidden;min-height:0}

/* LEFT */
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

/* Open positions - best bot only */
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

/* CENTER */
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

/* RIGHT */
#right{width:196px;min-width:196px;flex-shrink:0;background:var(--p1);
  border-left:1px solid var(--b2);display:flex;flex-direction:column;overflow:hidden}
#blist{flex:1;overflow-y:auto}
.brow{display:flex;align-items:center;gap:4px;padding:3px 7px;border-bottom:1px solid var(--b1);font-size:8.5px}
.brow.dead{opacity:.2}
.bdot{width:5px;height:5px;border-radius:50%;flex-shrink:0}
.bbar{flex:1;height:2px;background:var(--b2);border-radius:1px}
.bfill{height:100%;border-radius:1px;transition:width .8s}
.rsect{flex-shrink:0;padding:5px 9px;border-top:1px solid var(--b2);font-size:8px;line-height:1.9;color:var(--tx3)}

/* LOG */
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
table.mt{width:100%;border-collapse:collapse}
table.mt th{font-size:6.5px;color:var(--tx3);padding:2px 4px;border-bottom:1px solid var(--b2);
  position:sticky;top:0;background:var(--p3);white-space:nowrap;text-align:left}
table.mt td{font-size:8px;padding:2px 4px;border-bottom:1px solid var(--b1);white-space:nowrap}
table.mt tr:hover td{background:var(--p2)}
::-webkit-scrollbar{width:3px;height:3px}::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--b2);border-radius:2px}

/* ── HOVER TOOLTIP ── */
#chart-tooltip{position:fixed;pointer-events:none;z-index:100;display:none;
  background:#1e222d;border:1px solid #363a45;border-radius:4px;
  padding:7px 10px;font-family:'Share Tech Mono',monospace;font-size:8px;
  color:var(--tx);line-height:1.8;box-shadow:0 4px 20px #00000070;}
#chart-tooltip .tt-sym{font-family:'Orbitron',sans-serif;font-size:9px;font-weight:700;
  margin-bottom:3px;padding-bottom:3px;border-bottom:1px solid var(--b1);}
#chart-tooltip .tt-row{display:flex;justify-content:space-between;gap:12px;}
#chart-tooltip .tt-k{color:var(--tx3);}

/* ── FULLSCREEN OVERLAY ── */
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

/* ── STRATEGY MODAL ── */
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
    <div class="ph" style="border-top:1px solid var(--b2)">
      <span style="color:#7eb8ff">⬡ APEX AI</span>
      <span id="ai-wr-badge" style="font-size:6.5px;color:var(--tx3);font-weight:normal;text-transform:none;letter-spacing:0"></span>
    </div>
    <div id="ai-panel-left"><div style="padding:8px 10px;color:var(--tx3);font-size:8px">Learning... needs WR&gt;50% strategy per session</div></div>
    <div id="ai-trades-panel" style="flex-shrink:0;overflow-y:auto;max-height:130px;border-bottom:1px solid var(--b2);display:none"></div>
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
    <div class="ph">Leaderboard</div>
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
    <div class="rsect" style="font-size:7.5px">WR &lt;25% after 20 &rarr; suspended<br>Revives fresh at each new session<br>No wave spawning &mdash; all 17 run always</div>
  </div>
</div>
<div id="log"><span class="lc info">FF Elite Bots v4 &mdash; 8 markets &mdash; 4 index pairs &mdash; 10 session-aware strategies</span></div>
</div>

<!-- ── HOVER TOOLTIP ── -->
<div id="chart-tooltip"></div>

<!-- ── FULLSCREEN CHART OVERLAY ── -->
<div id="fs-overlay">
  <div id="fs-header">
    <div id="fs-meta">
      <span id="fs-sym"></span>
      <span id="fs-price">--</span>
      <span id="fs-chg"></span>
    </div>
    <span id="fs-close">✕ &nbsp;ESC</span>
  </div>
  <div id="fs-canvas-wrap"></div>
  <div id="fs-positions"></div>
</div>

<!-- ── STRATEGY TRADES MODAL ── -->
<div id="strat-modal">
  <div id="strat-modal-inner">
    <div id="strat-modal-header">
      <div>
        <div id="strat-modal-title"></div>
        <div id="strat-modal-sub"></div>
      </div>
      <span id="strat-modal-close">✕</span>
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
// Confidence tiers (matches your trading system):
//   T1 MAX  conf=1.00 → NQ/MNQ  — A+ setup, max volatility/reward (Nasdaq)
//   T2 HIGH conf=0.85 → ES/MES  — High probability, smooth/technical (S&P)
//   T3 MOD  conf=0.65 → YM/MYM  — Less certain, Blue Chip stable (Dow)
//   T4 LOW  conf=0.45 → RTY/M2K — Probe/test trades, least $/pt (Russell)
// conf drives ATR multiplier, RR ratio, and position sizing per trade
const MKTS=[
  {id:"NQ", code:"NQ", name:"E-Mini Nasdaq-100",   ptVal:20,  tick:0.25, col:"#ff9800", pair:"NDX", tier:1, conf:1.00, tierLabel:"T1·MAX"},
  {id:"MNQ",code:"MNQ",name:"Micro E-Mini NQ",     ptVal:2,   tick:0.25, col:"#ffb74d", pair:"NDX", tier:1, conf:1.00, tierLabel:"T1·MAX"},
  {id:"ES", code:"ES", name:"E-Mini S&P 500",      ptVal:50,  tick:0.25, col:"#2962ff", pair:"SPX", tier:2, conf:0.85, tierLabel:"T2·HIGH"},
  {id:"MES",code:"MES",name:"Micro E-Mini S&P",    ptVal:5,   tick:0.25, col:"#5585ff", pair:"SPX", tier:2, conf:0.85, tierLabel:"T2·HIGH"},
  {id:"YM", code:"YM", name:"E-Mini Dow Jones",    ptVal:5,   tick:1.00, col:"#00bfa5", pair:"DJI", tier:3, conf:0.65, tierLabel:"T3·MOD"},
  {id:"MYM",code:"MYM",name:"Micro E-Mini Dow",    ptVal:0.5, tick:1.00, col:"#4dd0c4", pair:"DJI", tier:3, conf:0.65, tierLabel:"T3·MOD"},
  {id:"RTY",code:"RTY",name:"E-Mini Russell 2000",  ptVal:50,  tick:0.10, col:"#e91e63", pair:"RUT", tier:4, conf:0.45, tierLabel:"T4·LOW"},
  {id:"M2K",code:"M2K",name:"Micro E-Mini Russell", ptVal:5,   tick:0.10, col:"#f06292", pair:"RUT", tier:4, conf:0.45, tierLabel:"T4·LOW"},
];
const snap=(p,tick)=>Math.round(p/tick)*tick;
let candles={},liveQ={},sources={},prevPx={},dirty={};
let processedTs={},iv="5m",isLive=false;
let wave=1,uid=0,totalClosed=0,bots=[],allClosed=[],logE=[];
let startupDone=false;
let prevBestTradeKeys=new Set();  // keys of best bot's open trades (for sound)
let prevBestBotUid=null;           // uid of best bot last time we checked
let soundSeeded=false;             // suppress sounds on first render
const bs=code=>candles[code]??[];
let hoverState={}; // {marketId: barIndex} — drives crosshair + tooltip
const pendingSignals={}; // {botUid_mktCode: {sig, barT}} — 1-bar confirmation buffer

// ── Performance matrix: {stratId|sess|code} -> {w,l,pnl,bestWin,trades[]} ──
// Each entry now stores an array of individual trade records with timestamps
// so recency decay can weight recent wins more than stale ones.
const perfMatrix={};
function recordPerf(stratId,sess,code,won,pnl,openTs){
  const k=`${stratId}|${sess}|${code}`;
  if(!perfMatrix[k])perfMatrix[k]={w:0,l:0,pnl:0,bestWin:0,trades:[]};
  won?perfMatrix[k].w++:perfMatrix[k].l++;
  perfMatrix[k].pnl=Math.round((perfMatrix[k].pnl+(pnl||0))*100)/100;
  if(won&&pnl>0)perfMatrix[k].bestWin=Math.max(perfMatrix[k].bestWin,pnl);
  // Store timestamped trade for recency decay
  perfMatrix[k].trades.push({ts:openTs||Date.now(),won,pnl:pnl||0});
  // Keep last 200 trades per key to avoid unbounded growth
  if(perfMatrix[k].trades.length>200)perfMatrix[k].trades=perfMatrix[k].trades.slice(-200);
}

// Fan out recordPerf to ALL sessions active at the trade's open timestamp.
// This ensures overlap periods like ASIA+SYD credit both ASIA and SYDNEY,
// so SYDNEY can accumulate qualifying strategies even though getSessionET
// almost always returns ASIA during the overlap due to priority ordering.
function recordPerfAll(stratId,openTs,code,won,pnl){
  const sessions=getActiveSessions(openTs).filter(s=>s!=="MAINT");
  if(!sessions.length)sessions.push(getSessionET(openTs));
  const seen=new Set();
  sessions.forEach(s=>{
    if(!seen.has(s)){seen.add(s);recordPerf(stratId,s,code,won,pnl,openTs);}
  });
}
function perfWR(stratId,sess,code){
  const k=`${stratId}|${sess}|${code}`;
  const p=perfMatrix[k];
  return p&&(p.w+p.l)>=3 ? p.w/(p.w+p.l) : null;
}

// Best learned combo for a market+session (used by adaptive panel)
// getBestStratForSession: returns {strat, wr, mktCode, n} for the
// highest-WR strategy found across ANY market for a given session.
// Requires min 3 trades. Returns null if no strategy qualifies yet.
function getBestStratForSession(sess){
  let best=null;
  STRATS.forEach(s=>{
    MKTS.forEach(m=>{
      const k=`${s.id}|${sess}|${m.code}`;
      const p=perfMatrix[k];
      if(!p)return;
      const n=p.w+p.l; if(n<3)return;
      const wr=p.w/n;
      if(!best||wr>best.wr)best={strat:s,wr,mktCode:m.code,mktCol:m.col,n,pnl:p.pnl};
    });
  });
  return best;
}

function comboScore(p){
  // Same logic as bot score: WR*80% + avgPnl/trade*20% (capped at $500 avg)
  if(!p)return 0;
  const n=p.w+p.l; if(n===0)return 0;
  const wr=p.w/n;
  const avgPnl=p.pnl/n;
  const pnlScore=Math.max(0,Math.min(1,avgPnl/500));
  return wr*0.80+pnlScore*0.20;
}
function getBestCombo(code,sess){
  let best=null;
  STRATS.forEach(s=>{
    const k=`${s.id}|${sess}|${code}`;
    const p=perfMatrix[k];
    if(!p)return;
    const n=p.w+p.l; if(n<3)return;
    const sc=comboScore(p);
    const wr=p.w/n;
    if(!best||sc>best.sc)best={stratId:s.id,strat:s,wr,sc,n,pnl:p.pnl};
  });
  return best;
}

// Adaptive (AI) bot state
const adaptiveBot={uid:-1,name:"Apex AI",openTrades:{},closedTrades:[],wins:0,losses:0,
  consecLosses:0,  // consecutive losses — pauses Apex at 3
  apexPaused:false // true when paused, re-evaluated each getDominantStrat call
};

// T1 consensus direction (set by computeT1Consensus each processBots call)
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

// ── Parabolic SAR ─────────────────────────────────────────────
// Returns array of SAR values. af=acceleration factor start, maxAF=max AF.
function sarArr(b,af=0.02,maxAF=0.2){
  if(b.length<2)return b.map(()=>null);
  const out=Array(b.length).fill(null);
  let bull=true; // start assuming uptrend
  let sar=b[0].l,ep=b[0].h,curAF=af;
  out[0]=sar;
  for(let i=1;i<b.length;i++){
    let nsar=sar+curAF*(ep-sar);
    // SAR cannot be above previous two lows in uptrend or below previous two highs in downtrend
    if(bull){
      nsar=Math.min(nsar,b[i-1].l,i>=2?b[i-2].l:b[i-1].l);
      if(b[i].l<nsar){// reversal
        bull=false;sar=ep;ep=b[i].l;curAF=af;
        nsar=sar+curAF*(ep-sar);
        nsar=Math.max(nsar,b[i-1].h,i>=2?b[i-2].h:b[i-1].h);
      }else{
        if(b[i].h>ep){ep=b[i].h;curAF=Math.min(curAF+af,maxAF);}
      }
    }else{
      nsar=Math.max(nsar,b[i-1].h,i>=2?b[i-2].h:b[i-1].h);
      if(b[i].h>nsar){// reversal
        bull=true;sar=ep;ep=b[i].h;curAF=af;
        nsar=sar+curAF*(ep-sar);
        nsar=Math.min(nsar,b[i-1].l,i>=2?b[i-2].l:b[i-1].l);
      }else{
        if(b[i].l<ep){ep=b[i].l;curAF=Math.min(curAF+af,maxAF);}
      }
    }
    sar=nsar;
    out[i]=Math.round(sar*10000)/10000;
  }
  return out;
}

// ── ADX (Average Directional Index) ──────────────────────────
// Returns array of ADX values (0–100). Values >25 = strong trend.
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
  // Smooth with Wilder's method
  let atr=tr.slice(0,p).reduce((a,v)=>a+v,0);
  let apdm=pdm.slice(0,p).reduce((a,v)=>a+v,0);
  let andm=ndm.slice(0,p).reduce((a,v)=>a+v,0);
  const dxArr=[];
  for(let i=p;i<tr.length;i++){
    atr=atr-atr/p+tr[i];
    apdm=apdm-apdm/p+pdm[i];
    andm=andm-andm/p+ndm[i];
    const pdi=atr>0?100*apdm/atr:0;
    const ndi=atr>0?100*andm/atr:0;
    const dx=(pdi+ndi>0)?100*Math.abs(pdi-ndi)/(pdi+ndi):0;
    dxArr.push(dx);
  }
  // ADX = smoothed DX
  if(dxArr.length<p)return out;
  let adx=dxArr.slice(0,p).reduce((a,v)=>a+v,0)/p;
  const adxStart=p+p; // offset in b array
  out[adxStart]=adx;
  for(let i=1;i<dxArr.length-p+1;i++){
    adx=(adx*(p-1)+dxArr[p-1+i])/p;
    if(adxStart+i<out.length)out[adxStart+i]=Math.round(adx*100)/100;
  }
  return out;
}

// ── Ichimoku Kinkō Hyō ────────────────────────────────────────
// Returns array of {tenkan, kijun, senkouA, senkouB, chikou}.
// Standard periods: Tenkan 9, Kijun 26, Senkou B 52, displacement 26.
function ichimokuArr(b,t=9,k=26,sb=52){
  const midVal=(bars,p,i)=>{
    if(i<p-1)return null;
    const sl=bars.slice(i-p+1,i+1);
    return(Math.max(...sl.map(x=>x.h))+Math.min(...sl.map(x=>x.l)))/2;
  };
  return b.map((_,i)=>{
    const tenkan=midVal(b,t,i);
    const kijun=midVal(b,k,i);
    // Senkou A = avg of tenkan+kijun, projected 26 bars ahead (we store at current index)
    const senkouA=tenkan!=null&&kijun!=null?(tenkan+kijun)/2:null;
    const senkouB=midVal(b,sb,i);
    const chikou=b[i].c; // lagging span (plotted 26 bars back, we just store close)
    return{tenkan,kijun,senkouA,senkouB,chikou};
  });
}

// ── Adaptive signal helpers ──────────────────────────────────────────────────

// sessScore: composite score for a perfMatrix entry used by Apex AI.
// Factors:
//   50% WR          — win rate (must be >0.50 to qualify)
//   30% avg P&L     — avg profit per trade, capped at $500 avg → 1.0
//   20% best win    — highest single winning trade, capped at $1000 → 1.0
// Returns 0–1. Strategies with WR≤0.50 or negative net P&L are excluded upstream.
function sessScore(p){
  if(!p)return 0;
  const n=p.w+p.l; if(n===0)return 0;
  const wr=p.w/n;
  const avgPnl=p.pnl/n;
  const bestW=p.bestWin||0;
  const wrS  =wr;                                       // 0–1
  const pnlS =Math.max(0,Math.min(1,avgPnl/500));       // $500 avg → 1.0
  const bestS=Math.max(0,Math.min(1,bestW/1000));       // $1000 best → 1.0
  return wrS*0.50+pnlS*0.30+bestS*0.20;
}

// Returns strategies that qualify for Apex AI voting:
//   - WR strictly > 0.50 (real trades, positive win rate)
//   - Net P&L positive (profitable in this session)
function getQualifiedStrats(sess,code){
  return STRATS.filter(s=>{
    const k=`${s.id}|${sess}|${code}`;
    const p=perfMatrix[k];
    if(!p)return false;
    const n=p.w+p.l; if(n===0)return false;
    return(p.w/n)>0.50&&p.pnl>0;
  });
}

// True if any market has ≥1 qualified strategy for this session.
function aiSessionReady(sess){
  return MKTS.some(m=>getQualifiedStrats(sess,m.code).length>0);
}

// Apex AI unlocks when ANY 2 sessions have at least one qualifying strategy.
// This ensures Apex fires during high-volume periods (e.g. NY+LONDON) without
// waiting for quieter sessions (ASIA/SYDNEY) to accumulate enough trades.
function aiFullyUnlocked(){
  return["NY","LONDON","ASIA","SYDNEY"].filter(s=>aiSessionReady(s)).length>=2;
}

// Best strategy for a session — ranked by sessScore (WR + profitability + best win).
// Used for the session checklist display in the AI panel.
function getBestForSession(sess){
  let best=null;
  STRATS.forEach(s=>{
    MKTS.forEach(m=>{
      const k=`${s.id}|${sess}|${m.code}`;
      const p=perfMatrix[k];
      if(!p)return;
      const n=p.w+p.l; if(n===0)return;
      if((p.w/n)<=0.50||p.pnl<=0)return; // must qualify
      const sc=sessScore(p);
      if(!best||sc>best.sc)
        best={strat:s,sc,wr:p.w/n,avgPnl:p.pnl/n,bestWin:p.bestWin||0,
              n,wins:p.w,mktCode:m.code,mktCol:m.col,pnl:p.pnl};
    });
  });
  return best;
}

// ── getDominantStrat: pick the strategy with the most DECAY-WEIGHTED wins ────
// Improvements over raw win count:
//
//   1. MIN 10 TRADES GATE — strategy must have ≥10 total trades (W+L) across all
//      markets in this session before it can become dominant. Prevents a 3W/0L
//      fluke from crowning a champion with no statistical basis.
//
//   2. RECENCY DECAY — each win is weighted by how recent it is. A win from 24h
//      ago counts as ~0.71 of a win; from 48h ~0.50; from 96h ~0.25. This means
//      strategies that are currently working outrank strategies that were hot days
//      ago but have gone cold. Half-life = 48 hours.
//
//   3. CONSECUTIVE LOSS PAUSE — if Apex has taken 3 losses in a row, it sets
//      apexPaused=true and won't fire until a different dominant strategy emerges
//      (i.e. the regime has shifted). The pause clears automatically when the
//      dominant strategy changes or when Apex wins again.
//
const DECAY_HALF_LIFE_MS = 48*60*60*1000; // 48 hours
function decayedWins(trades){
  const now=Date.now();
  return trades.filter(t=>t.won).reduce((sum,t)=>{
    const age=Math.max(0,now-t.ts);
    return sum+Math.pow(0.5,age/DECAY_HALF_LIFE_MS); // exponential decay
  },0);
}

function getDominantStrat(sess){
  const totals={};
  STRATS.forEach(s=>{
    MKTS.forEach(m=>{
      const k=`${s.id}|${sess}|${m.code}`;
      const p=perfMatrix[k];
      if(!p||!p.trades||p.trades.length===0)return;
      if(!totals[s.id])totals[s.id]={strat:s,w:0,l:0,pnl:0,bestWin:0,allTrades:[]};
      totals[s.id].w   +=p.w;
      totals[s.id].l   +=p.l;
      totals[s.id].pnl +=p.pnl;
      if(p.bestWin>totals[s.id].bestWin)totals[s.id].bestWin=p.bestWin;
      totals[s.id].allTrades.push(...p.trades);
    });
  });

  let best=null,bestDecayW=0;
  Object.values(totals).forEach(t=>{
    const n=t.w+t.l;
    // GATE 1: minimum 10 trades required
    if(n<10)return;
    const wr=t.w/n;
    if(wr<=0.50||t.pnl<=0)return;
    // GATE 2: rank by recency-decayed win count
    const dw=decayedWins(t.allTrades);
    if(!best||dw>bestDecayW){best=t;bestDecayW=dw;}
  });

  if(!best)return null;
  const n=best.w+best.l;
  const wr=best.w/n;
  const dom={strat:best.strat,wins:best.w,decayedWins:Math.round(bestDecayW*10)/10,
             n,wr,pnl:best.pnl,sc:sessScore(best)};

  // GATE 3: consecutive loss pause — auto-clears when dominant strategy changes
  if(adaptiveBot.apexPaused){
    const lastDom=adaptiveBot._lastDomId;
    if(dom.strat.id!==lastDom){
      // Regime shift — different strategy now leads, clear the pause
      adaptiveBot.apexPaused=false;
      adaptiveBot.consecLosses=0;
      adaptiveBot._lastDomId=dom.strat.id;
    }else{
      return null; // still paused, same strategy
    }
  }
  adaptiveBot._lastDomId=dom.strat.id;
  return dom;
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

// ── T1 consensus: ES and NQ must BOTH agree (short-term momentum) ────────────
// Uses dual check: price vs EMA21 AND most recent 3-bar momentum direction.
// "mixed" = conflicting signals between ES and NQ → T2/T3 markets skip that bar.
function computeT1Consensus(bars_ES,bars_NQ){
  if(!bars_ES||bars_ES.length<22||!bars_NQ||bars_NQ.length<22){t1Consensus=null;return;}
  const esC=bars_ES.map(c=>c.c),nqC=bars_NQ.map(c=>c.c);
  const esE=ema(esC,21),nqE=ema(nqC,21);
  const n=esC.length-1;
  // Trend: price above EMA
  const esUp=esC[n]>esE[n],nqUp=nqC[n]>nqE[n];
  // Momentum: last 3 bars higher or lower
  const esMom=esC[n]>esC[n-3],nqMom=nqC[n]>nqC[n-3];
  // Require BOTH trend AND momentum to agree within each market
  const esLong=esUp&&esMom, esShort=!esUp&&!esMom;
  const nqLong=nqUp&&nqMom, nqShort=!nqUp&&!nqMom;
  if(esLong&&nqLong)       t1Consensus="long";
  else if(esShort&&nqShort)t1Consensus="short";
  else                     t1Consensus="mixed";
}

// ── Session detector ──────────────────────────────────────────
// DST-aware ET hour helper
function etHour(ts){
  const d=new Date(ts??Date.now());
  const y=d.getUTCFullYear();
  const dstStart=new Date(Date.UTC(y,2,8-(new Date(Date.UTC(y,2,1)).getUTCDay()+7)%7,7));
  const dstEnd  =new Date(Date.UTC(y,10,1+(7-(new Date(Date.UTC(y,10,1)).getUTCDay()))%7,6));
  const off=d>=dstStart&&d<dstEnd?-4:-5;
  return((d.getUTCHours()+off)+24)%24+d.getUTCMinutes()/60;
}

// Session windows (EST = UTC-5, DST-aware via etHour):
//   Sydney  (Pacific)    : 5:00 PM – 2:00 AM  (h>=17 || h<2)
//   Tokyo   (Asian)      : 7:00 PM – 4:00 AM  (h>=19 || h<4)
//   London  (European)   : 3:00 AM – 12:00 PM (h>=3 && h<12)
//   NY      (N. American): 8:00 AM – 5:00 PM  (h>=8 && h<17)
//   Maintenance break    : 5:00 PM – 6:00 PM  (h>=17 && h<18) — no new trades

// Returns ALL active sessions at timestamp as array.
// Used to build overlap labels like ["NY","LONDON"] → "NY+LON"
// Clean session helpers — all session detection flows through these
function _inSydney(h){return(h>=18||h<2);}  // 6pm–2am (after maint ends at 6pm)
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

// Short display names for overlap labels
const _SESS_SHORT={NY:"NY",LONDON:"LON",ASIA:"ASIA",SYDNEY:"SYD",MAINT:"BREAK"};

// Display label: "NY+LON", "ASIA+SYD", "BREAK", etc.
function getSessionLabel(ts){
  return getActiveSessions(ts).map(s=>_SESS_SHORT[s]||s).join("+");
}

// Primary session for strategy routing + perfMatrix keys
// Priority: NY > LONDON > ASIA > SYDNEY, MAINT blocks trading entirely
function getSessionET(ts){
  const h=etHour(ts);
  if(_inMaint(h))  return"MAINT";
  if(_inNY(h))     return"NY";
  if(_inLondon(h)) return"LONDON";
  if(_inAsia(h))   return"ASIA";
  return"SYDNEY";
}

// Extract primary session from a display label for SESS_STYLE color lookup
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

// ── 10 Session-aware strategies ────────────────────────────────
const STRATS=[
  {id:"AsiaRangeFade",name:"Asia Fade",type:"RSI Fade / EMA Break",rr:2.0,atrMult:1.2,confirm:true,
   sess:{ASIA:"RSI 25/75",LONDON:"EMA 8/21",NY:"EMA 8/21"},
   desc:"ASIA: fade RSI extremes (25/75). LONDON/NY: EMA 8/21 golden-death cross.",
   signal(b){
     if(b.length<25)return null;
     const sess=getSessionET(b[b.length-1].t);
     const c=b.map(x=>x.c),n=c.length-1;
     if(sess==="ASIA"){
       const ri=rsiArr(c,14);
       if(ri[n]==null||ri[n-1]==null)return null;
       if(ri[n-1]<=25&&ri[n]>25)return"long";
       if(ri[n-1]>=75&&ri[n]<75)return"short";
     }else{
       const f=ema(c,8),s=ema(c,21);
       if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
       if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";
       if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     }
     return null;}},

  {id:"StochMaster",name:"Stoch Master",type:"Stoch %K Session",rr:1.5,atrMult:1.2,confirm:true,
   sess:{ASIA:"15/85",LONDON:"18/82",NY:"20/80"},
   desc:"Stochastic %K crossover tuned per session. Tighter in Asia, wider in NY.",
   signal(b){
     if(b.length<15)return null;
     const sess=getSessionET(b[b.length-1].t);
     const lo=sess==="ASIA"?15:sess==="LONDON"?18:20;
     const k=stochArr(b,9),n=k.length-1;
     if(k[n]==null||k[n-1]==null)return null;
     if(k[n-1]<=lo&&k[n]>lo)return"long";
     if(k[n-1]>=(100-lo)&&k[n]<(100-lo))return"short";
     return null;}},

  {id:"FFTopTrader",name:"FF Top Trader",type:"EMA Cross Session",rr:2.5,atrMult:1.5,
   sess:{ASIA:"EMA 5/13",LONDON:"EMA 8/21",NY:"EMA 8/34"},
   desc:"Golden/death cross with faster EMAs in quiet Asia, slower momentum in NY.",
   signal(b){
     if(b.length<40)return null;
     const sess=getSessionET(b[b.length-1].t);
     const c=b.map(x=>x.c),n=c.length-1;
     const [fp,sp]=sess==="ASIA"?[5,13]:sess==="LONDON"?[8,21]:[8,34];
     const f=ema(c,fp),s=ema(c,sp);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";
     if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;}},

  {id:"VelocityBreak",name:"Velocity Break",type:"ROC Session",rr:2.0,atrMult:1.5,
   sess:{ASIA:"ROC 0.15%",LONDON:"ROC 0.25%",NY:"ROC 0.40%"},
   desc:"Rate-of-change momentum. Low threshold in quiet Asia, high in NY volume.",
   signal(b){
     if(b.length<16)return null;
     const sess=getSessionET(b[b.length-1].t);
     const thresh=sess==="ASIA"?0.15:sess==="LONDON"?0.25:0.40;
     const c=b.map(x=>x.c),n=c.length-1;
     if(!c[n-10]||!c[n-11])return null;
     const r=(c[n]-c[n-10])/c[n-10]*100,rp=(c[n-1]-c[n-11])/c[n-11]*100;
     if(rp<thresh&&r>=thresh)return"long";
     if(rp>-thresh&&r<=-thresh)return"short";
     return null;}},

  {id:"BollingerBreak",name:"BB Squeeze",type:"Bollinger Session",rr:2.5,atrMult:1.5,
   sess:{ASIA:"BB(20,1.5)",LONDON:"BB(20,2.0)",NY:"BB(20,2.0)"},
   desc:"Close outside Bollinger Bands. Tighter 1.5x in slow Asia, 2.0x in London/NY.",
   signal(b){
     if(b.length<25)return null;
     const sess=getSessionET(b[b.length-1].t);
     const mult=sess==="ASIA"?1.5:2.0;
     const c=b.map(x=>x.c),bb2=bbArr(c,20,mult),n=c.length-1;
     if(!bb2[n].u||!bb2[n-1].u)return null;
     if(c[n-1]<=bb2[n-1].u&&c[n]>bb2[n].u)return"long";
     if(c[n-1]>=bb2[n-1].l&&c[n]<bb2[n].l)return"short";
     return null;}},

  {id:"MACDWave",name:"MACD Wave",type:"MACD Hist Zero Cross",rr:2.0,atrMult:1.5,confirm:true,
   sess:{ASIA:"MACD",LONDON:"MACD",NY:"MACD"},
   desc:"MACD histogram crosses zero. Universal — fires in all sessions.",
   signal(b){
     if(b.length<35)return null;
     const c=b.map(x=>x.c),{hist}=macdArr(c),n=hist.length-1;
     if(hist[n]==null||hist[n-1]==null)return null;
     if(hist[n-1]<=0&&hist[n]>0)return"long";
     if(hist[n-1]>=0&&hist[n]<0)return"short";
     return null;}},

  {id:"ATRChannel",name:"ATR Channel",type:"SMA+ATR Session",rr:2.5,atrMult:1.5,
   sess:{ASIA:"SMA20+1.5xATR",LONDON:"SMA20+2xATR",NY:"SMA20+2.5xATR"},
   desc:"Break above/below SMA20 ± ATR channel. Channel widens from Asia to NY.",
   signal(b){
     if(b.length<30)return null;
     const sess=getSessionET(b[b.length-1].t);
     const mult=sess==="ASIA"?1.5:sess==="LONDON"?2.0:2.5;
     const c=b.map(x=>x.c),at=atrArr(b,14),sm=sma(c,20),n=c.length-1;
     if(!at[n]||!sm[n]||!at[n-1]||!sm[n-1])return null;
     if(c[n-1]<=sm[n-1]+mult*at[n-1]&&c[n]>sm[n]+mult*at[n])return"long";
     if(c[n-1]>=sm[n-1]-mult*at[n-1]&&c[n]<sm[n]-mult*at[n])return"short";
     return null;}},

  {id:"CCIReversal",name:"CCI Reversal",type:"CCI Session",rr:2.0,atrMult:1.2,confirm:true,
   sess:{ASIA:"CCI ±80",LONDON:"CCI ±100",NY:"CCI ±100"},
   desc:"CCI crosses extreme. ±80 in tight Asia range, ±100 in London/NY.",
   signal(b){
     if(b.length<20)return null;
     const sess=getSessionET(b[b.length-1].t);
     const lev=sess==="ASIA"?80:100;
     const ci=cciArr(b,14),n=ci.length-1;
     if(ci[n]==null||ci[n-1]==null)return null;
     if(ci[n-1]<=-lev&&ci[n]>-lev)return"long";
     if(ci[n-1]>=lev&&ci[n]<lev)return"short";
     return null;}},

  {id:"RSIMomentum",name:"RSI Momentum",type:"RSI Session",rr:2.0,atrMult:1.2,confirm:true,
   sess:{ASIA:"RSI 25/75",LONDON:"RSI 28/72",NY:"RSI 30/70"},
   desc:"RSI oversold/overbought crossover. Wider for Asia fade, tighter for NY.",
   signal(b){
     if(b.length<20)return null;
     const sess=getSessionET(b[b.length-1].t);
     const lo=sess==="ASIA"?25:sess==="LONDON"?28:30;
     const c=b.map(x=>x.c),ri=rsiArr(c,14),n=ri.length-1;
     if(ri[n]==null||ri[n-1]==null)return null;
     if(ri[n-1]<=lo&&ri[n]>lo)return"long";
     if(ri[n-1]>=(100-lo)&&ri[n]<(100-lo))return"short";
     return null;}},

  {id:"OvernightMom",name:"Overnight Mom",type:"EMA 8/55 Session",rr:3.5,atrMult:1.5,trend:true,
   sess:{ASIA:"EMA 8/55",LONDON:"EMA 8/55",NY:"EMA 21/55"},
   desc:"ASIA/LONDON: fast 8/55 catches overnight momentum. NY: 21/55 rides session trend.",
   signal(b){
     if(b.length<62)return null;
     const sess=getSessionET(b[b.length-1].t);
     const c=b.map(x=>x.c),n=c.length-1;
     const fp=sess==="NY"?21:8;
     const f=ema(c,fp),s=ema(c,55);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";
     if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;}},

  // ── 7 NEW STRATEGIES ─────────────────────────────────────────────────────

  {id:"GoldenDeath",name:"Golden Death",type:"SMA 50/200 Cross",rr:3.5,atrMult:2.0,trend:true,
   sess:{ASIA:"SMA 50/200",LONDON:"SMA 50/200",NY:"SMA 50/200"},
   desc:"Classic Golden Cross (50 over 200) = long. Death Cross (50 under 200) = short. Universal.",
   signal(b){
     if(b.length<205)return null;
     const c=b.map(x=>x.c),n=c.length-1;
     const f=sma(c,50),s=sma(c,200);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";   // Golden Cross
     if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";  // Death Cross
     return null;}},

  {id:"RSI3070",name:"RSI 30/70",type:"RSI Overbought/Oversold",rr:2.0,atrMult:1.2,confirm:true,
   sess:{ASIA:"RSI 30/70",LONDON:"RSI 30/70",NY:"RSI 30/70"},
   desc:"Buy when RSI crosses up through 30 (oversold reversal). Sell when it crosses down through 70.",
   signal(b){
     if(b.length<20)return null;
     const c=b.map(x=>x.c),ri=rsiArr(c,14),n=ri.length-1;
     if(ri[n]==null||ri[n-1]==null)return null;
     if(ri[n-1]<=30&&ri[n]>30)return"long";
     if(ri[n-1]>=70&&ri[n]<70)return"short";
     return null;}},

  {id:"BBSqueeze",name:"BB Squeeze X",type:"Bollinger Squeeze Breakout",rr:2.5,atrMult:1.5,
   sess:{ASIA:"Squeeze+break",LONDON:"Squeeze+break",NY:"Squeeze+break"},
   desc:"Waits for bands to tighten to 50% of 20-bar average width, then trades the expansion breakout.",
   signal(b){
     if(b.length<30)return null;
     const c=b.map(x=>x.c),n=c.length-1;
     const bb=bbArr(c,20,2);
     if(!bb[n].u||!bb[n-1].u)return null;
     // Measure band width history
     const bw=bb.map(v=>v.u!=null?v.u-v.l:null);
     const recentBW=bw.slice(-20).filter(v=>v!=null);
     if(recentBW.length<10)return null;
     const avgBW=recentBW.reduce((a,v)=>a+v,0)/recentBW.length;
     const curBW=bw[n];
     // Squeeze: current width < 50% of avg, then close breaks a band
     const squeezed=curBW<avgBW*0.5;
     if(!squeezed)return null;
     if(c[n-1]<=bb[n-1].u&&c[n]>bb[n].u)return"long";
     if(c[n-1]>=bb[n-1].l&&c[n]<bb[n].l)return"short";
     return null;}},

  {id:"StochDivergence",name:"Stoch Divergence",type:"Stochastic Hidden Divergence",rr:2.5,atrMult:1.3,confirm:true,
   sess:{ASIA:"Stoch Div",LONDON:"Stoch Div",NY:"Stoch Div"},
   desc:"Price makes lower low but Stochastic makes higher low = hidden bullish divergence (and inverse).",
   signal(b){
     if(b.length<20)return null;
     const n=b.length-1;
     const k=stochArr(b,9);
     if(k[n]==null||k[n-5]==null)return null;
     // Look back 5 bars for swing comparison
     const priceLow5=Math.min(...b.slice(n-4,n+1).map(x=>x.l));
     const priceHigh5=Math.max(...b.slice(n-4,n+1).map(x=>x.h));
     const priceLow10=Math.min(...b.slice(n-9,n-4).map(x=>x.l));
     const priceHigh10=Math.max(...b.slice(n-9,n-4).map(x=>x.h));
     const kNow=k.slice(n-4,n+1).filter(v=>v!=null);
     const kPrev=k.slice(n-9,n-4).filter(v=>v!=null);
     if(!kNow.length||!kPrev.length)return null;
     const kLowNow=Math.min(...kNow),kLowPrev=Math.min(...kPrev);
     const kHighNow=Math.max(...kNow),kHighPrev=Math.max(...kPrev);
     // Bullish divergence: price lower low + stoch higher low
     if(priceLow5<priceLow10&&kLowNow>kLowPrev&&kLowNow<30)return"long";
     // Bearish divergence: price higher high + stoch lower high
     if(priceHigh5>priceHigh10&&kHighNow<kHighPrev&&kHighNow>70)return"short";
     return null;}},

  {id:"ParabolicSAR",name:"Parabolic SAR",type:"SAR Trend Reversal",rr:2.0,atrMult:1.5,confirm:true,
   sess:{ASIA:"SAR 0.02/0.2",LONDON:"SAR 0.02/0.2",NY:"SAR 0.02/0.2"},
   desc:"Trades the dot flip — when SAR flips from above to below price (long) or below to above (short).",
   signal(b){
     if(b.length<10)return null;
     const n=b.length-1;
     const sar=sarArr(b,0.02,0.2);
     if(sar[n]==null||sar[n-1]==null)return null;
     const wasAbove=sar[n-1]>b[n-1].c;
     const nowBelow=sar[n]<b[n].c;
     const wasBelow=sar[n-1]<b[n-1].c;
     const nowAbove=sar[n]>b[n].c;
     if(wasAbove&&nowBelow)return"long";   // SAR flipped below price
     if(wasBelow&&nowAbove)return"short";  // SAR flipped above price
     return null;}},

  {id:"ADXTrend",name:"ADX Trend",type:"ADX+EMA Filter",rr:3.5,atrMult:1.5,trend:true,
   sess:{ASIA:"ADX>20+EMA",LONDON:"ADX>25+EMA",NY:"ADX>25+EMA"},
   desc:"Only trades EMA 8/21 crosses when ADX confirms a real trend (>25 in London/NY, >20 in Asia).",
   signal(b){
     if(b.length<30)return null;
     const sess=getSessionET(b[b.length-1].t);
     const threshold=sess==="ASIA"?20:25;
     const c=b.map(x=>x.c),n=c.length-1;
     const adx=adxArr(b,14);
     if(adx[n]==null||adx[n]<threshold)return null; // filter out weak/ranging markets
     const f=ema(c,8),s=ema(c,21);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";
     if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";
     return null;}},

  {id:"IchimokuCloud",name:"Ichimoku Cloud",type:"Kumo Breakout",rr:4.0,atrMult:1.5,trend:true,
   sess:{ASIA:"Kumo break",LONDON:"Kumo break",NY:"Kumo break"},
   desc:"Price breaks out of the Ichimoku cloud (Senkou A/B). Only trades in direction of breakout.",
   signal(b){
     if(b.length<60)return null;
     const n=b.length-1;
     const ich=ichimokuArr(b);
     if(!ich[n]||ich[n].senkouA==null||ich[n].senkouB==null)return null;
     const top=Math.max(ich[n].senkouA,ich[n].senkouB);
     const bot=Math.min(ich[n].senkouA,ich[n].senkouB);
     const prev=ich[n-1];if(!prev||prev.senkouA==null)return null;
     const prevTop=Math.max(prev.senkouA,prev.senkouB);
     const prevBot=Math.min(prev.senkouA,prev.senkouB);
     const c=b[n].c,cp=b[n-1].c;
     // Breakout above cloud
     if(cp<=prevTop&&c>top)return"long";
     // Breakout below cloud
     if(cp>=prevBot&&c<bot)return"short";
     return null;}},
];

function mkBot(s,wv){return{uid:++uid,name:`${s.name} W${wv}`,strat:s,wave:wv,balance:50000,
  openTrades:{},closedTrades:[],wins:0,losses:0,killed:false,killReason:"",
  _sessWins:0,_sessLosses:0};}bots=STRATS.map(s=>mkBot(s,1));
const getPnl=b=>b.balance-50000;
const getWR=b=>{const t=b.wins+b.losses;return t?b.wins/t:0;};
function score(b){
  // Score = WR (80%) + P&L per trade (20% tiebreaker)
  // 100% WR is ~80pts. P&L adds up to 20pts based on avg $ per trade.
  // Avg $500/trade = full 20pts. Scales so early small profits still rank high.
  // No dependency on other bots — score only moves when THIS bot trades.
  const tot=b.wins+b.losses;
  if(tot===0)return 0;
  const wr=getWR(b);
  const avgPnl=getPnl(b)/tot;                        // avg $ per closed trade
  const pnlScore=Math.max(0,Math.min(1,avgPnl/500)); // $500 avg = 1.0
  return wr*0.80+pnlScore*0.20;
}
const live=()=>bots.filter(b=>!b.killed);
const bestBot=()=>{const ab=live();return ab.length?ab.reduce((b,x)=>score(x)>score(b)?x:b,ab[0]):null;};

function processBots(){
  if(!startupDone)return;

  // Reset per-cycle bar-close tracking (prevents double-close between processBots + checkLiveExits)
  bots.forEach(b=>{ b._barClosedCodes=new Set(); });
  computeT1Consensus(bs("ES"),bs("NQ"));

  // Process Tier 1 first, then Tier 2, then Tier 3 (so parents exist before micros)
  const orderedMkts=[...MKTS].sort((a,b)=>a.tier-b.tier);

  orderedMkts.forEach(mkt=>{
    const b=bs(mkt.code);if(!b||b.length<35)return;
    const atr=atrArr(b,14);
    const lastTs=processedTs[mkt.code]??0;
    let si=b.findIndex(bar=>bar.t>lastTs);
    if(si===-1||si>b.length-2)return;
    const ei=b.length-2;

    for(let i=si;i<=ei;i++){
      const bar=b[i];
      const sess=getSessionET(bar.t);
      const sessLabel=getSessionLabel(bar.t);

      // Skip maintenance break
      if(sess==="MAINT"){processedTs[mkt.code]=bar.t;continue;}

      // ── Session-boundary bot revival ─────────────────────────
      // When the primary session changes, revive all suspended bots with a clean slate.
      if(!mkt._lastSess)mkt._lastSess=sess;
      if(mkt._lastSess!==sess){
        mkt._lastSess=sess;
        const revived=[];
        bots.forEach(bot=>{
          if(!bot.killed)return;
          // Increment wave on revival — name updates to W2, W3, etc.
          bot.wave=(bot.wave||1)+1;
          bot.name=`${bot.strat.name} W${bot.wave}`;
          bot.killed=false;bot.killReason="";
          bot.balance=50000;
          bot.openTrades={};
          bot._sessWins=0;bot._sessLosses=0;
          revived.push(bot.name);
        });
        if(revived.length)addLog(`Session ${sess} — ${revived.length} bots revived (new wave)`,`wave`);
      }

      // ── Min ATR filter (improvement #4) ─────────────────────
      // Skip if current ATR < 50% of its 20-bar average (dead/choppy market).
      // Uses the pre-computed atr[] array — no recomputation per bar.
      const atr20slice=atr.slice(Math.max(0,i-19),i+1).filter(v=>v!=null);
      const avgATR=atr20slice.length?atr20slice.reduce((a,v)=>a+v,0)/atr20slice.length:0;
      const atrOK=atr[i]!=null&&(avgATR===0||atr[i]>=avgATR*0.5);

      // ── Session RR multiplier (improvement #6) ───────────────
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
            won?bot.wins++:bot.losses++;
            won?bot._sessWins++:bot._sessLosses++;
            totalClosed++;
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
            // Clear any pending signal for this market on close
            delete pendingSignals[`${bot.uid}_${mkt.code}`];
          }
        }else if(atrOK){
          const pKey=`${bot.uid}_${mkt.code}`;
          const rawSig=bot.strat.signal(b.slice(0,i+1));

          // ── 1-bar confirmation for oscillator strategies (improvement #5) ──
          // Crossover signals only fire on the exact crossover bar then return null.
          // So confirmation is: store signal on bar N, enter on bar N+1 regardless
          // of whether rawSig is still active — the crossover already happened.
          let sig=null;
          if(bot.strat.confirm){
            const pending=pendingSignals[pKey];
            if(pending){
              // A signal was stored last bar — enter now (1-bar delay confirmation)
              sig=pending.sig;
              delete pendingSignals[pKey];
            }
            if(rawSig&&!pending){
              // New signal this bar — store for entry next bar
              pendingSignals[pKey]={sig:rawSig,barT:bar.t};
            }
          }else{
            sig=rawSig; // trend strategies fire on the signal bar directly
          }

          if(sig&&atr[i]!=null){
            const entry=snap(bar.c,mkt.tick);
            // RR: strategy base × session multiplier (no tier cap)
            // Stop: ATR × atrMult × confidence — restores proportional sizing per market
            const c=mkt.conf??1.0;
            const rrMult=Math.max(1.0,bot.strat.rr*sessRRMult);
            const dist=snap(Math.max(atr[i]*bot.strat.atrMult*c,2*mkt.tick),mkt.tick);
            const sl=snap(sig==="long"?entry-dist:entry+dist,mkt.tick);
            const tp=snap(sig==="long"?entry+dist*rrMult:entry-dist*rrMult,mkt.tick);
            bot.openTrades[mkt.code]={dir:sig,entry,sl,tp,openT:bar.t,atr:atr[i],sess,sessLabel,rr:rrMult,conf:c};
          }
        }
      });

      // Adaptive bot
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
          // ── Consecutive loss tracking (improvement #3) ──────────
          if(won){
            adaptiveBot.consecLosses=0; // reset streak on any win
            if(adaptiveBot.apexPaused){adaptiveBot.apexPaused=false;} // win clears pause too
          }else{
            adaptiveBot.consecLosses++;
            if(adaptiveBot.consecLosses>=3){
              adaptiveBot.apexPaused=true;
              addLog(`AI PAUSED — 3 consecutive losses, waiting for regime shift`,"kill");
            }
          }
          const rec={code:mkt.code,col:mkt.col,botName:"Apex AI",stratId:"ADAPTIVE",
            dir:at.dir,entry:at.entry,exitPx:ex,pts:Math.round(pts*100)/100,
            pnlUSD:pnl,won,sl:at.sl,tp:at.tp,openT:at.openT,closeT:bar.t,
            atr:at.atr,sess:at.sess,sessLabel:at.sessLabel||at.sess,conf:at.conf};
          adaptiveBot.closedTrades=[...adaptiveBot.closedTrades,rec]; // no cap — kept indefinitely
          allClosed=[rec,...allClosed].slice(0,5000);
          delete adaptiveBot.openTrades[mkt.code];
          recordPerfAll("ADAPTIVE",at.openT,mkt.code,won,pnl);
          document.getElementById("tcl").textContent=totalClosed;
          addLog(`AI ${mkt.code} ${won?"WIN":"LOSS"} ${f$(pnl)} [${at.sessLabel||at.sess}] conf:${((at.conf||0)*100).toFixed(0)}%`,won?"win":"loss");
        }
      }else if(atr[i]!=null){
        // AI only trades when ALL 4 sessions have ≥1 qualified strategy (WR>0.50).
        const aiHasPos=Object.keys(adaptiveBot.openTrades).length>0;
        if(!aiHasPos&&aiFullyUnlocked()){
          const res=getAdaptiveSig(mkt.code,b.slice(0,i+1),sess,atr[i]);
          if(res){
            const entry=snap(bar.c,mkt.tick);
            const mkConf=mkt.conf??1.0;
            const combined=Math.min(1.0,mkConf*res.conf);
            const rrFinal=combined>=0.85?3.5:combined>=0.75?3.0:combined>=0.65?2.5:2.0;
            const dist=snap(Math.max(atr[i]*1.2*combined,2*mkt.tick),mkt.tick);
            const sl=snap(res.sig==="long"?entry-dist:entry+dist,mkt.tick);
            const tp=snap(res.sig==="long"?entry+dist*rrFinal:entry-dist*rrFinal,mkt.tick);
            adaptiveBot.openTrades[mkt.code]={dir:res.sig,entry,sl,tp,openT:bar.t,
              atr:atr[i],sess,sessLabel,conf:combined,rr:rrFinal,votes:res.votes,
              stratUsed:res.strat?.s?.id||"CONSENSUS"};
          }
        }
      }

      processedTs[mkt.code]=bar.t;
    }
  });

  // ── Kill check: suspend when WR<25% after 20 trades THIS session ────────
  bots.forEach(bot=>{
    if(bot.killed)return;
    const sw=bot._sessWins??bot.wins, sl=bot._sessLosses??bot.losses;
    const tot=sw+sl;
    if(tot>=20&&sw/tot<0.25){
      Object.entries(bot.openTrades).forEach(([code,t])=>{
        const mkt=MKTS.find(m=>m.code===code);if(!mkt)return;
        const ex=snap(liveQ[code]?.price||bs(code).at(-1)?.c||t.entry,mkt.tick);
        const pts=t.dir==="long"?ex-t.entry:t.entry-ex;
        const pnl=Math.round(pts*mkt.ptVal*100)/100;
        const won=pts>0;
        won?bot.wins++:bot.losses++;
        won?bot._sessWins++:bot._sessLosses++;
        totalClosed++;
        const rec={code,col:mkt.col,botName:bot.name,stratId:bot.strat.id,
          dir:t.dir,entry:t.entry,exitPx:ex,pts:Math.round(pts*100)/100,
          pnlUSD:pnl,won,sl:t.sl,tp:t.tp,openT:t.openT,closeT:Date.now(),atr:t.atr,sess:t.sess,sessLabel:t.sessLabel||t.sess};
        bot.closedTrades=[...bot.closedTrades.slice(-199),rec];
        allClosed=[rec,...allClosed].slice(0,5000);
        recordPerfAll(bot.strat.id,t.openT,code,won,pnl);
      });
      bot.openTrades={};
      bot.killed=true;bot.killReason="WR<25% (revives next session)";
      addLog(`${bot.name} SUSPENDED (WR<25%) — revives at next session`,"kill");
    }
  });

  document.getElementById("ta").textContent=live().length;
}


// ── FAST LOOP: live quotes every 1.5s ────────────────────────
async function refreshQuote(){
  try{
    const r=await fetch("/api/quote",{signal:AbortSignal.timeout(5000)});
    const d=await r.json();
    const now=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
    document.getElementById("qtag").textContent="Q "+now;
    MKTS.forEach(m=>{
      const q=d[m.code];if(!q)return;
      liveQ[m.code]=q;
      // Update forming candle
      const b=candles[m.code];
      if(b?.length){
        const last=b[b.length-1];
        if(q.price!==last.c||q.price>last.h||q.price<last.l){
          last.c=q.price;
          if(q.price>last.h)last.h=q.price;
          if(q.price<last.l)last.l=q.price;
          dirty[m.id]=true;
        }
      }
      // Top bar price
      const prev=prevPx[m.id];
      const pel=document.getElementById("p"+m.id);
      if(pel){
        pel.textContent=q.price.toFixed(2);
        if(prev!=null&&q.price!==prev){
          pel.style.color=q.price>prev?"var(--up)":"var(--dn)";
          clearTimeout(pel._ft);pel._ft=setTimeout(()=>{pel.style.color="var(--tx)";},500);
        }
      }
      prevPx[m.id]=q.price;
      // Change
      const cel=document.getElementById("c"+m.id);
      if(cel){
        const s=q.change>=0?"+":"";
        cel.textContent=`${s}${q.change.toFixed(2)} (${s}${q.changePct.toFixed(2)}%)`;
        cel.style.color=q.change>=0?"var(--up)":"var(--dn)";
      }
      // Day H/L
      const hlel=document.getElementById("hl"+m.id);
      if(hlel&&q.dayHigh){
        hlel.innerHTML=`<span style="color:#26a69a70">H:${q.dayHigh.toFixed(2)}</span> <span style="color:#ef535070">L:${q.dayLow.toFixed(2)}</span>`;
      }
      // Chart header price
      // Update forming bar's h/l with live price so wick-based exit checks work
      const bars=bs(m.code);
      if(bars.length){
        const lb=bars[bars.length-1];
        if(q.price>lb.h)lb.h=q.price;
        if(q.price<lb.l)lb.l=q.price;
        dirty[m.id]=true; // redraw chart to show updated wick
      }
      const cpx=document.getElementById("cpx-"+m.id);
      if(cpx){
        const p2=cpx._prev;
        cpx.textContent=q.price.toFixed(2);
        if(p2!=null&&q.price!==p2){
          cpx.style.color=q.price>p2?"var(--up)":"var(--dn)";
          clearTimeout(cpx._ft);cpx._ft=setTimeout(()=>{cpx.style.color="var(--tx)";},500);
        }
        cpx._prev=q.price;
      }
    });
  checkLiveExits();
  }catch(e){console.warn("quote:",e.message);}
}

// ── LIVE EXIT CHECK: closes trades using live price AND forming bar wicks ──
// processBots skips the last (forming) bar, so wick hits on the live bar
// are only caught here. We check both the current quote price AND the
// forming bar's high/low so wick spikes that retrace are still caught.
function checkLiveExits(){
  [...bots.filter(b=>!b.killed),adaptiveBot].forEach(bot=>{
    Object.entries(bot.openTrades).forEach(([code,t])=>{
      const q=liveQ[code];if(!q)return;
      const mkt=MKTS.find(m=>m.code===code);if(!mkt)return;
      const p=q.price;
      // Also get the forming bar's wick range (last candle in array)
      const bars=bs(code);
      const liveBar=bars.length?bars[bars.length-1]:null;
      const barH=liveBar?Math.max(liveBar.h,p):p; // wick high = max(bar.h, current price)
      const barL=liveBar?Math.min(liveBar.l,p):p; // wick low  = min(bar.l, current price)
      let closed=false,ex=0,won=false;
      if(t.dir==="long"){
        // Both TP and SL hit same bar — assume SL hit first (worst case, conservative)
        if(barH>=t.tp&&barL<=t.sl){ex=t.sl;closed=true;won=false;}
        else if(barH>=t.tp){ex=t.tp;closed=true;won=true;}
        else if(barL<=t.sl){ex=t.sl;closed=true;won=false;}
      }else{
        if(barL<=t.tp&&barH>=t.sl){ex=t.sl;closed=true;won=false;}
        else if(barL<=t.tp){ex=t.tp;closed=true;won=true;}
        else if(barH>=t.sl){ex=t.sl;closed=true;won=false;}
      }
      // Guard: if processBots already closed this market this cycle, skip
      if(closed&&bot._barClosedCodes?.has(code)){closed=false;}
      if(closed){
        ex=snap(ex,mkt.tick);
        const pts=t.dir==="long"?ex-t.entry:t.entry-ex;
        const pnl=Math.round(pts*mkt.ptVal*100)/100;
        const isAI=bot===adaptiveBot;
        if(!isAI)bot.balance=Math.round((bot.balance+pnl)*100)/100;
        won?bot.wins++:bot.losses++;totalClosed++;
        const rec={code,col:mkt.col,botName:bot.name,stratId:bot.strat?.id||"ADAPTIVE",
          dir:t.dir,entry:t.entry,exitPx:ex,pts:Math.round(pts*100)/100,
          pnlUSD:pnl,won,sl:t.sl,tp:t.tp,openT:t.openT,closeT:Date.now(),
          atr:t.atr,sess:t.sess,sessLabel:t.sessLabel||t.sess,live:true};
        bot.closedTrades=[...bot.closedTrades.slice(-199),rec];
        allClosed=[rec,...allClosed].slice(0,5000);
        delete bot.openTrades[code];
        recordPerfAll(rec.stratId,t.openT,code,won,pnl);
        document.getElementById("tcl").textContent=totalClosed;
        const tag=isAI?"AI ":"";
        addLog(`${tag}${code} ${bot.name} ${won?"WIN":"LOSS"} ${f$(pnl)} [live]`,won?"win":"loss");
        const mktObj=MKTS.find(m=>m.code===code);if(mktObj)dirty[mktObj.id]=true;
      }
    });
  });
}

// ── SLOW LOOP: full OHLC every 30s ────────────────────────────
async function refreshFull(){
  const tag=document.getElementById("ltag");tag.textContent="FETCHING";tag.className="";
  let liveN=0;
  await Promise.allSettled(MKTS.map(async mkt=>{
    try{
      const r=await fetch(`/api/candles?code=${mkt.code}&iv=${iv}`,{signal:AbortSignal.timeout(30000)});
      const d=await r.json();
      if(d.live&&d.candles?.length>10){
        candles[mkt.code]=d.candles;sources[mkt.code]=d.source||"?";liveN++;dirty[mkt.id]=true;
      }
    }catch(e){console.warn(mkt.code,e.message);}
  }));
  isLive=liveN>0;
  tag.textContent=isLive?`LIVE ${liveN}/8`:Object.keys(candles).length?"STALE":"CLOSED";
  tag.className=isLive?"live":!Object.keys(candles).length?"closed":"";
  document.getElementById("tu").textContent=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
  document.getElementById("tbars").textContent=candles["ES"]?.length||"--";
  if(!startupDone&&isLive){
    // Seed from NOW — do not replay history. Replaying causes fake wins/losses on startup.
    MKTS.forEach(m=>{const b=bs(m.code);if(b?.length)processedTs[m.code]=b[b.length-1].t;});
    startupDone=true;
    addLog("Live data loaded -- bots watching from NOW across all 8 markets","info");
  }
  processBots();renderLeft();renderAllTrades();renderRight();
}

// ── Sound: distinct tones per position ───────────────────────
const _audioCtx={ctx:null};
function _getACtx(){
  if(!_audioCtx.ctx)try{_audioCtx.ctx=new(window.AudioContext||window.webkitAudioContext)();}catch(e){}
  return _audioCtx.ctx;
}
function playOpenSound(idx){
  // Each position gets a different pitch so you can hear multiple opens
  const ctx=_getACtx();if(!ctx)return;
  const freqs=[[880,660],[1046,784],[1318,987],[1568,1174],[698,523],[932,698],[1109,831],[784,587]];
  const[hi,lo]=freqs[idx%freqs.length];
  [[hi,0,0.10],[lo,0.11,0.24]].forEach(([freq,start,end])=>{
    try{
      const o=ctx.createOscillator(),g=ctx.createGain();
      o.connect(g);g.connect(ctx.destination);
      o.type="sine";o.frequency.setValueAtTime(freq,ctx.currentTime+start);
      g.gain.setValueAtTime(0,ctx.currentTime+start);
      g.gain.linearRampToValueAtTime(0.18,ctx.currentTime+start+0.02);
      g.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+end);
      o.start(ctx.currentTime+start);o.stop(ctx.currentTime+end);
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
            transition:color .15s;user-select:none">⤢</span>
        </div>
      </div>
      <div class="cw" id="cw-${m.id}"><canvas id="cv-${m.id}"></canvas></div>
      <div class="sb" id="sb-${m.id}"><span style="color:var(--tx3);font-size:7px">watching...</span></div>
    </div>`).join("");
  MKTS.forEach(m=>{
    cvMap[m.id]=document.getElementById("cv-"+m.id);
    new ResizeObserver(()=>{dirty[m.id]=true;}).observe(document.getElementById("cw-"+m.id));
  });

  // ── Tooltip + crosshair mouse listeners ──────────────────────
  const ttEl=document.getElementById("chart-tooltip");
  MKTS.forEach(m=>{
    const cw=document.getElementById("cw-"+m.id);if(!cw)return;
    cw.addEventListener("mousemove",e=>{
      const b=bs(m.code);if(!b?.length){ttEl.style.display="none";return;}
      const rect=cw.getBoundingClientRect();
      const mx=e.clientX-rect.left;
      const W=rect.width;
      const PL=2,PR=62,CW2=W-PL-PR;
      const maxC=Math.max(20,Math.floor(CW2/7));
      const vis=b.slice(-maxC),n=vis.length;
      const gap=CW2/n;
      // Use nearest-center: bars are drawn centered at PL+i*gap+gap/2,
      // so divide by gap after subtracting the half-gap offset.
      // Math.floor((mx-PL)/gap) selects by left-edge and drifts one bar
      // ahead when the mouse is in the right half of a candle's slot.
      const idx=Math.max(0,Math.min(n-1,Math.round((mx-PL-gap/2)/gap)));
      if(hoverState[m.id]!==idx){hoverState[m.id]=idx;dirty[m.id]=true;}
      const bar=vis[idx];
      const dec=m.tick<1?2:0;
      const dt=new Date(bar.t);
      const ts2=iv==="1H"
        ?dt.toLocaleDateString([],{month:"short",day:"numeric",year:"2-digit"})
        :dt.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
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
      if(tx+150>window.innerWidth)tx=e.clientX-166;
      if(ty+160>window.innerHeight)ty=e.clientY-160;
      ttEl.style.left=tx+"px";ttEl.style.top=ty+"px";
    });
    cw.addEventListener("mouseleave",()=>{
      ttEl.style.display="none";
      hoverState[m.id]=null;dirty[m.id]=true;
    });

    // ── Fullscreen expand button ──────────────────────────────
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
  if(_W&&_H){W=_W;H=_H;}
  else{
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
    ctx.fillText(sources[mkt.code]||"Yahoo Finance",W/2,H/2+8);
    return;
  }

  const PL=2,PR=62,PT=6,PB=14,CW=W-PL-PR,VOLH=Math.round((H-PT-PB)*0.16),CH=H-PT-PB-VOLH-2;
  const maxC=Math.max(20,Math.floor(CW/7));
  const vis=b.slice(-maxC),n=vis.length;
  if(n<2)return;

  const gap=CW/n,bw=Math.max(1.2,gap*0.72),toX=i=>PL+i*gap+gap/2;

  let hiP=Math.max(...vis.map(c=>c.h)),loP=Math.min(...vis.map(c=>c.l));
  const rawRng=hiP-loP||hiP*0.01;
  hiP+=rawRng*0.08;loP-=rawRng*0.04;
  const rng=hiP-loP||1,toY=p=>PT+CH*(1-(p-loP)/rng);

  // Grid
  const rawStep=rawRng/5;
  const mag=Math.pow(10,Math.floor(Math.log10(rawStep)));
  let step=mag;
  for(const ns of[1,2,2.5,5,10]){if(mag*ns>=rawStep){step=mag*ns;break;}}
  ctx.font="7px 'Share Tech Mono'";ctx.textAlign="left";
  for(let pv=Math.ceil(loP/step)*step;pv<=hiP;pv=Math.round((pv+step)*1e6)/1e6){
    const y=toY(pv);if(y<PT||y>PT+CH)continue;
    ctx.strokeStyle="#1e222d";ctx.lineWidth=1;ctx.setLineDash([]);
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();
    ctx.fillStyle="#131722";ctx.fillRect(PL+CW+1,y-7,PR-2,12);
    ctx.fillStyle="#787b86";ctx.fillText(pv.toFixed(mkt.tick<1?2:0),PL+CW+4,y+3);
  }

  // Session shading — correct EST times, DST-aware via etHour()
  // Sydney 17–02 (5pm–2am) | Asia/Tokyo 19–04 (7pm–4am)
  // London 03–12 (3am–12pm) | NY 08–17 (8am–5pm) | Maintenance 17–18 (grey)
  const SESSION_DEFS=[
    {name:"SYD", startH:18,endH:2, wrap:true, col:"#ffd70010",lbl:"#ffd70055"},
    {name:"ASIA",startH:19,endH:4, wrap:true, col:"#8080ff13",lbl:"#8080ff70"},
    {name:"LON", startH:3, endH:12,wrap:false,col:"#f0903013",lbl:"#f0903070"},
    {name:"NY",  startH:8, endH:17,wrap:false,col:"#18c86013",lbl:"#18c86070"},
    {name:"MAINT",startH:17,endH:18,wrap:false,col:"#4c525e18",lbl:"#4c525e80"},
  ];
  // Pre-compute which sessions are active per bar
  const barSess=vis.map(c=>{
    const h=etHour(c.t);
    return SESSION_DEFS.filter(s=>s.wrap?(h>=s.startH||h<s.endH):(h>=s.startH&&h<s.endH));
  });
  // Draw shading first (background layers)
  SESSION_DEFS.forEach(s=>{
    vis.forEach((c,i)=>{
      if(!barSess[i].includes(s))return;
      const x0=Math.max(PL,toX(i)-gap/2);
      const w=Math.min(gap,PL+CW-x0);
      if(w<=0)return;
      ctx.fillStyle=s.col;
      ctx.fillRect(x0,PT,w,CH);
    });
  });
  // Draw session labels at the first bar of each session block
  const drawnLabel=new Set();
  vis.forEach((c,i)=>{
    barSess[i].forEach((s,si)=>{
      const key=s.name+"|"+(i>0&&barSess[i-1].includes(s)?"":"new");
      if(i>0&&barSess[i-1].includes(s))return; // not a new session start
      if(drawnLabel.has(s.name+"@"+i))return;
      drawnLabel.add(s.name+"@"+i);
      const x0=Math.max(PL,toX(i)-gap/2)+2;
      ctx.fillStyle=s.lbl;ctx.font="bold 6px 'Share Tech Mono'";ctx.textAlign="left";
      ctx.fillText(s.name,x0,PT+7+si*8);
    });
  });

  // EMAs
  const closes=vis.map(c=>c.c);
  [[9,"#f5a62380",1.2],[21,"#2962ff60",1.2]].forEach(([p,col,lw])=>{
    const vals=ema(closes,p);
    ctx.strokeStyle=col;ctx.lineWidth=lw;ctx.beginPath();let st=false;
    vals.forEach((v,i)=>{if(v==null)return;const x=toX(i),y=toY(v);st?ctx.lineTo(x,y):(ctx.moveTo(x,y),st=true);});
    ctx.stroke();
  });

  // Volume
  const volBase=PT+CH+2,maxVol=Math.max(...vis.map(c=>c.v||0))||1;
  vis.forEach((c,i)=>{
    const x=toX(i),vPct=(c.v||0)/maxVol,vh=Math.max(1,vPct*VOLH);
    ctx.fillStyle=c.c>=c.o?"#26a69a22":"#ef535022";
    ctx.fillRect(x-bw/2,volBase+VOLH-vh,bw,vh);
  });

  // Candles
  vis.forEach((c,i)=>{
    const x=toX(i),col=c.c>=c.o?"#26a69a":"#ef5350";
    ctx.globalAlpha=i===n-1?0.75:1;
    ctx.strokeStyle=col;ctx.lineWidth=1;ctx.setLineDash([]);
    ctx.beginPath();ctx.moveTo(x,toY(c.h));ctx.lineTo(x,toY(c.l));ctx.stroke();
    const bt=toY(Math.max(c.o,c.c)),bb2=toY(Math.min(c.o,c.c)),bh=Math.max(1.2,bb2-bt);
    if(bh<=1.2){ctx.strokeStyle=col;ctx.lineWidth=1.2;
      ctx.beginPath();ctx.moveTo(x-bw/2,toY(c.c));ctx.lineTo(x+bw/2,toY(c.c));ctx.stroke();}
    else{ctx.fillStyle=col;ctx.fillRect(x-bw/2,bt,bw,bh);}
    ctx.globalAlpha=1;
  });

  // Hover crosshair
  const hIdx=hoverState[mkt.id];
  if(hIdx!=null&&hIdx>=0&&hIdx<n){
    const hx=toX(hIdx);
    ctx.setLineDash([2,3]);ctx.strokeStyle="#d1d4dc28";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(hx,PT);ctx.lineTo(hx,PT+CH);ctx.stroke();
    ctx.setLineDash([]);
    const hc=vis[hIdx];
    const hbt=toY(Math.max(hc.o,hc.c)),hbb=toY(Math.min(hc.o,hc.c));
    const hhh=Math.max(2,hbb-hbt);
    ctx.strokeStyle="#ffffff30";ctx.lineWidth=1;
    ctx.strokeRect(hx-bw/2,hbt,bw,hhh);
  }

  // Best bot SL/Entry/TP lines
  const bb=bestBot();
  if(bb){const tr=bb.openTrades[mkt.code];if(tr){
    const lvl=(price,col,dash,lbl)=>{
      if(price<loP||price>hiP)return;
      const y=toY(price);
      ctx.setLineDash(dash);ctx.strokeStyle=col;ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=col;ctx.font="bold 6.5px 'Share Tech Mono'";ctx.textAlign="left";
      const dec=mkt.tick<1?2:0;
      ctx.fillText(lbl+" "+price.toFixed(dec),PL+CW+4,y+2.5);
    };
    lvl(tr.tp,"#26a69a",[5,3],"TP");lvl(tr.entry,"#787b86",[2,4],"E");lvl(tr.sl,"#ef5350",[5,3],"SL");
  }}

  // Live price tag
  const last=closes.at(-1);
  if(last!=null){
    const y=toY(last),isUp=(liveQ[mkt.code]?.change??0)>=0,tagCol=isUp?"#26a69a":"#ef5350";
    ctx.setLineDash([3,4]);ctx.strokeStyle="#2a2e3960";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();ctx.setLineDash([]);
    const bx=PL+CW+1,bxw=PR-2,byy=y-8;
    ctx.fillStyle=tagCol;
    if(ctx.roundRect){ctx.beginPath();ctx.roundRect(bx,byy,bxw,16,2);ctx.fill();}
    else ctx.fillRect(bx,byy,bxw,16);
    ctx.fillStyle="#fff";ctx.font="bold 8px 'Share Tech Mono'";ctx.textAlign="center";
    const dec=mkt.tick<1?2:0;
    ctx.fillText(last.toFixed(dec),bx+bxw/2,y+3);
  }

  // Time axis
  ctx.fillStyle="#4c525e";ctx.font="6.5px 'Share Tech Mono'";ctx.textAlign="center";
  const fmtT=ts=>{const d=new Date(ts);return iv==="1H"?d.toLocaleDateString([],{month:"short",day:"numeric"}):d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});};
  const timeY=H-2,usedX=[];
  [0,Math.floor(n*.25),Math.floor(n*.5),Math.floor(n*.75),n-1].forEach(i=>{
    if(i<0||i>=n||!vis[i])return;
    const x=toX(i);
    if(usedX.some(ux=>Math.abs(ux-x)<44))return;
    usedX.push(x);
    ctx.strokeStyle="#1e222d30";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,PT);ctx.lineTo(x,volBase+VOLH);ctx.stroke();
    ctx.fillStyle="#4c525e";ctx.fillText(fmtT(vis[i].t),x,timeY);
  });
}

function updateSessionClock(){
  const h=etHour();
  const etH=Math.floor(h), etM=new Date().getUTCMinutes();

  // Correct session windows (EST, DST-aware):
  // Sydney  5pm–2am | Tokyo/Asia 7pm–4am | London 3am–12pm | NY 8am–5pm
  // Maintenance break 5pm–6pm (no trading)
  const isMaint =_inMaint(h);
  const inNY    =_inNY(h);
  const inLondon=_inLondon(h);
  const inAsia  =_inAsia(h);
  const inSydney=_inSydney(h);

  document.getElementById("sess-ny").classList.toggle("active",inNY);
  document.getElementById("sess-london").classList.toggle("active",inLondon);
  document.getElementById("sess-asia").classList.toggle("active",inAsia);
  const syd=document.getElementById("sess-sydney");
  if(syd)syd.classList.toggle("active",inSydney);

  const dH=(etH%12)||12,dM=String(etM).padStart(2,"0"),ampm=etH<12?"AM":"PM";
  const activeSess=[];
  if(isMaint)activeSess.push("BREAK");
  else{
    if(inNY)    activeSess.push("NY");
    if(inLondon)activeSess.push("LON");
    if(inAsia)  activeSess.push("ASIA");
    if(inSydney)activeSess.push("SYD");
  }
  if(!activeSess.length)activeSess.push("--");
  const el=document.getElementById("sess-et");
  if(el)el.textContent=`ET ${dH}:${dM}${ampm} · ${activeSess.join("+")}`;
}

function rafLoop(){
  MKTS.forEach(m=>{if(dirty[m.id]){drawChart(m);dirty[m.id]=false;}});
  requestAnimationFrame(rafLoop);
}

// ═══════════════════════════════════════════════════════════════
// ── FULLSCREEN CHART ─────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════
let fsMkt=null,fsRafId=null,fsCanvas=null;
const fsOverlay=()=>document.getElementById("fs-overlay");
const fsWrap=()=>document.getElementById("fs-canvas-wrap");

function openFullscreen(mkt){
  fsMkt=mkt;
  const ov=fsOverlay();ov.classList.add("open");
  document.getElementById("fs-sym").textContent=mkt.code;
  document.getElementById("fs-sym").style.color=mkt.col;
  if(!fsCanvas){fsCanvas=document.createElement("canvas");fsWrap().appendChild(fsCanvas);}
  new ResizeObserver(drawFsChart).observe(fsWrap());
  drawFsChart();
  if(fsRafId)cancelAnimationFrame(fsRafId);
  (function loop(){if(!fsMkt)return;drawFsChart();fsRafId=requestAnimationFrame(loop);})();
}

function closeFullscreen(){
  fsMkt=null;fsOverlay().classList.remove("open");
  if(fsRafId){cancelAnimationFrame(fsRafId);fsRafId=null;}
}

function drawFsChart(){
  if(!fsMkt||!fsCanvas)return;
  const wrap=fsWrap();
  const dpr=window.devicePixelRatio||1;
  const W=wrap.clientWidth,H=wrap.clientHeight;
  if(W<20||H<20)return;
  fsCanvas.width=Math.round(W*dpr);fsCanvas.height=Math.round(H*dpr);
  fsCanvas.style.width=W+"px";fsCanvas.style.height=H+"px";
  drawChart(fsMkt,fsCanvas,W,H);
  const q=liveQ[fsMkt.code];
  if(q){
    const dec=fsMkt.tick<1?2:0;
    const px=document.getElementById("fs-price");
    px.textContent=q.price.toFixed(dec);
    px.style.color=q.change>=0?"#26a69a":"#ef5350";
    const chg=document.getElementById("fs-chg");
    const s=q.change>=0?"+":"";
    chg.textContent=`${s}${q.change.toFixed(dec)} (${s}${q.changePct.toFixed(2)}%)`;
    chg.style.color=q.change>=0?"#26a69a":"#ef5350";
  }
  renderFsPositions();
}

function renderFsPositions(){
  if(!fsMkt)return;
  const bar=document.getElementById("fs-positions");if(!bar)return;
  const m=fsMkt;
  const dec=m.tick<1?2:0;

  // Collect all open trades on this market from every bot + AI
  const trades=[];
  [...bots.filter(b=>!b.killed),adaptiveBot].forEach(bot=>{
    const t=bot.openTrades[m.code];if(!t)return;
    const rawCur=bs(m.code).at(-1)?.c??t.entry;
    const cur=t.dir==="long"
      ?Math.max(t.sl,Math.min(t.tp,rawCur))
      :Math.min(t.sl,Math.max(t.tp,rawCur));
    const pts=t.dir==="long"?cur-t.entry:t.entry-cur;
    const unr=Math.round(pts*m.ptVal*100)/100;
    const isAI=bot===adaptiveBot;
    trades.push({bot,t,unr,isAI,cur});
  });

  if(!trades.length){
    bar.classList.remove("has-trades");
    bar.innerHTML="";
    return;
  }
  bar.classList.add("has-trades");

  // Sort by unrealized P&L descending
  trades.sort((a,b2)=>b2.unr-a.unr);

  bar.innerHTML=trades.map(({bot,t,unr,isAI})=>{
    const sess=t.sessLabel||t.sess||"--";
    const ss=SESS_STYLE[primarySess(sess)]||SESS_STYLE.NY;
    const slDist=Math.abs(t.entry-t.sl).toFixed(dec);
    const tpDist=Math.abs(t.tp-t.entry).toFixed(dec);
    const isLong=t.dir==="long";
    const botLabel=isAI?"⬡ Apex AI":bot.name;
    const stratLabel=isAI
      ?(STRATS.find(s=>s.id===t.stratUsed)?.name||"dominant")
      :bot.strat.name;
    return`<div class="fs-pos-card ${isLong?"long-card":"short-card"}">
      <div class="fs-pos-top">
        <span class="fs-pos-dir ${isLong?"long":"short"}">${isLong?"LONG ▲":"SHORT ▼"}</span>
        <span style="font-size:6px;padding:1px 5px;border-radius:2px;
          color:${ss.col};background:${ss.bg};border:1px solid ${ss.border}">${sess}</span>
      </div>
      <div class="fs-pos-bot">${botLabel} · ${stratLabel}</div>
      <div class="fs-pos-levels">
        <div class="fs-pos-lv" style="border:1px solid #26a69a30">
          <div class="fs-pos-lv-lbl" style="color:#26a69a">TP</div>
          <div class="fs-pos-lv-val" style="color:#26a69a">${t.tp.toFixed(dec)}</div>
          <div style="font-size:5px;color:#26a69a60">+${tpDist}</div>
        </div>
        <div class="fs-pos-lv" style="border:1px solid #d0e0ff20">
          <div class="fs-pos-lv-lbl" style="color:var(--tx2)">ENTRY</div>
          <div class="fs-pos-lv-val" style="color:#dce8ff">${t.entry.toFixed(dec)}</div>
          <div style="font-size:5px;color:var(--tx4)">${fTs(t.openT)}</div>
        </div>
        <div class="fs-pos-lv" style="border:1px solid #ef535030">
          <div class="fs-pos-lv-lbl" style="color:#ef5350">SL</div>
          <div class="fs-pos-lv-val" style="color:#ef5350">${t.sl.toFixed(dec)}</div>
          <div style="font-size:5px;color:#ef535060">-${slDist}</div>
        </div>
      </div>
      <div class="fs-pos-unr" style="color:${clr(unr)}">${f$(unr)}</div>
      <div class="fs-pos-meta">
        <span>RR ${(t.rr||2).toFixed(1)}:1</span>
        <span>ATR ${t.atr?.toFixed(2)??'--'}</span>
        <span>conf ${((t.conf||0)*100).toFixed(0)}%</span>
      </div>
    </div>`;
  }).join("")+
  // Summary chip at the end if >1 trade
  (trades.length>1?`<div style="display:inline-flex;flex-direction:column;justify-content:center;
    align-items:center;min-width:80px;padding:0 12px;gap:4px;flex-shrink:0">
    <div style="font-size:7px;color:var(--tx3)">${trades.length} positions</div>
    <div style="font-family:'Orbitron',sans-serif;font-size:12px;font-weight:700;
      color:${clr(trades.reduce((s,x)=>s+x.unr,0))}">${f$(trades.reduce((s,x)=>s+x.unr,0))}</div>
    <div style="font-size:6px;color:var(--tx3)">total unrealized</div>
  </div>`:"");
}

document.getElementById("fs-close").addEventListener("click",closeFullscreen);
document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeFullscreen();closeStratModal();}});

// ═══════════════════════════════════════════════════════════════
// ── STRATEGY TRADES MODAL ────────────────────────────────────
// ═══════════════════════════════════════════════════════════════
function openStratModal(bot){
  if(!bot)return;
  document.getElementById("strat-modal-title").textContent=bot.name;
  const tot=bot.wins+bot.losses;
  const wr=tot?(bot.wins/tot*100).toFixed(1)+"%":"--";
  const pnl=bot.closedTrades.reduce((s,t)=>s+(t.pnlUSD||0),0);
  const avgPnl=tot?pnl/tot:0;
  document.getElementById("strat-modal-sub").textContent=
    `${bot.strat.type} · RR ${bot.strat.rr}:1 · Wave ${bot.wave}`;
  document.getElementById("strat-modal-stats").innerHTML=`
    <div class="sm-stat"><span>Trades</span><b style="color:var(--tx)">${tot}</b></div>
    <div class="sm-stat"><span>Win Rate</span><b style="color:${bot.wins/Math.max(tot,1)>=0.5?"#26a69a":"#ef5350"}">${wr}</b></div>
    <div class="sm-stat"><span>W / L</span><b style="color:var(--tx2)">${bot.wins} / ${bot.losses}</b></div>
    <div class="sm-stat"><span>Net P&L</span><b style="color:${clr(pnl)}">${f$(pnl)}</b></div>
    <div class="sm-stat"><span>Avg/Trade</span><b style="color:${clr(avgPnl)}">${f$(avgPnl)}</b></div>
    <div class="sm-stat"><span>Balance</span><b style="color:${clr(bot.balance-50000)}">${"$"+bot.balance.toFixed(2)}</b></div>`;
  const seen=new Set(),trades=[];
  const addT=t=>{const k=`${t.openT??0}|${t.entry??0}|${t.code}`;if(!seen.has(k)){seen.add(k);trades.push(t);}};
  bot.closedTrades.forEach(addT);
  allClosed.filter(t=>t.botName===bot.name).forEach(addT);
  trades.sort((a,b2)=>(b2.closeT||b2.openT)-(a.closeT||a.openT));
  document.getElementById("strat-modal-tbody").innerHTML=trades.length
    ?trades.map(t=>{
        const mkt=MKTS.find(m=>m.code===t.code);
        const dec=mkt?.tick<1?2:0;
        const _sl=t.sessLabel||t.sess||"NY";const ss2=SESS_STYLE[primarySess(_sl)]||SESS_STYLE.NY;
        return`<tr style="background:${t.won?"#26a69a08":"#ef535008"}">
          <td><b style="color:${mkt?.col||"#fff"}">${t.code}</b></td>
          <td style="color:${ss2?.col||"var(--tx3)"};font-size:7px">${ t.sessLabel||t.sess||"--"}</td>
          <td style="color:${t.dir==="long"?"#26a69a80":"#ef535080"}">${t.dir==="long"?"▲ L":"▼ S"}</td>
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
document.getElementById("strat-modal").addEventListener("click",e=>{
  if(e.target===document.getElementById("strat-modal"))closeStratModal();
});

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

  // ── Best bot's open positions only ────────────────────────────
  const bbTrades=Object.entries(bb.openTrades).map(([code,t])=>({code,t}));
  bbTrades.sort((a,b2)=>{
    // Sort by unrealized P&L descending
    const mA=MKTS.find(m=>m.code===a.code),mB=MKTS.find(m=>m.code===b2.code);
    const cA=bs(a.code).at(-1)?.c??a.t.entry,cB=bs(b2.code).at(-1)?.c??b2.t.entry;
    const uA=(a.t.dir==="long"?cA-a.t.entry:a.t.entry-cA)*mA.ptVal;
    const uB=(b2.t.dir==="long"?cB-b2.t.entry:b2.t.entry-cB)*mB.ptVal;
    return uB-uA;
  });

  // ── Sound: one tone per NEW position on the SAME best bot ──────
  const curKeys=new Set(bbTrades.map(({code,t})=>`${code}|${t.openT}`));
  const bestBotChanged = bb.uid !== prevBestBotUid;
  if(!soundSeeded || bestBotChanged){
    // First render or best bot swapped -- seed silently, no sounds
    prevBestTradeKeys=curKeys;
    prevBestBotUid=bb.uid;
    soundSeeded=true;
  } else {
    // Same best bot -- fire sound only for genuinely new opens
    let newIdx=0;
    curKeys.forEach(k=>{
      if(!prevBestTradeKeys.has(k)){
        playOpenSound(newIdx++);
        const code=k.split("|")[0];
        const trd=bb.openTrades[code];
        if(trd)addLog(`${bb.name} OPENED ${code} ${trd.dir.toUpperCase()} @ ${trd.entry} (${trd.sess??'--'})`, "open");
      }
    });
    prevBestTradeKeys=curKeys;
  }

  // Update open count badge
  const oc=document.getElementById("open-count");
  if(oc)oc.textContent=bbTrades.length?`${bbTrades.length} active`:"";

  document.getElementById("openbox").innerHTML=bbTrades.length
    ?bbTrades.map(({code,t},idx)=>{
        const mkt=MKTS.find(m=>m.code===code);
        const rawCur=bs(code).at(-1)?.c??t.entry;
        // Clamp to trade bounds — price can't realise beyond TP or SL
        const cur=t.dir==="long"?Math.max(t.sl,Math.min(t.tp,rawCur)):Math.min(t.sl,Math.max(t.tp,rawCur));
        const pts=t.dir==="long"?cur-t.entry:t.entry-cur;
        const unr=Math.round(pts*mkt.ptVal*100)/100;
        const sess=t.sess||"NY";
        const ss=SESS_STYLE[sess]||SESS_STYLE.NY;
        const dec=mkt.tick<1?2:0;
        const slDist=Math.abs(t.entry-t.sl).toFixed(dec);
        const tpDist=Math.abs(t.tp-t.entry).toFixed(dec);
        const sigName=bb.strat.sess?.[sess]||bb.strat.type;
        return`<div class="pos-card">
          <div class="pos-header">
            <div>
              <div style="display:flex;align-items:center;gap:5px;margin-bottom:2px">
                <span class="pos-mkt" style="color:${mkt.col}">${mkt.code}</span>
                <span class="pos-sess" style="color:${ss.col};background:${ss.bg};border:1px solid ${ss.border}">${sess}</span>
              </div>
              <div class="pos-strat">${mkt.name} &middot; ${sigName}</div>
            </div>
            <span class="pos-dir ${t.dir}">${t.dir==="long"?"LONG ▲":"SHORT ▼"}</span>
          </div>
          <div class="pos-levels">
            <div class="pos-lv" style="border:1px solid #26a69a30">
              <div class="pos-lv-label" style="color:#26a69a">TARGET</div>
              <div class="pos-lv-val" style="color:#26a69a">${t.tp.toFixed(dec)}</div>
              <div class="pos-lv-dist" style="color:#26a69a">+${tpDist}pt</div>
            </div>
            <div class="pos-lv" style="border:1px solid #d0e0ff20">
              <div class="pos-lv-label" style="color:var(--tx2)">ENTRY</div>
              <div class="pos-lv-val" style="color:#dce8ff">${t.entry.toFixed(dec)}</div>
              <div class="pos-lv-dist" style="color:var(--tx3)">${fTs(t.openT)}</div>
            </div>
            <div class="pos-lv" style="border:1px solid #ef535030">
              <div class="pos-lv-label" style="color:#ef5350">STOP</div>
              <div class="pos-lv-val" style="color:#ef5350">${t.sl.toFixed(dec)}</div>
              <div class="pos-lv-dist" style="color:#ef5350">-${slDist}pt</div>
            </div>
          </div>
          <div class="pos-footer">
            <div>
              <div class="pos-unr" style="color:${clr(unr)}">${f$(unr)}</div>
              <div style="font-size:6px;color:var(--tx3)">unrealized &middot; ATR ${t.atr?.toFixed(2)}</div>
            </div>
            <div class="pos-meta">
              <div style="color:var(--tx2)">RR ${bb.strat.rr}:1</div>
              <div>Score ${(score(bb)*100).toFixed(0)}/100</div>
            </div>
          </div>
        </div>`;}).join("")
    :`<div style="padding:10px;color:var(--tx3);font-size:8.5px;text-align:center">
       No open positions<br><span style="font-size:7.5px;color:var(--tx4)">Watching ${MKTS.length} markets for signals</span>
     </div>`;

  // Apex AI left panel
  renderAILeft();
}

function renderAILeft(){
  const el=document.getElementById("ai-panel-left");if(!el)return;
  const ab=adaptiveBot;
  const tot=ab.wins+ab.losses;
  const wr=tot?ab.wins/tot:0;
  const pnl=ab.closedTrades.reduce((s,t)=>s+t.pnlUSD,0);
  const currSess=getSessionET();
  const unlocked=aiFullyUnlocked();
  const foundCount=["NY","LONDON","ASIA","SYDNEY"].filter(s=>aiSessionReady(s)).length;

  // Badge — use allClosed count so it stays accurate after interval resets
  const badge=document.getElementById("ai-wr-badge");
  if(badge){
    const allAI=allClosed.filter(t=>t.botName==="Apex AI");
    const allAITot=allAI.length;
    const allAIWins=allAI.filter(t=>t.won).length;
    const allAIWR=allAITot?allAIWins/allAITot:0;
    if(unlocked)
      badge.innerHTML=`<span style="color:#26a69a">● LIVE · ${allAITot>0?(allAIWR*100).toFixed(0)+"%WR · "+allAITot+"t":"watching"}</span>`;
    else
      badge.innerHTML=`<span style="color:#f5a623">⧗ SCANNING · ${foundCount}/4 sessions · need 2</span>`;
  }

  // AI open positions
  const aiTrades=Object.entries(ab.openTrades).map(([code,t])=>({code,t}));

  // ── Session checklist — shows dominant strategy (most wins) per session ──────
  const sessRows=["NY","LONDON","ASIA","SYDNEY"].map(sess=>{
    const sst=SESS_STYLE[sess]||SESS_STYLE.NY;
    const isNow=sess===currSess;
    // Display: use getBestForSession (no min-trade gate) so the checklist
    // shows the best available strategy immediately, not just after 10 trades.
    // The 10-trade gate only applies to getDominantStrat for actual firing.
    const best=getBestForSession(sess);
    const dom=getDominantStrat(sess); // null if < 10 trades — shows lock icon
    const ready=best!==null;
    const locked=ready&&dom===null; // has a strategy but not yet dominant-ready
    return`<div style="display:flex;align-items:center;gap:4px;padding:2px 6px;
      border-bottom:1px solid var(--b1);
      ${isNow?"background:"+sst.bg+"20;border-left:2px solid "+sst.col+";":""}>
      <span style="font-size:8.5px;line-height:1;color:${ready?(locked?"#f5a623":"#26a69a"):"#4c525e"}">${ready?(locked?"◐":"✓"):"○"}</span>
      <span style="font-size:6px;color:${sst.col};min-width:38px;font-weight:${isNow?"700":"400"}">${sess}</span>
      ${ready
        ?`<span style="flex:1;font-size:6px;color:var(--tx2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${best.strat.name}</span>
          <span style="font-size:5.5px;color:${locked?"#f5a623":"#26a69a"};flex-shrink:0;margin-left:3px;white-space:nowrap">${best.wins??best.w??0}W · ${(best.wr*100).toFixed(0)}%${locked?" (building)":""}</span>`
        :`<span style="flex:1;font-size:6px;color:var(--tx4)">waiting for winning strategy</span>`
      }
    </div>`;
  }).join("");

  // Dominant strategy for current session — shown at top
  const domNow=getDominantStrat(currSess);
  const domBanner=domNow?`
    <div style="padding:4px 8px;background:${adaptiveBot.apexPaused?"#3e1c1c":"#7eb8ff12"};border-bottom:1px solid var(--b1);
      display:flex;align-items:center;gap:6px">
      <span style="font-size:7px;color:${adaptiveBot.apexPaused?"#f87171":"#7eb8ff"};font-weight:700;letter-spacing:1px">${adaptiveBot.apexPaused?"⏸ PAUSED":"DOMINANT"}</span>
      <span style="flex:1;font-size:7.5px;color:var(--tx);font-weight:700;overflow:hidden;
        text-overflow:ellipsis;white-space:nowrap">${domNow.strat.name}</span>
      <span style="font-size:6.5px;color:#26a69a;flex-shrink:0;white-space:nowrap">${domNow.wins}W(${domNow.decayedWins??domNow.wins}d) · ${(domNow.wr*100).toFixed(0)}%WR · ${domNow.n}t</span>
    </div>`:`<div style="padding:3px 8px;background:var(--b1);border-bottom:1px solid var(--b1);
      font-size:6px;color:var(--tx4)">Waiting for dominant strategy (min 10 trades)</div>`;

  let html=`
  ${domBanner}
  <div style="font-size:6px;font-weight:700;color:${unlocked?"#26a69a":"#f5a623"};
    padding:3px 8px;border-bottom:1px solid var(--b1)">
    ${unlocked?"✓ AI LIVE — dominant strategy active":"⧗ SCANNING — need 2 sessions to unlock"}
  </div>
  <div>${sessRows}</div>`;

  if(aiTrades.length){
    html+=aiTrades.map(({code,t})=>{
      const mkt=MKTS.find(m=>m.code===code);if(!mkt)return"";
      const rawCur=bs(code).at(-1)?.c??t.entry;
      const cur=t.dir==="long"?Math.max(t.sl,Math.min(t.tp,rawCur)):Math.min(t.sl,Math.max(t.tp,rawCur));
      const pts=t.dir==="long"?cur-t.entry:t.entry-cur;
      const unr=Math.round(pts*mkt.ptVal*100)/100;
      const sess=t.sess||"NY";
      const ss=SESS_STYLE[sess]||SESS_STYLE.NY;
      const dec=mkt.tick<1?2:0;
      const slDist=Math.abs(t.entry-t.sl).toFixed(dec);
      const tpDist=Math.abs(t.tp-t.entry).toFixed(dec);
      const rrDisp=(t.rr||2).toFixed(1);
      const strat=STRATS.find(s=>s.id===t.stratUsed);
      return`<div class="pos-card">
        <div class="pos-header">
          <div>
            <div style="display:flex;align-items:center;gap:5px;margin-bottom:2px">
              <span class="pos-mkt" style="color:${mkt.col}">${mkt.code}</span>
              <span class="pos-sess" style="color:${ss.col};background:${ss.bg};border:1px solid ${ss.border}">${sess}</span>
            </div>
            <div class="pos-strat">AI · ${strat?.name||t.stratUsed||"dominant"}</div>
          </div>
          <span class="pos-dir ${t.dir}">${t.dir==="long"?"LONG ▲":"SHORT ▼"}</span>
        </div>
        <div class="pos-levels">
          <div class="pos-lv" style="border:1px solid #26a69a30">
            <div class="pos-lv-label" style="color:#26a69a">TARGET</div>
            <div class="pos-lv-val" style="color:#26a69a">${t.tp.toFixed(dec)}</div>
            <div class="pos-lv-dist" style="color:#26a69a">+${tpDist}pt</div>
          </div>
          <div class="pos-lv" style="border:1px solid #d0e0ff20">
            <div class="pos-lv-label" style="color:var(--tx2)">ENTRY</div>
            <div class="pos-lv-val" style="color:#dce8ff">${t.entry.toFixed(dec)}</div>
            <div class="pos-lv-dist" style="color:var(--tx3)">${fTs(t.openT)}</div>
          </div>
          <div class="pos-lv" style="border:1px solid #ef535030">
            <div class="pos-lv-label" style="color:#ef5350">STOP</div>
            <div class="pos-lv-val" style="color:#ef5350">${t.sl.toFixed(dec)}</div>
            <div class="pos-lv-dist" style="color:#ef5350">-${slDist}pt</div>
          </div>
        </div>
        <div class="pos-footer">
          <div>
            <div class="pos-unr" style="color:${clr(unr)}">${f$(unr)}</div>
            <div style="font-size:6px;color:var(--tx3)">conf ${((t.conf||0)*100).toFixed(0)}% · dominant strat</div>
          </div>
          <div class="pos-meta">
            <div style="color:var(--tx2)">RR ${rrDisp}:1</div>
            <div>${tot>0?(wr*100).toFixed(0)+"% WR":""}</div>
          </div>
        </div>
      </div>`;}).join("");
  } else {
    html+=`<div style="padding:6px 10px;color:var(--tx4);font-size:7px;text-align:center">
      ${unlocked
        ?"Watching "+currSess+" — fires on dominant strategy signal"
        :"Need "+Math.max(0,2-foundCount)+" more session"+(2-foundCount===1?"":"s")+" · "+foundCount+"/4 ready"}
    </div>`;
  }
  el.innerHTML=html;

  // ── AI Trades Panel (shown below once unlocked and has trades) ────────────
  const tp=document.getElementById("ai-trades-panel");if(!tp)return;
  if(!unlocked){tp.style.display="none";return;}

  // Pull from allClosed (survives interval resets) + ab.closedTrades, dedup by key
  const aiSeen=new Set(),aiClosedTrades=[];
  const addAI=t=>{
    const k=`${t.openT??0}|${t.entry??0}|${t.code}`;
    if(!aiSeen.has(k)){aiSeen.add(k);aiClosedTrades.push(t);}
  };
  allClosed.filter(t=>t.botName==="Apex AI").forEach(addAI);
  ab.closedTrades.forEach(t=>{
    const k=`${t.openT??0}|${t.entry??0}|${t.code}`;
    if(!aiSeen.has(k)){aiSeen.add(k);aiClosedTrades.push(t);}
  });
  aiClosedTrades.sort((a,b2)=>(b2.closeT||b2.openT)-(a.closeT||a.openT));

  if(!aiClosedTrades.length){tp.style.display="none";return;}
  tp.style.display="block";

  // Recalculate stats from full trade list (not ab.wins/losses which reset on interval change)
  const aiWins=aiClosedTrades.filter(t=>t.won).length;
  const aiLosses=aiClosedTrades.filter(t=>!t.won).length;
  const aiTot=aiClosedTrades.length;
  const aiWR=aiTot?aiWins/aiTot:0;
  const aiPnl=aiClosedTrades.reduce((s,t)=>s+(t.pnlUSD||0),0);

  tp.innerHTML=`
    <div style="padding:4px 8px;background:var(--p3);border-bottom:1px solid var(--b1);
      display:flex;gap:1px">
      <div style="flex:1;text-align:center;font-size:6px;color:var(--tx3);line-height:1.7">
        Trades<br><b style="font-size:9px;font-family:'Orbitron',sans-serif;color:var(--tx)">${aiTot}</b></div>
      <div style="flex:1;text-align:center;font-size:6px;color:var(--tx3);line-height:1.7">
        Win Rate<br><b style="font-size:9px;font-family:'Orbitron',sans-serif;color:${aiWR>=0.5?"#26a69a":"#ef5350"}">${(aiWR*100).toFixed(0)}%</b></div>
      <div style="flex:1;text-align:center;font-size:6px;color:var(--tx3);line-height:1.7">
        W / L<br><b style="font-size:9px;font-family:'Orbitron',sans-serif;color:var(--tx2)">${aiWins}/${aiLosses}</b></div>
      <div style="flex:1;text-align:center;font-size:6px;color:var(--tx3);line-height:1.7">
        Net P&amp;L<br><b style="font-size:9px;font-family:'Orbitron',sans-serif;color:${clr(aiPnl)}">${f$(aiPnl)}</b></div>
    </div>
    <table class="mt"><thead><tr>
      <th>MKT</th><th>SESS</th><th>DIR</th><th>PTS</th><th>P&amp;L</th><th>RES</th>
    </tr></thead><tbody>${
    aiClosedTrades.slice(0,30).map(t=>{
      const mkt=MKTS.find(m=>m.code===t.code);
      const _sl=t.sessLabel||t.sess||"NY";const ss2=SESS_STYLE[primarySess(_sl)]||SESS_STYLE.NY;
      return`<tr style="background:${t.won?"#26a69a08":"#ef535008"}">
        <td><b style="color:${mkt?.col||"#fff"}">${t.code}</b></td>
        <td style="color:${ss2?.col||"var(--tx3)"};font-size:6.5px">${_sl}</td>
        <td style="color:${t.dir==="long"?"#26a69a80":"#ef535080"}">${t.dir==="long"?"▲":"▼"}</td>
        <td style="color:${clr(t.pts)}">${fPts(t.pts??0)}</td>
        <td><b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b></td>
        <td style="color:${t.won?"#26a69a":"#ef5350"};font-weight:700">${t.won?"W":"L"}</td>
      </tr>`;}).join("")
    }</tbody></table>`;
}

function renderSigBars(){
  MKTS.forEach(m=>{
    const sb=document.getElementById("sb-"+m.id);if(!sb)return;
    const dec=m.tick<1?2:0;
    const openHere=[];
    [...bots.filter(b=>!b.killed),adaptiveBot].forEach(bot=>{
      const t=bot.openTrades[m.code];if(!t)return;
      const rawCur=bs(m.code).at(-1)?.c??t.entry;
      const cur=t.dir==="long"?Math.max(t.sl,Math.min(t.tp,rawCur)):Math.min(t.sl,Math.max(t.tp,rawCur));
      const pts=t.dir==="long"?cur-t.entry:t.entry-cur;
      const unr=Math.round(pts*m.ptVal*100)/100;
      openHere.push({bot,t,unr,isAI:bot===adaptiveBot});
    });
    if(openHere.length){
      // Show ALL open positions for this market — no truncation, no +N overflow
      sb.innerHTML=openHere.map(({bot,t,unr,isAI})=>
        `<span class="chip ${t.dir==="long"?"cl":"cs"}" style="flex-direction:column;align-items:flex-start;gap:0;padding:1px 4px">
          <span style="font-size:7px">${isAI?"⬡AI":""}${bot.name.split(" W")[0].slice(0,8)} ${t.dir==="long"?"▲":"▼"}</span>
          <span style="font-size:6px">E:${t.entry?.toFixed(dec)} TP:${t.tp?.toFixed(dec)}</span>
          <b style="font-size:6px;color:${clr(unr)}">${f$(unr)}</b>
        </span>`).join("");
    }else{
      sb.innerHTML=`<span style="color:var(--tx4);font-size:6.5px">${m.tierLabel||("T"+m.tier)} · watching</span>`;
    }
    const q=liveQ[m.code];
    if(q){const cc=document.getElementById("cchg-"+m.id);if(cc){
      const s=q.change>=0?"+":"";
      cc.textContent=`${s}${q.change.toFixed(2)}(${s}${q.changePct.toFixed(2)}%)`;
      cc.style.color=q.change>=0?"#26a69a":"#ef5350";
    }}
  });
}

function renderAllTrades(){
  const seen=new Set(),merged=[];
  const addRec=t=>{
    // Rich key: code + entry + openT + botName prevents both dups and false-drops
    const k=`${t.code}|${t.openT??0}|${t.entry??0}|${t.botName}`;
    if(!seen.has(k)){seen.add(k);merged.push(t);}
  };
  // Pull from every source: global allClosed, each bot, and AI
  allClosed.forEach(addRec);
  bots.forEach(b=>b.closedTrades.forEach(addRec));
  adaptiveBot.closedTrades.forEach(addRec);
  merged.sort((a,b)=>(b.closeT||b.openT)-(a.closeT||a.openT));

  document.getElementById("atbody").innerHTML=merged.length
    ?merged.map(t=>{
        const mkt=MKTS.find(m=>m.code===t.code);
        const dec=mkt?.tick<1?2:0;
        const _sl=t.sessLabel||t.sess||"NY";const ss2=SESS_STYLE[primarySess(_sl)]||SESS_STYLE.NY;
        return`<tr style="background:${t.won?"#26a69a08":"#ef535008"}">
          <td><b style="color:${mkt?.col||'#fff'}">${t.code}</b></td>
          <td style="color:#9c27b0;max-width:72px;overflow:hidden;text-overflow:ellipsis;font-size:7px">${t.botName?.replace(" W1","").replace(" W2","").replace(" W3","")}</td>
          <td style="color:${ss2?.col||'var(--tx3)'}; font-size:7px">${ t.sessLabel||t.sess||"--"}</td>
          <td style="color:${t.dir==="long"?"#26a69a70":"#ef535070"}">${t.dir==="long"?"L":"S"}</td>
          <td style="color:var(--tx2)">${t.entry?.toFixed(dec)}</td>
          <td style="color:var(--tx2)">${(t.exitPx??t.ex)?.toFixed(dec)}</td>
          <td style="color:${clr(t.pts)}">${fPts(t.pts??0)}</td>
          <td><b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b></td>
          <td style="color:${t.won?"#26a69a":"#ef5350"}">${t.won?"WIN":"LOSS"}</td>
        </tr>`;}).join("")
    :`<tr><td colspan="9" style="text-align:center;color:var(--tx3);padding:12px">
       Bots fire on crossover signals -- trades appear when SL or TP is hit on a real bar.
     </td></tr>`;
}

function renderRight(){
  const ab=live(),bb=bestBot();
  document.getElementById("blist").innerHTML=[...bots]
    .sort((a,b2)=>score(b2)-score(a)).slice(0,22)
    .map(b=>{
      const tot=b.wins+b.losses;
      const wr=getWR(b);
      const p=getPnl(b);
      // Absolute coloring — no relative tricks:
      // green = has trades AND winning (WR>=50% or P&L>0)
      // yellow = has trades but not yet profitable
      // red = no trades or losing
      // dim = killed
      const bc=b.killed?"#2a2e39"
        :tot===0?"#4c525e"                            // no trades yet — neutral dim
        :(wr>=0.5&&p>=0)?"#26a69a"                   // winning — green
        :(tot>0&&p>=0)?"#f5a623"                     // trades but marginal — yellow
        :"#ef5350";                                   // losing — red
      const isBest=b===bb;
      const wrBar=Math.round(wr*100);
      return`<div class="brow${b.killed?" dead":""}" onclick="openStratModal(bots.find(x=>x.uid===${b.uid}))" title="Click to view ${b.name} trades">
        <span class="bdot" style="background:${bc}"></span>
        <div style="flex:1;min-width:0">
          <div style="display:flex;justify-content:space-between;gap:2px">
            <span style="color:${isBest?"var(--cy)":b.killed?"#363a45":"#787b86"};
              font-size:7.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">
              ${isBest?"★ ":""}${b.name}</span>
            <b style="color:${tot===0?"#4c525e":clr(p)};font-size:7.5px;flex-shrink:0">${tot===0?"no trades":f$(p)}</b>
          </div>
          <div style="display:flex;align-items:center;gap:3px">
            <div class="bbar"><div class="bfill" style="width:${wrBar}%;background:${bc}"></div></div>
            <span style="color:${bc};font-size:7px;flex-shrink:0">${tot===0?"--":fPct(wr)}</span>
          </div>
          ${b.killed?`<div style="color:#3e1c1c;font-size:6.5px">${b.killReason}</div>`:""}
        </div></div>`;}).join("");
  document.getElementById("srcsect").innerHTML=MKTS.map(m=>{
    const src=sources[m.code]||"--",q=liveQ[m.code],ok=!!candles[m.code]?.length;
    return`<div style="display:flex;justify-content:space-between;margin-bottom:1px">
      <span style="color:${m.col}">${m.code}</span>
      <span style="font-size:7.5px;color:${ok?"#26a69a":"#ef5350"}">${src.replace("Yahoo Finance ","YF")}</span>
    </div>`;
  }).join("");
}

function renderAdaptive(){
  // AI left panel is rendered by renderAILeft() inside renderLeft().
  // This fn updates the per-session best-strategy section in the right panel.
  const currSess=getSessionET();
  const sessions=["NY","SYDNEY","ASIA","LONDON"];
  const ssect=document.getElementById("sess-best-sect");
  if(!ssect)return;

  const sessMap=sessions.map(sess=>{
    const best=getBestStratForSession(sess);
    return{sess,best};
  }).filter(x=>x.best);

  if(!sessMap.length){
    ssect.innerHTML=`<div style="padding:5px 9px;color:var(--tx4);font-size:7px">Waiting — need WR&gt;50% strategy per session</div>`;
    return;
  }
  ssect.innerHTML=sessMap.map(({sess,best})=>{
    const sst=SESS_STYLE[sess]||SESS_STYLE.NY;
    const isNow=sess===currSess;
    const wrPct=(best.wr*100).toFixed(0);
    const wrCol=best.wr>=0.65?"#26a69a":best.wr>=0.45?"#f5a623":"#ef5350";
    return`<div style="display:flex;align-items:center;gap:3px;padding:2px 7px;
      border-bottom:1px solid var(--b1);
      ${isNow?"background:"+sst.bg+"20;border-left:2px solid "+sst.col+";":""}>
      <span style="font-size:6px;padding:1px 4px;border-radius:2px;
        color:${sst.col};background:${sst.bg};border:1px solid ${sst.border};
        min-width:28px;text-align:center">${sess}</span>
      <b style="font-size:7px;color:${best.mktCol};flex-shrink:0">${best.mktCode}</b>
      <span style="flex:1;font-size:6px;color:var(--tx2);overflow:hidden;text-overflow:ellipsis;
        white-space:nowrap">${best.strat?.name||best.stratId}</span>
      <div style="text-align:right;flex-shrink:0;line-height:1.3">
        <b style="font-size:7px;color:${wrCol};display:block">${wrPct}% WR</b>
        <span style="font-size:5.5px;color:var(--tx3)">${best.n}t</span>
      </div>
    </div>`;}).join("");
}
function addLog(msg,type="info"){
  logE.unshift({msg,type,ts:Date.now()});logE=logE.slice(0,80);
  document.getElementById("log").innerHTML=logE.map(e=>
    `<span class="lc ${e.type}">
       ${new Date(e.ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"})}
       ${e.msg}
     </span>`).join("");
}

document.querySelectorAll(".ivb").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".ivb").forEach(b=>b.classList.remove("on"));
    btn.classList.add("on");iv=btn.dataset.iv;
    candles={};liveQ={};sources={};prevPx={};dirty={};
    processedTs={};startupDone=false;prevBestTradeKeys=new Set();prevBestBotUid=null;soundSeeded=false;if(adaptiveBot){adaptiveBot.openTrades={};adaptiveBot.consecLosses=0;adaptiveBot.apexPaused=false;adaptiveBot._lastDomId=null;} // wins/losses/closedTrades kept across interval changes
    addLog("Interval → "+iv+" -- chart refreshed, all trades kept","info");
    refreshFull();
  });
});
window.addEventListener("resize",()=>MKTS.forEach(m=>{dirty[m.id]=true;}));

buildGrid();
updateSessionClock();
setInterval(updateSessionClock,5000); // 5s so session transitions are instant
refreshFull();
setInterval(refreshFull,30000);
setInterval(refreshQuote,750);   // ↑ faster tick: was 1500ms
refreshQuote();
setInterval(()=>{renderLeft();renderSigBars();renderRight();renderAdaptive();},1500); // ↑ faster UI: was 3000ms
requestAnimationFrame(rafLoop);
</script>
</body>
</html>"""


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
        else:
            self.send_response(404)
            self.end_headers()

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
    _safe("  FF ELITE BOTS v4  --  8 Markets  --  4 Index Pairs")
    _safe("  ==================================================")
    _safe("  S&P 500  : ES  / MES   (E-mini & Micro)")
    _safe("  Nasdaq   : NQ  / MNQ   (E-mini & Micro)")
    _safe("  Dow Jones: YM  / MYM   (E-mini & Micro)")
    _safe("  Russell  : RTY / M2K   (E-mini & Micro)")
    _safe("")
    _safe("  Strategies : 10 session-aware bots (Asia / London / NY)")
    _safe("  Data       : Yahoo Finance v8 OHLC + v7 quotes -> Stooq")
    _safe("")
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
        _safe("  Stopped.")
        sys.exit(0)