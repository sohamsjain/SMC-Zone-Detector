"""Entry point — run this to fetch data, detect SMC zones, and show the chart."""

from __future__ import annotations

import sys

import config
from chart import plot_zones
from kite_fetcher import fetch_ohlcv, get_instrument_token, get_kite_client
from zone_detector import find_zones


def main() -> None:
    print(f"Fetching {config.DAYS_BACK} days of {config.INTERVAL} data for {config.INSTRUMENT}...")

    try:
        kite = get_kite_client()
    except ValueError as exc:
        print(f"\nConfiguration error:\n{exc}")
        sys.exit(1)

    try:
        token = get_instrument_token(kite, config.INSTRUMENT, config.EXCHANGE)
    except ValueError as exc:
        print(f"\nInstrument lookup failed:\n{exc}")
        sys.exit(1)

    try:
        df = fetch_ohlcv(kite, token, config.INTERVAL, config.DAYS_BACK)
    except Exception:
        sys.exit(1)

    if df.empty:
        print("No data returned from Kite Connect. Check instrument and date range.")
        sys.exit(1)

    print(
        f"Loaded {len(df)} bars from {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}"
    )

    print("Detecting zones...")
    zones = find_zones(df)

    demand_count = sum(1 for z in zones if z["type"] == "demand")
    supply_count = sum(1 for z in zones if z["type"] == "supply")
    print(f"Found {len(zones)} zones: {demand_count} demand, {supply_count} supply")

    if not zones:
        print(
            "No zones met the current filters.\n"
            "Try lowering MIN_SCORE or IMPULSE_ATR_MULT in config.py."
        )
    else:
        for zone in sorted(zones, key=lambda z: z["score"], reverse=True):
            print(
                f"  [{zone['type'].upper():6}] Score {zone['score']:.1f} | "
                f"{zone['probability']:12} | "
                f"{zone['zone_low']:.2f} – {zone['zone_high']:.2f} | "
                f"{'MITIGATED' if zone['mitigated'] else 'FRESH':9} | "
                f"{zone['score_details']}"
            )

    print("Opening chart...")
    plot_zones(df, zones)


if __name__ == "__main__":
    main()
