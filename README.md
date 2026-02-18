# SMC Zone Detector

Fetches 5-minute OHLCV data from Zerodha Kite Connect, detects **Smart Money Concepts (SMC)** supply and demand zones, and displays them on an interactive Plotly chart.

Also ships a **fully automated F&O scanner** (`scanner.py`) that monitors all NSE F&O equity stocks every 5 minutes during market hours, persists zones to SQLite, and fires Telegram alerts for new high-probability zones and for zones that become mitigated.

---

## Setup

```bash
pip install -r requirements.txt
```

---

## How to get your Access Token

> Kite Connect tokens expire **daily**. Repeat these steps each trading day.

1. Open this URL in your browser (replace `YOUR_API_KEY`):
   ```
   https://kite.trade/connect/login?api_key=YOUR_API_KEY
   ```
2. Log in with your Zerodha credentials.
3. After the redirect, copy the `request_token` value from the URL query string.
4. Run the following snippet **once** to exchange it for an access token:
   ```python
   from kiteconnect import KiteConnect
   kite = KiteConnect(api_key="YOUR_API_KEY")
   data = kite.generate_session("REQUEST_TOKEN_FROM_URL", api_secret="YOUR_API_SECRET")
   print(data["access_token"])
   ```
5. Paste the printed token into `ACCESS_TOKEN` in `config.py`.

---

## Configuration (`config.py`)

### Kite Connect

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `""` | Kite Connect API key |
| `API_SECRET` | `""` | Kite Connect API secret |
| `ACCESS_TOKEN` | `""` | Daily access token (see above) |

### Single-instrument chart (`main.py`)

| Variable | Default | Description |
|---|---|---|
| `INSTRUMENT` | `"NIFTY 50"` | Zerodha tradingsymbol |
| `EXCHANGE` | `"NSE"` | `"NSE"` or `"BSE"` |
| `INTERVAL` | `"5minute"` | Kite interval string |
| `DAYS_BACK` | `10` | Calendar days of history to fetch |
| `MIN_SCORE` | `4` | Minimum zone score to display (0–6) |

### Zone detection (shared)

| Variable | Default | Description |
|---|---|---|
| `BASE_MAX_CANDLES` | `5` | Max candles in a base/consolidation |
| `BASE_RANGE_ATR_PCT` | `1.2` | Base height must be < this × ATR |
| `IMPULSE_ATR_MULT` | `3.5` | Departure impulse must be > this × ATR |
| `ATR_PERIOD` | `14` | ATR look-back period |
| `LOOKBACK_SWINGS` | `5` | Bars each side for swing detection |

### Telegram

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `""` | From @BotFather |
| `TELEGRAM_CHAT_ID` | `""` | Your chat/group/channel ID |

### F&O Scanner (`scanner.py`)

| Variable | Default | Description |
|---|---|---|
| `ALERT_MIN_SCORE` | `5.0` | Minimum score to trigger a Telegram alert |
| `SCAN_DELAY_SECONDS` | `0.5` | Delay between Kite API calls (rate-limit guard) |
| `DB_PATH` | `"zones.db"` | SQLite database file path |
| `SEND_SCAN_SUMMARY` | `False` | Send a Telegram summary after each full scan |

---

## Single-instrument chart

```bash
python main.py
```

Opens an interactive Plotly chart in the browser for the instrument in `config.py`.

---

## F&O Zone Scanner

```bash
python scanner.py
```

### What it does

1. **Derives the instrument list** — queries Kite NFO instruments for all active futures contracts, maps underlyings back to NSE equity tokens, and caches the list for the trading day (~200–250 stocks).
2. **Runs every 5-minute candle close** — sleeps until 30 seconds after each boundary (09:20, 09:25 … 15:30 IST).
3. **Persists all zones** — stores every detected zone in `zones.db` (SQLite). On repeat scans the same zone is not duplicated; its `last_updated` and `mitigated` fields are updated instead.
4. **Sends Telegram alerts** for:
   - 🟢/🔴 **New zone** — when a demand or supply zone with score ≥ `ALERT_MIN_SCORE` appears for the first time.
   - ⚠️ **Mitigation** — when price trades through a tracked zone.
