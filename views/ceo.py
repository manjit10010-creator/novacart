import plotly.express as px
import streamlit as st

from common import (Filters, compute_kpis, filter_orders, kpi_card,
                    load_orders, pct_delta, weekly_series)


def ratio(actual: float, target: float) -> float:
    return actual / target if target else 0


def build_alerts(current, previous):
    drops, gains = [], []
    for dim in ["channel", "category", "country"]:
        c = current.groupby(dim)["revenue"].sum()
        p = previous.groupby(dim)["revenue"].sum().reindex(c.index)
        change = ((c - p) / p).dropna()
        for name, v in change.items():
            msg = f"**{name}** ({dim}) revenue {v * 100:+.0f}% vs previous period"
            if v <= -0.10:
                drops.append((v, msg))
            elif v >= 0.15:
                gains.append((v, msg))
    drops.sort(key=lambda x: x[0])
    gains.sort(key=lambda x: -x[0])
    return [m for _, m in drops[:3]], [m for _, m in gains[:2]]


def render(f: Filters):
    df = load_orders()
    current, previous = filter_orders(df, f)

    st.sidebar.header("Targets (editable)")
    st.sidebar.caption("Demo assumptions. Set your own to see status change.")
    t_rev = st.sidebar.number_input("Monthly revenue target ($)", value=150_000, step=10_000)
    t_orders = st.sidebar.number_input("Monthly orders target", value=3_000, step=100)
    t_margin = st.sidebar.number_input("Profit margin target (%)", value=20.0, step=1.0)

    st.title("🏢 Executive Overview")
    st.caption(
        "Demo built on synthetic data. "
        f"Showing {f.start:%d %b %Y} to {f.end:%d %b %Y} ({f.span} days)."
    )
    if current.empty:
        st.warning("No orders match the current filters.")
        return

    cur, prev = compute_kpis(current), compute_kpis(previous)
    weekly = weekly_series(current)
    scale = f.span / 30.4  # monthly targets scaled to the selected period
    rev_target, orders_target = t_rev * scale, t_orders * scale
    margin_delta = f"{cur['margin'] - prev['margin']:+.1f} pts" if prev["revenue"] else None

    r1, r2 = st.columns(3), st.columns(3)
    kpi_card(r1[0], "revenue", "Revenue", f"${cur['revenue']:,.0f}",
             pct_delta(cur["revenue"], prev["revenue"]),
             ratio(cur["revenue"], rev_target), f"${rev_target:,.0f}", weekly["revenue"])
    kpi_card(r1[1], "profit", "Profit", f"${cur['profit']:,.0f}",
             pct_delta(cur["profit"], prev["profit"]), spark=weekly["profit"])
    kpi_card(r1[2], "orders", "Orders", f"{cur['orders']:,}",
             pct_delta(cur["orders"], prev["orders"]),
             ratio(cur["orders"], orders_target), f"{orders_target:,.0f}", weekly["orders"])
    kpi_card(r2[0], "margin", "Profit margin", f"{cur['margin']:.1f}%", margin_delta,
             ratio(cur["margin"], t_margin), f"{t_margin:.0f}%", weekly["margin"])
    kpi_card(r2[1], "aov", "Avg. order value", f"${cur['aov']:,.2f}",
             pct_delta(cur["aov"], prev["aov"]), spark=weekly["aov"])
    kpi_card(r2[2], "customers", "Active customers", f"{cur['customers']:,}",
             pct_delta(cur["customers"], prev["customers"]), spark=weekly["customers"])
    st.caption(
        "Deltas compare against the previous period of equal length. "
        "Status: 🟢 on or above target, 🟡 within 10%, 🔴 more than 10% below."
    )

    st.subheader("Alerts")
    drops, gains = build_alerts(current, previous)
    if not drops and not gains:
        st.info("No notable changes vs the previous period.")
    for m in drops:
        st.warning(m)
    for m in gains:
        st.success(m)

    st.subheader("Drill-down")
    tab_trend, tab_products, tab_segments = st.tabs(["Revenue & profit trend", "Products", "Segments"])

    with tab_trend:
        gran = st.radio("Group by", ["Day", "Week", "Month"], index=1, horizontal=True)
        freq = {"Day": "D", "Week": "W", "Month": "MS"}[gran]
        trend = current.set_index("order_date")[["revenue", "profit"]].resample(freq).sum().reset_index()
        fig = px.line(trend, x="order_date", y=["revenue", "profit"], markers=True)
        fig.update_layout(xaxis_title=None, yaxis_title="$", legend_title=None)
        st.plotly_chart(fig)

    with tab_products:
        left, right = st.columns(2)
        with left:
            st.markdown("**Top 10 products by revenue**")
            top = current.groupby("product")["revenue"].sum().nlargest(10).sort_values().reset_index()
            fig = px.bar(top, x="revenue", y="product", orientation="h")
            fig.update_layout(xaxis_title="Revenue ($)", yaxis_title=None)
            st.plotly_chart(fig)
        with right:
            st.markdown("**Revenue by category**")
            cat = current.groupby("category")["revenue"].sum().reset_index()
            st.plotly_chart(px.pie(cat, names="category", values="revenue", hole=0.45))

    with tab_segments:
        left, right = st.columns(2)
        for col, dim in [(left, "channel"), (right, "country")]:
            with col:
                st.markdown(f"**Revenue by {dim}**")
                seg = current.groupby(dim)["revenue"].sum().sort_values().reset_index()
                fig = px.bar(seg, x="revenue", y=dim, orientation="h")
                fig.update_layout(xaxis_title="Revenue ($)", yaxis_title=None)
                st.plotly_chart(fig)