#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
live_trader.py -- routes Pine-strategy signals to a Tradovate account.

  CMD 1:   python run.py
  CMD 2:   TRADOVATE_DRY_RUN=1 python live_trader.py

  Dashboard / webhook:  http://localhost:7434

Polls run.py /api/candles for closed 5m bars, runs pine_strategy.evaluate,
and submits bracket (OSO) orders to Tradovate. Also accepts TradingView
webhook alerts at POST /webhook.

DRY RUN IS ON BY DEFAULT (TRADOVATE_DRY_RUN=1): requests are logged, nothing
is sent. Set TRADOVATE_DRY_RUN=0 to place real orders -- with
TRADOVATE_ENV=live that is REAL MONEY.
"""

import sys, io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except AttributeError:
    pass

import json, time, datetime, threading, socket, os
import urllib.request, urllib.parse, http.server

import pine_strategy as ps
from tradovate import TradovateClient, TradovateConfig, TradovateError

# =============================================================================
#  CONFIGURATION
# =============================================================================

RUN_HOST   = "http://127.0.0.1:7432"
POLL_IV    = "5m"
POLL_EVERY = 30
DASH_PORT  = 7434
STATE_FILE = "live_state.json"

MARKET_ENABLED   = {"ES": True, "MES": False, "NQ": False, "MNQ": False}
TRADOVATE_SYMBOLS = {c: os.environ.get(f"TRADOVATE_SYMBOL_{c}", "")
                     for c in ("ES", "MES", "NQ", "MNQ")}
WEBHOOK_TOKEN    = os.environ.get("WEBHOOK_TOKEN", "")

CFG = ps.PineConfig()


def sp(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


# =============================================================================
#  CANDLE FETCH  (same endpoint as broker.py)
# =============================================================================

def _fetch(code):
    url = f"{RUN_HOST}/api/candles?code={urllib.parse.quote(code)}&iv={POLL_IV}"
    with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
        d = json.loads(r.read())
    return d.get("candles", []) if d.get("live") else []


# =============================================================================
#  LIVE TRADER
# =============================================================================

class LiveTrader:
    def __init__(self, client, cfg=CFG, state_file=STATE_FILE):
        self.client = client
        self.cfg = cfg
        self.state_file = state_file
        self.markets = {}          # code -> {position, last_bar_t, last_signal, orders}
        self.symbols = {}          # code -> tradovate contract symbol
        self.contract_ids = {}     # code -> contractId
        self._lock = threading.Lock()
        self._load_state()

    # ── state persistence ──

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                for code, m in d.get("markets", {}).items():
                    self.markets[code] = m
                sp(f"  [STATE] restored {len(self.markets)} market(s)")
            except Exception:
                pass

    def _save_state(self):
        with self._lock:
            d = {"markets": self.markets,
                 "saved_at": datetime.datetime.now().isoformat()}
            try:
                with open(self.state_file, "w", encoding="utf-8") as f:
                    json.dump(d, f, indent=2)
            except Exception as e:
                sp(f"  [STATE] save failed: {e}")

    def _mkt(self, code):
        return self.markets.setdefault(code, {
            "position": None, "last_bar_t": 0, "last_signal": None, "orders": []})

    # ── symbol resolution ──

    def resolve_symbols(self):
        for code, enabled in MARKET_ENABLED.items():
            if not enabled:
                continue
            sym = TRADOVATE_SYMBOLS.get(code)
            if not sym:
                try:
                    sym = self.client.suggest_contract(code)
                except Exception as e:
                    sp(f"  [SYMBOL] {code}: suggest failed: {e}")
                    sym = None
            if not sym:
                sp(f"  [SYMBOL] {code}: could not resolve contract, skipping")
                continue
            self.symbols[code] = sym
            sp(f"  [SYMBOL] {code} -> {sym}")
            try:
                c = self.client.find_contract(sym)
                if c and c.get("id"):
                    self.contract_ids[code] = c["id"]
            except Exception as e:
                sp(f"  [SYMBOL] {code}: contract lookup failed: {e}")

    def reconcile_positions(self):
        try:
            positions = self.client.positions()
        except Exception as e:
            sp(f"  [RECONCILE] positions failed: {e}")
            return
        for code in self.symbols:
            cid = self.contract_ids.get(code)
            net = 0
            for p in positions:
                if cid is None or p.get("contractId") == cid:
                    net += p.get("netPos", 0)
            if net > 0:
                self._mkt(code)["position"] = "long"
            elif net < 0:
                self._mkt(code)["position"] = "short"
        self._save_state()

    # ── order routing ──

    def _flatten(self, code):
        cid = self.contract_ids.get(code)
        sym = self.symbols.get(code)
        try:
            self.client.cancel_all_orders(cid)
        except Exception as e:
            sp(f"  [ORDERS] {code} cancel failed: {e}")
        if cid is not None:
            try:
                self.client.liquidate(cid)
            except Exception as e:
                sp(f"  [ORDERS] {code} liquidate failed: {e}")
        m = self._mkt(code)
        m["position"] = None
        m["orders"] = []

    def route_signal(self, code, result):
        """Execute an evaluate() result: Signal, 'flat', or None."""
        m = self._mkt(code)
        if result is None:
            return []
        if result == "flat":
            if m["position"]:
                sp(f"  [TRADE] {code} FLAT (opposite signal)")
                self._flatten(code)
                self._save_state()
            return []

        sig = result
        sym = self.symbols.get(code)
        if not sym:
            sp(f"  [TRADE] {code}: no symbol resolved, signal ignored")
            return []
        if m["position"] and m["position"] != sig.side:
            sp(f"  [TRADE] {code} reversing {m['position']} -> {sig.side}")
            self._flatten(code)
        elif m["position"] == sig.side:
            return []

        sp(f"  [TRADE] {code} {sig.side.upper()} x{sig.qty}  entry~{sig.entry}  "
           f"stop={sig.stop}  tps={sig.tps}  [{sig.reason}]")
        try:
            resps = self.client.submit_signal(sym, sig)
        except TradovateError as e:
            sp(f"  [TRADE] {code} order failed: {e}")
            return []
        m["position"] = sig.side
        m["orders"] = resps
        m["last_signal"] = {"side": sig.side, "entry": sig.entry, "stop": sig.stop,
                            "tps": sig.tps, "qty": sig.qty, "bar_t": sig.bar_t,
                            "reason": sig.reason,
                            "at": datetime.datetime.now().isoformat()}
        self._save_state()
        return resps

    # ── poll loop ──

    def poll_once(self):
        for code, enabled in MARKET_ENABLED.items():
            if not enabled or code not in self.symbols:
                continue
            try:
                bars = _fetch(code)
            except Exception as e:
                sp(f"  [POLL] {code}: {e}")
                continue
            if len(bars) < 2:
                continue
            m = self._mkt(code)
            closed = bars[-2]
            if closed["t"] == m["last_bar_t"]:
                continue
            m["last_bar_t"] = closed["t"]
            try:
                result = ps.evaluate(bars[:-1], self.cfg, m["position"])
            except Exception as e:
                sp(f"  [EVAL] {code}: {e}")
                continue
            if result is not None:
                sp(f"  [SIGNAL] {code} bar_t={closed['t']} -> "
                   f"{result if result == 'flat' else result.side}")
            self.route_signal(code, result)

    def poll_loop(self):
        while True:
            self.poll_once()
            time.sleep(POLL_EVERY)

    # ── status ──

    def status(self):
        return {
            "dry_run": self.client.cfg.dry_run,
            "env": self.client.cfg.env,
            "symbols": dict(self.symbols),
            "markets": {c: dict(m) for c, m in self.markets.items()},
            "webhook_configured": bool(WEBHOOK_TOKEN),
            "time": datetime.datetime.now().isoformat(),
        }


# =============================================================================
#  WEBHOOK  (testable as a plain function)
# =============================================================================

def handle_webhook(payload, trader):
    """Handle a TradingView alert payload. Returns (http_status, response_dict).

    Expected JSON: {"token": str, "code": "ES", "action": "long"|"short"|"flat",
                    "qty"?: int, "stop"?: float, "tps"?: [float, ...]}
    """
    if not WEBHOOK_TOKEN or payload.get("token") != WEBHOOK_TOKEN:
        return 401, {"error": "unauthorized"}

    code = str(payload.get("code", "")).upper()
    action = str(payload.get("action", "")).lower()
    if code not in MARKET_ENABLED or not MARKET_ENABLED[code]:
        return 400, {"error": f"market {code} not enabled"}
    if action not in ("long", "short", "flat"):
        return 400, {"error": "action must be long|short|flat"}

    if action == "flat":
        resps = trader.route_signal(code, "flat")
        return 200, {"action": "flat", "responses": resps}

    stop = payload.get("stop")
    tps = payload.get("tps")
    qty = int(payload.get("qty") or trader.cfg.qty_per_trade)
    qty = max(1, min(qty, len(trader.cfg.tp_mults)))

    try:
        bars = _fetch(code)
    except Exception as e:
        return 502, {"error": f"candle fetch failed: {e}"}
    if len(bars) < 2:
        return 502, {"error": "not enough candles"}

    if stop is None or not tps:
        st = ps.compute_state(bars[:-1], trader.cfg)
        if not st:
            return 500, {"error": "could not compute ATR levels"}
        close = st["close"]
        a = st["atr"]
        if action == "long":
            stop = ps.snap(close - a * trader.cfg.stop_mult, trader.cfg.tick)
            tps = [ps.snap(close + a * m, trader.cfg.tick)
                   for m in trader.cfg.tp_mults[:qty]]
        else:
            stop = ps.snap(close + a * trader.cfg.stop_mult, trader.cfg.tick)
            tps = [ps.snap(close - a * m, trader.cfg.tick)
                   for m in trader.cfg.tp_mults[:qty]]
        entry = ps.snap(close, trader.cfg.tick)
    else:
        tps = [float(x) for x in tps][:qty]
        entry = ps.snap(float(bars[-2]["c"]), trader.cfg.tick)

    sig = ps.Signal(side=action, entry=entry, stop=float(stop),
                    tps=[float(x) for x in tps], qty=qty,
                    bar_t=bars[-2]["t"], reason="webhook")
    resps = trader.route_signal(code, sig)
    return 200, {"signal": {"side": sig.side, "entry": sig.entry, "stop": sig.stop,
                            "tps": sig.tps, "qty": sig.qty},
                 "responses": resps}


# =============================================================================
#  DASHBOARD + HTTP SERVER  (http://localhost:7434)
# =============================================================================

_TRADER = [None]


def _dash_html():
    t = _TRADER[0]
    if not t:
        return "<html><body>Starting...</body></html>"
    s = t.status()
    rows = "".join(
        f"<tr><td>{c}</td><td>{m.get('position') or '-'}</td>"
        f"<td>{(m.get('last_signal') or {}).get('side', '-')}</td>"
        f"<td>{s['symbols'].get(c, '-')}</td></tr>"
        for c, m in s["markets"].items())
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="15"><title>FF Live Trader</title>
<style>body{{background:#020209;color:#b8cce0;font-family:monospace;padding:16px}}
h1{{color:#18d8f0;font-size:16px}}td,th{{padding:4px 10px;border-bottom:1px solid #141438;text-align:left}}
.warn{{color:#f03050;font-weight:bold}}</style></head><body>
<h1>FF ELITE BOTS &mdash; LIVE TRADER (Pine &rarr; Tradovate)</h1>
<p>env: <b>{s['env']}</b> &nbsp; dry_run: <b class="{'' if s['dry_run'] else 'warn'}">{s['dry_run']}</b>
&nbsp; webhook: {'configured' if s['webhook_configured'] else 'DISABLED (no WEBHOOK_TOKEN)'}</p>
<table><tr><th>MARKET</th><th>POSITION</th><th>LAST SIGNAL</th><th>CONTRACT</th></tr>{rows}</table>
<p style="color:#304060">auto-refresh 15s &middot; {s['time']}</p>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, _dash_html(), "text/html;charset=utf-8")
        elif self.path == "/api/status":
            t = _TRADER[0]
            self._send(200, json.dumps(t.status() if t else {}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/webhook":
            self._send(404, json.dumps({"error": "not found"}))
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send(400, json.dumps({"error": "invalid json"}))
            return
        try:
            status, resp = handle_webhook(payload, _TRADER[0])
        except Exception as e:
            status, resp = 500, {"error": str(e)}
        self._send(status, json.dumps(resp))

    def log_message(self, *_):
        pass


# =============================================================================
#  ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    sp("")
    sp("  FF ELITE BOTS  --  Live Trader (Pine strategy -> Tradovate)")
    sp("  ==========================================================")
    cfg = TradovateConfig.from_env()
    sp(f"  run.py API : {RUN_HOST}")
    sp(f"  Dashboard  : http://localhost:{DASH_PORT}")
    sp(f"  Tradovate  : {cfg.env} ({cfg.base_url})")
    sp(f"  DRY RUN    : {cfg.dry_run}" + ("  << REAL ORDERS OFF" if cfg.dry_run else
       "  *** REAL ORDERS WILL BE PLACED ***"))
    sp(f"  Interval   : {POLL_IV}  |  Poll every {POLL_EVERY}s")
    sp(f"  Webhook    : {'enabled' if WEBHOOK_TOKEN else 'DISABLED (set WEBHOOK_TOKEN)'}")
    sp("")

    sp("  Checking run.py (port 7432)...")
    for attempt in range(12):
        try:
            with socket.create_connection(("127.0.0.1", 7432), timeout=2):
                break
        except OSError:
            if attempt == 11:
                sp("  ERROR: run.py not running.\n  Start it: python run.py")
                sys.exit(1)
            sp(f"  Waiting ({attempt+1}/12)...")
            time.sleep(3)
    sp("  run.py OK")
    sp("")

    client = TradovateClient(cfg)
    try:
        client.authenticate()
    except TradovateError as e:
        sp(f"  ERROR: Tradovate auth failed: {e}")
        sys.exit(1)

    trader = LiveTrader(client)
    _TRADER[0] = trader
    trader.resolve_symbols()
    trader.reconcile_positions()

    threading.Thread(target=trader.poll_loop, daemon=True).start()
    srv = http.server.HTTPServer(("127.0.0.1", DASH_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    sp(f"  Dashboard: http://localhost:{DASH_PORT}")
    sp("  Ctrl+C to stop.")
    sp("")

    try:
        while True:
            time.sleep(120)
            sp("  " + json.dumps(trader.status()["markets"]))
    except KeyboardInterrupt:
        trader._save_state()
        sp("\n  Stopped.")
        sys.exit(0)
