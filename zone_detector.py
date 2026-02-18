"""SMC (Smart Money Concepts) supply and demand zone detection."""

from __future__ import annotations

from typing import TypedDict

import numpy as np
import pandas as pd

import config


class ZoneDict(TypedDict):
    type: str               # "demand" or "supply"
    zone_high: float
    zone_low: float
    zone_mid: float
    score: float
    probability: str        # "High", "Medium-High"
    base_start_idx: int
    base_end_idx: int
    mitigated: bool
    fvg_present: bool
    impulse_ratio: float
    score_details: dict[str, float]
    datetime_start: object  # pandas Timestamp
    datetime_end: object    # pandas Timestamp


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def _compute_atr(df: pd.DataFrame, period: int) -> np.ndarray:
    """Compute Average True Range using Wilder's smoothing."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    n = len(df)

    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )

    atr = np.empty(n)
    atr[:period] = np.nan
    if n >= period:
        atr[period - 1] = tr[:period].mean()
        alpha = 1.0 / period
        for i in range(period, n):
            atr[i] = atr[i - 1] * (1 - alpha) + tr[i] * alpha
    return atr


# ---------------------------------------------------------------------------
# Swing highs / lows
# ---------------------------------------------------------------------------

def _compute_swings(df: pd.DataFrame, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Return boolean arrays marking swing highs and swing lows.

    A bar at index *i* is a swing high when its high is the maximum in the
    window ``[i-n, i+n]`` (inclusive).  Same logic for swing lows.
    """
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    length = len(df)
    swing_high = np.zeros(length, dtype=bool)
    swing_low = np.zeros(length, dtype=bool)

    for i in range(n, length - n):
        window_high = high[i - n : i + n + 1]
        window_low = low[i - n : i + n + 1]
        if high[i] == window_high.max():
            swing_high[i] = True
        if low[i] == window_low.min():
            swing_low[i] = True

    return swing_high, swing_low


# ---------------------------------------------------------------------------
# BOS (Break of Structure)
# ---------------------------------------------------------------------------

