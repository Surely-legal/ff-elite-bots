# FF Elite Bots v4

A fully autonomous paper trading dashboard and strategy engine for **ES, MES, NQ, and MNQ** CME futures contracts.

Zero external libraries. Zero accounts required. Standard Python only.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Mac%20%7C%20Linux-lightgrey)

---

## What It Does

**`run.py`** — Live charting dashboard with 10 autonomous trading bots  
**`broker.py`** — Paper trading engine that promotes the best-performing strategy to real paper trades

The bots compete against each other in simulation. After an observation period, the best-performing strategy (by composite score) is automatically promoted to paper trading with a persistent trade ledger.

---

## Screenshots

> Dashboard runs at `http://localhost:7432`  
> Paper trading ledger at `http://localhost:7433`

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/ff-elite-bots.git
cd ff-elite-bots

# Window 1 — live chart dashboard
python run.py

# Window 2 — paper trading engine (optional)
python broker.py
```

No `pip install` needed. Pure Python standard library.

---

## Features

### Dashboard (`run.py`)
- Live candlestick charts for all 4 contracts — ES, MES, NQ, MNQ
- Data fetched from Yahoo Finance v8 API → Stooq CSV fallback
- 10 competing strategy bots running simultaneously
- Real-time leaderboard, P&L tracking, win rate scoring
- EMA 9/21 overlays, volume bars, SL/TP lines on chart
- Interval switching: 1m, 5m, 15m, 1H
- Auto-respawns new bot waves when fleet drops below 5 active bots

### Paper Trading Engine (`broker.py`)
- Automatically promotes the best bot after configurable observation period
- Promotion gates: composite score, minimum trades, minimum win rate
- Persistent trade ledger saved to `paper_ledger.json`
- Web dashboard at `http://localhost:7433`
- Survives restarts — restores promoted strategy from ledger
- Ready to swap in a real broker API when you're ready to go live

---

## The 10 Strategies

| Strategy | Type | R:R | ATR Mult |
|---|---|---|---|
| TrendFollow A | EMA 21/55 Cross | 3.0 | 1.5× |
| Stoch Master | Stochastic %K(9) 20/80 | 1.5 | 1.2× |
| FF Top Trader | EMA 8/34 Cross | 2.5 | 1.5× |
| Gold Patrol 99 | ROC(5) ±0.25% | 1.5 | 1.2× |
| Velocity Trader | ROC(10) ±0.4% | 2.0 | 1.5× |
| Bollinger Break | BB(20,2) Outside Band | 2.5 | 1.5× |
| MACD Wave | MACD(12,26,9) Hist Zero | 2.0 | 1.5× |
| ATR Channel | SMA20 ±2×ATR(14) | 2.5 | 1.5× |
| CCI Reversal | CCI(14) ±100 Cross | 2.0 | 1.2× |
| RSI Momentum | RSI(14) 30/70 Cross | 2.0 | 1.2× |

---

## Pricing & Exit Logic

```
Entry  = snap(bar.close, 0.25pt tick)       -- exact close of signal bar
SL/TP  = entry ± ATR(14) × mult             -- snapped to 0.25pt grid
Exit   = real bar High ≥ TP  or  Low ≤ SL
P&L    = (exit − entry) × ptVal
```

| Contract | $/pt | $/tick | Tick |
|---|---|---|---|
| ES | $50 | $12.50 | 0.25pt |
| MES | $5 | $1.25 | 0.25pt |
| NQ | $20 | $5.00 | 0.25pt |
| MNQ | $2 | $0.50 | 0.25pt |

---

## Bot Scoring & Kill Rules

**Score** = Win Rate × 50% + Normalized P&L × 50%

**Kill conditions:**
- Balance drops below $48,000
- Win rate below 25% after 20+ trades

**Wave replenishment:** When 5 or fewer bots remain active, 10 new bots spawn

---

## Configuration

Edit the config block at the top of each file:

**`run.py`**
```python
PORT = 7432   # dashboard port
```

**`broker.py`**
```python
PROMOTE_AFTER_MINUTES = 60    # observe bots before promoting
MIN_SCORE             = 55    # composite score gate (0-100)
MIN_TRADES            = 6     # minimum closed trades gate
MIN_WIN_RATE          = 0.40  # win rate gate

MARKET_ENABLED = {
    "ES":  True,
    "MES": True,
    "NQ":  True,
    "MNQ": True,
}
```

