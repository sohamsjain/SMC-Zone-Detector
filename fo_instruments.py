"""Fetch and cache the NSE F&O equity instrument list from Kite Connect.

Only equity underlyings are returned (indices like NIFTY / BANKNIFTY are
excluded because their historical data lives in a different segment and is
handled separately).
"""

from __future__ import annotations

import logging
from datetime import date

from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)

# In-memory cache — refreshed once per calendar day.
_cache: list[dict] | None = None
_cache_date: str | None = None


def get_fo_equity_instruments(kite: KiteConnect) -> list[dict]:
    """Return NSE equity instruments that have active F&O (futures) contracts.

    Results are cached for the session and refreshed at the start of each new
    calendar day, so repeated calls within the same day are free.

    Args:
        kite: Authenticated :class:`~kiteconnect.KiteConnect` instance.

    Returns:
        List of dicts, each containing:
        ``tradingsymbol``, ``instrument_token`` (int), ``name`` (str).
        Sorted alphabetically by ``tradingsymbol``.
    """
    global _cache, _cache_date

    today = date.today().isoformat()
    if _cache is not None and _cache_date == today:
        return _cache

    logger.info("Fetching NFO instrument list to identify F&O underlyings…")
    nfo_instruments = kite.instruments("NFO")

    # Collect unique underlying names from active futures contracts.
    fo_names: set[str] = {
        inst["name"]
        for inst in nfo_instruments
        if inst["instrument_type"] == "FUT" and inst["name"]
    }
    logger.info("Found %d unique F&O underlying names in NFO.", len(fo_names))

    logger.info("Fetching NSE equity instrument list…")
    nse_instruments = kite.instruments("NSE")

    seen: set[str] = set()
    result: list[dict] = []
    for inst in nse_instruments:
        sym = inst["tradingsymbol"]
        if sym in fo_names and inst["instrument_type"] == "EQ" and sym not in seen:
            seen.add(sym)
            result.append(
                {
                    "tradingsymbol": sym,
                    "instrument_token": int(inst["instrument_token"]),
                    "name": inst.get("name") or sym,
                }
            )

    result.sort(key=lambda x: x["tradingsymbol"])
    logger.info(
        "Matched %d NSE equity instruments for F&O underlyings.", len(result)
    )

    _cache = result
    _cache_date = today
    return result
