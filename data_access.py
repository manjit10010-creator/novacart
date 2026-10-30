import pandas as pd
import streamlit as st

from audit import log_event

ALL = None  # None means "every column"

FILES = {
    "orders": ("orders.csv", ("order_date",)),
    "marketing": ("marketing_daily.csv", ("order_date",)),
    "inventory": ("inventory.csv", ()),
    "returns": ("returns.csv", ("order_date", "return_date")),
    "tickets": ("tickets.csv", ("created_date",)),
}

# dataset -> role -> allowed columns (ALL = every column). A role not listed has NO access.
ACCESS = {
    "orders": {
        "CEO": ALL,
        "Finance Manager": ALL,
        "Marketing Manager": [
            "order_id", "order_date", "customer_id", "product", "quantity",
            "channel", "category", "country", "revenue",
        ],
        "Inventory Manager": [
            "order_id", "order_date", "product", "quantity", "channel", "category", "country",
        ],
        "Customer Support Manager": ["order_id", "order_date", "category", "country", "channel"],
    },
    "marketing": {"CEO": ALL, "Marketing Manager": ALL},
    "inventory": {"CEO": ALL, "Inventory Manager": ALL},
    "returns": {"CEO": ALL, "Finance Manager": ALL, "Inventory Manager": ALL},
    "tickets": {"CEO": ALL, "Customer Support Manager": ALL},
}


def can_access(role: str, dataset: str) -> bool:
    return role in ACCESS.get(dataset, {})


def columns_for(role: str, dataset: str):
    """Allowed columns for a role (None = all). Raises if the role has no access."""
    if not can_access(role, dataset):
        raise PermissionError(f"Role '{role}' cannot access '{dataset}'.")
    return ACCESS[dataset][role]


@st.cache_data
def _read_csv(file: str, date_cols: tuple) -> pd.DataFrame:
    return pd.read_csv(file, parse_dates=list(date_cols))


def load_dataset(name: str) -> pd.DataFrame:
    """The only door to the data files. Checks the signed-in user's role first."""
    user = st.session_state.get("user")
    if not user:
        raise PermissionError("Not signed in.")
    role = user["role"]
    if not can_access(role, name):
        log_event("ACCESS_DENIED", f"dataset={name}")
        raise PermissionError(f"Your role ({role}) doesn't have access to the '{name}' data.")
    file, date_cols = FILES[name]
    df = _read_csv(file, date_cols)
    cols = columns_for(role, name)
    return df if cols is None else df[cols].copy()