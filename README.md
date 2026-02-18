# SMC Zone Detector

Fetches 5-minute OHLCV data from Zerodha Kite Connect, detects **Smart Money Concepts (SMC)** supply and demand zones, and displays them on an interactive Plotly chart.

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

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `""` | Kite Connect API key |
| `API_SECRET` | `""` | Kite Connect API secret |
| `ACCESS_TOKEN` | `""` | Daily access token (see above) |
| `INSTRUMENT` | `"NIFTY 50"` | Zerodha tradingsymbol |
| `EXCHANGE` | `"NSE"` | `"NSE"` or `"BSE"` |
| `INTERVAL` | `"5minute"` | Kite interval string |
| `DAYS_BACK` | `10` | Calendar days of history to fetch |
| `MIN_SCORE` | `4` | Minimum zone score to display (0–6) |
| `BASE_MAX_CANDLES` | `5` | Max candles in a base/consolidation |
| `BASE_RANGE_ATR_PCT` | `1.2` | Base height must be < this × ATR |
| `IMPULSE_ATR_MULT` | `3.5` | Departure impulse must be > this × ATR |
| `ATR_PERIOD` | `14` | ATR look-back period |
| `LOOKBACK_SWINGS` | `5` | Bars each side for swing detection |

---

## Run

```bash
python main.py
```

The chart opens automatically in your default browser.

---

## Changing the instrument

Edit `INSTRUMENT` and `EXCHANGE` in `config.py`. Use exact Zerodha tradingsymbols, for example:

| Symbol | Exchange |
|---|---|
| `NIFTY 50` | `NSE` |
| `BANKNIFTY` | `NSE` |
| `RELIANCE` | `NSE` |
| `HDFCBANK` | `NSE` |
| `INFY` | `NSE` |

A full instrument list is available at `https://api.kite.trade/instruments/NSE`.

---

## Tuning zone sensitivity

**Fewer, higher-quality zones**
```python
MIN_SCORE = 5
IMPULSE_ATR_MULT = 4.0
```

**More zones**
```python
MIN_SCORE = 3
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

- **Score >= 5** -> "High" probability (brighter colours on chart)
- **Score 4** -> "Medium-High" probability

---

## Project structure

```
smc_zone_detector/
├── main.py           # Entry point
├── config.py         # API credentials and settings
├── kite_fetcher.py   # Kite Connect data fetching
├── zone_detector.py  # SMC zone detection and scoring
├── chart.py          # Interactive Plotly chart
├── requirements.txt
└── README.md
```
