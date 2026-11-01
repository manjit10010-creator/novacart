from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ---------- Data loading ----------
from data_access import load_dataset


def load_orders() -> pd.DataFrame:
    return load_dataset("orders")


def load_marketing() -> pd.DataFrame:
    return load_dataset("marketing")


def load_inventory() -> pd.DataFrame:
    inv = load_dataset("inventory")

    # Overlay live stock from the Business Simulation, if it exists.
    try:
        from sim_engine import get_products

        sim = pd.DataFrame(get_products())
        if not sim.empty and not inv.empty:
            live_stock = sim.set_index("product")["stock"]
            inv = inv.copy()
            inv["stock"] = (
                inv["product"].map(live_stock).fillna(inv["stock"]).astype(int)
            )
            sold_per_day = inv["units_sold_30d"].replace(0, np.nan) / 30
            inv["days_of_stock"] = (inv["stock"] / sold_per_day).round(1)
    except Exception:
        # If the simulation isn't available, fall back to the CSV snapshot.
        pass

    return inv


def load_returns() -> pd.DataFrame:
    return load_dataset("returns")

# ---------- Filters ----------
@dataclass
class Filters:
    start: date
    end: date
    categories: list
    countries: list
    channels: list

    @property
    def span(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def start_ts(self) -> pd.Timestamp:
        return pd.Timestamp(self.start)

    @property
    def end_ts(self) -> pd.Timestamp:
        return pd.Timestamp(self.end)

    @property
    def prev_start_ts(self) -> pd.Timestamp:
        return self.start_ts - pd.Timedelta(days=self.span)

    @property
    def prev_end_ts(self) -> pd.Timestamp:
        return self.start_ts - pd.Timedelta(days=1)


def sidebar_filters(df: pd.DataFrame) -> Filters:
    st.sidebar.header("Filters")
    min_date = df["order_date"].min().date()
    max_date = df["order_date"].max().date()
    default_start = max(min_date, max_date - pd.Timedelta(days=89))

    date_range = st.sidebar.date_input(
        "Date range",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:  # user is mid-selection
        start, end = default_start, max_date

    cats = sorted(df["category"].unique())
    countries = sorted(df["country"].unique())
    channels = sorted(df["channel"].unique())
    return Filters(
        start=start,
        end=end,
        categories=st.sidebar.multiselect("Category", cats, default=cats),
        countries=st.sidebar.multiselect("Country", countries, default=countries),
        channels=st.sidebar.multiselect("Channel", channels, default=channels),
    )


def in_period(data: pd.DataFrame, f: Filters, col: str = "order_date"):
    """Split data into (current period, previous period of equal length)."""
    cur = data[data[col].between(f.start_ts, f.end_ts)]
    prev = data[data[col].between(f.prev_start_ts, f.prev_end_ts)]
    return cur, prev


def filter_orders(df: pd.DataFrame, f: Filters):
    base = df[
        df["category"].isin(f.categories)
        & df["country"].isin(f.countries)
        & df["channel"].isin(f.channels)
    ]
    return in_period(base, f)


# ---------- KPI calculations ----------
def compute_kpis(data: pd.DataFrame) -> dict:
    if data.empty:
        return dict(revenue=0, profit=0, orders=0, aov=0, customers=0, repeat=0, margin=0)
    orders = data["order_id"].nunique()
    revenue = data["revenue"].sum()
    profit = data["profit"].sum()
    per_customer = data.groupby("customer_id")["order_id"].nunique()
    return dict(
        revenue=revenue,
        profit=profit,
        orders=orders,
        aov=revenue / orders,
        customers=len(per_customer),
        repeat=(per_customer >= 2).mean() * 100,
        margin=profit / revenue * 100 if revenue else 0,
    )


def weekly_series(data: pd.DataFrame) -> pd.DataFrame:
    r = data.set_index("order_date").resample("W")
    out = pd.DataFrame(
        {
            "revenue": r["revenue"].sum(),
            "profit": r["profit"].sum(),
            "orders": r["order_id"].nunique(),
            "customers": r["customer_id"].nunique(),
        }
    ).astype(float)
    out["aov"] = out["revenue"] / out["orders"].replace(0, np.nan)
    out["margin"] = out["profit"] / out["revenue"].replace(0, np.nan) * 100
    return out


def pct_delta(cur: float, prev: float):
    if not prev:
        return None
    return f"{(cur - prev) / abs(prev) * 100:+.1f}%"


# ---------- UI helpers ----------
def status_icon(ratio: float) -> str:
    if ratio >= 1:
        return "🟢"
    if ratio >= 0.9:
        return "🟡"
    return "🔴"


def sparkline(series: pd.Series, key: str):
    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode="lines", fill="tozeroy"))
    fig.update_layout(
        height=60,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    st.plotly_chart(fig, key=key, config={"displayModeBar": False})


def kpi_card(col, key, label, value_text, delta=None, ratio=None,
             target_text=None, spark=None, delta_color="normal"):
    with col, st.container(border=True):
        st.metric(label, value_text, delta, delta_color=delta_color)
        if ratio is not None:
            st.progress(min(max(ratio, 0.0), 1.0))
            st.caption(f"{status_icon(ratio)} {ratio * 100:.0f}% of target ({target_text})")
        if spark is not None and len(spark) > 1:
            sparkline(spark, key=f"spark_{key}")