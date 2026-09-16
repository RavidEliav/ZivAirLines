"""Create bookings on a visual seat map, and manage existing ones."""

import streamlit as st

from src.helpers import CLASS_MULTIPLIER, TIER_DISCOUNT, calc_price
from src.queries import (
    BookingError, bookable_flights, create_booking, flight_seat_map,
    get_booking, search_bookings, search_customers, set_booking_status,
)
from src.ui import STATUS_ICON, conn, page_header, refresh, rows_to_df

page_header("Bookings", "Seat a passenger on a flight, or change an existing reservation")

db = conn()
new_tab, manage_tab = st.tabs(["🎫 New booking", "🗂️ Manage bookings"])

# ------------------------------------------------------------------ new booking
with new_tab:
    flights = bookable_flights(db)
    if not flights:
        st.warning("No bookable flights available.")
        st.stop()

    flight_labels = {
        f"{f['flight_no']} · {f['origin_code']}→{f['dest_code']} · {f['departure_utc']} "
        f"· {f['capacity'] - f['seats_sold']} free": f
        for f in flights
    }
    c1, c2 = st.columns([3, 2])
    flight = flight_labels[c1.selectbox("Flight", flight_labels)]
    cabin = c2.radio("Cabin class", list(CLASS_MULTIPLIER), horizontal=True)

    passenger_query = st.text_input("Find passenger", placeholder="Name, email or passport")
    candidates = search_customers(db, text=passenger_query or None, limit=50)
    if not candidates:
        st.error("No matching customer — add one on the Customers page.")
        st.stop()

    cust_labels = {f"#{c['id']} · {c['first_name']} {c['last_name']} · {c['tier']}": c for c in candidates}
    customer = cust_labels[st.selectbox("Passenger", cust_labels)]

    if st.session_state.get("seat_flight") != flight["id"]:
        st.session_state["seat_flight"] = flight["id"]
        st.session_state["seat_pick"] = None

    seats = [s for s in flight_seat_map(db, flight["id"]) if s["cabin_class"] == cabin]
    if not seats:
        st.warning(f"This aircraft has no {cabin} cabin.")
        st.stop()

    st.markdown("##### Pick a seat")
    row_numbers = sorted({int(s["seat"][:-1]) for s in seats})
    blocks = [row_numbers[i:i + 8] for i in range(0, len(row_numbers), 8)]
    block_labels = [f"Rows {b[0]}–{b[-1]}" for b in blocks]
    block = blocks[block_labels.index(st.radio("Rows", block_labels, horizontal=True,
                                               label_visibility="collapsed"))]

    for row in block:
        row_seats = [s for s in seats if int(s["seat"][:-1]) == row]
        cols = st.columns(len(row_seats) + 1)
        cols[0].markdown(f"**{row}**")
        for col, seat in zip(cols[1:], row_seats):
            picked = st.session_state.get("seat_pick") == seat["seat"]
            label = ("🔵 " if picked else "🟥 " if seat["taken"] else "🟩 ") + seat["seat"]
            if col.button(label, key=f"seat_{seat['seat']}", disabled=seat["taken"],
                          use_container_width=True):
                st.session_state["seat_pick"] = seat["seat"]
                st.rerun()

    st.caption("🟩 free · 🟥 taken · 🔵 selected")

    chosen = st.session_state.get("seat_pick")
    st.divider()
    if not chosen:
        st.info("Select a free seat to continue.")
    else:
        price = calc_price(flight["base_price"], cabin, customer["tier"])
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Seat", chosen)
        k2.metric("Class", cabin)
        k3.metric("Tier discount", f"{(1 - TIER_DISCOUNT[customer['tier']]):.0%}")
        k4.metric("Price", f"€{price:,.2f}")
        if st.button("Confirm booking", type="primary", use_container_width=True):
            try:
                ref = create_booking(db, flight["id"], customer["id"], chosen, cabin)
                st.session_state["seat_pick"] = None
                refresh()
                st.success(
                    f"Booked **{ref}** — {customer['first_name']} {customer['last_name']} "
                    f"on {flight['flight_no']}, seat {chosen} ({cabin}), €{price:,.2f}."
                )
                st.balloons()
            except BookingError as exc:
                st.error(str(exc))

# ------------------------------------------------------------------ manage
with manage_tab:
    c1, c2 = st.columns([3, 1])
    query = c1.text_input("Search bookings", placeholder="Booking ref, last name, email or flight no")
    status = c2.selectbox("Status", ["Any", "Confirmed", "CheckedIn", "Cancelled"])

    results = search_bookings(db, text=query or None, status=None if status == "Any" else status)
    st.caption(f"{len(results)} booking(s).")

    if results:
        df = rows_to_df(results)
        df["Route"] = df["origin_code"] + " → " + df["dest_code"]
        df["Status"] = df["status"].map(lambda s: f"{STATUS_ICON.get(s, '')} {s}")
        st.dataframe(
            df[["booking_ref", "customer_name", "flight_no", "Route", "departure_utc",
                "seat", "cabin_class", "price_paid", "Status"]].rename(
                columns={"booking_ref": "Ref", "customer_name": "Passenger", "flight_no": "Flight",
                         "departure_utc": "Departure", "seat": "Seat", "cabin_class": "Class",
                         "price_paid": "Paid (€)"}),
            hide_index=True, use_container_width=True,
            column_config={"Paid (€)": st.column_config.NumberColumn(format="€%.2f")},
        )

    st.markdown("##### Change a booking")
    ref = st.text_input("Booking reference", placeholder="ZVAB12CD").strip().upper()
    if ref:
        booking = get_booking(db, ref)
        if booking is None:
            st.error(f"No booking found for {ref}.")
        else:
            st.write(
                f"**{booking['customer_name']}** · {booking['flight_no']} "
                f"{booking['origin_code']}→{booking['dest_code']} · seat {booking['seat']} "
                f"({booking['cabin_class']}) · €{booking['price_paid']:,.2f} · "
                f"status **{booking['status']}**"
            )
            a, b = st.columns(2)
            if a.button("✅ Check in", use_container_width=True,
                        disabled=booking["status"] != "Confirmed"):
                try:
                    set_booking_status(db, ref, "CheckedIn")
                    refresh()
                    st.success(f"{ref} checked in.")
                    st.rerun()
                except BookingError as exc:
                    st.error(str(exc))
            if b.button("🗑️ Cancel booking", use_container_width=True,
                        disabled=booking["status"] == "Cancelled"):
                try:
                    set_booking_status(db, ref, "Cancelled")
                    refresh()
                    st.success(f"{ref} cancelled — seat {booking['seat']} released.")
                    st.rerun()
                except BookingError as exc:
                    st.error(str(exc))
