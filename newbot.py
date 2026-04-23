#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF ELITE BOTS v4
================
  python run.py   (Windows CMD, PowerShell, Mac, Linux -- no pip needed)

DUAL-LOOP DATA ARCHITECTURE:
  /api/quote    every 1.5 s -- Yahoo Finance v7 batch, all 4 prices in 1 call
                               patches forming candle -> requestAnimationFrame redraw
  /api/candles  every 30 s  -- full OHLC: YF v8 query1 -> query2 -> Stooq CSV
                               rebuilds bars, runs bot engine on new complete bars
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
CODES = ("ES", "MES", "NQ", "MNQ")

IV_CFG = {
    "1m":  ("1m",  "1d",   "5"),
    "5m":  ("5m",  "5d",   "5"),
    "15m": ("15m", "60d",  "15"),
    "1H":  ("1h",  "180d", "60"),
}

CONTRACTS = {
    "ES":  {"yf": "ES=F",  "stooq": "es.f"},
    "MES": {"yf": "MES=F", "stooq": "mes.f"},
    "NQ":  {"yf": "NQ=F",  "stooq": "nq.f"},
    "MNQ": {"yf": "MNQ=F", "stooq": "mnq.f"},
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


def _get(url, hdrs=None, timeout=18):
    req = urllib.request.Request(url, headers=hdrs or YF_HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try: raw = gzip.decompress(raw)
    except: pass
    return raw


def _yf_ohlc(yf_sym, yf_iv, yf_range, host="query1"):
    url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(yf_sym)}?interval={yf_iv}&range={yf_range}"
           f"&includePrePost=false&corsDomain=finance.yahoo.com")
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
        out = {"live":False,"candles":[],"source":"unavailable"}
    with _lock: _ohlc_cache[key] = {"data":out,"ts":time.time()}
    return out

def get_quotes():
    with _lock:
        if time.time()-_quote_cache["ts"] < 1.5: return _quote_cache["data"]
    try:
        data = fetch_quotes_batch()
        with _lock: _quote_cache["data"]=data; _quote_cache["ts"]=time.time()
        return data
    except Exception as e:
        _safe(f"  [--] quotes: {e}")
        return {}


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
  --up:#26a69a;--dn:#ef5350;--yw:#f5a623;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--tx);
  font-family:'Share Tech Mono',monospace;font-size:11px}
#app{display:flex;flex-direction:column;height:100vh;overflow:hidden}
#top{display:flex;align-items:center;height:38px;flex-shrink:0;padding:0 12px;
  background:var(--p1);border-bottom:1px solid var(--b2);gap:0}
#logo{font-family:'Orbitron',sans-serif;font-size:12px;font-weight:900;color:var(--cy);
  letter-spacing:2px;padding-right:12px;border-right:1px solid var(--b1);margin-right:10px}
#ltag{padding:2px 8px;border-radius:3px;font-size:8px;font-weight:bold;
  background:var(--p2);color:var(--tx3);border:1px solid var(--b1);margin-right:10px;
  transition:all .3s;min-width:68px;text-align:center}
#ltag.live{background:#1a2e1a;color:var(--up);border-color:#26a69a40}
#ltag.closed{background:#1a1a2e;color:var(--pu);border-color:#9c27b040}
.ivg{display:flex;gap:2px;margin-right:10px;padding-right:10px;border-right:1px solid var(--b1)}
.ivb{padding:3px 10px;border:1px solid transparent;border-radius:3px;background:transparent;
  color:var(--tx3);cursor:pointer;font-family:'Share Tech Mono',monospace;font-size:10px;transition:all .15s}
.ivb:hover{color:var(--tx);background:var(--b1)}
.ivb.on{background:var(--cy);color:#fff;border-color:var(--cy)}
.ts{color:var(--tx3);font-size:9px;margin-right:10px;white-space:nowrap}.ts b{color:var(--tx)}
.sp{flex:1}
#prices{display:flex;border-left:1px solid var(--b1)}
.mpx{display:flex;flex-direction:column;padding:1px 10px;border-right:1px solid var(--b1);min-width:92px;justify-content:center}
.mpx .sym{font-size:7.5px;color:var(--tx3);letter-spacing:1px}
.mpx .val{font-family:'Orbitron',sans-serif;font-size:12px;font-weight:700;line-height:1.2;transition:color .3s}
.mpx .chg{font-size:8px}
#tu{font-size:8px;color:var(--tx3);margin-left:10px}
#qtag{font-size:7.5px;color:var(--tx3);margin-left:6px;padding:2px 6px;
  border-radius:2px;background:var(--b1);white-space:nowrap}

#body{display:flex;flex:1;overflow:hidden;min-height:0}
#left{width:228px;min-width:228px;flex-shrink:0;background:var(--p1);
  border-right:1px solid var(--b2);display:flex;flex-direction:column;overflow:hidden}
.ph{font-size:8px;font-weight:700;letter-spacing:1.5px;color:var(--tx3);
  padding:5px 10px;border-bottom:1px solid var(--b1);background:var(--p3);
  flex-shrink:0;text-transform:uppercase}
.card{padding:8px 10px;border-bottom:1px solid var(--b2)}
.r2{display:flex;justify-content:space-between;align-items:center;padding:1px 0;font-size:9px}
.r2 .k{color:var(--tx3)}
#bname{font-family:'Orbitron',sans-serif;font-size:10px;font-weight:700;color:var(--tx);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:2px}
#btype{color:var(--tx3);font-size:8px;margin-bottom:5px}
svg#spark{display:block;width:100%;height:24px;margin-top:4px;overflow:hidden}
#openbox{flex-shrink:0;overflow-y:auto;max-height:340px;border-bottom:1px solid var(--b2)}
.ti{padding:7px 10px;border-bottom:1px solid var(--b1);font-size:9px}
.big3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:5px 0}
.big3-cell{text-align:center;background:var(--p3);border-radius:3px;padding:4px 2px}
.big3-lbl{font-size:7px;letter-spacing:1px;margin-bottom:2px}
.big3-val{font-family:'Orbitron',sans-serif;font-size:14px;font-weight:700;line-height:1}
#histbox{flex-shrink:0;overflow-y:auto;max-height:104px;border-bottom:1px solid var(--b2)}
.hi{display:flex;justify-content:space-between;padding:2px 10px;font-size:8.5px;border-bottom:1px solid var(--b1)}
#stratbox{flex:1;overflow-y:auto;padding:7px 10px;font-size:9px;line-height:1.9}

