"""SQLite-backed persistent storage for SMC supply/demand zones.

Schema
------
zones
  id                    INTEGER PRIMARY KEY
  zone_key              TEXT UNIQUE          -- stable identity hash
  instrument            TEXT
  exchange              TEXT
  zone_type             TEXT                 -- 'demand' | 'supply'
  zone_high             REAL
  zone_low              REAL
  zone_mid              REAL
  score                 REAL
  probability           TEXT                 -- 'High' | 'Medium-High'
  mitigated             INTEGER              -- 0 / 1 bool
  fvg_present           INTEGER              -- 0 / 1 bool
  impulse_ratio         REAL
  datetime_start        TEXT                 -- ISO-8601
  datetime_end          TEXT                 -- ISO-8601
  first_seen            TEXT                 -- UTC ISO-8601
  last_updated          TEXT                 -- UTC ISO-8601
  alert_sent            INTEGER              -- 0 / 1 bool
  mitigation_alert_sent INTEGER              -- 0 / 1 bool
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS zones (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_key              TEXT    NOT NULL UNIQUE,
    instrument            TEXT    NOT NULL,
    exchange              TEXT    NOT NULL,
    zone_type             TEXT    NOT NULL,
    zone_high             REAL    NOT NULL,
    zone_low              REAL    NOT NULL,
    zone_mid              REAL    NOT NULL,
    score                 REAL    NOT NULL,
    probability           TEXT    NOT NULL,
    mitigated             INTEGER NOT NULL DEFAULT 0,
    fvg_present           INTEGER NOT NULL DEFAULT 0,
    impulse_ratio         REAL    NOT NULL,
    datetime_start        TEXT    NOT NULL,
    datetime_end          TEXT    NOT NULL,
    first_seen            TEXT    NOT NULL,
    last_updated          TEXT    NOT NULL,
    alert_sent            INTEGER NOT NULL DEFAULT 0,
    mitigation_alert_sent INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_zones_instrument ON zones (instrument);
CREATE INDEX IF NOT EXISTS idx_zones_mitigated  ON zones (mitigated);
CREATE INDEX IF NOT EXISTS idx_zones_alert      ON zones (alert_sent, mitigated);
"""


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str) -> None:
    """Create the zones table and indexes if they do not already exist."""
    with _connect(db_path) as conn:
        conn.executescript(_DDL)
    logger.debug("Database ready at %s", db_path)


def make_zone_key(
    instrument: str,
    zone_type: str,
    datetime_start: Any,
    zone_high: float,
    zone_low: float,
) -> str:
    """Build a stable, unique string key for a zone.

    The key is deterministic given the same inputs so repeated scans of the
    same data produce the same key, enabling idempotent upserts.
    """
    dt_str = str(datetime_start)[:19]  # truncate to seconds
    return f"{instrument}|{zone_type}|{dt_str}|{zone_high:.2f}|{zone_low:.2f}"


def upsert_zone(
    db_path: str,
    instrument: str,
    exchange: str,
    zone: dict,
) -> bool:
    """Insert a zone if it is new; update ``last_updated`` and ``mitigated`` if it exists.

    Args:
        db_path: Path to the SQLite file.
        instrument: Trading symbol, e.g. ``"RELIANCE"``.
        exchange: Exchange, e.g. ``"NSE"``.
        zone: ZoneDict as returned by :func:`zone_detector.find_zones`.

    Returns:
        ``True`` if the zone was newly inserted, ``False`` if it already existed.
    """
    now = _now_utc()
    key = make_zone_key(
        instrument, zone["type"], zone["datetime_start"], zone["zone_high"], zone["zone_low"]
    )

    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM zones WHERE zone_key = ?", (key,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE zones SET last_updated = ?, mitigated = ? WHERE zone_key = ?",
                (now, int(zone["mitigated"]), key),
            )
            return False

        conn.execute(
            """
            INSERT INTO zones (
                zone_key, instrument, exchange, zone_type,
                zone_high, zone_low, zone_mid, score, probability,
                mitigated, fvg_present, impulse_ratio,
                datetime_start, datetime_end,
                first_seen, last_updated,
                alert_sent, mitigation_alert_sent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                key, instrument, exchange, zone["type"],
                zone["zone_high"], zone["zone_low"], zone["zone_mid"],
                zone["score"], zone["probability"],
                int(zone["mitigated"]), int(zone["fvg_present"]),
                zone["impulse_ratio"],
                str(zone["datetime_start"]), str(zone["datetime_end"]),
                now, now,
            ),
        )
        logger.debug("Inserted new zone: %s", key)
        return True


def get_active_zones(db_path: str, instrument: str) -> list[sqlite3.Row]:
    """Return all non-mitigated zones stored for *instrument*."""
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM zones WHERE instrument = ? AND mitigated = 0",
            (instrument,),
        ).fetchall()


def mark_mitigated(db_path: str, zone_key: str) -> None:
    """Flag a zone as mitigated (price has traded through it)."""
    now = _now_utc()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE zones SET mitigated = 1, last_updated = ? WHERE zone_key = ?",
            (now, zone_key),
        )
    logger.debug("Marked mitigated: %s", zone_key)


def mark_alert_sent(db_path: str, zone_key: str) -> None:
    """Record that the new-zone Telegram alert was dispatched."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE zones SET alert_sent = 1 WHERE zone_key = ?", (zone_key,)
        )


def mark_mitigation_alert_sent(db_path: str, zone_key: str) -> None:
    """Record that the mitigation Telegram alert was dispatched."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE zones SET mitigation_alert_sent = 1 WHERE zone_key = ?",
            (zone_key,),
        )


def get_all_active_zones(db_path: str) -> list[sqlite3.Row]:
    """Return every non-mitigated zone across all instruments, best score first."""
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM zones WHERE mitigated = 0 ORDER BY score DESC"
        ).fetchall()


def get_zone_counts(db_path: str) -> dict[str, int]:
    """Return a summary dict with total / active / mitigated zone counts."""
    with _connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM zones WHERE mitigated = 0"
        ).fetchone()[0]
    return {"total": total, "active": active, "mitigated": total - active}
