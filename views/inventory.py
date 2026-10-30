import numpy as np
import plotly.express as px
import streamlit as st

from common import Filters, filter_orders, load_inventory, load_orders, load_returns


def render(f: Filters):
    inv = load_inventory()
    inv = inv[inv["category"].isin(f.categories)].copy()
    df, returns = load_orders(), load_returns()
    current, _ = filter_orders(df, f)
    ret = returns[returns["order_id"].isin(current["order_id"])]

    st.title("📦 Inventory & Returns")
    st.caption(
        "Demo built on synthetic data. Stock levels are a snapshot as of the latest data date. "
        "The date and channel filters apply only to the returns section."
    )
    if inv.empty:
        st.warning("No products match the current category filter.")
        return

    inv["status"] = np.select(
        [inv["stock"] <= 0, inv["stock"] <= inv["reorder_level"], inv["days_of_stock"] > 60],
        ["🔴 Out of stock", "🟡 Low stock", "🔵 Overstock"],
        default="🟢 OK",
    )
    needs_reorder = inv[inv["status"].isin(["🔴 Out of stock", "🟡 Low stock"])]
    return_rate = len(ret) / current["order_id"].nunique() * 100 if not current.empty else 0

    c = st.columns(5)
    c[0].metric("Products tracked", f"{len(inv)}")
    c[1].metric("Need reordering", f"{len(needs_reorder)}")
    c[2].metric("Median days of stock", f"{inv['days_of_stock'].median():.0f}")
    c[3].metric("Inventory value (at cost)", f"${(inv['stock'] * inv['unit_cost']).sum():,.0f}")
    c[4].metric("Return rate", f"{return_rate:.1f}%")

    tab_stock, tab_returns = st.tabs(["Stock levels", "Returns"])

    with tab_stock:
        if len(needs_reorder):
            st.warning(f"{len(needs_reorder)} product(s) are at or below their reorder level.")
        else:
            st.success("All products are above their reorder level.")

        lowest = inv.dropna(subset=["days_of_stock"]).nsmallest(15, "days_of_stock").sort_values(
            "days_of_stock", ascending=False
        )
        st.markdown("**15 products with the least stock cover (days)**")
        fig = px.bar(lowest, x="days_of_stock", y="product", orientation="h", color="status")
        fig.add_vline(x=14, line_dash="dash", annotation_text="14-day reorder cover")
        fig.update_layout(xaxis_title="Days of stock", yaxis_title=None, legend_title=None)
        st.plotly_chart(fig)

        cols = ["product", "category", "stock", "reorder_level", "units_sold_30d", "days_of_stock", "status"]
        st.markdown("**Reorder list**")
        st.dataframe(needs_reorder.sort_values("days_of_stock")[cols], hide_index=True)

        with st.expander("Overstocked products (more than 60 days of stock)"):
            st.dataframe(
                inv[inv["status"] == "🔵 Overstock"].sort_values("days_of_stock", ascending=False)[cols],
                hide_index=True,
            )
        with st.expander("Full inventory"):
            st.dataframe(inv[cols], hide_index=True)

    with tab_returns:
        if current.empty or ret.empty:
            st.info("No returns in the selected period.")
            return

        def rate_by(dim: str, min_orders: int = 0):
            n_orders = current.groupby(dim)["order_id"].nunique()
            n_ret = ret.groupby(dim)["order_id"].nunique().reindex(n_orders.index).fillna(0)
            out = (n_ret / n_orders * 100).rename("return_rate").to_frame()
            out["orders"] = n_orders
            return out[out["orders"] >= min_orders].reset_index()

        left, right = st.columns(2)
        with left:
            st.markdown("**Return rate by category**")
            cat = rate_by("category").sort_values("return_rate")
            fig = px.bar(cat, x="return_rate", y="category", orientation="h")
            fig.update_layout(xaxis_title="Return rate (%)", yaxis_title=None)
            st.plotly_chart(fig)
        with right:
            st.markdown("**Return reasons**")
            reasons = ret.groupby("reason").size().sort_values().reset_index(name="returns")
            fig = px.bar(reasons, x="returns", y="reason", orientation="h")
            fig.update_layout(xaxis_title="Returns", yaxis_title=None)
            st.plotly_chart(fig)

        st.markdown("**Products with the highest return rate** (at least 30 orders)")
        prod = rate_by("product", min_orders=30).nlargest(10, "return_rate")
        st.dataframe(
            prod, hide_index=True,
            column_config={"return_rate": st.column_config.NumberColumn("Return rate", format="%.1f%%")},
        )