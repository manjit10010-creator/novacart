import plotly.express as px
import streamlit as st

from common import Filters, filter_orders, load_orders, load_returns, pct_delta

TABLE_CONFIG = {
    "revenue": st.column_config.NumberColumn("Revenue", format="$%.0f"),
    "cogs": st.column_config.NumberColumn("Product cost", format="$%.0f"),
    "shipping": st.column_config.NumberColumn("Shipping", format="$%.0f"),
    "marketing": st.column_config.NumberColumn("Marketing", format="$%.0f"),
    "profit": st.column_config.NumberColumn("Profit", format="$%.0f"),
    "margin_pct": st.column_config.NumberColumn("Margin %", format="%.1f%%"),
}


def perf_table(data, dim):
    t = data.groupby(dim).agg(
        orders=("order_id", "nunique"),
        revenue=("revenue", "sum"),
        cogs=("cogs", "sum"),
        shipping=("shipping_cost", "sum"),
        marketing=("marketing_cost", "sum"),
        profit=("profit", "sum"),
    ).reset_index()
    t["margin_pct"] = t["profit"] / t["revenue"] * 100
    return t.sort_values("profit", ascending=False)


def fin_totals(data, rets) -> dict:
    revenue, refunds = data["revenue"].sum(), rets["refund_amount"].sum()
    profit = data["profit"].sum()
    net_sales = revenue - refunds
    after = profit - refunds
    return dict(
        revenue=revenue, refunds=refunds, net_sales=net_sales,
        refund_rate=refunds / revenue * 100 if revenue else 0,
        cost=data["total_cost"].sum(), profit=profit, after=after,
        margin=after / net_sales * 100 if net_sales else 0,
    )


def render(f: Filters):
    df, returns = load_orders(), load_returns()
    current, previous = filter_orders(df, f)
    ret_cur = returns[returns["order_id"].isin(current["order_id"])]
    ret_prev = returns[returns["order_id"].isin(previous["order_id"])]

    st.title("💰 Finance")
    st.caption(
        "Demo built on synthetic data. Costs are modeled assumptions (product cost by category, "
        "shipping by country, marketing by channel). Refunds assume returned items are not resold. "
        f"Showing {f.start:%d %b %Y} to {f.end:%d %b %Y}."
    )
    if current.empty:
        st.warning("No orders match the current filters.")
        return

    c, p = fin_totals(current, ret_cur), fin_totals(previous, ret_prev)

    r1, r2 = st.columns(4), st.columns(4)
    r1[0].metric("Gross revenue", f"${c['revenue']:,.0f}", pct_delta(c["revenue"], p["revenue"]))
    r1[1].metric("Refunds", f"${c['refunds']:,.0f}", pct_delta(c["refunds"], p["refunds"]), delta_color="inverse")
    r1[2].metric("Net sales", f"${c['net_sales']:,.0f}", pct_delta(c["net_sales"], p["net_sales"]))
    r1[3].metric("Refund rate", f"{c['refund_rate']:.1f}%")
    r2[0].metric("Total cost", f"${c['cost']:,.0f}", pct_delta(c["cost"], p["cost"]), delta_color="inverse")
    r2[1].metric("Gross profit", f"${c['profit']:,.0f}", pct_delta(c["profit"], p["profit"]))
    r2[2].metric("Profit after refunds", f"${c['after']:,.0f}", pct_delta(c["after"], p["after"]))
    r2[3].metric("Margin after refunds", f"{c['margin']:.1f}%")

    tab_over, tab_country, tab_product = st.tabs(["Overview", "Countries", "Products"])

    with tab_over:
        left, right = st.columns(2)
        with left:
            st.markdown("**Where the money goes**")
            costs = {
                "Product cost": current["cogs"].sum(),
                "Shipping": current["shipping_cost"].sum(),
                "Marketing": current["marketing_cost"].sum(),
                "Refunds": c["refunds"],
            }
            fig = px.pie(names=list(costs), values=list(costs.values()), hole=0.45)
            st.plotly_chart(fig)
        with right:
            st.markdown("**Refunds by reason**")
            reasons = ret_cur.groupby("reason")["refund_amount"].sum().sort_values().reset_index()
            fig = px.bar(reasons, x="refund_amount", y="reason", orientation="h")
            fig.update_layout(xaxis_title="Refund amount ($)", yaxis_title=None)
            st.plotly_chart(fig)

        st.markdown("**Monthly revenue and profit**")
        m = current.set_index("order_date")[["revenue", "profit"]].resample("MS").sum().reset_index()
        fig = px.bar(m, x="order_date", y=["revenue", "profit"], barmode="group")
        fig.update_layout(xaxis_title=None, yaxis_title="$", legend_title=None)
        st.plotly_chart(fig)

    with tab_country:
        country_perf = perf_table(current, "country")
        left, right = st.columns([3, 2])
        with left:
            fig = px.bar(
                country_perf.sort_values("profit"), x="profit", y="country", orientation="h",
                color="margin_pct", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
            )
            fig.update_layout(xaxis_title="Profit ($)", yaxis_title=None, coloraxis_colorbar_title="Margin %")
            st.plotly_chart(fig)
        with right:
            st.dataframe(country_perf, hide_index=True, column_config=TABLE_CONFIG)

        st.markdown("**Margin % by category and country**")
        heat = current.groupby(["category", "country"]).agg(
            revenue=("revenue", "sum"), profit=("profit", "sum")
        ).reset_index()
        heat["margin_pct"] = heat["profit"] / heat["revenue"] * 100
        pivot = heat.pivot(index="category", columns="country", values="margin_pct")
        fig = px.imshow(pivot, text_auto=".1f", color_continuous_scale="RdYlGn",
                        color_continuous_midpoint=0, aspect="auto")
        fig.update_layout(coloraxis_colorbar_title="Margin %")
        st.plotly_chart(fig)

    with tab_product:
        prod_perf = perf_table(current, "product")
        cat_map = df.drop_duplicates("product").set_index("product")["category"]
        prod_perf["category"] = prod_perf["product"].map(cat_map)

        fig = px.scatter(prod_perf, x="revenue", y="margin_pct", size="orders", color="category",
                         hover_name="product", size_max=30)
        fig.add_hline(y=0, line_dash="dash")
        fig.update_layout(xaxis_title="Revenue ($)", yaxis_title="Margin %")
        st.plotly_chart(fig)
        st.caption("Top right is best (high revenue, high margin). Below the dashed line a product loses money.")

        losers = prod_perf[prod_perf["profit"] < 0]
        if not losers.empty:
            st.error(
                f"{len(losers)} product(s) lost money in this period: "
                + ", ".join(losers.sort_values("profit")["product"].head(5))
            )

        best, worst = st.columns(2)
        with best:
            st.markdown("**Top 10 products by profit**")
            st.dataframe(prod_perf.head(10), hide_index=True, column_config=TABLE_CONFIG)
        with worst:
            st.markdown("**Bottom 10 products by profit**")
            st.dataframe(prod_perf.tail(10).iloc[::-1], hide_index=True, column_config=TABLE_CONFIG)