#center{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
#cgrid{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;
  flex:1;gap:1px;padding:1px;background:var(--b1);min-height:0;overflow:hidden}
.cc{background:var(--bg);display:flex;flex-direction:column;overflow:hidden;min-height:0}
.ch{display:flex;justify-content:space-between;align-items:center;
  padding:4px 10px;border-bottom:1px solid var(--b2);flex-shrink:0;height:28px;background:var(--p1)}
.csym{font-family:'Orbitron',sans-serif;font-size:10px;font-weight:700}
.clive{font-family:'Orbitron',sans-serif;font-size:13px;font-weight:700;transition:color .3s}
.cw{flex:1;position:relative;overflow:hidden;min-height:0}
.cw canvas{display:block;position:absolute;top:0;left:0}
.sb{flex-shrink:0;border-top:1px solid var(--b2);padding:2px 8px;min-height:20px;
  display:flex;gap:4px;flex-wrap:wrap;align-items:center;background:var(--p1)}
.chip{padding:1px 6px;border-radius:2px;font-size:8px}
.cl{background:#26a69a18;color:var(--up);border:1px solid #26a69a30}
.cs{background:#ef535018;color:var(--dn);border:1px solid #ef535030}
#tradepane{height:148px;flex-shrink:0;display:flex;flex-direction:column;border-top:1px solid var(--b2)}
.tscroll{flex:1;overflow-y:auto}

#right{width:208px;min-width:208px;flex-shrink:0;background:var(--p1);
  border-left:1px solid var(--b2);display:flex;flex-direction:column;overflow:hidden}
#blist{flex:1;overflow-y:auto}
.brow{display:flex;align-items:center;gap:4px;padding:3px 8px;border-bottom:1px solid var(--b1);font-size:9px}
.brow.dead{opacity:.2}
.bdot{width:5px;height:5px;border-radius:50%;flex-shrink:0}
.bbar{flex:1;height:2px;background:var(--b2);border-radius:1px}
.bfill{height:100%;border-radius:1px;transition:width .8s}
.rsect{flex-shrink:0;padding:6px 10px;border-top:1px solid var(--b2);font-size:8.5px;line-height:2;color:var(--tx3)}

#log{height:34px;flex-shrink:0;background:var(--p3);border-top:1px solid var(--b2);
  overflow-x:auto;overflow-y:hidden;display:flex;align-items:center;padding:0 8px;gap:4px;white-space:nowrap}
.lc{display:inline-flex;align-items:center;padding:1px 8px;border-radius:2px;
  font-size:8px;border:1px solid var(--b1);flex-shrink:0}
