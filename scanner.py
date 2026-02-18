"""F&O-wide SMC zone scanner with automatic 5-minute scheduling.

Run with:
    python scanner.py

The scanner:
  1. Derives the complete list of NSE F&O equity underlyings from Kite Connect.
  2. Fetches 5-minute OHLCV for every instrument after each candle close.
  3. Detects SMC supply/demand zones and persists them to SQLite.
  4. Sends Telegram alerts for new high-probability zones and for zones that
     become mitigated (price trades through them).
  5. Sleeps between scans, aligning to 5-minute candle boundaries (IST).
  6. Runs only during NSE market hours (Mon–Fri, 09:20–15:30 IST).

Press Ctrl-C for a clean shutdown.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytz

import config
from fo_instruments import get_fo_equity_instruments
from kite_fetcher import get_kite_client, fetch_ohlcv
from kiteconnect.exceptions import KiteException
from telegram_notifier import (
    send_mitigation_alert,
    send_new_zone_alert,
    send_scan_summary,
)
from zone_detector import find_zones
from zone_store import (
    get_active_zones,
    init_db,
    make_zone_key,
    mark_alert_sent,
    mark_mitigation_alert_sent,
    mark_mitigated,
    upsert_zone,
)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scanner.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("scanner")

# ── Constants ─────────────────────────────────────────────────────────────────

IST = pytz.timezone("Asia/Kolkata")
EXCHANGE = "NSE"

# NSE market window (IST); first 5-min candle closes at 09:20, last at 15:30.
_MARKET_OPEN_H, _MARKET_OPEN_M = 9, 20
_MARKET_CLOSE_H, _MARKET_CLOSE_M = 15, 30

# Seconds after the candle close to start scanning (data propagation buffer).
_SCAN_OFFSET_S = 30

# ── Graceful shutdown ─────────────────────────────────────────────────────────

_shutdown = False


def _handle_signal(signum: int, _frame: object) -> None:
    global _shutdown
    logger.info("Shutdown signal received (%s). Finishing current scan…", signum)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Scheduling helpers ────────────────────────────────────────────────────────

def _ist_now() -> datetime:
    return datetime.now(IST)


def _is_market_hours() -> bool:
    """Return True if the current IST time falls within NSE trading hours."""
    now = _ist_now()
    if now.weekday() >= 5:  # Saturday / Sunday
        return False
    t = now.time()
    from datetime import time as _time
    return _time(_MARKET_OPEN_H, _MARKET_OPEN_M) <= t <= _time(_MARKET_CLOSE_H, _MARKET_CLOSE_M)


def _sleep_until_next_candle() -> None:
    """Sleep until *_SCAN_OFFSET_S* seconds after the next 5-minute candle close (IST)."""
    now = _ist_now()
    total_minutes = now.hour * 60 + now.minute
    minutes_to_next_close = 5 - (total_minutes % 5)
    next_close = (now + timedelta(minutes=minutes_to_next_close)).replace(
        second=_SCAN_OFFSET_S, microsecond=0
    )
    if next_close <= now:
        next_close += timedelta(minutes=5)

    sleep_s = (next_close - now).total_seconds()
    logger.info(
        "Next scan at %s IST (sleeping %.0fs).",
        next_close.strftime("%H:%M:%S"),
        sleep_s,
    )
    # Sleep in small increments so shutdown signals are handled promptly.
    deadline = time.monotonic() + sleep_s
    while time.monotonic() < deadline and not _shutdown:
        time.sleep(min(5.0, deadline - time.monotonic()))


def _sleep_until_market_open() -> None:
    """Sleep until the next NSE market open day at 09:20:30 IST."""
    now = _ist_now()
    next_open = now.replace(
        hour=_MARKET_OPEN_H,
        minute=_MARKET_OPEN_M,
        second=_SCAN_OFFSET_S,
        microsecond=0,
    )
    if next_open <= now:
        next_open += timedelta(days=1)
    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)

    sleep_s = (next_open - now).total_seconds()
    logger.info(
        "Market closed. Sleeping until %s IST (%.1fh).",
        next_open.strftime("%Y-%m-%d %H:%M:%S"),
        sleep_s / 3600,
    )
    deadline = time.monotonic() + sleep_s
    while time.monotonic() < deadline and not _shutdown:
        time.sleep(min(30.0, deadline - time.monotonic()))


# ── Mitigation check ──────────────────────────────────────────────────────────

def _check_mitigation(
    df: pd.DataFrame,
    zone_high: float,
    zone_low: float,
    datetime_end_str: str,
) -> bool:
    """Return True if any candle after *datetime_end_str* traded inside the zone."""
    try:
        dt_end = pd.Timestamp(datetime_end_str)
    except Exception:
        return False

    after = df[df["datetime"] > dt_end]
    if after.empty:
        return False

    return bool(((after["low"] < zone_high) & (after["high"] > zone_low)).any())


# ── Per-instrument scan ───────────────────────────────────────────────────────

@dataclass
class _ScanResult:
    new_zones: int = 0
    mitigations: int = 0
    error: bool = False


def _scan_instrument(
    kite,
    tradingsymbol: str,
    instrument_token: int,
    db_path: str,
    scan_time_utc: str,
) -> _ScanResult:
    result = _ScanResult()

    # --- Fetch OHLCV ---
    try:
        df = fetch_ohlcv(kite, instrument_token, config.INTERVAL, config.DAYS_BACK)
    except KiteException as exc:
        logger.warning("Kite error for %s: %s", tradingsymbol, exc)
        result.error = True
        return result
    except Exception as exc:
        logger.warning("Unexpected error fetching %s: %s", tradingsymbol, exc)
        result.error = True
        return result

    min_bars = config.ATR_PERIOD + config.BASE_MAX_CANDLES + config.LOOKBACK_SWINGS + 5
    if df.empty or len(df) < min_bars:
        logger.debug("%s: insufficient data (%d bars), skipping.", tradingsymbol, len(df))
        return result

    # --- Detect zones ---
    try:
        zones = find_zones(df)
    except Exception as exc:
        logger.warning("Zone detection failed for %s: %s", tradingsymbol, exc)
        result.error = True
        return result

    # --- Upsert detected zones; collect newly inserted ones ---
    newly_inserted: list[tuple[str, dict]] = []
    for zone in zones:
        zone_key = make_zone_key(
            tradingsymbol, zone["type"], zone["datetime_start"],
            zone["zone_high"], zone["zone_low"],
        )
        is_new = upsert_zone(db_path, tradingsymbol, EXCHANGE, zone)
        if is_new:
            newly_inserted.append((zone_key, zone))

    result.new_zones = len(newly_inserted)

    # --- Check stored active zones for mitigation ---
    stored_active = get_active_zones(db_path, tradingsymbol)
    for row in stored_active:
        mitigated = _check_mitigation(
            df, row["zone_high"], row["zone_low"], row["datetime_end"]
        )
        if mitigated:
            mark_mitigated(db_path, row["zone_key"])
            result.mitigations += 1
            if row["score"] >= config.ALERT_MIN_SCORE and not row["mitigation_alert_sent"]:
                if send_mitigation_alert(tradingsymbol, EXCHANGE, dict(row), scan_time_utc):
                    mark_mitigation_alert_sent(db_path, row["zone_key"])

    # --- Send alerts for qualifying new zones ---
    for zone_key, zone in newly_inserted:
        if zone["score"] >= config.ALERT_MIN_SCORE and not zone["mitigated"]:
            if send_new_zone_alert(tradingsymbol, EXCHANGE, zone):
                mark_alert_sent(db_path, zone_key)

    return result


# ── Full scan ─────────────────────────────────────────────────────────────────

def run_full_scan(kite) -> None:
    """Fetch F&O instrument list and scan every equity underlying."""
    scan_time_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    logger.info("=== Scan started at %s UTC ===", scan_time_utc)
    t0 = time.monotonic()

    try:
        instruments = get_fo_equity_instruments(kite)
    except Exception as exc:
        logger.error("Failed to fetch F&O instrument list: %s", exc)
        return

    total = len(instruments)
    logger.info("Scanning %d F&O instruments…", total)

    agg_new = agg_mit = agg_err = 0

    for idx, inst in enumerate(instruments, start=1):
        if _shutdown:
            logger.info("Shutdown requested — stopping scan early.")
            break

        sym = inst["tradingsymbol"]
        logger.debug("[%d/%d] %s", idx, total, sym)

        result = _scan_instrument(
            kite=kite,
            tradingsymbol=sym,
            instrument_token=inst["instrument_token"],
            db_path=config.DB_PATH,
            scan_time_utc=scan_time_utc,
        )
        agg_new += result.new_zones
        agg_mit += result.mitigations
        if result.error:
            agg_err += 1

        # Rate-limit guard between instruments.
        if idx < total:
            time.sleep(config.SCAN_DELAY_SECONDS)

    duration = time.monotonic() - t0
    logger.info(
        "=== Scan done in %.1fs | instruments=%d new_zones=%d mitigations=%d errors=%d ===",
        duration, total, agg_new, agg_mit, agg_err,
    )

    if config.SEND_SCAN_SUMMARY:
        send_scan_summary(total, agg_new, agg_mit, agg_err, duration)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("SMC F&O Scanner starting up.")

    if not config.ACCESS_TOKEN:
        logger.error(
            "ACCESS_TOKEN is empty in config.py. "
            "See README.md for token generation instructions."
        )
        sys.exit(1)

    init_db(config.DB_PATH)
    logger.info("Zone database initialised at '%s'.", config.DB_PATH)

    try:
        kite = get_kite_client()
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    logger.info(
        "Connected to Kite. Alert threshold: score >= %.1f.", config.ALERT_MIN_SCORE
    )

    while not _shutdown:
        if _is_market_hours():
            run_full_scan(kite)
            if not _shutdown:
                _sleep_until_next_candle()
        else:
            _sleep_until_market_open()

    logger.info("Scanner shut down cleanly.")


if __name__ == "__main__":
    main()
