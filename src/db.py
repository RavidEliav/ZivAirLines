"""SQLite connection handling and schema definition for ZivAirLines."""

from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "zivair.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS airports (
    code    TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    city    TEXT NOT NULL,
    country TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aircraft (
    id             INTEGER PRIMARY KEY,
    model          TEXT NOT NULL,
    rows           INTEGER NOT NULL,
    seats_per_row  INTEGER NOT NULL,
    business_rows  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS flights (
    id            INTEGER PRIMARY KEY,
    flight_no     TEXT NOT NULL UNIQUE,
    origin_code   TEXT NOT NULL REFERENCES airports(code),
    dest_code     TEXT NOT NULL REFERENCES airports(code),
    departure_utc TEXT NOT NULL,
    arrival_utc   TEXT NOT NULL,
    aircraft_id   INTEGER NOT NULL REFERENCES aircraft(id),
    base_price    REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'Scheduled'
                  CHECK (status IN ('Scheduled','Delayed','Departed','Landed','Cancelled'))
);

CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    phone       TEXT NOT NULL,
    passport_no TEXT NOT NULL UNIQUE,
    tier        TEXT NOT NULL DEFAULT 'Basic'
                CHECK (tier IN ('Basic','Silver','Gold')),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id           INTEGER PRIMARY KEY,
    booking_ref  TEXT NOT NULL UNIQUE,
    flight_id    INTEGER NOT NULL REFERENCES flights(id),
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    seat         TEXT NOT NULL,
    cabin_class  TEXT NOT NULL CHECK (cabin_class IN ('Economy','Business')),
    price_paid   REAL NOT NULL,
    status       TEXT NOT NULL DEFAULT 'Confirmed'
                 CHECK (status IN ('Confirmed','CheckedIn','Cancelled')),
    booked_at    TEXT NOT NULL
);

-- A seat can only be held by one non-cancelled booking per flight.
CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_seat
    ON bookings (flight_id, seat) WHERE status <> 'Cancelled';

CREATE INDEX IF NOT EXISTS ix_flights_departure ON flights (departure_utc);
CREATE INDEX IF NOT EXISTS ix_flights_route     ON flights (origin_code, dest_code);
CREATE INDEX IF NOT EXISTS ix_bookings_flight   ON bookings (flight_id);
CREATE INDEX IF NOT EXISTS ix_bookings_customer ON bookings (customer_id);
"""


def get_conn(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open a connection with foreign keys enabled and dict-like rows."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = ("airports", "aircraft", "flights", "customers", "bookings")
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