.lc.win{background:#26a69a18;color:var(--up);border-color:#26a69a30}
.lc.loss{background:#ef535018;color:var(--dn);border-color:#ef535030}
.lc.kill{background:#3e1c1c;color:#f87171}.lc.wave{background:#1e1a2e;color:var(--pu)}
.lc.info{background:var(--b1);color:var(--tx3)}
table.mt{width:100%;border-collapse:collapse}
table.mt th{font-size:7px;color:var(--tx3);padding:2px 5px;border-bottom:1px solid var(--b2);
  position:sticky;top:0;background:var(--p3);white-space:nowrap;text-align:left}
table.mt td{font-size:8.5px;padding:2px 5px;border-bottom:1px solid var(--b1);white-space:nowrap}
table.mt tr:hover td{background:var(--p2)}
::-webkit-scrollbar{width:3px;height:3px}::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--b2);border-radius:2px}
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
  <span class="ts">Active:<b id="ta">10</b></span>
  <span class="ts">Wave:<b id="tw" style="color:var(--pu)">1</b></span>
  <span class="ts">Closed:<b id="tcl" style="color:var(--up)">0</b></span>
  <span class="ts">Bars:<b id="tbars" style="color:var(--tx2)">--</b></span>
  <span id="qtag">QUOTE --</span>
  <div class="sp"></div>
  <div id="prices">
    <div class="mpx"><span class="sym" style="color:var(--cy)">ES</span>
      <span class="val" id="pES">--</span><span class="chg" id="cES"></span></div>
    <div class="mpx"><span class="sym" style="color:var(--pu)">MES</span>
      <span class="val" id="pMES">--</span><span class="chg" id="cMES"></span></div>
    <div class="mpx"><span class="sym" style="color:var(--or)">NQ</span>
      <span class="val" id="pNQ">--</span><span class="chg" id="cNQ"></span></div>
    <div class="mpx"><span class="sym" style="color:var(--pk)">MNQ</span>
      <span class="val" id="pMNQ">--</span><span class="chg" id="cMNQ"></span></div>
  </div>
  <div id="tu">--</div>
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
      <svg id="spark" viewBox="0 0 200 24" preserveAspectRatio="none"></svg>
    </div>
    <div class="ph">Open Positions</div>
    <div id="openbox"><div style="padding:5px 10px;color:var(--tx3)">No open trades</div></div>
    <div class="ph">Last 8 Closed</div>
    <div id="histbox"><div style="padding:5px 10px;color:var(--tx3)">No trades yet</div></div>
    <div class="ph">Strategy</div>
    <div id="stratbox"><span style="color:var(--tx3)">--</span></div>
  </div>
  <div id="center">
    <div id="cgrid"></div>
    <div id="tradepane">
      <div class="ph">All Bots -- Closed Trades
        <span style="font-size:7px;color:var(--tx3);font-weight:normal;text-transform:none;letter-spacing:0;margin-left:8px">
          entry/exit = exact bar close &middot; P&amp;L=(exit-entry)xptVal
        </span>
      </div>
      <div class="tscroll">
        <table class="mt"><thead><tr>
          <th>MKT</th><th>BOT</th><th>DIR</th><th>ENTRY</th><th>EXIT</th><th>PTS</th><th>P&amp;L</th><th>RES</th>
        </tr></thead><tbody id="atbody"></tbody></table>
      </div>
    </div>
  </div>
  <div id="right">
    <div class="ph">Leaderboard</div>
    <div id="blist"></div>
    <div class="ph" style="border-top:1px solid var(--b2)">Data Sources</div>
    <div id="srcsect" class="rsect"></div>
    <div class="ph" style="border-top:1px solid var(--b2)">Contract Specs</div>
    <div class="rsect">
      <span style="color:var(--cy)">ES </span> $50/pt &middot; $12.50/tick<br>
      <span style="color:var(--pu)">MES</span> $5/pt &middot; $1.25/tick<br>
      <span style="color:var(--or)">NQ </span> $20/pt &middot; $5.00/tick<br>
      <span style="color:var(--pk)">MNQ</span> $2/pt &middot; $0.50/tick<br>
      <span style="color:var(--tx4)">0.25pt tick &middot; all independent</span>
    </div>
    <div class="ph" style="border-top:1px solid var(--b2)">Kill / Wave</div>
    <div class="rsect">Balance &lt; $48k &rarr; killed<br>WR &lt; 25% after 20 trades &rarr; killed<br>5 or fewer active &rarr; +10 bots</div>
  </div>
</div>
<div id="log"><span class="lc info">FF Elite Bots v4 -- live quotes 1.5s -- RAF charts -- all 4 contracts independent</span></div>
</div>
<script>
const MKTS=[
  {id:"ES", code:"ES", name:"E-Mini S&P 500",   ptVal:50,tick:0.25,col:"#2962ff"},
  {id:"MES",code:"MES",name:"Micro E-Mini S&P",  ptVal:5, tick:0.25,col:"#9c27b0"},
  {id:"NQ", code:"NQ", name:"E-Mini Nasdaq-100", ptVal:20,tick:0.25,col:"#ff9800"},
  {id:"MNQ",code:"MNQ",name:"Micro E-Mini NQ",   ptVal:2, tick:0.25,col:"#e91e63"},
];
const snap=p=>Math.round(p*4)/4;
let candles={},liveQ={},sources={},prevPx={},dirty={};
let processedIdx={},iv="5m",isLive=false;
let wave=1,uid=0,totalClosed=0,bots=[],allClosed=[],logE=[];
let startupDone=false;
let prevOpenKeys={};  // track open trades for sound detection
const bs=code=>candles[code]??[];

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

const STRATS=[
  {id:"TrendFollow_A",name:"TrendFollow A",type:"EMA 21/55 Cross",rr:3.0,atrMult:1.5,
   desc:"Long on EMA21 cross above EMA55. Short on cross below. 3:1 R:R.",
   signal(b){if(b.length<62)return null;const c=b.map(x=>x.c),n=c.length-1,f=ema(c,21),s=ema(c,55);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";return null;}},
  {id:"Stoch_Master",name:"Stoch Master",type:"Stoch %K 20/80",rr:1.5,atrMult:1.2,
   desc:"Long on %K cross above 20. Short on cross below 80.",
   signal(b){if(b.length<15)return null;const k=stochArr(b,9),n=k.length-1;
     if(k[n]==null||k[n-1]==null)return null;
     if(k[n-1]<=20&&k[n]>20)return"long";if(k[n-1]>=80&&k[n]<80)return"short";return null;}},
  {id:"FF_Top_Trader",name:"FF Top Trader",type:"EMA 8/34 Cross",rr:2.5,atrMult:1.5,
   desc:"EMA8/EMA34 golden/death cross.",
   signal(b){if(b.length<40)return null;const c=b.map(x=>x.c),n=c.length-1,f=ema(c,8),s=ema(c,34);
     if(!f[n]||!s[n]||!f[n-1]||!s[n-1])return null;
     if(f[n-1]<=s[n-1]&&f[n]>s[n])return"long";if(f[n-1]>=s[n-1]&&f[n]<s[n])return"short";return null;}},
  {id:"GoldPatrol99",name:"Gold Patrol 99",type:"ROC(5) +/-0.25%",rr:1.5,atrMult:1.2,
   desc:"Long when 5-bar ROC crosses above +0.25%.",
   signal(b){if(b.length<12)return null;const c=b.map(x=>x.c),n=c.length-1;
     if(!c[n-5]||!c[n-6])return null;
     const r=(c[n]-c[n-5])/c[n-5]*100,rp=(c[n-1]-c[n-6])/c[n-6]*100;
     if(rp<0.25&&r>=0.25)return"long";if(rp>-0.25&&r<=-0.25)return"short";return null;}},
  {id:"VelocityTrader",name:"Velocity Trader",type:"ROC(10) +/-0.4%",rr:2.0,atrMult:1.5,
   desc:"Long when 10-bar ROC crosses above +0.4%.",
   signal(b){if(b.length<15)return null;const c=b.map(x=>x.c),n=c.length-1;
     if(!c[n-10]||!c[n-11])return null;
     const r=(c[n]-c[n-10])/c[n-10]*100,rp=(c[n-1]-c[n-11])/c[n-11]*100;
     if(rp<0.4&&r>=0.4)return"long";if(rp>-0.4&&r<=-0.4)return"short";return null;}},
  {id:"BollingerBreak",name:"Bollinger Break",type:"BB(20,2) Breakout",rr:2.5,atrMult:1.5,
   desc:"Long on close above upper BB. Short below lower BB.",
   signal(b){if(b.length<25)return null;const c=b.map(x=>x.c),bb2=bbArr(c,20,2),n=c.length-1;
     if(!bb2[n].u||!bb2[n-1].u)return null;
     if(c[n-1]<=bb2[n-1].u&&c[n]>bb2[n].u)return"long";
     if(c[n-1]>=bb2[n-1].l&&c[n]<bb2[n].l)return"short";return null;}},
  {id:"MACD_Wave",name:"MACD Wave",type:"MACD Hist Zero Cross",rr:2.0,atrMult:1.5,
   desc:"Long on MACD histogram crossing above zero.",
   signal(b){if(b.length<35)return null;const c=b.map(x=>x.c),{hist}=macdArr(c),n=hist.length-1;
     if(hist[n]==null||hist[n-1]==null)return null;
     if(hist[n-1]<=0&&hist[n]>0)return"long";if(hist[n-1]>=0&&hist[n]<0)return"short";return null;}},
  {id:"ATR_Channel",name:"ATR Channel",type:"SMA20 +/- 2xATR",rr:2.5,atrMult:1.5,
   desc:"Long on break above SMA20+2xATR. Short below SMA20-2xATR.",
   signal(b){if(b.length<30)return null;const c=b.map(x=>x.c),at=atrArr(b,14),sm=sma(c,20),n=c.length-1;
     if(!at[n]||!sm[n]||!at[n-1]||!sm[n-1])return null;
     if(c[n-1]<=sm[n-1]+2*at[n-1]&&c[n]>sm[n]+2*at[n])return"long";
     if(c[n-1]>=sm[n-1]-2*at[n-1]&&c[n]<sm[n]-2*at[n])return"short";return null;}},
  {id:"CCI_Reversal",name:"CCI Reversal",type:"CCI(14) +/-100",rr:2.0,atrMult:1.2,
   desc:"Long on CCI cross above -100. Short on cross below +100.",
   signal(b){if(b.length<20)return null;const ci=cciArr(b,14),n=ci.length-1;
     if(ci[n]==null||ci[n-1]==null)return null;
     if(ci[n-1]<=-100&&ci[n]>-100)return"long";if(ci[n-1]>=100&&ci[n]<100)return"short";return null;}},
  {id:"RSI_Momentum",name:"RSI Momentum",type:"RSI(14) 30/70",rr:2.0,atrMult:1.2,
   desc:"Long on RSI cross above 30. Short on cross below 70.",
   signal(b){if(b.length<20)return null;const c=b.map(x=>x.c),ri=rsiArr(c,14),n=ri.length-1;
     if(ri[n]==null||ri[n-1]==null)return null;
     if(ri[n-1]<=30&&ri[n]>30)return"long";if(ri[n-1]>=70&&ri[n]<70)return"short";return null;}},
];

function mkBot(s,wv){return{uid:++uid,name:`${s.name} W${wv}`,strat:s,wave:wv,balance:50000,
  openTrades:{},closedTrades:[],wins:0,losses:0,killed:false,killReason:""};}
bots=STRATS.map(s=>mkBot(s,1));
const getPnl=b=>b.balance-50000;
const getWR=b=>{const t=b.wins+b.losses;return t?b.wins/t:0;};
function score(b,all){const ps=all.map(x=>getPnl(x)),mn=Math.min(...ps),mx=Math.max(...ps),rng=mx-mn||1;
  return getWR(b)*0.5+((getPnl(b)-mn)/rng)*0.5;}
const live=()=>bots.filter(b=>!b.killed);
const bestBot=()=>{const ab=live();return ab.length?ab.reduce((b,x)=>score(x,ab)>score(b,ab)?x:b,ab[0]):null;};

function processBots(){
  if(!startupDone)return;
  MKTS.forEach(mkt=>{
    const b=bs(mkt.code);if(!b||b.length<35)return;
    const atr=atrArr(b,14);
    const si=(processedIdx[mkt.code]??b.length-2)+1,ei=b.length-2;
    if(si>ei)return;
    for(let i=si;i<=ei;i++){
      const bar=b[i];
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
            ex=snap(ex);const pts=t.dir==="long"?ex-t.entry:t.entry-ex;
            const pnl=Math.round(pts*mkt.ptVal*100)/100;
            bot.balance=Math.round((bot.balance+pnl)*100)/100;
            won?bot.wins++:bot.losses++;totalClosed++;
            const rec={code:mkt.code,col:mkt.col,botName:bot.name,dir:t.dir,
              entry:t.entry,exitPx:ex,pts:Math.round(pts*100)/100,pnlUSD:pnl,won,
              sl:t.sl,tp:t.tp,openT:t.openT,closeT:bar.t,atr:t.atr};
            bot.closedTrades=[...bot.closedTrades.slice(-49),rec];
            allClosed=[rec,...allClosed].slice(0,60);
            delete bot.openTrades[mkt.code];
            document.getElementById("tcl").textContent=totalClosed;
            addLog(`${mkt.code} ${bot.name} ${won?"WIN":"LOSS"} ${f$(pnl)} (${fPts(pts)})`,won?"win":"loss");
          }
        }else{
          const sig=bot.strat.signal(b.slice(0,i+1));
          if(sig&&atr[i]!=null){
            const entry=snap(bar.c),dist=snap(Math.max(atr[i]*bot.strat.atrMult,2*mkt.tick));
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

// FAST LOOP: live quote every 1.5s
async function refreshQuote(){
  try{
    const r=await fetch("/api/quote",{signal:AbortSignal.timeout(5000)});
    const d=await r.json();
    const now=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
    document.getElementById("qtag").textContent="QUOTE "+now;
    MKTS.forEach(m=>{
      const q=d[m.code];if(!q)return;
      liveQ[m.code]=q;
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
      const cel=document.getElementById("c"+m.id);
      if(cel){
        const s=q.change>=0?"+":"";
        cel.textContent=`${s}${q.change.toFixed(2)} (${s}${q.changePct.toFixed(2)}%)`;
        cel.style.color=q.change>=0?"var(--up)":"var(--dn)";
      }
      const cpx=document.getElementById("cpx-"+m.id);
      if(cpx){
        const prev2=cpx._prev;
        cpx.textContent=q.price.toFixed(2);
        if(prev2!=null&&q.price!==prev2){
          cpx.style.color=q.price>prev2?"var(--up)":"var(--dn)";
          clearTimeout(cpx._ft);cpx._ft=setTimeout(()=>{cpx.style.color="var(--tx)";},500);
        }
        cpx._prev=q.price;
      }
    });
  }catch(e){console.warn("quote:",e.message);}
}

// SLOW LOOP: full OHLC rebuild every 30s
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
  tag.textContent=isLive?`LIVE ${liveN}/4`:Object.keys(candles).length?"STALE":"CLOSED";
  tag.className=isLive?"live":!Object.keys(candles).length?"closed":"";
  document.getElementById("tu").textContent=new Date().toLocaleTimeString();
  document.getElementById("tbars").textContent=candles["ES"]?.length||"--";
  if(!startupDone&&isLive){
    MKTS.forEach(m=>{const b=bs(m.code);if(b?.length)processedIdx[m.code]=b.length-2;});
    startupDone=true;addLog("Live data loaded -- bots watching for signals","info");
  }
  processBots();renderLeft();renderAllTrades();renderRight();
}

// RAF render -- redraws dirty charts only
const cvMap={};
function buildGrid(){
  document.getElementById("cgrid").innerHTML=MKTS.map(m=>`
    <div class="cc">
      <div class="ch">
        <div style="display:flex;align-items:center;gap:8px">
          <span class="csym" style="color:${m.col}">${m.code}</span>
          <span style="font-size:8px;color:var(--tx3)">${m.name}</span>
          <span style="font-size:8px;color:var(--tx3)">
            <span style="color:#f5a623">&#9472;</span>E9
            <span style="color:#2962ff">&#9472;</span>E21
          </span>
        </div>
        <div style="display:flex;align-items:center;gap:5px">
          <span class="clive" id="cpx-${m.id}" style="color:var(--tx)">--</span>
          <span style="font-size:9px" id="cchg-${m.id}"></span>
        </div>
      </div>
      <div class="cw" id="cw-${m.id}"><canvas id="cv-${m.id}"></canvas></div>
      <div class="sb" id="sb-${m.id}"><span style="color:var(--tx3);font-size:8px">watching...</span></div>
    </div>`).join("");
  MKTS.forEach(m=>{
    cvMap[m.id]=document.getElementById("cv-"+m.id);
    new ResizeObserver(()=>{dirty[m.id]=true;}).observe(document.getElementById("cw-"+m.id));
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
  ctx.fillStyle="#131722";ctx.fillRect(0,0,W,H);

  const b=bs(mkt.code);
  if(!b?.length){
    ctx.fillStyle="#2a2e39";ctx.font="11px 'Share Tech Mono'";ctx.textAlign="center";
    ctx.fillText("Fetching "+mkt.code+"...",W/2,H/2-8);
    ctx.fillStyle="#1e222d";ctx.font="9px 'Share Tech Mono'";
    ctx.fillText(sources[mkt.code]||"Yahoo Finance / Stooq",W/2,H/2+8);
    return;
  }

  const PL=6,PR=74,PT=10,PB=22,CW=W-PL-PR,CH=H-PT-PB;
  const maxC=Math.max(20,Math.floor(CW/9));
  const vis=b.slice(-maxC),n=vis.length;
  if(n<2)return;

  // Gap-based X: centre of candle i = PL + i*gap + gap/2
  const gap=CW/n,bw=Math.max(1.5,gap*0.7),toX=i=>PL+i*gap+gap/2;

  let hiP=Math.max(...vis.map(c=>c.h)),loP=Math.min(...vis.map(c=>c.l));
  const pad=(hiP-loP)*0.06||hiP*0.001;hiP+=pad;loP-=pad;
  const rng=hiP-loP||1,toY=p=>PT+CH*(1-(p-loP)/rng);

  // Grid
  ctx.font="7.5px 'Share Tech Mono'";ctx.textAlign="left";
  for(let gi=0;gi<=5;gi++){
    const pv=loP+(rng/5)*gi,y=toY(pv);
    ctx.strokeStyle="#1e222d";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();
    ctx.fillStyle="#4c525e";ctx.fillText(pv.toFixed(2),PL+CW+5,y+3);
  }

  // EMA 9 (gold) + EMA 21 (blue) -- aligned to candle centres via same toX()
  const closes=vis.map(c=>c.c);
  [[9,"#f5a62390",1.5],[21,"#2962ff70",1.5]].forEach(([p,col,lw])=>{
    const vals=ema(closes,p);
    ctx.strokeStyle=col;ctx.lineWidth=lw;ctx.beginPath();let st=false;
    vals.forEach((v,i)=>{if(v==null)return;
      const x=toX(i),y=toY(v);st?ctx.lineTo(x,y):(ctx.moveTo(x,y),st=true);});
    ctx.stroke();
  });

  // Candles -- TradingView up=#26a69a dn=#ef5350
  vis.forEach((c,i)=>{
    const x=toX(i),isUp=c.c>=c.o,col=isUp?"#26a69a":"#ef5350";
    ctx.globalAlpha=i===n-1?0.75:1;
    ctx.strokeStyle=col;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,toY(c.h));ctx.lineTo(x,toY(c.l));ctx.stroke();
    const by=toY(Math.max(c.o,c.c)),bh=Math.max(1.5,toY(Math.min(c.o,c.c))-by);
    ctx.fillStyle=isUp?"#26a69a30":"#ef535030";ctx.fillRect(x-bw/2,by,bw,bh);
    ctx.strokeStyle=col;ctx.strokeRect(x-bw/2,by,bw,bh);
    ctx.globalAlpha=1;
  });

  // Best bot SL/Entry/TP
  const bb=bestBot();
  if(bb){const tr=bb.openTrades[mkt.code];if(tr){
    const lvl=(price,col,dash,lbl)=>{
      if(price<loP||price>hiP)return;
      const y=toY(price);
      ctx.setLineDash(dash);ctx.strokeStyle=col;ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=col;ctx.font="bold 7.5px 'Share Tech Mono'";ctx.textAlign="left";
      ctx.fillText(lbl+" "+price.toFixed(2),PL+CW+5,y+3);
    };
    lvl(tr.tp,"#26a69a",[6,3],"TP");lvl(tr.entry,"#787b86",[2,5],"E");lvl(tr.sl,"#ef5350",[6,3],"SL");
  }}

  // Live price tag (solid colored box -- TradingView style)
  const last=closes.at(-1);
  if(last!=null){
    const y=toY(last),isUp=(liveQ[mkt.code]?.change??0)>=0,tagCol=isUp?"#26a69a":"#ef5350";
    ctx.setLineDash([3,4]);ctx.strokeStyle="#2a2e39";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(PL+CW,y);ctx.stroke();ctx.setLineDash([]);
    const bx=PL+CW+1,bxw=PR-2,byy=y-9;
    ctx.fillStyle=tagCol;
    if(ctx.roundRect){ctx.beginPath();ctx.roundRect(bx,byy,bxw,18,2);ctx.fill();}
    else ctx.fillRect(bx,byy,bxw,18);
    ctx.fillStyle="#fff";ctx.font="bold 9px 'Share Tech Mono'";ctx.textAlign="center";
    ctx.fillText(last.toFixed(2),bx+bxw/2,y+3.5);
  }

  // Time axis
  ctx.fillStyle="#4c525e";ctx.font="7px 'Share Tech Mono'";ctx.textAlign="center";
  const fmtT=ts=>new Date(ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
  [0,Math.floor(n/4),Math.floor(n/2),Math.floor(3*n/4),n-1].forEach(i=>{
    if(i<0||i>=n||!vis[i])return;
    const x=toX(i);
    ctx.strokeStyle="#1e222d";ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,PT+CH);ctx.lineTo(x,PT+CH+3);ctx.stroke();
    ctx.fillText(fmtT(vis[i].t),x,H-4);
  });
}

function rafLoop(){
  MKTS.forEach(m=>{if(dirty[m.id]){drawChart(m);dirty[m.id]=false;}});
  requestAnimationFrame(rafLoop);
}

const f$=v=>(v>=0?"+":"-")+"$"+Math.abs(v).toFixed(2);
const fPts=v=>(v>=0?"+":"")+v.toFixed(2)+"pts";
const fPct=v=>(v*100).toFixed(1)+"%";
const clr=v=>v>0?"#26a69a":v<0?"#ef5350":"#787b86";
const fTs=ts=>new Date(ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});


function playTradeOpen(){
  try{
    const ctx=new(window.AudioContext||window.webkitAudioContext)();
    // Two-tone alert: high then mid
    [[880,0,0.12],[660,0.13,0.28]].forEach(([freq,start,end])=>{
      const o=ctx.createOscillator(),g=ctx.createGain();
      o.connect(g);g.connect(ctx.destination);
      o.type="sine";o.frequency.setValueAtTime(freq,ctx.currentTime+start);
      g.gain.setValueAtTime(0.0,ctx.currentTime+start);
      g.gain.linearRampToValueAtTime(0.22,ctx.currentTime+start+0.02);
      g.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+end);
      o.start(ctx.currentTime+start);o.stop(ctx.currentTime+end);
    });
  }catch(e){}
}

function renderLeft(){
  const bb=bestBot();if(!bb)return;
  document.getElementById("bname").textContent=bb.name;
  document.getElementById("btype").textContent=`${bb.strat.type} | RR${bb.strat.rr}:1 | ATRx${bb.strat.atrMult}`;
  const p=getPnl(bb);
  document.getElementById("bbal").textContent="$"+bb.balance.toFixed(2);
  const pe=document.getElementById("bpnl");pe.textContent=f$(p);pe.style.color=clr(p);
  document.getElementById("bwr").textContent=fPct(getWR(bb));
  document.getElementById("bwl").textContent=`${bb.wins}/${bb.losses}/${bb.wins+bb.losses}`;
  document.getElementById("bsc").textContent=(score(bb,live())*100).toFixed(1)+"/100";
  if(bb.closedTrades.length>1){
    const cum=bb.closedTrades.map((_,i,a)=>a.slice(0,i+1).reduce((s,t)=>s+t.pnlUSD,0));
    const mn=Math.min(...cum),mx=Math.max(...cum),rng=mx-mn||1;
    const pts=cum.map((v,i)=>`${(i/(cum.length-1))*200},${23-((v-mn)/rng)*21}`).join(" ");
    const zy=23-((0-mn)/rng)*21;
    document.getElementById("spark").innerHTML=
      `<line x1="0" y1="${zy}" x2="200" y2="${zy}" stroke="#2a2e39" stroke-width="1" stroke-dasharray="3,4"/>` +
      `<polyline points="${pts}" fill="none" stroke="${p>=0?"#26a69a":"#ef5350"}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
  }
  // Top 3 bots by score
  const ab=live();
  const top3=[...ab].sort((a,b2)=>score(b2,ab)-score(a,ab)).slice(0,3);

  // Collect all open trades from top 3
  const top3Trades=[];
  top3.forEach(bot=>Object.entries(bot.openTrades).forEach(([code,t])=>top3Trades.push({bot,code,t})));

  // Sound: detect any new opens in top 3
  const curKeys={};
  top3Trades.forEach(({bot,code})=>{curKeys[bot.name+"|"+code]=true;});
  const hasNew=Object.keys(curKeys).some(k=>!prevOpenKeys[k]);
  if(hasNew)playTradeOpen();
  prevOpenKeys=curKeys;

  document.getElementById("openbox").innerHTML=top3Trades.length
    ?top3Trades.map(({bot,code,t})=>{
        const mkt=MKTS.find(m=>m.code===code);
        const cur=bs(code).at(-1)?.c??t.entry,pts=t.dir==="long"?cur-t.entry:t.entry-cur;
        const unr=Math.round(pts*mkt.ptVal*100)/100;
        const rank=top3.indexOf(bot)+1;
        const rankCol=rank===1?"#f0c020":rank===2?"#b0b0b0":"#cd7f32";
        return`<div class="ti">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <div style="display:flex;align-items:center;gap:5px">
              <span style="color:${rankCol};font-size:8px;font-family:'Orbitron',sans-serif">#${rank}</span>
              <b style="color:${mkt.col};font-size:11px">${mkt.code}</b>
              <span style="color:var(--tx3);font-size:8px">${bot.name}</span>
            </div>
            <b style="color:${t.dir==="long"?"#26a69a":"#ef5350"};font-size:11px;letter-spacing:1px">${t.dir.toUpperCase()}</b>
          </div>
          <div class="big3">
            <div class="big3-cell">
              <div class="big3-lbl" style="color:var(--tx3)">ENTRY</div>
              <div class="big3-val" style="color:#dce8ff">${t.entry.toFixed(2)}</div>
            </div>
            <div class="big3-cell">
              <div class="big3-lbl" style="color:#ef5350">STOP</div>
              <div class="big3-val" style="color:#ef5350">${t.sl.toFixed(2)}</div>
              <div style="font-size:7px;color:#ef535060;margin-top:1px">${Math.abs(t.entry-t.sl).toFixed(2)}pt</div>
            </div>
            <div class="big3-cell">
              <div class="big3-lbl" style="color:#26a69a">TARGET</div>
              <div class="big3-val" style="color:#26a69a">${t.tp.toFixed(2)}</div>
              <div style="font-size:7px;color:#26a69a60;margin-top:1px">${Math.abs(t.tp-t.entry).toFixed(2)}pt</div>
            </div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:8px;margin-top:2px">
            <span style="color:${clr(unr)}">${f$(unr)} unrealized</span>
            <span style="color:var(--tx3)">open ${fTs(t.openT)} &middot; ATR ${t.atr?.toFixed(2)}</span>
          </div>
        </div>`;}).join("")
    :`<div style="padding:5px 10px;color:var(--tx3)">No open trades in top 3</div>`;
  document.getElementById("histbox").innerHTML=bb.closedTrades.length
    ?bb.closedTrades.slice(-8).reverse().map(t=>{
        const mkt=MKTS.find(m=>m.code===t.code);
        return`<div class="hi" style="background:${t.won?"#26a69a0a":"#ef53500a"}">
          <span style="color:${mkt?.col||'#fff'}">${t.code}</span>
          <span style="color:${t.dir==="long"?"#26a69a70":"#ef535070"}">${t.dir==="long"?"L":"S"}</span>
          <span style="color:var(--tx2)">E:${t.entry?.toFixed(2)}</span>
          <span style="color:var(--tx2)">X:${t.exitPx?.toFixed(2)}</span>
          <b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b>
          <b style="color:${t.won?"#26a69a":"#ef5350"}">${t.won?"W":"L"}</b>
        </div>`;}).join("")
    :`<div style="padding:5px 10px;color:var(--tx3)">No trades yet</div>`;
  document.getElementById("stratbox").innerHTML=
    `<b style="color:var(--cy)">${bb.strat.type}</b><br>
     <span style="color:var(--tx2)">${bb.strat.desc}</span><br><br>
     <span class="k">R:R </span><b>${bb.strat.rr}:1</b> &nbsp;
     <span class="k">ATRx </span><b>${bb.strat.atrMult}</b> &nbsp;
     <span class="k">Wave </span><b style="color:var(--pu)">${bb.wave}</b><br>
     <span class="k">Trades </span><b>${bb.wins+bb.losses}</b> &nbsp;
     <span class="k">WR </span><b>${fPct(getWR(bb))}</b>`;
}

function renderSigBars(){
  MKTS.forEach(m=>{
    const sb=document.getElementById("sb-"+m.id);if(!sb)return;
    const open=live().filter(b=>b.openTrades[m.code]);
    if(open.length){
      sb.innerHTML=open.slice(0,5).map(b=>{
        const t=b.openTrades[m.code],cur=bs(m.code).at(-1)?.c??t.entry;
        const pts=t.dir==="long"?cur-t.entry:t.entry-cur;
        const unr=Math.round(pts*m.ptVal*100)/100;
        return`<span class="chip ${t.dir==="long"?"cl":"cs"}">
          ${b.name.split(" W")[0]} ${t.dir==="long"?"L":"S"}
          E:${t.entry.toFixed(2)} TP:${t.tp.toFixed(2)} SL:${t.sl.toFixed(2)}
          <span style="color:${clr(unr)}">${f$(unr)}</span>
        </span>`;}).join("");
    }else{
      sb.innerHTML=`<span style="color:var(--tx3);font-size:8px">watching for signal...</span>`;
    }
    const q=liveQ[m.code];
    if(q){const cc=document.getElementById("cchg-"+m.id);if(cc){
      const s=q.change>=0?"+":"";
      cc.textContent=`${s}${q.change.toFixed(2)} (${s}${q.changePct.toFixed(2)}%)`;
      cc.style.color=q.change>=0?"#26a69a":"#ef5350";
    }}
  });
}

function renderAllTrades(){
  document.getElementById("atbody").innerHTML=allClosed.length
    ?allClosed.map(t=>{
        const mkt=MKTS.find(m=>m.code===t.code);
        return`<tr style="background:${t.won?"#26a69a08":"#ef535008"}">
          <td><b style="color:${mkt?.col||'#fff'}">${t.code}</b></td>
          <td style="color:#9c27b0;max-width:88px;overflow:hidden;text-overflow:ellipsis">${t.botName}</td>
          <td style="color:${t.dir==="long"?"#26a69a70":"#ef535070"}">${t.dir==="long"?"L":"S"}</td>
          <td style="color:var(--tx2)">${t.entry?.toFixed(2)}</td>
          <td style="color:var(--tx2)">${t.exitPx?.toFixed(2)}</td>
          <td style="color:${clr(t.pts)}">${fPts(t.pts??0)}</td>
          <td><b style="color:${clr(t.pnlUSD)}">${f$(t.pnlUSD)}</b></td>
          <td style="color:${t.won?"#26a69a":"#ef5350"}">${t.won?"WIN":"LOSS"}</td>
        </tr>`;}).join("")
    :`<tr><td colspan="8" style="text-align:center;color:var(--tx3);padding:14px">
       Bots fire on crossover signals -- trades appear when SL or TP is hit on a real bar.
     </td></tr>`;
}

function renderRight(){
  const ab=live(),bb=bestBot();
  document.getElementById("blist").innerHTML=[...bots]
    .sort((a,b2)=>score(b2,ab)-score(a,ab)).slice(0,26)
    .map((b,i)=>{
      const sc=score(b,ab)*100,p=getPnl(b),bc=b.killed?"#2a2e39":sc>60?"#26a69a":sc>35?"#f5a623":"#ef5350";
      const isBest=b===bb;
      return`<div class="brow${b.killed?" dead":""}">
        <span class="bdot" style="background:${b.killed?"#2a2e39":bc}"></span>
        <div style="flex:1;min-width:0">
          <div style="display:flex;justify-content:space-between;gap:2px">
            <span style="color:${isBest?"var(--cy)":b.killed?"#363a45":"#787b86"};
              font-size:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">
              ${isBest?"* ":""}${b.name}</span>
            <b style="color:${clr(p)};font-size:8px;flex-shrink:0">${f$(p)}</b>
          </div>
          <div style="display:flex;align-items:center;gap:3px">
            <div class="bbar"><div class="bfill" style="width:${Math.max(0,Math.min(100,sc))}%;background:${bc}"></div></div>
            <span style="color:${bc};font-size:7.5px;flex-shrink:0">${fPct(getWR(b))}</span>
          </div>
          ${b.killed?`<div style="color:#3e1c1c;font-size:7px">${b.killReason}</div>`:""}
        </div></div>`;}).join("");
  document.getElementById("srcsect").innerHTML=MKTS.map(m=>{
    const src=sources[m.code]||"--",q=liveQ[m.code],ok=!!candles[m.code]?.length;
    return`<div style="display:flex;justify-content:space-between;margin-bottom:1px">
      <span style="color:${m.col}">${m.code}</span>
      <span style="font-size:8px;color:${ok?"#26a69a":"#ef5350"}">${src}</span>
    </div>${q?`<div style="font-size:7.5px;color:var(--tx3);margin-bottom:3px">H:${q.dayHigh} L:${q.dayLow} chg:${q.change>=0?"+":""}${q.change.toFixed(2)}</div>`:""}`;
  }).join("");
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
    candles={};liveQ={};sources={};prevPx={};dirty={};processedIdx={};startupDone=false;
    allClosed=[];totalClosed=0;wave=1;uid=0;bots=STRATS.map(s=>mkBot(s,1));
    document.getElementById("tcl").textContent="0";document.getElementById("tw").textContent="1";
    addLog("Interval -> "+iv+" -- fetching...","info");refreshFull();
  });
});
window.addEventListener("resize",()=>MKTS.forEach(m=>{dirty[m.id]=true;}));

buildGrid();
refreshFull();
setInterval(refreshFull,30000);
setInterval(refreshQuote,1500);
refreshQuote();
setInterval(()=>{renderLeft();renderSigBars();renderRight();},3000);
requestAnimationFrame(rafLoop);
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path=self.path.split("?")[0]
        if path in ("/","","/index.html"):
            body=HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-cache, no-store")
            self.end_headers();self.wfile.write(body)
        elif path=="/api/candles":
            params={}
            if "?" in self.path:
                for part in self.path.split("?",1)[1].split("&"):
                    if "=" in part:
                        k,v=part.split("=",1);params[k]=urllib.parse.unquote(v)
            code=params.get("code","ES").upper();iv_=params.get("iv","5m")
            d=get_ohlc(code,iv_);body=json.dumps(d).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers();self.wfile.write(body)
        elif path=="/api/quote":
            d=get_quotes();body=json.dumps(d).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers();self.wfile.write(body)
        else:
            self.send_response(404);self.end_headers()
    def log_message(self,*_): pass

def serve():
    http.server.HTTPServer(("127.0.0.1",PORT),Handler).serve_forever()

if __name__=="__main__":
    if sys.platform=="win32":
        try:
            import subprocess;subprocess.run(["chcp","65001"],capture_output=True,shell=True)
        except: pass
    _safe("")
    _safe("  FF ELITE BOTS v4")
    _safe("  ================")
    _safe("  OHLC history : Yahoo Finance v8 (query1->query2) -> Stooq CSV")
    _safe("  Live quotes  : Yahoo Finance v7 batch -- all 4 symbols in 1 call")
    _safe("  Update speed : OHLC every 30s | live price every 1.5s | RAF charts")
    _safe("  Libraries    : none -- standard library only")
    _safe("")
    _safe("  Pre-flight check...")
    _safe("")
    ok=0
    for code in CODES:
        try: fetch_ohlc(code,"5m");ok+=1
        except RuntimeError as e: _safe(f"  [--] {code}: {e}")
    _safe("")
    try:
        q=fetch_quotes_batch()
        _safe(f"  [OK] Quotes: {', '.join(f'{c}={v[chr(112)]+str(v[chr(114)+chr(105)+chr(99)+chr(101)])}'.replace(chr(112),'') for c,v in q.items())}")
    except: pass
    try:
        q=fetch_quotes_batch()
        items=[]
        for c,v in q.items(): items.append(f"{c}={v['price']}")
        _safe(f"  [OK] Quotes: {', '.join(items)}")
    except Exception as e: _safe(f"  [--] Quotes: {e}")
    _safe("")
    if ok: _safe(f"  {ok}/4 OHLC OK -- charts update every 1.5s via requestAnimationFrame")
    else:  _safe("  No data -- market may be closed. Auto-retries every 30s.")
    _safe("  CME Globex: Sun 6pm - Fri 5pm ET")
    _safe("")
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1",PORT))==0:
            _safe(f"  Port {PORT} already in use -- close that process first.");_safe("");sys.exit(1)
    threading.Thread(target=serve,daemon=True).start()
    time.sleep(0.4)
    url=f"http://localhost:{PORT}"
    _safe(f"  Running at  {url}")
    _safe("")
    _safe("  Press Ctrl+C to stop.")
    _safe("")
    webbrowser.open(url)
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        _safe("");_safe("  Stopped.");_safe("");sys.exit(0)