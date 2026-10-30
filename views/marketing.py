import numpy as np
import plotly.express as px
import streamlit as st

from common import Filters, in_period, kpi_card, load_marketing, pct_delta


def totals(d) -> dict:
    spend, revenue, orders = d["ad_spend"].sum(), d["revenue"].sum(), d["orders"].sum()
    visits, clicks, imps = d["visits"].sum(), d["clicks"].sum(), d["impressions"].sum()
    return dict(
        visits=visits,
        conv=orders / visits * 100 if visits else 0,
        spend=spend,
        roas=revenue / spend if spend else 0,
        ctr=clicks / imps * 100 if imps else 0,
        cpo=spend / orders if orders else 0,
    )


def render(f: Filters):
    mk = load_marketing()
    base = mk[mk["channel"].isin(f.channels)]
    current, previous = in_period(base, f)

    st.title("📣 Marketing Performance")
    st.caption(
        "Demo built on synthetic data. Marketing data is tracked by channel and date, "
        "so the category and country filters don't apply here. "
        f"Showing {f.start:%d %b %Y} to {f.end:%d %b %Y}."
    )
    if current.empty:
        st.warning("No marketing data for the current filters.")
        return

    cur, prev = totals(current), totals(previous)
    w = current.set_index("order_date").resample("W")[
        ["visits", "orders", "ad_spend", "revenue", "impressions", "clicks"]
    ].sum()
    w["conv"] = w["orders"] / w["visits"].replace(0, np.nan) * 100
    w["roas"] = w["revenue"] / w["ad_spend"].replace(0, np.nan)
    w["ctr"] = w["clicks"] / w["impressions"].replace(0, np.nan) * 100
    w["cpo"] = w["ad_spend"] / w["orders"].replace(0, np.nan)

    r1, r2 = st.columns(3), st.columns(3)
    kpi_card(r1[0], "visits", "Website visits", f"{cur['visits']:,}",
             pct_delta(cur["visits"], prev["visits"]), spark=w["visits"])
    kpi_card(r1[1], "conv", "Conversion rate", f"{cur['conv']:.2f}%",
             pct_delta(cur["conv"], prev["conv"]), spark=w["conv"])
    kpi_card(r1[2], "spend", "Marketing spend", f"${cur['spend']:,.0f}",
             pct_delta(cur["spend"], prev["spend"]), spark=w["ad_spend"], delta_color="inverse")
    kpi_card(r2[0], "roas", "Blended ROAS", f"{cur['roas']:.1f}x",
             pct_delta(cur["roas"], prev["roas"]), spark=w["roas"])
    kpi_card(r2[1], "ctr", "Click-through rate", f"{cur['ctr']:.2f}%",
             pct_delta(cur["ctr"], prev["ctr"]), spark=w["ctr"])
    kpi_card(r2[2], "cpo", "Marketing cost per order", f"${cur['cpo']:,.2f}",
             pct_delta(cur["cpo"], prev["cpo"]), spark=w["cpo"], delta_color="inverse")
    st.caption(
        "Blended ROAS = revenue from all channels ÷ marketing spend. "
        "For spend or cost, an increase is shown in red."
    )

    ch = current.groupby("channel").agg(
        visits=("visits", "sum"), orders=("orders", "sum"), revenue=("revenue", "sum"),
        spend=("ad_spend", "sum"), impressions=("impressions", "sum"), clicks=("clicks", "sum"),
    ).reset_index()
    ch["conv_pct"] = ch["orders"] / ch["visits"] * 100
    ch["roas"] = ch["revenue"] / ch["spend"].replace(0, np.nan)
    ch["cost_per_order"] = ch["spend"] / ch["orders"]

    paid = ch[ch["spend"] > 0].dropna(subset=["roas"])
    if len(paid) >= 2:
        best, worst = paid.sort_values("roas").iloc[-1], paid.sort_values("roas").iloc[0]
        st.info(
            f"Among paid channels, **{best['channel']}** returns the most revenue per $1 "
            f"({best['roas']:.1f}x), while **{worst['channel']}** returns the least "
            f"({worst['roas']:.1f}x)."
        )

    st.subheader("Channel performance")
    left, right = st.columns(2)
    with left:
        st.markdown("**Spend vs revenue by channel**")
        long = ch.melt(id_vars="channel", value_vars=["spend", "revenue"])
        fig = px.bar(long, x="channel", y="value", color="variable", barmode="group")
        fig.update_layout(xaxis_title=None, yaxis_title="$", legend_title=None)
        st.plotly_chart(fig)
    with right:
        st.markdown("**Conversion rate by channel**")
        fig = px.bar(ch.sort_values("conv_pct"), x="conv_pct", y="channel", orientation="h")
        fig.update_layout(xaxis_title="Conversion rate (%)", yaxis_title=None)
        st.plotly_chart(fig)

    st.markdown("**Weekly visits by channel**")
    wk = current.groupby([current["order_date"].dt.to_period("W").dt.start_time, "channel"])[
        "visits"
    ].sum().reset_index()
    fig = px.line(wk, x="order_date", y="visits", color="channel")
    fig.update_layout(xaxis_title=None, yaxis_title="Visits", legend_title=None)
    st.plotly_chart(fig)

    st.markdown("**Channel table**")
    st.dataframe(
        ch[["channel", "visits", "orders", "conv_pct", "spend", "revenue", "roas", "cost_per_order"]],
        hide_index=True,
        column_config={
            "conv_pct": st.column_config.NumberColumn("Conv. %", format="%.2f%%"),
            "spend": st.column_config.NumberColumn("Spend", format="$%.0f"),
            "revenue": st.column_config.NumberColumn("Revenue", format="$%.0f"),
            "roas": st.column_config.NumberColumn("ROAS", format="%.1fx"),
            "cost_per_order": st.column_config.NumberColumn("Cost / order", format="$%.2f"),
        },
    )
    st.caption("Organic has no spend, so ROAS doesn't apply to it.")