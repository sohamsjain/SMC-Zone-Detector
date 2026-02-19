# Zerodha Kite Connect credentials
# Fill these in before running main.py or scanner.py
API_KEY: str = ""        # Kite Connect API key
API_SECRET: str = ""     # Kite Connect API secret
ACCESS_TOKEN: str = ""   # Generated after login (see README for steps)

# Instrument to analyse (used by main.py single-instrument chart only)
INSTRUMENT: str = "NIFTY 50"  # e.g. "NIFTY 50", "BANKNIFTY", "RELIANCE", "INFY"
EXCHANGE: str = "NSE"          # NSE or BSE
INTERVAL: str = "5minute"      # Kite interval string
DAYS_BACK: int = 10            # How many calendar days of history to fetch

# Zone detection tuning
MIN_SCORE: float = 4.0         # Minimum zone score to display (max 6)
BASE_MAX_CANDLES: int = 5      # Max candles allowed in a base/consolidation
BASE_RANGE_ATR_PCT: float = 1.2  # Base height must be < this multiple of ATR
IMPULSE_ATR_MULT: float = 3.5  # Departure impulse must be > this multiple of ATR
ATR_PERIOD: int = 14
LOOKBACK_SWINGS: int = 5       # Bars each side for swing high/low detection

# ── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = ""   # From @BotFather
TELEGRAM_CHAT_ID: str = ""     # Your personal chat ID or group/channel ID

# ── F&O Scanner ─────────────────────────────────────────────────────────────
# Only zones with score >= ALERT_MIN_SCORE trigger a Telegram notification.
ALERT_MIN_SCORE: float = 5.0

# Seconds to wait between successive historical-data API calls.
# Keep >= 0.4 to respect Kite Connect rate limits (~3 req/s).
SCAN_DELAY_SECONDS: float = 0.5

# SQLite database file for persistent zone storage.
DB_PATH: str = "zones.db"

# Set to True to send a brief summary message to Telegram after each full scan.
SEND_SCAN_SUMMARY: bool = False