def _compute_bos(
    df: pd.DataFrame,
    swing_high: np.ndarray,
    swing_low: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return boolean arrays for bullish and bearish BOS.

    Bullish BOS: close breaks above the most recent confirmed swing high.
    Bearish BOS: close breaks below the most recent confirmed swing low.
    """
    close = df["close"].to_numpy(dtype=float)
    length = len(df)
    bullish_bos = np.zeros(length, dtype=bool)
    bearish_bos = np.zeros(length, dtype=bool)

    last_swing_high: float | None = None
    last_swing_low: float | None = None

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    for i in range(length):
        if swing_high[i]:
            last_swing_high = high[i]
        if swing_low[i]:
            last_swing_low = low[i]

        if last_swing_high is not None and close[i] > last_swing_high:
            bullish_bos[i] = True
        if last_swing_low is not None and close[i] < last_swing_low:
            bearish_bos[i] = True

    return bullish_bos, bearish_bos


# ---------------------------------------------------------------------------
# FVG (Fair Value Gap)
# ---------------------------------------------------------------------------

def _compute_fvg(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Return boolean arrays for bullish and bearish FVG at each bar.

    Bullish FVG at bar i: high[i-1] < low[i+1]
    Bearish FVG at bar i: low[i-1] > high[i+1]
    """
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    length = len(df)
    bullish_fvg = np.zeros(length, dtype=bool)
    bearish_fvg = np.zeros(length, dtype=bool)

    for i in range(1, length - 1):
        if high[i - 1] < low[i + 1]:
            bullish_fvg[i] = True
        if low[i - 1] > high[i + 1]:
            bearish_fvg[i] = True

    return bullish_fvg, bearish_fvg


# ---------------------------------------------------------------------------
# Zone freshness
# ---------------------------------------------------------------------------

def _is_fresh(
    df: pd.DataFrame,
    base_end_idx: int,
    zone_high: float,
    zone_low: float,
) -> bool:
    """Return True if price has NOT returned into the zone after formation."""
    # Check all bars after the base
    future_low = df["low"].iloc[base_end_idx + 1 :].to_numpy(dtype=float)
    future_high = df["high"].iloc[base_end_idx + 1 :].to_numpy(dtype=float)
    for fl, fh in zip(future_low, future_high):
        if fl < zone_high and fh > zone_low:
            return False
    return True


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_zone(
    zone_type: str,
    impulse_atr_ratio: float,
    base_range: float,
    atr_val: float,
    is_fresh: bool,
    fvg_present: bool,
    bos_aligned: bool,
    base_len: int,
) -> tuple[float, dict[str, float]]:
    """Score a zone on 6 criteria; return (total_score, details_dict)."""
    details: dict[str, float] = {}

    # 1. Departure impulse quality
    if impulse_atr_ratio > 3.0:
        details["impulse"] = 1.0
    elif impulse_atr_ratio > 1.8:
        details["impulse"] = 0.5
    else:
        details["impulse"] = 0.0

    # 2. Base tightness
    base_pct = base_range / atr_val if atr_val > 0 else 1.0
    if base_pct < 0.20:
        details["tightness"] = 1.0
    elif base_pct < 0.40:
        details["tightness"] = 0.5
    else:
        details["tightness"] = 0.0

    # 3. Freshness
    details["freshness"] = 1.0 if is_fresh else 0.0

    # 4. FVG present in departure candles
    details["fvg"] = 1.0 if fvg_present else 0.0

    # 5. BOS alignment
    details["bos"] = 1.0 if bos_aligned else 0.0

    # 6. Clean base (1–2 candles)
    details["clean_base"] = 1.0 if base_len <= 2 else 0.0

    total = sum(details.values())
    return total, details


# ---------------------------------------------------------------------------
# Main detection function
# ---------------------------------------------------------------------------

def find_zones(df: pd.DataFrame) -> list[ZoneDict]:
    """Detect SMC supply and demand zones.

    Args:
        df: OHLCV DataFrame with columns ``[datetime, open, high, low, close, volume]``.

    Returns:
        List of :class:`ZoneDict` sorted by score descending, de-duplicated.
    """
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    n = len(df)

    atr = _compute_atr(df, config.ATR_PERIOD)
    swing_high_arr, swing_low_arr = _compute_swings(df, config.LOOKBACK_SWINGS)
    bullish_bos, bearish_bos = _compute_bos(df, swing_high_arr, swing_low_arr)
    bullish_fvg, bearish_fvg = _compute_fvg(df)

    raw_zones: list[ZoneDict] = []
    bmc = config.BASE_MAX_CANDLES

    for i in range(bmc, n - bmc - 1):
        atr_i = atr[i]
        if np.isnan(atr_i) or atr_i == 0:
            continue

        for base_len in range(1, bmc + 1):
            base_start = i - base_len + 1
            base_end = i  # inclusive

            base_slice_high = high[base_start : base_end + 1]
            base_slice_low = low[base_start : base_end + 1]
            base_high = base_slice_high.max()
            base_low = base_slice_low.min()
            base_range = base_high - base_low

            if base_range > config.BASE_RANGE_ATR_PCT * atr_i:
                continue

            # --- Look ahead for impulse ---
            look_end = min(i + 4, n)
            future_highs = high[i : look_end]
            future_lows = low[i : look_end]

            up_move = future_highs.max() - base_high
            down_move = base_low - future_lows.min()

            is_demand = up_move >= config.IMPULSE_ATR_MULT * atr_i
            is_supply = down_move >= config.IMPULSE_ATR_MULT * atr_i

            if not is_demand and not is_supply:
                continue

            for zone_type, condition, impulse_move in [
                ("demand", is_demand, up_move),
                ("supply", is_supply, down_move),
            ]:
                if not condition:
                    continue

                impulse_ratio = impulse_move / atr_i

                # FVG in departure bars
                if zone_type == "demand":
                    fvg_present = any(bullish_fvg[i : look_end])
                    bos_aligned = any(bullish_bos[i : look_end])
                else:
                    fvg_present = any(bearish_fvg[i : look_end])
                    bos_aligned = any(bearish_bos[i : look_end])

                fresh = _is_fresh(df, base_end, base_high, base_low)

                score, score_details = _score_zone(
                    zone_type=zone_type,
                    impulse_atr_ratio=impulse_ratio,
                    base_range=base_range,
                    atr_val=atr_i,
                    is_fresh=fresh,
                    fvg_present=fvg_present,
                    bos_aligned=bos_aligned,
                    base_len=base_len,
                )

                if score < config.MIN_SCORE:
                    continue

                if score >= 5:
                    probability = "High"
                else:
                    probability = "Medium-High"

                zone: ZoneDict = {
                    "type": zone_type,
                    "zone_high": float(base_high),
                    "zone_low": float(base_low),
                    "zone_mid": float((base_high + base_low) / 2),
                    "score": score,
                    "probability": probability,
                    "base_start_idx": base_start,
                    "base_end_idx": base_end,
                    "mitigated": not fresh,
                    "fvg_present": fvg_present,
                    "impulse_ratio": impulse_ratio,
                    "score_details": score_details,
                    "datetime_start": df["datetime"].iloc[base_start],
                    "datetime_end": df["datetime"].iloc[base_end],
                }
                raw_zones.append(zone)

    # --- De-duplicate: keep highest-score, skip overlapping same-type zones ---
    raw_zones.sort(key=lambda z: z["score"], reverse=True)
    kept: list[ZoneDict] = []
    for zone in raw_zones:
        overlaps = False
        for kept_zone in kept:
            if kept_zone["type"] != zone["type"]:
                continue
            # Price-level overlap check
            if zone["zone_low"] < kept_zone["zone_high"] and zone["zone_high"] > kept_zone["zone_low"]:
                overlaps = True
                break
        if not overlaps:
            kept.append(zone)

    return kept
