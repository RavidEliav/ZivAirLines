"""Flight search and inspection."""

from datetime import date, timedelta

import streamlit as st

from src.queries import flight_seat_map, list_airports, list_statuses, search_flights
from src.ui import STATUS_ICON, conn, page_header, rows_to_df

page_header("Flights", "Filter the network and inspect any flight's cabin")

db = conn()
airports = list_airports(db)
codes = {f"{a['code']} · {a['city']}": a["code"] for a in airports}

with st.form("flight_filters"):
    c1, c2, c3 = st.columns(3)
    origin = c1.selectbox("Origin", ["Any", *codes], index=0)
    dest = c2.selectbox("Destination", ["Any", *codes], index=0)
    text = c3.text_input("Search", placeholder="Flight no or city")

    c4, c5, c6 = st.columns(3)
    date_from = c4.date_input("From", value=date.today())
    date_to = c5.date_input("To", value=date.today() + timedelta(days=60))
    statuses = c6.multiselect("Status", list_statuses(db), default=["Scheduled", "Delayed"])
    submitted = st.form_submit_button("Search", type="primary", use_container_width=True)

flights = search_flights(
    db,
    origin=codes.get(origin),
    dest=codes.get(dest),
    date_from=date_from,
    date_to=date_to,
    statuses=statuses or None,
    text=text or None,
)

st.caption(f"{len(flights)} flight(s) found." + ("" if submitted else " Adjust the filters and search."))

if not flights:
    st.info("No flights match these filters.")
    st.stop()

df = rows_to_df(flights)
df["Route"] = df["origin_city"] + " (" + df["origin_code"] + ") → " + df["dest_city"] + " (" + df["dest_code"] + ")"
df["Status"] = df["status"].map(lambda s: f"{STATUS_ICON.get(s, '')} {s}")
df["Load"] = df["seats_sold"] / df["capacity"]
df["Free"] = df["capacity"] - df["seats_sold"]

st.dataframe(
    df[["flight_no", "Route", "departure_utc", "arrival_utc", "Status",
        "aircraft_model", "seats_sold", "Free", "Load", "base_price"]].rename(
        columns={"flight_no": "Flight", "departure_utc": "Departure", "arrival_utc": "Arrival",
                 "aircraft_model": "Aircraft", "seats_sold": "Sold", "base_price": "Base (€)"}),
    hide_index=True,
    use_container_width=True,
    column_config={
        "Load": st.column_config.ProgressColumn("Load factor", format="%.0f%%", min_value=0, max_value=1),
        "Base (€)": st.column_config.NumberColumn(format="€%.2f"),
    },
)

st.divider()
st.subheader("Flight detail")

labels = {f"{f['flight_no']} · {f['origin_code']}→{f['dest_code']} · {f['departure_utc']}": f for f in flights}
selected = labels[st.selectbox("Pick a flight", labels, label_visibility="collapsed")]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Status", selected["status"])
m2.metric("Aircraft", selected["aircraft_model"])
m3.metric("Seats sold", f"{selected['seats_sold']} / {selected['capacity']}")
m4.metric("Base price", f"€{selected['base_price']:.2f}")

seats = flight_seat_map(db, selected["id"])
business = [s for s in seats if s["cabin_class"] == "Business"]
economy = [s for s in seats if s["cabin_class"] == "Economy"]
b_free = sum(1 for s in business if not s["taken"])
e_free = sum(1 for s in economy if not s["taken"])

st.write(
    f"**Business:** {b_free} free of {len(business)} · "
    f"**Economy:** {e_free} free of {len(economy)}"
)

with st.expander("Cabin occupancy map"):
    per_row = len(set(s["seat"][-1] for s in seats))
    rows = sorted({int(s["seat"][:-1]) for s in seats})
    chunk = st.select_slider("Rows", options=[r for r in rows if (r - 1) % 10 == 0],
                             value=rows[0], format_func=lambda r: f"{r}–{r + 9}")
    visible = [s for s in seats if chunk <= int(s["seat"][:-1]) < chunk + 10]
    grid = ""
    for row in range(chunk, chunk + 10):
        row_seats = [s for s in visible if int(s["seat"][:-1]) == row]
        if not row_seats:
            continue
        cells = " ".join(("🟥" if s["taken"] else "🟩") + s["seat"] for s in row_seats)
        grid += f"`{row:>2}` {cells}\n\n"
    st.markdown(grid or "_No seats in this range._")
    st.caption(f"🟩 free · 🟥 taken · {per_row} seats per row")
