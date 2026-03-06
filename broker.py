#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF ELITE BOTS  --  Local Paper Trading Engine
=============================================
Zero accounts.  Zero API keys.  Zero pip installs.

  CMD 1:   python run.py
  CMD 2:   python broker.py

  Dashboard:  http://localhost:7433

HOW IT WORKS
------------
1. Polls run.py for real candle data every 30 s
2. Runs the same 10 strategies + scoring logic in Python
3. After PROMOTE_AFTER_MINUTES the best qualifying bot is promoted
4. Every signal from the promoted strategy fires a paper order
5. Fills use the EXACT same bar-close / SL-TP logic as run.py
6. All trades saved to  paper_ledger.json  (persists across restarts)
7. Mini web dashboard at  http://localhost:7433

PROMOTION GATES (all must pass before paper trading starts)
-----------------------------------------------------------
  PROMOTE_AFTER_MINUTES = 60   -- observe bots for this long first
  MIN_SCORE             = 55   -- composite score 0-100
  MIN_TRADES            = 6    -- minimum closed sim trades
  MIN_WIN_RATE          = 0.40 -- minimum win rate

When ready for a real broker, replace place_order() with a real API call.
The promotion logic and signal mirroring stay exactly the same.
"""

import sys, io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except AttributeError:
    pass

import json, time, datetime, threading, socket, os
import urllib.request, urllib.parse, http.server

# =============================================================================
#  CONFIGURATION
# =============================================================================

RUN_HOST   = "http://127.0.0.1:7432"
DASH_PORT  = 7433
POLL_IV    = "5m"
POLL_EVERY = 30
LEDGER     = "paper_ledger.json"

PROMOTE_AFTER_MINUTES = 60
MIN_SCORE             = 55
MIN_TRADES            = 6
MIN_WIN_RATE          = 0.40

MSPEC = {
    "ES":  {"ptVal": 50,  "tick": 0.25},
    "MES": {"ptVal": 5,   "tick": 0.25},
    "NQ":  {"ptVal": 20,  "tick": 0.25},
    "MNQ": {"ptVal": 2,   "tick": 0.25},
}
MARKET_ENABLED = {"ES": True, "MES": True, "NQ": True, "MNQ": True}
PAPER_START    = 50000.0

def sp(msg):
    try:    print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))

# =============================================================================
#  LEDGER
# =============================================================================

class Ledger:
    def __init__(self, path):
        self.path  = path
        self._lock = threading.Lock()
        self._d    = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"trades":[], "open":{},
                "balance":{c: PAPER_START for c in MSPEC},
                "promoted":None, "promoted_at":None}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._d, f, indent=2)

    def get(self, key, default=None):
        with self._lock: return self._d.get(key, default)

    def set_promoted(self, name):
        with self._lock:
            self._d["promoted"]    = name
            self._d["promoted_at"] = datetime.datetime.now().isoformat()
            self._save()

    def open_trade(self, code, td):
        with self._lock:
            self._d["open"][code] = {**td, "opened_at": datetime.datetime.now().isoformat()}
            self._save()

    def close_trade(self, code, exit_price, bar_t, won):
        with self._lock:
            t = self._d["open"].get(code)
            if not t: return None
            pts = round((exit_price-t["entry"]) if t["dir"]=="long" else (t["entry"]-exit_price), 2)
            pnl = round(pts * MSPEC[code]["ptVal"], 2)
            self._d["balance"][code] = round(self._d["balance"][code] + pnl, 2)
            rec = {**t, "code":code, "exit_price":exit_price, "pts":pts, "pnl":pnl,
                   "won":won, "closed_at":datetime.datetime.now().isoformat(), "bar_t":bar_t}
            self._d["trades"].append(rec)
            del self._d["open"][code]
            self._save()
            return rec

    def all_trades(self):
        with self._lock: return list(self._d["trades"])
    def open_positions(self):
        with self._lock: return dict(self._d["open"])
    def balances(self):
        with self._lock: return dict(self._d["balance"])
    def summary(self):
        with self._lock:
            ts=self._d["trades"]
            wins=sum(1 for t in ts if t["won"]); losses=len(ts)-wins
            return {"trades":len(ts),"wins":wins,"losses":losses,
                    "wr":wins/len(ts) if ts else 0.0,
                    "total_pnl":sum(t["pnl"] for t in ts),
                    "balances":dict(self._d["balance"]),
                    "promoted":self._d.get("promoted"),
                    "promoted_at":self._d.get("promoted_at"),
                    "open":dict(self._d["open"])}

_ledger = Ledger(LEDGER)

# =============================================================================
#  INDICATORS
# =============================================================================

snap = lambda p: round(p*4)/4

def _ema(a,p):
    if len(a)<p: return [None]*len(a)
    k=2/(p+1); o=[None]*len(a); o[p-1]=sum(a[:p])/p
    for i in range(p,len(a)): o[i]=a[i]*k+o[i-1]*(1-k)
    return o
def _sma(a,p): return [None if i<p-1 else sum(a[i-p+1:i+1])/p for i in range(len(a))]
def _atr(bars,p=14):
    if not bars: return []
    tr=[bars[0]["h"]-bars[0]["l"]]
    for i in range(1,len(bars)):
        tr.append(max(bars[i]["h"]-bars[i]["l"],
                      abs(bars[i]["h"]-bars[i-1]["c"]),
                      abs(bars[i]["l"]-bars[i-1]["c"])))
    return [None if i<p else sum(tr[i-p+1:i+1])/p for i in range(len(tr))]
def _rsi(c,p=14):
    r=[None]*len(c)
    if len(c)<p+1: return r
    g=l=0.0
    for i in range(1,p+1):
        d=c[i]-c[i-1];g+=d if d>0 else 0;l+=(-d if d<0 else 0)
    ag,al=g/p,l/p; r[p]=100-100/(1+ag/max(al,1e-10))
    for i in range(p+1,len(c)):
        d=c[i]-c[i-1]
        ag=(ag*(p-1)+(d if d>0 else 0))/p; al=(al*(p-1)+(-d if d<0 else 0))/p
        r[i]=100-100/(1+ag/max(al,1e-10))
    return r
def _macd(c):
    f=_ema(c,12);s=_ema(c,26)
    ln=[f[i]-s[i] if f[i] is not None and s[i] is not None else None for i in range(len(c))]
    sig_r=_ema([v for v in ln if v is not None],9);si=0;sg=[]
    for v in ln:
        if v is None:sg.append(None)
        else:sg.append(sig_r[si] if si<len(sig_r) else None);si+=1
    return [ln[i]-sg[i] if ln[i] is not None and sg[i] is not None else None for i in range(len(c))]
def _bb(c,p=20,m=2):
    sm=_sma(c,p);out=[]
    for i in range(len(c)):
        if sm[i] is None:out.append((None,None));continue
        sl=c[i-p+1:i+1];mn=sm[i];std=(sum((v-mn)**2 for v in sl)/p)**0.5
        out.append((mn+m*std,mn-m*std))
    return out
def _stoch(bars,p=9):
    out=[]
    for i in range(len(bars)):
        if i<p-1:out.append(None);continue
        sl=bars[i-p+1:i+1];hi=max(c["h"] for c in sl);lo=min(c["l"] for c in sl)
        out.append(50.0 if hi==lo else (bars[i]["c"]-lo)/(hi-lo)*100)
    return out
def _cci(bars,p=14):
    out=[]
    for i in range(len(bars)):
        if i<p-1:out.append(None);continue
        sl=bars[i-p+1:i+1];tp=[(c["h"]+c["l"]+c["c"])/3 for c in sl]
        mn=sum(tp)/p;md=sum(abs(v-mn) for v in tp)/p
        out.append(((bars[i]["h"]+bars[i]["l"]+bars[i]["c"])/3-mn)/(0.015*md) if md else 0)
    return out

# =============================================================================
#  STRATEGIES
# =============================================================================

def _s_trend(b):
    if len(b)<62:return None
    c=[x["c"] for x in b];n=len(c)-1;f,s=_ema(c,21),_ema(c,55)
    if None in(f[n],s[n],f[n-1],s[n-1]):return None
    if f[n-1]<=s[n-1] and f[n]>s[n]:return"long"
    if f[n-1]>=s[n-1] and f[n]<s[n]:return"short"
def _s_stoch(b):
    if len(b)<15:return None
    k=_stoch(b,9);n=len(k)-1
    if None in(k[n],k[n-1]):return None
    if k[n-1]<=20 and k[n]>20:return"long"
    if k[n-1]>=80 and k[n]<80:return"short"
def _s_fftop(b):
    if len(b)<40:return None
    c=[x["c"] for x in b];n=len(c)-1;f,s=_ema(c,8),_ema(c,34)
    if None in(f[n],s[n],f[n-1],s[n-1]):return None
    if f[n-1]<=s[n-1] and f[n]>s[n]:return"long"
    if f[n-1]>=s[n-1] and f[n]<s[n]:return"short"
def _s_gold(b):
    if len(b)<12:return None
    c=[x["c"] for x in b];n=len(c)-1
    if not c[n-5] or not c[n-6]:return None
    r=(c[n]-c[n-5])/c[n-5]*100;rp=(c[n-1]-c[n-6])/c[n-6]*100
    if rp<0.25 and r>=0.25:return"long"
    if rp>-0.25 and r<=-0.25:return"short"
def _s_vel(b):
    if len(b)<15:return None
    c=[x["c"] for x in b];n=len(c)-1
    if not c[n-10] or not c[n-11]:return None
    r=(c[n]-c[n-10])/c[n-10]*100;rp=(c[n-1]-c[n-11])/c[n-11]*100
    if rp<0.4 and r>=0.4:return"long"
    if rp>-0.4 and r<=-0.4:return"short"
def _s_bb(b):
    if len(b)<25:return None
    c=[x["c"] for x in b];n=len(c)-1;bb=_bb(c,20,2)
    if None in(bb[n][0],bb[n-1][0]):return None
    if c[n-1]<=bb[n-1][0] and c[n]>bb[n][0]:return"long"
    if c[n-1]>=bb[n-1][1] and c[n]<bb[n][1]:return"short"
def _s_macd(b):
    if len(b)<35:return None
    h=_macd([x["c"] for x in b]);n=len(h)-1
    if None in(h[n],h[n-1]):return None
    if h[n-1]<=0 and h[n]>0:return"long"
    if h[n-1]>=0 and h[n]<0:return"short"
def _s_atr(b):
    if len(b)<30:return None
    c=[x["c"] for x in b];n=len(c)-1;at=_atr(b,14);sm=_sma(c,20)
    if None in(at[n],sm[n],at[n-1],sm[n-1]):return None
    if c[n-1]<=sm[n-1]+2*at[n-1] and c[n]>sm[n]+2*at[n]:return"long"
    if c[n-1]>=sm[n-1]-2*at[n-1] and c[n]<sm[n]-2*at[n]:return"short"
def _s_cci(b):
    if len(b)<20:return None
    ci=_cci(b,14);n=len(ci)-1
    if None in(ci[n],ci[n-1]):return None
    if ci[n-1]<=-100 and ci[n]>-100:return"long"
    if ci[n-1]>=100  and ci[n]<100: return"short"
def _s_rsi(b):
    if len(b)<20:return None
    ri=_rsi([x["c"] for x in b],14);n=len(ri)-1
    if None in(ri[n],ri[n-1]):return None
    if ri[n-1]<=30 and ri[n]>30:return"long"
    if ri[n-1]>=70 and ri[n]<70:return"short"

STRATS=[
    {"id":"TrendFollow_A","name":"TrendFollow A",  "rr":3.0,"m":1.5,"fn":_s_trend},
    {"id":"Stoch_Master", "name":"Stoch Master",   "rr":1.5,"m":1.2,"fn":_s_stoch},
    {"id":"FF_Top_Trader","name":"FF Top Trader",  "rr":2.5,"m":1.5,"fn":_s_fftop},
    {"id":"GoldPatrol99", "name":"Gold Patrol 99", "rr":1.5,"m":1.2,"fn":_s_gold},
    {"id":"VelocityTrader","name":"Velocity Trader","rr":2.0,"m":1.5,"fn":_s_vel},
    {"id":"BollingerBreak","name":"Bollinger Break","rr":2.5,"m":1.5,"fn":_s_bb},
    {"id":"MACD_Wave",    "name":"MACD Wave",      "rr":2.0,"m":1.5,"fn":_s_macd},
    {"id":"ATR_Channel",  "name":"ATR Channel",    "rr":2.5,"m":1.5,"fn":_s_atr},
    {"id":"CCI_Reversal", "name":"CCI Reversal",   "rr":2.0,"m":1.2,"fn":_s_cci},
    {"id":"RSI_Momentum", "name":"RSI Momentum",   "rr":2.0,"m":1.2,"fn":_s_rsi},
]
MARKETS=[{"code":c,"ptVal":v["ptVal"],"tick":v["tick"]} for c,v in MSPEC.items()]

# =============================================================================
#  BOT ENGINE  (simulation fleet)
# =============================================================================

class Bot:
    def __init__(self,s,w=1):
        self.name=f"{s['name']} W{w}";self.strat=s;self.wave=w
        self.balance=50000.0;self.open_trades={};self.closed=[]
        self.wins=self.losses=0;self.killed=False;self.kill_reason=""
    @property
    def pnl(self):return self.balance-50000
    @property
    def wr(self):t=self.wins+self.losses;return self.wins/t if t else 0.0
    @property
    def trades(self):return self.wins+self.losses
    def score(self,ab):
        ps=[b.pnl for b in ab];mn=min(ps);mx=max(ps);rng=mx-mn or 1
        return self.wr*0.5+((self.pnl-mn)/rng)*0.5

class BotEngine:
    def __init__(self):
        self.bots=[Bot(s,1) for s in STRATS];self.wave=1;self.pidx={};self.ready=False
    def live(self):return [b for b in self.bots if not b.killed]
    def best(self):
        ab=self.live();return max(ab,key=lambda b:b.score(ab)) if ab else None

    def update(self,candles):
        if not self.ready:
            for code,bars in candles.items():
                if bars and len(bars)>=2:self.pidx[code]=len(bars)-2
            self.ready=True;return
        for mkt in MARKETS:
            code=mkt["code"];bars=candles.get(code,[])
            if len(bars)<35:continue
            atr=_atr(bars,14)
            start=self.pidx.get(code,len(bars)-2)+1;end=len(bars)-2
            for i in range(start,end+1):
                bar=bars[i]
                for bot in self.bots:
                    if bot.killed:continue
                    t=bot.open_trades.get(code)
                    if t:self._exit(bot,mkt,bar,t)
                    else:self._enter(bot,mkt,bar,bars,i,atr)
                self.pidx[code]=i
            for bot in self.bots:
                if bot.killed:continue
                if bot.balance<48000:bot.killed=True;bot.kill_reason="Bal<$48k";bot.open_trades={}
                if bot.trades>=20 and bot.wr<0.25:bot.killed=True;bot.kill_reason="WR<25%";bot.open_trades={}
        if len(self.live())<=5:
            self.wave+=1;self.bots.extend([Bot(s,self.wave) for s in STRATS])
            sp(f"  [SIM] Wave {self.wave} spawned")

    def _exit(self,bot,mkt,bar,t):
        code=mkt["code"];closed=False;ep=0;won=False
        if t["dir"]=="long":
            if   bar["h"]>=t["tp"] and bar["l"]<=t["sl"]:ep=t["sl"];closed=True
            elif bar["h"]>=t["tp"]:ep=t["tp"];closed=True;won=True
            elif bar["l"]<=t["sl"]:ep=t["sl"];closed=True
        else:
            if   bar["l"]<=t["tp"] and bar["h"]>=t["sl"]:ep=t["sl"];closed=True
            elif bar["l"]<=t["tp"]:ep=t["tp"];closed=True;won=True
            elif bar["h"]>=t["sl"]:ep=t["sl"];closed=True
        if closed:
            ep=snap(ep);pts=ep-t["entry"] if t["dir"]=="long" else t["entry"]-ep
            pnl=round(pts*mkt["ptVal"],2);bot.balance=round(bot.balance+pnl,2)
            if won:bot.wins+=1
            else:bot.losses+=1
            bot.closed.append({**t,"exit":ep,"pts":round(pts,2),"pnl":pnl,"won":won})
            del bot.open_trades[code]

    def _enter(self,bot,mkt,bar,bars,idx,atr):
        code=mkt["code"];sig=bot.strat["fn"](bars[:idx+1]);av=atr[idx]
        if sig and av is not None:
            entry=snap(bar["c"]);dist=snap(max(av*bot.strat["m"],2*mkt["tick"]))
            sl=snap(entry-dist if sig=="long" else entry+dist)
            tp=snap(entry+dist*bot.strat["rr"] if sig=="long" else entry-dist*bot.strat["rr"])
            bot.open_trades[code]={"dir":sig,"entry":entry,"sl":sl,"tp":tp,"open_t":bar["t"],"atr":av}

# =============================================================================
#  PAPER ENGINE
# =============================================================================

class PaperEngine:
    """
    Mirrors the promoted bot's open_trades dict directly.
    After BotEngine.update() runs, the promoted bot's open_trades is the
    ground truth -- we just sync the ledger to match it.
    No independent bar scanning -- no index drift, no missed signals.
    """
    def __init__(self,sim):
        self.sim=sim;self.promoted=None;self.start=time.time()
        # Track what the bot had last cycle so we can detect open/close events
        self._prev_trades={}   # code -> trade dict that was open last cycle

    def on_candles(self,candles):
        # 1. Let the sim engine process all new bars for every bot
        self.sim.update(candles)
        # 2. Decide if we should promote a bot
        self._check_promote()
        # 3. Sync ledger to the promoted bot's current open_trades
        if self.promoted:
            self._sync(candles)

    def _check_promote(self):
        if self.promoted:return
        # Restore promoted bot from a previous session
        saved=_ledger.get("promoted")
        if saved:
            for bot in self.sim.bots:
                if bot.name==saved:
                    self.promoted=bot
                    # Seed _prev_trades so we don't immediately re-open everything
                    self._prev_trades=dict(bot.open_trades)
                    sp(f"  [PAPER] Restored promoted bot: {saved}")
                    return
        elapsed=(time.time()-self.start)/60
        if elapsed<PROMOTE_AFTER_MINUTES:return
        bb=self.sim.best()
        if not bb:return
        ab=self.sim.live();sc=bb.score(ab)*100
        sp(f"  [PAPER] Promotion check: {bb.name}  score={sc:.1f}  wr={bb.wr*100:.1f}%  trades={bb.trades}")
        if sc<MIN_SCORE:sp(f"  [PAPER] Score {sc:.1f} < {MIN_SCORE}");return
        if bb.trades<MIN_TRADES:sp(f"  [PAPER] Only {bb.trades} trades, need {MIN_TRADES}");return
        if bb.wr<MIN_WIN_RATE:sp(f"  [PAPER] WR {bb.wr*100:.1f}% < {MIN_WIN_RATE*100:.0f}%");return
        self.promoted=bb
        self._prev_trades=dict(bb.open_trades)
        _ledger.set_promoted(bb.name)
        sp("");sp("  *** PROMOTED TO PAPER TRADING ***")
        sp(f"  Bot   : {bb.name}  ({bb.strat['id']})")
        sp(f"  Score : {sc:.1f}/100  WR={bb.wr*100:.1f}%  pnl=${bb.pnl:+.2f}");sp("")

    def _sync(self,candles):
        """
        Compare the promoted bot's current open_trades against last cycle.
        - Trade appeared  -> bot just opened a position -> write to ledger
        - Trade vanished  -> bot just closed a position -> close in ledger
        This runs AFTER BotEngine.update() so the bot state is always fresh.
        """
        bot=self.promoted
        cur=bot.open_trades   # live dict after this cycle's bar processing
        prev=self._prev_trades

        for mkt in MARKETS:
            code=mkt["code"]
            if not MARKET_ENABLED.get(code):continue

            in_cur  = code in cur
            in_prev = code in prev
            in_led  = code in _ledger.open_positions()

            # ── Trade just opened ─────────────────────────────────
            if in_cur and not in_prev:
                t=cur[code]
                _ledger.open_trade(code,{
                    "dir":t["dir"],"entry":t["entry"],
                    "sl":t["sl"],"tp":t["tp"],"atr":t["atr"],
                    "strategy":bot.strat["id"],
                })
                sp(f"  [PAPER] OPEN  {code} {t['dir'].upper()}"
                   f"  entry={t['entry']:.2f}  SL={t['sl']:.2f}  TP={t['tp']:.2f}")

            # ── Trade just closed ─────────────────────────────────
            elif in_prev and not in_cur and in_led:
                # Work out exit price and outcome from the bot's last closed record
                exit_price=None;won=False;bar_t=0
                if bot.closed:
                    last=bot.closed[-1]
                    if last.get("dir")==prev[code]["dir"] and abs(last.get("entry",0)-prev[code]["entry"])<0.01:
                        exit_price=last["exit"];won=last["won"];bar_t=last.get("open_t",0)
                if exit_price is None:
                    # Fallback: infer from current bar close
                    bars=candles.get(code,[])
                    if bars:
                        bar=bars[-2] if len(bars)>=2 else bars[-1]
                        t=prev[code]
                        # determine which side was hit
                        if bar["h"]>=t["tp"] and bar["l"]>t["sl"]:
                            exit_price=t["tp"];won=True
                        else:
                            exit_price=t["sl"];won=False
                        bar_t=bar["t"]
                    else:
                        exit_price=snap(prev[code]["entry"]);won=False;bar_t=0
                rec=_ledger.close_trade(code,snap(exit_price),bar_t,won)
                if rec:
                    sp(f"  [PAPER] CLOSE {code} {prev[code]['dir'].upper()}"
                       f"  exit={exit_price:.2f}  pts={rec['pts']:+.2f}"
                       f"  pnl=${rec['pnl']:+.2f}  {'WIN' if won else 'LOSS'}")

            # ── Ledger open but bot has nothing -- cleanup orphan ─
            elif in_led and not in_cur:
                bars=candles.get(code,[])
                bar=bars[-2] if bars and len(bars)>=2 else None
                if bar:
                    t=_ledger.open_positions()[code]
                    if t["dir"]=="long":
                        ep=t["tp"] if bar["h"]>=t["tp"] else t["sl"];won=bar["h"]>=t["tp"]
                    else:
                        ep=t["tp"] if bar["l"]<=t["tp"] else t["sl"];won=bar["l"]<=t["tp"]
                    rec=_ledger.close_trade(code,snap(ep),bar["t"],won)
                    if rec:
                        sp(f"  [PAPER] CLOSE(orphan) {code}  exit={ep:.2f}"
                           f"  pnl=${rec['pnl']:+.2f}  {'WIN' if won else 'LOSS'}")

        # Save this cycle's state for next comparison
        self._prev_trades=dict(cur)

    def status_lines(self):
        bb=self.sim.best();ab=self.sim.live();summ=_ledger.summary()
        elapsed=(time.time()-self.start)/60
        lines=[f"Elapsed: {elapsed:.0f}min  |  Sim bots: {len(ab)} active"]
        if bb:
            sc=bb.score(ab)*100
            lines.append(f"Sim best: {bb.name}  score={sc:.1f}  wr={bb.wr*100:.1f}%  pnl=${bb.pnl:+.2f}")
        if self.promoted:
            lines.append(f"Promoted: {self.promoted.name}  |  Paper trades: {summ['trades']}"
                         f"  WR={summ['wr']*100:.1f}%  total pnl=${summ['total_pnl']:+.2f}")
        else:
            remain=max(0,PROMOTE_AFTER_MINUTES-elapsed)
            lines.append(f"Promoting in ~{remain:.0f} min (if criteria met)")
        return lines

# =============================================================================
#  CANDLE FETCH
# =============================================================================

_ENGINE = [None]  # mutable container -- avoids global keyword

def _fetch(code):
    url=f"{RUN_HOST}/api/candles?code={urllib.parse.quote(code)}&iv={POLL_IV}"
    with urllib.request.urlopen(urllib.request.Request(url),timeout=20) as r:
        d=json.loads(r.read())
    return d.get("candles",[]) if d.get("live") else []

def _poll_loop(engine):
    while True:
        candles={}
        for mkt in MARKETS:
            try:
                bars=_fetch(mkt["code"])
                if bars:candles[mkt["code"]]=bars
            except Exception as e:sp(f"  [POLL] {mkt['code']}: {e}")
        if candles:engine.on_candles(candles)
        time.sleep(POLL_EVERY)

# =============================================================================
#  DASHBOARD  (http://localhost:7433)
# =============================================================================

_STYLE="""
*{box-sizing:border-box;margin:0;padding:0}
body{background:#020209;color:#b8cce0;font-family:'Courier New',monospace;font-size:12px;padding:16px}
h1{color:#18d8f0;font-size:16px;letter-spacing:3px;margin-bottom:12px}
h2{color:#8080ff;font-size:11px;letter-spacing:2px;margin:14px 0 6px;border-bottom:1px solid #141438;padding-bottom:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-bottom:12px}
.card{background:#08081e;border:1px solid #141438;border-radius:4px;padding:10px}
.label{color:#304060;font-size:10px;margin-bottom:2px}.val{font-size:15px;font-weight:bold}
.pos{color:#18c860}.neg{color:#f03050}.neu{color:#687898}
table{width:100%;border-collapse:collapse;margin-top:4px}
th{font-size:9px;color:#304060;padding:3px 6px;border-bottom:1px solid #141438;text-align:left;background:#08081e;position:sticky;top:0}
td{font-size:10px;padding:3px 6px;border-bottom:1px solid #0c0c26}
tr:hover td{background:#0c0c26}
.tbl-wrap{max-height:320px;overflow-y:auto;border:1px solid #141438}
.tag{display:inline-block;padding:1px 7px;border-radius:2px;font-size:9px}
.win{background:#04200e;color:#18c860}.loss{background:#20040a;color:#f03050}
.lng{color:#18c86080}.sht{color:#f0305080}
footer{margin-top:16px;font-size:9px;color:#1e2848}
"""

def _dash():
    if not _ENGINE[0]:
        return f"<html><body style='background:#020209;color:#18d8f0;font-family:monospace;padding:20px'>Starting up...</body></html>"
    summ=_ledger.summary();ts=_ledger.all_trades()
    bb=_ENGINE[0].sim.best();ab=_ENGINE[0].sim.live()
    promo=_ENGINE[0].promoted;elapsed=(time.time()-_ENGINE[0].start)/60

    def clr(v):return "pos" if v>0 else("neg" if v<0 else"neu")

    cards=f"""<div class="grid">
      <div class="card"><div class="label">PAPER TRADES</div><div class="val">{summ['trades']}</div></div>
      <div class="card"><div class="label">WINS / LOSSES</div><div class="val">{summ['wins']}W / {summ['losses']}L</div></div>
      <div class="card"><div class="label">WIN RATE</div><div class="val {clr(summ['wr']-.5)}">{summ['wr']*100:.1f}%</div></div>
      <div class="card"><div class="label">TOTAL PAPER P&L</div><div class="val {clr(summ['total_pnl'])}">${summ['total_pnl']:+,.2f}</div></div>
      <div class="card"><div class="label">ELAPSED</div><div class="val">{elapsed:.0f} min</div></div>
      <div class="card"><div class="label">PROMOTED STRATEGY</div>
        <div class="val" style="font-size:11px;color:#8080ff">{promo.name if promo else '-- observing --'}</div></div>
    </div>"""

    bals=""
    for code,bal in summ["balances"].items():
        pnl=bal-PAPER_START
        bals+=f'<div class="card"><div class="label">{code} BALANCE</div><div class="val {clr(pnl)}">${bal:,.2f}</div><div style="font-size:9px;color:#304060">pnl <span class="{clr(pnl)}">${pnl:+,.2f}</span></div></div>'
    bals=f'<div class="grid">{bals}</div>'

    op=summ["open"]
    if op:
        rows="".join(f'<tr><td style="color:#18d8f0">{c}</td><td class="{"lng" if t["dir"]=="long" else "sht"}">{t["dir"].upper()}</td><td>{t["entry"]:.2f}</td><td style="color:#f03050">{t["sl"]:.2f}</td><td style="color:#18c860">{t["tp"]:.2f}</td><td style="color:#304060">{t.get("opened_at","?")[:16]}</td></tr>'
               for c,t in op.items())
        open_s=f'<h2>OPEN POSITIONS</h2><div class="tbl-wrap"><table><thead><tr><th>MKT</th><th>DIR</th><th>ENTRY</th><th>SL</th><th>TP</th><th>OPENED</th></tr></thead><tbody>{rows}</tbody></table></div>'
    else:
        open_s='<h2>OPEN POSITIONS</h2><p style="color:#1e2848;padding:8px">None</p>'

    if ts:
        rows="".join(f'<tr><td style="color:#18d8f0">{t["code"]}</td><td class="{"lng" if t["dir"]=="long" else "sht"}">{t["dir"].upper()}</td><td>{t["entry"]:.2f}</td><td>{t["exit_price"]:.2f}</td><td class="{clr(t["pts"])}">{t["pts"]:+.2f}</td><td class="{clr(t["pnl"])}">${t["pnl"]:+.2f}</td><td><span class="tag {"win" if t["won"] else "loss"}">{"WIN" if t["won"] else "LOSS"}</span></td><td style="color:#304060">{t.get("closed_at","?")[:16]}</td></tr>'
               for t in reversed(ts[-50:]))
        hist_s=f'<h2>PAPER TRADE HISTORY (last 50)</h2><div class="tbl-wrap"><table><thead><tr><th>MKT</th><th>DIR</th><th>ENTRY</th><th>EXIT</th><th>PTS</th><th>P&L</th><th>RES</th><th>CLOSED</th></tr></thead><tbody>{rows}</tbody></table></div>'
    else:
        hist_s='<h2>PAPER TRADE HISTORY</h2><p style="color:#1e2848;padding:8px">Waiting for strategy promotion and signals...</p>'

    sim_rows="".join(f'<tr><td style="color:#dce8ff">{b.name}</td><td style="color:{"#18c860" if b.score(ab)*100>60 else "#f0c020" if b.score(ab)*100>35 else "#f03050"}">{b.score(ab)*100:.1f}</td><td>{b.wr*100:.1f}%</td><td>{b.wins}W/{b.losses}L</td><td class="{clr(b.pnl)}">${b.pnl:+.2f}</td></tr>'
                     for b in sorted(ab,key=lambda x:x.score(ab),reverse=True)[:15])
    sim_s=f'<h2>SIM LEADERBOARD (top 15)</h2><div class="tbl-wrap"><table><thead><tr><th>BOT</th><th>SCORE</th><th>WR</th><th>W/L</th><th>SIM P&L</th></tr></thead><tbody>{sim_rows}</tbody></table></div>'

    if not promo:
        remain=max(0,PROMOTE_AFTER_MINUTES-elapsed)
        gates=f'<p style="color:#304060;padding:8px;font-size:10px">Promotion unlocks in ~{remain:.0f} min &mdash; needs score&ge;{MIN_SCORE}, trades&ge;{MIN_TRADES}, WR&ge;{MIN_WIN_RATE*100:.0f}%</p>'
    else:
        gates=""

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="15"><title>FF Paper Trading</title>
<style>{_STYLE}</style></head><body>
<h1>FF ELITE BOTS &mdash; PAPER TRADING ENGINE</h1>
{cards}{bals}{gates}{open_s}{hist_s}{sim_s}
<footer>Auto-refresh 15s &middot; ledger: paper_ledger.json &middot; data from run.py:7432 &middot; {datetime.datetime.now().strftime('%H:%M:%S')}</footer>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in("/","/index.html"):
            body=_dash().encode("utf-8")
            self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8")
            self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        elif self.path=="/api/summary":
            body=json.dumps(_ledger.summary()).encode()
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        else:self.send_response(404);self.end_headers()
    def log_message(self,*_):pass

# =============================================================================
#  ENTRY POINT
# =============================================================================

if __name__=="__main__":
    if sys.platform=="win32":
        try:
            import subprocess
            subprocess.run(["chcp","65001"],capture_output=True,shell=True)
        except Exception:pass

    sp("")
    sp("  FF ELITE BOTS  --  Local Paper Trading Engine")
    sp("  ===============================================")
    sp("  No accounts.  No API keys.  Zero external libraries.")
    sp("")
    sp(f"  run.py API : {RUN_HOST}")
    sp(f"  Dashboard  : http://localhost:{DASH_PORT}")
    sp(f"  Ledger     : {os.path.abspath(LEDGER)}")
    sp(f"  Interval   : {POLL_IV}  |  Poll every {POLL_EVERY}s")
    sp(f"  Promote    : after {PROMOTE_AFTER_MINUTES}min  score>={MIN_SCORE}  trades>={MIN_TRADES}  WR>={MIN_WIN_RATE*100:.0f}%")
    sp("")

    sp("  Checking run.py (port 7432)...")
    for attempt in range(12):
        try:
            with socket.create_connection(("127.0.0.1",7432),timeout=2):break
        except OSError:
            if attempt==11:sp("  ERROR: run.py not running.\n  Start it: python run.py");sys.exit(1)
            sp(f"  Waiting ({attempt+1}/12)...");time.sleep(3)
    sp("  run.py OK")
    sp("")

    existing=_ledger.all_trades()
    if existing:
        summ=_ledger.summary()
        sp(f"  Ledger loaded: {summ['trades']} trades  WR={summ['wr']*100:.1f}%  pnl=${summ['total_pnl']:+.2f}")
    else:
        sp("  Fresh ledger.")
    sp("")

    sp("  Loading candles from run.py...")
    sim=BotEngine();paper=PaperEngine(sim);_ENGINE[0]=paper
    candles={}
    for mkt in MARKETS:
        try:
            bars=_fetch(mkt["code"])
            if bars:candles[mkt["code"]]=bars;sp(f"  {mkt['code']}  {len(bars)} bars  last={bars[-1]['c']}")
        except Exception as e:sp(f"  {mkt['code']}: {e}")
    if candles:paper.on_candles(candles)
    sp("")

    threading.Thread(target=_poll_loop,args=(paper,),daemon=True).start()
    srv=http.server.HTTPServer(("127.0.0.1",DASH_PORT),Handler)
    threading.Thread(target=srv.serve_forever,daemon=True).start()

    sp(f"  Dashboard: http://localhost:{DASH_PORT}")
    sp("  Ctrl+C to stop.")
    sp("")

    try:
        while True:
            time.sleep(120)
            sp("  "+"  |  ".join(_ENGINE[0].status_lines()))
    except KeyboardInterrupt:
        sp("\n  Stopped.");sys.exit(0)