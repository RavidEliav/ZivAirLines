"""Generate synthetic ZivAirLines data into the SQLite database.

Run with:  python -m src.seed  [--force]
"""

from __future__ import annotations

import argparse
import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone

from faker import Faker

from .db import DB_PATH, get_conn, init_db, table_counts
from .helpers import calc_price, gen_booking_ref, seat_labels

SEED = 42
N_FLIGHTS = 150
N_CUSTOMERS = 120
DAYS_PAST = 30
DAYS_FUTURE = 60

# code, name, city, country, lat, lon
AIRPORTS = [
    ("TLV", "Ben Gurion Airport", "Tel Aviv", "Israel", 32.01, 34.89),
    ("LHR", "Heathrow Airport", "London", "United Kingdom", 51.47, -0.45),
    ("CDG", "Charles de Gaulle", "Paris", "France", 49.01, 2.55),
    ("FCO", "Fiumicino Airport", "Rome", "Italy", 41.80, 12.25),
    ("BCN", "El Prat Airport", "Barcelona", "Spain", 41.30, 2.08),
    ("ATH", "Eleftherios Venizelos", "Athens", "Greece", 37.94, 23.95),
    ("FRA", "Frankfurt Airport", "Frankfurt", "Germany", 50.04, 8.56),
    ("AMS", "Schiphol Airport", "Amsterdam", "Netherlands", 52.31, 4.76),
    ("IST", "Istanbul Airport", "Istanbul", "Turkey", 41.28, 28.75),
    ("DXB", "Dubai International", "Dubai", "United Arab Emirates", 25.25, 55.36),
    ("JFK", "John F. Kennedy", "New York", "United States", 40.64, -73.78),
    ("LCA", "Larnaca Airport", "Larnaca", "Cyprus", 34.88, 33.63),
]

# model, rows, seats_per_row, business_rows
AIRCRAFT = [
    ("Airbus A320neo", 30, 6, 3),
    ("Boeing 737-800", 32, 6, 2),
    ("Boeing 787-9", 40, 8, 5),
    ("Embraer E195", 24, 4, 2),
]

HUB = "TLV"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(sep=" ")


def _seed_reference(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO airports (code, name, city, country) VALUES (?, ?, ?, ?)",
        [(c, n, ci, co) for c, n, ci, co, _, _ in AIRPORTS],
    )
    conn.executemany(
        "INSERT INTO aircraft (model, rows, seats_per_row, business_rows) VALUES (?, ?, ?, ?)",
        AIRCRAFT,
    )


