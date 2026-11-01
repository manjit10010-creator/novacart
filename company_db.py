import sqlite3

import pandas as pd
import streamlit as st

from audit import log_event
from presence import LOGGED_IN, status_at

DB_FILE = "company.db"

# Manager roles and the department each one can see
ROLE_DEPT = {
    "Marketing Manager": "Marketing",
    "Finance Manager": "Finance",
    "Inventory Manager": "Inventory & Warehouse",
    "Customer Support Manager": "Customer Support",
}


@st.cache_data
def _load_all() -> pd.DataFrame:
    with sqlite3.connect(DB_FILE) as con:
        return pd.read_sql("SELECT * FROM employees", con)


def load_workforce(when) -> pd.DataFrame:
    """Employees with their status at `when`. CEO sees everyone; managers only their own department."""
    user = st.session_state.get("user")
    if not user:
        raise PermissionError("Not signed in.")
    role = user["role"]

    df = _load_all()
    if role != "CEO":
        dept = ROLE_DEPT.get(role)
        if not dept:
            log_event("ACCESS_DENIED", "dataset=employees")
            raise PermissionError(f"Your role ({role}) doesn't have access to workforce data.")
        df = df[df["department"] == dept]
    df = df.copy()

    df["status"] = df.apply(lambda r: status_at(r, when), axis=1)
    df["logged_in"] = df["status"].isin(LOGGED_IN)
    if role != "CEO":
        df = df.drop(columns=["reliability"])  # internal model input, CEO only
    return df