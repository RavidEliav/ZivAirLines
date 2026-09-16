"""All SQL access for the ZivAirLines app. Every statement is parameterized."""

from __future__ import annotations

import sqlite3
from datetime import date

from .helpers import calc_price, gen_booking_ref, seat_labels

ACTIVE = ("Confirmed", "CheckedIn")


class BookingError(Exception):
    """Raised when a booking cannot be created or changed."""


# --------------------------------------------------------------------------- reference data

def list_airports(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM airports ORDER BY city").fetchall()


def list_statuses(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT status FROM flights ORDER BY status")]


# --------------------------------------------------------------------------- flights

FLIGHT_SELECT = """
SELECT f.*,
       o.city  AS origin_city,
       d.city  AS dest_city,
       a.model AS aircraft_model,
       a.rows * a.seats_per_row AS capacity,
       (SELECT COUNT(*) FROM bookings b
         WHERE b.flight_id = f.id AND b.status IN ('Confirmed','CheckedIn')) AS seats_sold
FROM flights f
JOIN airports o ON o.code = f.origin_code
JOIN airports d ON d.code = f.dest_code
JOIN aircraft a ON a.id = f.aircraft_id
"""


def search_flights(
    conn: sqlite3.Connection,
    origin: str | None = None,
    dest: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    statuses: list[str] | None = None,
    text: str | None = None,
    limit: int = 500,
) -> list[sqlite3.Row]:
    clauses, params = [], []
    if origin:
        clauses.append("f.origin_code = ?")
        params.append(origin)
    if dest:
        clauses.append("f.dest_code = ?")
        params.append(dest)
    if date_from:
        clauses.append("date(f.departure_utc) >= ?")
        params.append(date_from.isoformat())
    if date_to:
        clauses.append("date(f.departure_utc) <= ?")
        params.append(date_to.isoformat())
    if statuses:
        clauses.append(f"f.status IN ({','.join('?' * len(statuses))})")
        params.extend(statuses)
    if text:
        clauses.append("(f.flight_no LIKE ? OR o.city LIKE ? OR d.city LIKE ?)")
        params.extend([f"%{text}%"] * 3)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"{FLIGHT_SELECT} {where} ORDER BY f.departure_utc LIMIT ?"
    return conn.execute(sql, [*params, limit]).fetchall()


def get_flight(conn: sqlite3.Connection, flight_id: int) -> sqlite3.Row | None:
    return conn.execute(f"{FLIGHT_SELECT} WHERE f.id = ?", (flight_id,)).fetchone()


def bookable_flights(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Future flights that are not cancelled."""
    return conn.execute(
        f"""{FLIGHT_SELECT}
            WHERE f.status IN ('Scheduled','Delayed')
              AND f.departure_utc >= datetime('now')
            ORDER BY f.departure_utc"""
    ).fetchall()


def flight_seat_map(conn: sqlite3.Connection, flight_id: int) -> list[dict]:
    """Every seat on the flight's aircraft with its occupancy state."""
    plane = conn.execute(
        "SELECT a.* FROM aircraft a JOIN flights f ON f.aircraft_id = a.id WHERE f.id = ?",
        (flight_id,),
    ).fetchone()
    if plane is None:
        return []

    taken = {
        r["seat"]: r["booking_ref"]
        for r in conn.execute(
            "SELECT seat, booking_ref FROM bookings "
            "WHERE flight_id = ? AND status IN ('Confirmed','CheckedIn')",
            (flight_id,),
        )
    }
    return [
        {"seat": seat, "cabin_class": cabin, "taken": seat in taken, "booking_ref": taken.get(seat)}
        for seat, cabin in seat_labels(plane["rows"], plane["seats_per_row"], plane["business_rows"])
    ]


def free_seats(conn: sqlite3.Connection, flight_id: int, cabin_class: str | None = None) -> list[str]:
    return [
        s["seat"]
        for s in flight_seat_map(conn, flight_id)
        if not s["taken"] and (cabin_class is None or s["cabin_class"] == cabin_class)
    ]


# --------------------------------------------------------------------------- customers

def search_customers(conn: sqlite3.Connection, text: str | None = None, tier: str | None = None,
                     limit: int = 300) -> list[sqlite3.Row]:
    clauses, params = [], []
    if text:
        clauses.append("(first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR passport_no LIKE ?)")
        params.extend([f"%{text}%"] * 4)
    if tier:
        clauses.append("tier = ?")
        params.append(tier)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(
        f"SELECT * FROM customers {where} ORDER BY last_name, first_name LIMIT ?",
        [*params, limit],
    ).fetchall()


def get_customer(conn: sqlite3.Connection, customer_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()


def create_customer(conn: sqlite3.Connection, first_name: str, last_name: str, email: str,
                    phone: str, passport_no: str, tier: str) -> int:
    try:
        cur = conn.execute(
            """INSERT INTO customers (first_name, last_name, email, phone, passport_no, tier, created_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (first_name.strip(), last_name.strip(), email.strip().lower(),
             phone.strip(), passport_no.strip().upper(), tier),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise BookingError("Email or passport number already exists.") from exc
    return int(cur.lastrowid)


# --------------------------------------------------------------------------- bookings

BOOKING_SELECT = """
SELECT b.*,
       c.first_name || ' ' || c.last_name AS customer_name,
       c.email, c.tier,
       f.flight_no, f.departure_utc, f.origin_code, f.dest_code, f.status AS flight_status
FROM bookings b
JOIN customers c ON c.id = b.customer_id
JOIN flights   f ON f.id = b.flight_id
"""


def search_bookings(conn: sqlite3.Connection, text: str | None = None, status: str | None = None,
                    flight_id: int | None = None, customer_id: int | None = None,
                    limit: int = 300) -> list[sqlite3.Row]:
    clauses, params = [], []
    if text:
        clauses.append("(b.booking_ref LIKE ? OR c.last_name LIKE ? OR c.email LIKE ? OR f.flight_no LIKE ?)")
        params.extend([f"%{text}%"] * 4)
    if status:
        clauses.append("b.status = ?")
        params.append(status)
    if flight_id:
        clauses.append("b.flight_id = ?")
        params.append(flight_id)
    if customer_id:
        clauses.append("b.customer_id = ?")
        params.append(customer_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(
        f"{BOOKING_SELECT} {where} ORDER BY f.departure_utc DESC LIMIT ?", [*params, limit]
    ).fetchall()


def get_booking(conn: sqlite3.Connection, booking_ref: str) -> sqlite3.Row | None:
    return conn.execute(f"{BOOKING_SELECT} WHERE b.booking_ref = ?", (booking_ref,)).fetchone()


def create_booking(conn: sqlite3.Connection, flight_id: int, customer_id: int, seat: str,
                   cabin_class: str) -> str:
    flight = get_flight(conn, flight_id)
    customer = get_customer(conn, customer_id)
    if flight is None or customer is None:
        raise BookingError("Unknown flight or customer.")
    if flight["status"] == "Cancelled":
        raise BookingError(f"Flight {flight['flight_no']} is cancelled.")

    price = calc_price(flight["base_price"], cabin_class, customer["tier"])
    for _ in range(5):  # retry only to dodge a booking-reference collision
        ref = gen_booking_ref()
        try:
            conn.execute(
                """INSERT INTO bookings (booking_ref, flight_id, customer_id, seat, cabin_class,
                                         price_paid, status, booked_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'Confirmed', datetime('now'))""",
                (ref, flight_id, customer_id, seat, cabin_class, price),
            )
            conn.commit()
            return ref
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            if "booking_ref" not in str(exc):
                raise BookingError(f"Seat {seat} is already taken on this flight.") from exc
    raise BookingError("Could not allocate a booking reference, please retry.")


def set_booking_status(conn: sqlite3.Connection, booking_ref: str, status: str) -> None:
    booking = get_booking(conn, booking_ref)
    if booking is None:
        raise BookingError(f"Booking {booking_ref} not found.")
    if booking["status"] == status:
        raise BookingError(f"Booking is already {status}.")
    try:
        conn.execute("UPDATE bookings SET status = ? WHERE booking_ref = ?", (status, booking_ref))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise BookingError(f"Seat {booking['seat']} has been taken in the meantime.") from exc


# --------------------------------------------------------------------------- analytics

def dashboard_kpis(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """
        SELECT (SELECT COUNT(*) FROM flights) AS total_flights,
               (SELECT COUNT(*) FROM flights
                 WHERE departure_utc >= datetime('now') AND status <> 'Cancelled') AS upcoming_flights,
               (SELECT COUNT(*) FROM customers) AS total_customers,
               (SELECT COUNT(*) FROM bookings WHERE status IN ('Confirmed','CheckedIn')) AS active_bookings,
               (SELECT COALESCE(SUM(price_paid), 0) FROM bookings
                 WHERE status IN ('Confirmed','CheckedIn')) AS revenue,
               (SELECT COUNT(*) FROM bookings WHERE status = 'Cancelled') AS cancelled_bookings
        """
    ).fetchone()
    kpis = dict(row)

    load = conn.execute(
        """
        SELECT AVG(1.0 * sold / capacity) AS avg_load FROM (
            SELECT (SELECT COUNT(*) FROM bookings b
                     WHERE b.flight_id = f.id AND b.status IN ('Confirmed','CheckedIn')) AS sold,
                   a.rows * a.seats_per_row AS capacity
            FROM flights f JOIN aircraft a ON a.id = f.aircraft_id
            WHERE f.status <> 'Cancelled')
        """
    ).fetchone()
    kpis["avg_load_factor"] = load["avg_load"] or 0.0
    return kpis


def revenue_by_month(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT strftime('%Y-%m', f.departure_utc) AS month,
                  ROUND(SUM(b.price_paid), 2) AS revenue,
                  COUNT(*) AS bookings
           FROM bookings b JOIN flights f ON f.id = b.flight_id
           WHERE b.status IN ('Confirmed','CheckedIn')
           GROUP BY month ORDER BY month"""
    ).fetchall()


def bookings_per_day(conn: sqlite3.Connection, days: int = 60) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT date(booked_at) AS day, COUNT(*) AS bookings
           FROM bookings
           WHERE booked_at >= datetime('now', ?)
           GROUP BY day ORDER BY day""",
        (f"-{days} days",),
    ).fetchall()


def top_routes(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT f.origin_code || ' -> ' || f.dest_code AS route,
                  COUNT(*) AS bookings,
                  ROUND(SUM(b.price_paid), 2) AS revenue
           FROM bookings b JOIN flights f ON f.id = b.flight_id
           WHERE b.status IN ('Confirmed','CheckedIn')
           GROUP BY route ORDER BY revenue DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def cabin_split(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT cabin_class, COUNT(*) AS bookings, ROUND(SUM(price_paid), 2) AS revenue
           FROM bookings WHERE status IN ('Confirmed','CheckedIn')
           GROUP BY cabin_class"""
    ).fetchall()


def flight_status_split(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT status, COUNT(*) AS flights FROM flights GROUP BY status ORDER BY flights DESC"
    ).fetchall()


def load_factors(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT f.flight_no,
                  f.origin_code || ' -> ' || f.dest_code AS route,
                  ROUND(100.0 * (SELECT COUNT(*) FROM bookings b
                                  WHERE b.flight_id = f.id
                                    AND b.status IN ('Confirmed','CheckedIn'))
                        / (a.rows * a.seats_per_row), 1) AS load_factor
           FROM flights f JOIN aircraft a ON a.id = f.aircraft_id
           WHERE f.status <> 'Cancelled'"""
    ).fetchall()