def _seed_customers(conn: sqlite3.Connection, fake: Faker, rng: random.Random, now: datetime) -> list[sqlite3.Row]:
    rows = []
    seen_emails: set[str] = set()
    for i in range(1, N_CUSTOMERS + 1):
        first, last = fake.first_name(), fake.last_name()
        email = f"{first}.{last}{i}".lower().replace(" ", "") + "@example.com"
        if email in seen_emails:
            continue
        seen_emails.add(email)
        tier = rng.choices(["Basic", "Silver", "Gold"], weights=[70, 22, 8])[0]
        created = now - timedelta(days=rng.randint(30, 900))
        rows.append(
            (first, last, email, fake.numerify("+972-5#-###-####"),
             fake.bothify("??######").upper(), tier, _iso(created))
        )
    conn.executemany(
        """INSERT INTO customers (first_name, last_name, email, phone, passport_no, tier, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    return conn.execute("SELECT * FROM customers").fetchall()


def _seed_flights(conn: sqlite3.Connection, rng: random.Random, now: datetime) -> list[sqlite3.Row]:
    coords = {c: (lat, lon) for c, _, _, _, lat, lon in AIRPORTS}
    spokes = [c for c in coords if c != HUB]
    aircraft = conn.execute("SELECT * FROM aircraft").fetchall()

    rows = []
    for i in range(N_FLIGHTS):
        spoke = rng.choice(spokes)
        # Two thirds of the network radiates from the hub, the rest are point-to-point.
        if rng.random() < 0.66:
            origin, dest = (HUB, spoke) if i % 2 == 0 else (spoke, HUB)
        else:
            origin, dest = rng.sample(spokes, 2)

        distance = haversine_km(*coords[origin], *coords[dest])
        duration_min = int(45 + distance / 800 * 60)
        offset_days = rng.randint(-DAYS_PAST, DAYS_FUTURE)
        departure = (now + timedelta(days=offset_days)).replace(
            hour=rng.randint(5, 22), minute=rng.choice([0, 10, 20, 30, 40, 50]), second=0, microsecond=0
        )
        arrival = departure + timedelta(minutes=duration_min)

        if departure < now - timedelta(hours=3):
            status = rng.choices(["Landed", "Cancelled"], weights=[95, 5])[0]
        elif departure < now:
            status = "Departed"
        else:
            status = rng.choices(["Scheduled", "Delayed", "Cancelled"], weights=[86, 10, 4])[0]

        base_price = round(45 + distance * rng.uniform(0.045, 0.075), 2)
        plane = rng.choice(aircraft)
        rows.append(
            (f"ZV{100 + i}", origin, dest, _iso(departure), _iso(arrival),
             plane["id"], base_price, status)
        )

    conn.executemany(
        """INSERT INTO flights (flight_no, origin_code, dest_code, departure_utc, arrival_utc,
                                aircraft_id, base_price, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    return conn.execute("SELECT * FROM flights").fetchall()


def _seed_bookings(
    conn: sqlite3.Connection,
    rng: random.Random,
    now: datetime,
    flights: list[sqlite3.Row],
    customers: list[sqlite3.Row],
) -> None:
    planes = {r["id"]: r for r in conn.execute("SELECT * FROM aircraft").fetchall()}
    used_refs: set[str] = set()
    rows = []

    for flight in flights:
        plane = planes[flight["aircraft_id"]]
        seats = seat_labels(plane["rows"], plane["seats_per_row"], plane["business_rows"])
        load_factor = rng.uniform(0.35, 0.92)
        chosen = rng.sample(seats, int(len(seats) * load_factor))
        departure = datetime.fromisoformat(flight["departure_utc"])

        for seat, cabin in chosen:
            customer = rng.choice(customers)
            booked_at = departure - timedelta(days=rng.randint(1, 90), hours=rng.randint(0, 23))
            if flight["status"] == "Cancelled":
                status = "Cancelled"
            elif departure < now:
                status = rng.choices(["CheckedIn", "Cancelled"], weights=[93, 7])[0]
            else:
                status = rng.choices(["Confirmed", "CheckedIn", "Cancelled"], weights=[80, 14, 6])[0]

            ref = gen_booking_ref(rng)
            while ref in used_refs:
                ref = gen_booking_ref(rng)
            used_refs.add(ref)

            rows.append(
                (ref, flight["id"], customer["id"], seat, cabin,
                 calc_price(flight["base_price"], cabin, customer["tier"]),
                 status, _iso(booked_at))
            )

    conn.executemany(
        """INSERT INTO bookings (booking_ref, flight_id, customer_id, seat, cabin_class,
                                 price_paid, status, booked_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )


def seed(force: bool = False, db_path=DB_PATH) -> dict[str, int]:
    if force and db_path.exists():
        db_path.unlink()

    conn = get_conn(db_path)
    init_db(conn)

    if conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0] > 0 and not force:
        counts = table_counts(conn)
        conn.close()
        return counts

    rng = random.Random(SEED)
    fake = Faker()
    Faker.seed(SEED)
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    _seed_reference(conn)
    customers = _seed_customers(conn, fake, rng, now)
    flights = _seed_flights(conn, rng, now)
    _seed_bookings(conn, rng, now, flights, customers)
    conn.commit()

    counts = table_counts(conn)
    conn.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the ZivAirLines database.")
    parser.add_argument("--force", action="store_true", help="drop and rebuild the database")
    args = parser.parse_args()

    counts = seed(force=args.force)
    print(f"Database: {DB_PATH}")
    for table, count in counts.items():
        print(f"  {table:<10} {count:>6}")


if __name__ == "__main__":
    main()
