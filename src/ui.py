"""Streamlit-side helpers shared by every page."""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from .db import DB_PATH, get_conn, init_db
from .seed import seed

BRAND = "ZivAirLines"
STATUS_ICON = {
    "Scheduled": "🟢", "Delayed": "🟠", "Departed": "🛫",
    "Landed": "🛬", "Cancelled": "🔴",
    "Confirmed": "🟢", "CheckedIn": "✅",
}


@st.cache_resource
def conn() -> sqlite3.Connection:
    """One shared SQLite connection for the whole Streamlit process."""
    if not DB_PATH.exists():
        seed()
    connection = get_conn()
    init_db(connection)
    return connection


def page_header(title: str, subtitle: str = "") -> None:
    st.set_page_config(page_title=f"{title} · {BRAND}", page_icon="✈️", layout="wide")
    st.title(f"✈️ {title}")
    if subtitle:
        st.caption(subtitle)


def rows_to_df(rows) -> pd.DataFrame:
    return pd.DataFrame([dict(r) for r in rows])


def refresh() -> None:
    """Invalidate cached query results after a write."""
    st.cache_data.clear()
