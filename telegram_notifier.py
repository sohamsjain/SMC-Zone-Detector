"""Telegram Bot API notifications for SMC zone events.

All public functions return ``True`` on success, ``False`` on failure.
They never raise exceptions so that a Telegram outage cannot crash the scanner.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT_S = 10


def _is_configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _send(text: str) -> bool:
    """POST a message to the configured Telegram chat (HTML parse mode)."""
    if not _is_configured():
        logger.warning("Telegram credentials not set — skipping notification.")
        return False

    url = _BASE_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    payload: dict[str, Any] = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT_S)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


# ── Formatters ────────────────────────────────────────────────────────────────

def _flag(value: bool) -> str:
    return "✅" if value else "❌"


def _zone_header(zone_type: str, is_new: bool) -> str:
    emoji = "🟢" if zone_type == "demand" else "🔴"
    label = zone_type.upper()
    prefix = "NEW " if is_new else ""
    return f"{emoji} <b>{prefix}{label} ZONE</b>"


def _zone_body(
    instrument: str,
    exchange: str,
    zone_high: float,
    zone_low: float,
    score: float,
    probability: str,
    impulse_ratio: float,
    fvg_present: bool,
    bos_present: bool,
    is_fresh: bool,
    datetime_start: str,
) -> str:
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{instrument}</b> | {exchange} | 5-Min\n"
        f"💰 Zone: <code>{zone_low:.2f} – {zone_high:.2f}</code>\n"
        f"⭐ Score: <b>{score:.1f}/6</b> | {probability}\n"
        f"📈 Impulse: {impulse_ratio:.1f}× ATR\n"
        f"🔍 Fresh: {_flag(is_fresh)} | FVG: {_flag(fvg_present)} | BOS: {_flag(bos_present)}\n"
        f"📅 Formed: {datetime_start[:16]}"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def send_new_zone_alert(instrument: str, exchange: str, zone: dict) -> bool:
    """Send a Telegram alert for a freshly detected high-probability zone.

    Args:
        instrument: Trading symbol, e.g. ``"RELIANCE"``.
        exchange: Exchange name, e.g. ``"NSE"``.
        zone: ZoneDict as returned by :func:`zone_detector.find_zones`.
    """
    score_details = zone.get("score_details", {})
    text = "\n".join(
        [
            _zone_header(zone["type"], is_new=True),
            _zone_body(
                instrument=instrument,
                exchange=exchange,
                zone_high=zone["zone_high"],
                zone_low=zone["zone_low"],
                score=zone["score"],
                probability=zone["probability"],
                impulse_ratio=zone["impulse_ratio"],
                fvg_present=zone["fvg_present"],
                bos_present=bool(score_details.get("bos", 0)),
                is_fresh=not zone["mitigated"],
                datetime_start=str(zone["datetime_start"]),
            ),
        ]
    )
    ok = _send(text)
    if ok:
        logger.info(
            "Alert sent ▶ %s %s @ %.2f–%.2f (score %.1f)",
            instrument, zone["type"], zone["zone_low"], zone["zone_high"], zone["score"],
        )
    return ok


def send_mitigation_alert(
    instrument: str,
    exchange: str,
    zone_row: dict,
    mitigated_at: str,
) -> bool:
    """Send a Telegram alert when a previously tracked zone gets mitigated.

    Args:
        instrument: Trading symbol.
        exchange: Exchange name.
        zone_row: Dict-like DB row for the zone (keys match the ``zones`` table).
        mitigated_at: UTC ISO-8601 timestamp of the mitigation event.
    """
    zone_type = zone_row["zone_type"]
    emoji = "⚠️"
    label = zone_type.upper()

    text = (
        f"{emoji} <b>{label} ZONE MITIGATED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{instrument}</b> | {exchange} | 5-Min\n"
        f"💰 Zone: <code>{zone_row['zone_low']:.2f} – {zone_row['zone_high']:.2f}</code>\n"
        f"⭐ Score: {zone_row['score']:.1f}/6 | {zone_row['probability']}\n"
        f"📅 Formed: {str(zone_row['datetime_start'])[:16]}\n"
        f"🕐 Mitigated: {mitigated_at[:16]}"
    )
    ok = _send(text)
    if ok:
        logger.info(
            "Mitigation alert sent ▶ %s %s @ %.2f–%.2f",
            instrument, zone_type, zone_row["zone_low"], zone_row["zone_high"],
        )
    return ok


def send_scan_summary(
    instruments_scanned: int,
    new_zones: int,
    mitigations: int,
    errors: int,
    duration_s: float,
) -> bool:
    """Send a brief scan-complete summary to Telegram."""
    text = (
        f"📡 <b>F&amp;O Scan Complete</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 Instruments scanned: {instruments_scanned}\n"
        f"🆕 New zones: {new_zones}\n"
        f"⚠️ Mitigations: {mitigations}\n"
        f"❌ Errors: {errors}\n"
        f"⏱ Duration: {duration_s:.1f}s"
    )
    return _send(text)
