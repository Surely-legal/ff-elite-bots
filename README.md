# FF Elite Bots v5

A fully autonomous paper trading dashboard and strategy engine for **8 CME index futures markets** (4 contract pairs): **ES/MES**, **NQ/MNQ**, **YM/MYM**, **RTY/M2K**.

Zero external libraries. Zero accounts required. Standard Python only.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Mac%20%7C%20Linux-lightgrey)

---

## What It Does

**`newbot.py`** — Live charting dashboard + 17 session-aware trading bots + the **Apex AI** adaptive learner, all in a single Python file.

17 strategies compete in simulation across four global sessions (Asia, London, NY, Sydney). Apex AI watches every closed trade from strategies that survive each session and builds a per-session win/loss tally it uses to take its own positions. Everything runs in one process, state auto-saves every 30 minutes to `ff_bots_state_v5.json`, and the dashboard lives at `http://localhost:7432`.

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/Surely-legal/ff-elite-bots.git
cd ff-elite-bots

# Run the dashboard + bots
python newbot.py
```

Then open http://localhost:7432 in your browser.

No `pip install` needed. Pure Python standard library.

---

## Features

- Live candlestick charts for all 8 markets — ES, MES, NQ, MNQ, YM, MYM, RTY, M2K
- Data fetched from Yahoo Finance v8 OHLC + v7 quotes → Stooq CSV fallback
- 17 competing session-aware strategies running on every bar
- **Apex AI (`adaptiveBot`)** — learns from non-suspended strategies, keeps a per-session W/L tally (NY / LONDON / ASIA / SYDNEY) that persists across interval changes
- Real-time leaderboard, P&L tracking, win-rate scoring
- Interval switching: 1m, 5m, 15m, 1H
- Session indicator lights (NY / London / Asia / Sydney / Maintenance)
- Auto-save every 30 minutes to `ff_bots_state_v5.json` — fully isolated from v3/v4 saves
- Suspension rule: WR < 25% after 20 trades → bot is suspended, revives at the next session (no wave spawning — all 17 always run)

---

## Markets

| Contract | Name                     | $/pt  | Tick  | Pair | Tier          |
|----------|--------------------------|-------|-------|------|---------------|
| NQ       | E-Mini Nasdaq-100        | $20   | 0.25  | NDX  | T1 · MAX      |
| MNQ      | Micro E-Mini NQ          | $2    | 0.25  | NDX  | T1 · MAX      |
| ES       | E-Mini S&P 500           | $50   | 0.25  | SPX  | T2 · HIGH     |
| MES      | Micro E-Mini S&P         | $5    | 0.25  | SPX  | T2 · HIGH     |
| YM       | E-Mini Dow Jones         | $5    | 1.00  | DJI  | T3 · MOD      |
| MYM      | Micro E-Mini Dow         | $0.50 | 1.00  | DJI  | T3 · MOD      |
| RTY      | E-Mini Russell 2000      | $50   | 0.10  | RUT  | T4 · LOW      |
| M2K      | Micro E-Mini Russell     | $5    | 0.10  | RUT  | T4 · LOW      |

---

## The 17 Strategies

| Strategy           | Type                              | R:R | ATR Mult |
|--------------------|-----------------------------------|-----|----------|
| Asia Fade          | RSI Fade / EMA Break              | 2.0 | 1.2×     |
| Stoch Master       | Stoch %K Session                  | 1.5 | 1.2×     |
| FF Top Trader      | EMA Cross Session                 | 2.5 | 1.5×     |
| Velocity Break     | ROC Session                       | 2.0 | 1.5×     |
| BB Squeeze         | Bollinger Session                 | 2.5 | 1.5×     |
| MACD Wave          | MACD Histogram Zero Cross         | 2.0 | 1.5×     |
| ATR Channel        | SMA + ATR Session                 | 2.5 | 1.5×     |
| CCI Reversal       | CCI Session                       | 2.0 | 1.2×     |
| RSI Momentum       | RSI Session                       | 2.0 | 1.2×     |
| Overnight Mom      | EMA 8/55 Session (trend)          | 3.5 | 1.5×     |
| Golden Death       | SMA 50/200 Cross (trend)          | 3.5 | 2.0×     |
| RSI 30/70          | RSI Overbought/Oversold           | 2.0 | 1.2×     |
| BB Squeeze X       | Bollinger Squeeze Breakout        | 2.5 | 1.5×     |
| Stoch Divergence   | Stochastic Hidden Divergence      | 2.5 | 1.3×     |
| Parabolic SAR      | SAR Trend Reversal                | 2.0 | 1.5×     |
| ADX Trend          | ADX + EMA Filter (trend)          | 3.5 | 1.5×     |
| Ichimoku Cloud     | Kumo Breakout (trend)             | 4.0 | 1.5×     |

Most strategies tune their thresholds per session (tighter in Asia, wider in London/NY); a few are universal.

---

## Sessions

| Session | ET hours (approx) |
|---------|-------------------|
| ASIA    | 19:00 – 04:00     |
| LONDON  | 03:00 – 12:00     |
| NY      | 09:30 – 16:00     |
| SYDNEY  | (overlaps Asia)   |
| MAINT   | CME daily halt    |

Sessions can overlap — each bar is evaluated against every active session and strategies that are session-specific only fire in the matching window. Apex AI keeps a separate win/loss tally per session.

---

## Pricing & Exit Logic

```
Entry  = snap(bar.close, tick)              -- exact close of signal bar
SL/TP  = entry ± ATR(14) × mult             -- snapped to contract tick grid
Exit   = real bar High ≥ TP  or  Low ≤ SL
P&L    = (exit − entry) × ptVal
```

---

## Apex AI (adaptive learner)

- Watches only non-suspended strategies (filtered by `getLiveStratIds()`).
- Records each closed trade's session result into `sessionTally[NY|LONDON|ASIA|SYDNEY]`.
- `sessionTally` persists across interval switches — flipping from 5m to 15m does not wipe its memory.
- Per-bar close hook `_aiTallyAdd()` updates the tally on both bar-close and live-exit paths.
- `_barClosedCodes` is reset at the top of every `processBots` cycle so a market can only register one bar-close per cycle.

State file: `ff_bots_state_v5.json` (auto-saved every 30 minutes, restored on startup; fully isolated from v3/v4 save files).

---

## Suspension & Revival

- Bots with win rate < 25% after 20 trades are suspended for the rest of the current session.
- Suspended bots revive fresh at the start of the next session.
- There is no wave spawning — all 17 strategies are always in the fleet.

---

## Data Sources

Data is fetched independently per contract (no mirroring):

1. **Yahoo Finance v8 API** (`query1`) — primary OHLC
2. **Yahoo Finance v7 quotes** — live-tick updates
3. **Stooq CSV** — final fallback

All free. No API keys. No accounts.

> Note: Yahoo Finance futures data has a ~1–10 minute delay. For tick-accurate data, an Interactive Brokers account with TWS running can be connected by modifying the data-fetch layer.

---

## Requirements

- Python 3.8+
- No external packages (`pip install` not needed)
- Windows / Mac / Linux

---

## Project Structure

```
ff-elite-bots/
├── newbot.py                # dashboard + 17 strategies + Apex AI (single file)
├── ff_bots_state_v5.json    # auto-created, auto-saved every 30 min (gitignored)
├── LICENSE
└── README.md
```

---

## Version History

This branch (`version-history`) contains 6 progressive commits of `newbot.py`, oldest → newest:

| Tag / commit msg | Original filename    | Size      |
|------------------|----------------------|-----------|
| v1               | `newbot.py`          | 53,731 B  |
| v2               | `newbotv2.py`        | 61,525 B  |
| v3               | `newbotv3save.py`    | 116,809 B |
| v4               | `newbotv4.py`        | 135,469 B |
| v5               | `newbotv4save.py`    | 126,047 B |
| v6 (current)     | `newbotv5save.py`    | 126,811 B |

Check out any earlier version with `git log` + `git checkout <sha>`.

---

## Disclaimer

This software is for **educational and paper trading purposes only**.
Past simulated performance does not guarantee future results.
Futures trading involves substantial risk of loss.
The authors are not responsible for any financial losses incurred.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
