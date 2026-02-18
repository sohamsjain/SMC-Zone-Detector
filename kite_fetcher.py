"""Kite Connect data fetching module."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException, NetworkException, TokenException

import config


def get_kite_client() -> KiteConnect:
    """Return an authenticated KiteConnect instance.

    Raises:
        ValueError: If ACCESS_TOKEN is empty, with instructions for generating one.
    """
    if not config.ACCESS_TOKEN:
        raise ValueError(
            "ACCESS_TOKEN is empty in config.py.\n"
            "Generate one by following these steps:\n"
            "  1. Visit https://kite.trade/connect/login?api_key=YOUR_API_KEY\n"
            "  2. Log in with your Zerodha credentials.\n"
            "  3. After redirect, copy the 'request_token' from the URL.\n"
            "  4. Run:\n"
            "       from kiteconnect import KiteConnect\n"
            "       kite = KiteConnect(api_key='YOUR_API_KEY')\n"
            "       data = kite.generate_session('REQUEST_TOKEN', api_secret='YOUR_API_SECRET')\n"
            "       print(data['access_token'])\n"
            "  5. Paste the printed token into ACCESS_TOKEN in config.py."
        )
    kite = KiteConnect(api_key=config.API_KEY)
    kite.set_access_token(config.ACCESS_TOKEN)
    return kite


def get_instrument_token(kite: KiteConnect, tradingsymbol: str, exchange: str) -> int:
    """Find the instrument_token for the given symbol on the given exchange.

    Args:
        kite: Authenticated KiteConnect instance.
        tradingsymbol: Trading symbol, e.g. ``"NIFTY 50"`` or ``"RELIANCE"``.
        exchange: Exchange name, e.g. ``"NSE"`` or ``"BSE"``.

    Returns:
        The integer instrument token.

    Raises:
        ValueError: If the symbol is not found on the exchange.
    """
    instruments = kite.instruments(exchange)
    for instrument in instruments:
        if instrument["tradingsymbol"] == tradingsymbol:
            return int(instrument["instrument_token"])
    raise ValueError(
        f"Instrument '{tradingsymbol}' not found on '{exchange}'.\n"
        f"Tip: Use exact Zerodha tradingsymbols such as 'NIFTY 50', 'BANKNIFTY', "
        f"'RELIANCE', 'HDFCBANK'.\n"
        f"Check https://api.kite.trade/instruments/{exchange} for a full list."
    )


def fetch_ohlcv(
    kite: KiteConnect,
    instrument_token: int,
    interval: str,
    days_back: int,
) -> pd.DataFrame:
    """Fetch OHLCV data from Kite Connect.

    Args:
        kite: Authenticated KiteConnect instance.
        instrument_token: The instrument token returned by :func:`get_instrument_token`.
        interval: Kite interval string, e.g. ``"5minute"``.
        days_back: Number of calendar days of history to fetch.

    Returns:
        DataFrame with columns ``[datetime, open, high, low, close, volume]``
        sorted ascending by ``datetime``.
    """
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)

    try:
        records = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            continuous=False,
            oi=False,
        )
    except TokenException:
        print(
            "Access token expired. Re-generate it and update ACCESS_TOKEN in config.py.\n"
            "See README.md for step-by-step instructions."
        )
        raise
    except NetworkException:
        print("Network error. Check your internet connection.")
        raise
    except KiteException as exc:
        print(f"Kite API error: {exc}")
        raise

    df = pd.DataFrame(records)
    df = df.rename(columns={"date": "datetime"})
    df = df[["datetime", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("datetime").reset_index(drop=True)
    return df