5. **Runs only during market hours** — Mon–Fri 09:20–15:30 IST; sleeps overnight and across weekends automatically.
6. **Graceful shutdown** — press Ctrl-C; the scanner finishes its current instrument and exits cleanly.

### Telegram alert format

```
🟢 NEW DEMAND ZONE
━━━━━━━━━━━━━━━━━━━━
📊 RELIANCE | NSE | 5-Min
💰 Zone: 2850.00 – 2865.00
⭐ Score: 5.5/6 | High
📈 Impulse: 4.2× ATR
🔍 Fresh: ✅ | FVG: ✅ | BOS: ✅
📅 Formed: 2024-01-15 10:35
```

### How to set up a Telegram bot

1. Chat with **@BotFather** on Telegram and send `/newbot`.
2. Copy the bot token into `TELEGRAM_BOT_TOKEN` in `config.py`.
3. Start a chat with your bot (or add it to a group/channel).
4. Get your chat ID:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Look for `"chat": {"id": 123456789}` in the response.
5. Set `TELEGRAM_CHAT_ID` in `config.py` to that ID.

---

## Changing the instrument (single-chart mode)

Edit `INSTRUMENT` and `EXCHANGE` in `config.py`. Use exact Zerodha tradingsymbols, for example:

| Symbol | Exchange |
|---|---|
| `NIFTY 50` | `NSE` |
| `BANKNIFTY` | `NSE` |
| `RELIANCE` | `NSE` |
| `HDFCBANK` | `NSE` |
| `INFY` | `NSE` |

A full instrument list: `https://api.kite.trade/instruments/NSE`

---

## Tuning zone sensitivity

**Fewer, higher-quality zones / alerts**
```python
ALERT_MIN_SCORE = 5.5
IMPULSE_ATR_MULT = 4.0
```

**More zones**
```python
MIN_SCORE = 3
ALERT_MIN_SCORE = 4.0
IMPULSE_ATR_MULT = 2.5
```

---

## Zone scoring (max 6 points)

| # | Criterion | Points |
|---|---|---|
| 1 | Departure impulse > 3× ATR | 1 (0.5 if > 1.8×) |
| 2 | Base range < 20% ATR (very tight) | 1 (0.5 if < 40%) |
| 3 | Zone is **fresh** — price has NOT returned | 1 |
| 4 | FVG exists in departure candles | 1 |
| 5 | BOS at impulse end aligns with zone type | 1 |
| 6 | Base is 1–2 candles (clean) | 1 |

- **Score >= 5** -> "High" probability
- **Score 4** -> "Medium-High" probability

---

## Project structure

```
smc_zone_detector/
├── main.py               # Single-instrument interactive chart
├── scanner.py            # Automated F&O-wide zone scanner
├── config.py             # All credentials and settings
├── kite_fetcher.py       # Kite Connect data fetching
├── fo_instruments.py     # NSE F&O equity instrument list
├── zone_detector.py      # SMC zone detection and scoring
├── zone_store.py         # SQLite zone persistence
├── telegram_notifier.py  # Telegram Bot API alerts
├── chart.py              # Interactive Plotly chart
├── requirements.txt
└── README.md
```

### Database schema (`zones.db`)

The `zones` table stores every detected zone with full metadata:

| Column | Type | Description |
|---|---|---|
| `zone_key` | TEXT UNIQUE | Stable identity key |
| `instrument` | TEXT | Trading symbol |
| `zone_type` | TEXT | `demand` or `supply` |
| `zone_high/low/mid` | REAL | Price levels |
| `score` | REAL | Detection score (0–6) |
| `probability` | TEXT | `High` or `Medium-High` |
| `mitigated` | INTEGER | 1 if price entered zone |
| `fvg_present` | INTEGER | 1 if FVG found at departure |
| `impulse_ratio` | REAL | Impulse size in ATR multiples |
| `datetime_start/end` | TEXT | Base candle timestamps |
| `first_seen` | TEXT | When first detected (UTC) |
| `alert_sent` | INTEGER | 1 if Telegram alert fired |
| `mitigation_alert_sent` | INTEGER | 1 if mitigation alert fired |
