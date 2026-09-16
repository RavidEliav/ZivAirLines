"""Customer directory and per-customer booking history."""

import streamlit as st

from src.helpers import TIER_DISCOUNT
from src.queries import BookingError, create_customer, search_bookings, search_customers
from src.ui import STATUS_ICON, conn, page_header, refresh, rows_to_df

page_header("Customers", "Look up passengers, add new ones and review their trips")

db = conn()

c1, c2 = st.columns([3, 1])
text = c1.text_input("Search", placeholder="Name, email or passport number")
tier = c2.selectbox("Tier", ["Any", *TIER_DISCOUNT])

customers = search_customers(db, text=text or None, tier=None if tier == "Any" else tier)
st.caption(f"{len(customers)} customer(s).")

if customers:
    df = rows_to_df(customers)
    df["Name"] = df["first_name"] + " " + df["last_name"]
    st.dataframe(
        df[["id", "Name", "email", "phone", "passport_no", "tier", "created_at"]].rename(
            columns={"id": "ID", "email": "Email", "phone": "Phone",
                     "passport_no": "Passport", "tier": "Tier", "created_at": "Member since"}),
        hide_index=True, use_container_width=True,
    )

    st.subheader("Booking history")
    labels = {f"#{c['id']} · {c['first_name']} {c['last_name']} ({c['tier']})": c for c in customers}
    picked = labels[st.selectbox("Customer", labels, label_visibility="collapsed")]

    history = search_bookings(db, customer_id=picked["id"])
    if history:
        hdf = rows_to_df(history)
        hdf["Route"] = hdf["origin_code"] + " → " + hdf["dest_code"]
        hdf["Status"] = hdf["status"].map(lambda s: f"{STATUS_ICON.get(s, '')} {s}")
        spent = sum(b["price_paid"] for b in history if b["status"] != "Cancelled")
        k1, k2, k3 = st.columns(3)
        k1.metric("Bookings", len(history))
        k2.metric("Lifetime value", f"€{spent:,.2f}")
        k3.metric("Tier discount", f"{(1 - TIER_DISCOUNT[picked['tier']]):.0%}")
        st.dataframe(
            hdf[["booking_ref", "flight_no", "Route", "departure_utc", "seat",
                 "cabin_class", "price_paid", "Status"]].rename(
                columns={"booking_ref": "Ref", "flight_no": "Flight", "departure_utc": "Departure",
                         "seat": "Seat", "cabin_class": "Class", "price_paid": "Paid (€)"}),
            hide_index=True, use_container_width=True,
            column_config={"Paid (€)": st.column_config.NumberColumn(format="€%.2f")},
        )
    else:
        st.info("This customer has no bookings yet.")
else:
    st.info("No customers match this search.")

st.divider()
with st.expander("➕ Add a new customer"):
    with st.form("new_customer", clear_on_submit=True):
        a, b = st.columns(2)
        first = a.text_input("First name")
        last = b.text_input("Last name")
        email = a.text_input("Email")
        phone = b.text_input("Phone")
        passport = a.text_input("Passport number")
        new_tier = b.selectbox("Tier", list(TIER_DISCOUNT))
        if st.form_submit_button("Create customer", type="primary"):
            if not all([first, last, email, phone, passport]):
                st.error("All fields are required.")
            else:
                try:
                    new_id = create_customer(db, first, last, email, phone, passport, new_tier)
                    refresh()
                    st.success(f"Customer #{new_id} created.")
                except BookingError as exc:
                    st.error(str(exc))
