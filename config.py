# Zerodha Kite Connect credentials
# Fill these in before running main.py
API_KEY: str = ""        # Kite Connect API key
API_SECRET: str = ""     # Kite Connect API secret
ACCESS_TOKEN: str = ""   # Generated after login (see README for steps)

# Instrument to analyse
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