---

## Data Sources

Data is fetched independently for each contract — no mirroring.

1. **Yahoo Finance v8 API** (query1) — primary
2. **Yahoo Finance v8 API** (query2) — load-balanced fallback
3. **Stooq CSV** — final fallback

All free. No API keys. No accounts.

> Note: Yahoo Finance futures data has a ~1-10 minute delay. For tick-accurate data, an Interactive Brokers account with TWS running can be connected by modifying the data fetch layer.

---

## Going Live

When you're ready to connect a real broker, the only change needed is in `broker.py`'s `_sync()` method — replace the `_ledger` calls with your broker's order API. The promotion logic, signal generation, and trade mirroring all stay the same.

Brokers with REST APIs that work well with this architecture:
- **Tradovate** (requires funded live account + API key)
- **Interactive Brokers** (requires funded account + TWS running locally)
- **TradeStation** (requires account)

---

## Requirements

- Python 3.8+
- No external packages (`pip install` not needed)
- Windows / Mac / Linux

---

## Project Structure

```
ff-elite-bots/
├── run.py            # live dashboard + bot simulation engine
├── broker.py         # paper trading engine + promotion logic
├── paper_ledger.json # auto-created on first run, persists trade history
└── README.md
```

---

## Live Trading — Pine Strategy → Tradovate

`live_trader.py` ports the TradingView Pine strategy **"50/100 Cross + 20 EMA Direction + Structure"** to Python (`pine_strategy.py`) and routes its signals to a real Tradovate account via REST (`tradovate.py`). Each entry submits one OSO bracket per contract — every contract gets its own take-profit at a different ATR multiple, all sharing one stop — exactly like the Pine multi-TP model.

```bash
# Window 3 — dry run (default, nothing is sent to Tradovate)
TRADOVATE_DRY_RUN=1 python live_trader.py
```

Status dashboard and webhook listener run at `http://localhost:7434`.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `TRADOVATE_ENV` | `demo` | `demo` or `live` API endpoint |
| `TRADOVATE_DRY_RUN` | `1` | `1` = log payloads only, `0` = place real orders |
| `TRADOVATE_USERNAME` | — | Tradovate username |
| `TRADOVATE_PASSWORD` | — | Tradovate password |
| `TRADOVATE_APP_ID` | `FFEliteBots` | App ID from Tradovate API access settings |
| `TRADOVATE_APP_VERSION` | `1.0` | App version |
| `TRADOVATE_CID` | — | API key CID |
| `TRADOVATE_SECRET` | — | API key secret |
| `TRADOVATE_DEVICE_ID` | uuid5(hostname) | Device ID |
| `TRADOVATE_ACCOUNT_ID` | first account | Numeric account ID to trade |
| `TRADOVATE_SYMBOL_ES` (also `MES`,`NQ`,`MNQ`) | auto | Contract symbol (e.g. `ESZ5`); empty = resolve front month via `/contract/suggest` |
| `WEBHOOK_TOKEN` | unset (disabled) | Shared secret required on TradingView webhook alerts |

### TradingView webhook

Add an alert on the strategy with webhook URL `http://<host>:7434/webhook` and a JSON message like:

```json
{"token": "YOUR_WEBHOOK_TOKEN", "code": "ES", "action": "long", "qty": 2}
```

`action` may be `long`, `short`, or `flat`. `stop` and `tps` are optional — when omitted they are computed from the latest candles using the strategy's ATR levels. `GET /api/status` returns JSON state.

### ⚠️ Real-money warning

`TRADOVATE_DRY_RUN=0` combined with `TRADOVATE_ENV=live` **places real orders with real money**. Test thoroughly on `demo` first. Market orders and bracket exits are submitted automatically on every strategy signal — there is no confirmation step.

---

## Disclaimer

This software is for **educational and paper trading purposes only**.  
Past simulated performance does not guarantee future results.  
Futures trading involves substantial risk of loss.  
The authors are not responsible for any financial losses incurred.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Contributing

Pull requests welcome. Please open an issue first to discuss major changes.

Ideas for contributions:
- Additional strategy implementations
- Better data sources (WebSocket feeds)
- Broker integrations (Tradovate, IBKR)
- Backtesting mode
- Mobile-friendly dashboard
