"""Commercial analytics for the ZivAirLines network."""

import plotly.express as px
import streamlit as st

from src.queries import (
    bookings_per_day, cabin_split, dashboard_kpis, flight_status_split,
    load_factors, revenue_by_month, top_routes,
)
from src.ui import conn, page_header, rows_to_df

page_header("Dashboard", "Revenue, demand and capacity at a glance")

db = conn()
kpis = dashboard_kpis(db)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total flights", kpis["total_flights"])
c2.metric("Upcoming", kpis["upcoming_flights"])
c3.metric("Active bookings", f"{kpis['active_bookings']:,}")
c4.metric("Revenue", f"€{kpis['revenue']:,.0f}")
c5.metric("Avg load factor", f"{kpis['avg_load_factor']:.1%}")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Revenue by month")
    df = rows_to_df(revenue_by_month(db))
    st.plotly_chart(
        px.bar(df, x="month", y="revenue", text_auto=".2s",
               labels={"month": "Month", "revenue": "Revenue (€)"}),
        use_container_width=True,
    )

with right:
    st.subheader("Bookings created per day")
    df = rows_to_df(bookings_per_day(db, days=90))
    st.plotly_chart(
        px.line(df, x="day", y="bookings", markers=True,
                labels={"day": "Date", "bookings": "Bookings"}),
        use_container_width=True,
    )

left, right = st.columns(2)

with left:
    st.subheader("Top 10 routes by revenue")
    df = rows_to_df(top_routes(db))
    st.plotly_chart(
        px.bar(df.sort_values("revenue"), x="revenue", y="route", orientation="h",
               color="bookings", color_continuous_scale="Blues",
               labels={"revenue": "Revenue (€)", "route": "Route", "bookings": "Bookings"}),
        use_container_width=True,
    )

with right:
    st.subheader("Cabin class mix")
    df = rows_to_df(cabin_split(db))
    st.plotly_chart(
        px.pie(df, names="cabin_class", values="revenue", hole=0.45),
        use_container_width=True,
    )

left, right = st.columns(2)

with left:
    st.subheader("Flight status breakdown")
    df = rows_to_df(flight_status_split(db))
    st.plotly_chart(
        px.pie(df, names="status", values="flights", hole=0.55),
        use_container_width=True,
    )

with right:
    st.subheader("Load factor distribution")
    df = rows_to_df(load_factors(db))
    st.plotly_chart(
        px.histogram(df, x="load_factor", nbins=20,
                     labels={"load_factor": "Load factor (%)", "count": "Flights"}),
        use_container_width=True,
    )

with st.expander("Route detail table"):
    st.dataframe(rows_to_df(top_routes(db, limit=25)), hide_index=True, use_container_width=True)
