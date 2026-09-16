"""ZivAirLines travel-agent console — home page."""

import streamlit as st

from src.queries import dashboard_kpis, search_flights
from src.ui import page_header, rows_to_df, conn

page_header("ZivAirLines Agent Console", "Track flights and manage passenger bookings")

db = conn()
kpis = dashboard_kpis(db)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Flights", kpis["total_flights"], f"{kpis['upcoming_flights']} upcoming")
c2.metric("Customers", kpis["total_customers"])
c3.metric("Active bookings", f"{kpis['active_bookings']:,}")
c4.metric("Revenue", f"€{kpis['revenue']:,.0f}")

st.divider()

left, right = st.columns([2, 1])

with left:
    st.subheader("Next departures")
    upcoming = [f for f in search_flights(db, limit=500)
                if f["status"] in ("Scheduled", "Delayed")][:10]
    if upcoming:
        df = rows_to_df(upcoming)
        df["Route"] = df["origin_code"] + " → " + df["dest_code"]
        df["Load"] = (df["seats_sold"] / df["capacity"]).map("{:.0%}".format)
        st.dataframe(
            df[["flight_no", "Route", "departure_utc", "status", "Load", "base_price"]].rename(
                columns={"flight_no": "Flight", "departure_utc": "Departure",
                         "status": "Status", "base_price": "From (€)"}
            ),
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("No upcoming flights.")

with right:
    st.subheader("Where to go")
    st.page_link("pages/1_Flights.py", label="Browse flights", icon="🗺️")
    st.page_link("pages/2_Customers.py", label="Manage customers", icon="👤")
    st.page_link("pages/3_Bookings.py", label="Book & manage seats", icon="🎫")
    st.page_link("pages/4_Dashboard.py", label="Analytics dashboard", icon="📊")
    st.caption(
        f"Average load factor across active flights: **{kpis['avg_load_factor']:.0%}** · "
        f"{kpis['cancelled_bookings']:,} cancelled bookings on record."
    )
