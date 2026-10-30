import pandas as pd
import plotly.express as px
import streamlit as st

from data_access import load_dataset
from common import Filters, in_period, kpi_card





def fmt_hours(h: float) -> str:
    if pd.isna(h):
        return "n/a"
    return f"{h * 60:.0f} min" if h < 1 else f"{h:.1f} h"


def delta(cur, prev):
    if pd.isna(cur) or pd.isna(prev) or prev == 0:
        return None
    return f"{(cur - prev) / abs(prev) * 100:+.1f}%"


def prep(d: pd.DataFrame, t_frt: float) -> pd.DataFrame:
    return d.assign(
        sla_ok=(d["first_response_hours"] <= t_frt).astype(float),
        repeat_f=d["repeat_contact"].astype(float),
    )


def stats(d: pd.DataFrame) -> dict:
    return dict(
        tickets=len(d),
        frt=d["first_response_hours"].mean(),
        res=d["resolution_hours"].mean(),
        csat=d["csat"].mean(),
        sla=d["sla_ok"].mean() * 100 if len(d) else float("nan"),
        repeat=d["repeat_f"].mean() * 100 if len(d) else float("nan"),
    )


def ratio_lower_better(actual, target):
    return target / actual if actual and not pd.isna(actual) else 0


def build_alerts(current, previous):
    spikes = []
    for dim, label in [("issue_type", "issue"), ("country", "country"), ("channel", "channel")]:
        c = current.groupby(dim).size()
        p = previous.groupby(dim).size().reindex(c.index)
        change = ((c - p) / p).dropna()
        for name, v in change.items():
            if v >= 0.25 and c[name] >= 20:
                spikes.append((v, f"**{name}** ({label}) tickets {v * 100:+.0f}% vs previous period ({int(c[name])} tickets)"))
    spikes.sort(key=lambda x: -x[0])
    return [m for _, m in spikes[:3]]


def render(f: Filters):
    tickets = load_dataset("tickets")
    base = tickets[tickets["country"].isin(f.countries) & tickets["category"].isin(f.categories)]
    current, previous = in_period(base, f, "created_date")

    st.sidebar.header("Support targets (editable)")
    t_frt = st.sidebar.number_input("First response target (hours)", value=4.0, step=0.5)
    t_res = st.sidebar.number_input("Resolution time target (hours)", value=24.0, step=1.0)
    t_csat = st.sidebar.number_input("CSAT target (out of 5)", value=4.2, step=0.1)

    st.title("🎧 Customer Support")
    st.caption(
        "Demo built on synthetic data. Category is the product category of the order; "
        "the sales channel filter doesn't apply to tickets. "
        f"Showing {f.start:%d %b %Y} to {f.end:%d %b %Y}."
    )
    if current.empty:
        st.warning("No tickets match the current filters.")
        return

    current, previous = prep(current, t_frt), prep(previous, t_frt)
    cur, prev = stats(current), stats(previous)

    r = current.set_index("created_date").resample("W")
    w = pd.DataFrame({
        "tickets": r["ticket_id"].count().astype(float),
        "frt": r["first_response_hours"].mean(),
        "res": r["resolution_hours"].mean(),
        "csat": r["csat"].mean(),
        "sla": r["sla_ok"].mean() * 100,
        "repeat": r["repeat_f"].mean() * 100,
    })

    r1, r2 = st.columns(3), st.columns(3)
    kpi_card(r1[0], "tickets", "Ticket volume", f"{cur['tickets']:,}",
             delta(cur["tickets"], prev["tickets"]), spark=w["tickets"], delta_color="inverse")
    kpi_card(r1[1], "frt", "Avg first response", fmt_hours(cur["frt"]),
             delta(cur["frt"], prev["frt"]), ratio_lower_better(cur["frt"], t_frt),
             f"{t_frt:g} h", w["frt"], delta_color="inverse")
    kpi_card(r1[2], "res", "Avg resolution time", fmt_hours(cur["res"]),
             delta(cur["res"], prev["res"]), ratio_lower_better(cur["res"], t_res),
             f"{t_res:g} h", w["res"], delta_color="inverse")
    csat_text = f"{cur['csat']:.2f} / 5" if not pd.isna(cur["csat"]) else "n/a"
    kpi_card(r2[0], "csat", "Customer satisfaction (CSAT)", csat_text,
             delta(cur["csat"], prev["csat"]),
             cur["csat"] / t_csat if not pd.isna(cur["csat"]) else None,
             f"{t_csat:g}", w["csat"])
    kpi_card(r2[1], "sla", "First response within target", f"{cur['sla']:.0f}%",
             delta(cur["sla"], prev["sla"]), spark=w["sla"])
    kpi_card(r2[2], "repeat", "Repeat contact rate", f"{cur['repeat']:.1f}%",
             delta(cur["repeat"], prev["repeat"]), spark=w["repeat"], delta_color="inverse")
    st.caption(
        "Deltas compare against the previous period of equal length. Time and volume increases show in red. "
        "Repeat contact = same customer wrote again within 14 days. "
        "CSAT is based on the resolved tickets that received a rating."
    )

    st.subheader("Alerts")
    alerts = build_alerts(current, previous)
    if not pd.isna(cur["csat"]) and not pd.isna(prev["csat"]) and cur["csat"] < prev["csat"] - 0.2:
        st.error(f"CSAT fell from {prev['csat']:.2f} to {cur['csat']:.2f} vs the previous period.")
    for m in alerts:
        st.warning(m)
    if not alerts:
        st.info("No notable ticket spikes vs the previous period.")

    tab_over, tab_speed, tab_csat, tab_backlog = st.tabs(
        ["Overview", "Response & resolution", "Satisfaction", "Backlog & agents"]
    )

    with tab_over:
        st.markdown("**Weekly tickets by issue type**")
        wk = current.groupby([pd.Grouper(key="created_date", freq="W"), "issue_type"]).size().reset_index(name="tickets")
        fig = px.bar(wk, x="created_date", y="tickets", color="issue_type")
        fig.update_layout(xaxis_title=None, yaxis_title="Tickets", legend_title=None)
        st.plotly_chart(fig)

        left, right = st.columns(2)
        with left:
            st.markdown("**Tickets by issue type**")
            it = current.groupby("issue_type").size().sort_values().reset_index(name="tickets")
            fig = px.bar(it, x="tickets", y="issue_type", orientation="h")
            fig.update_layout(xaxis_title="Tickets", yaxis_title=None)
            st.plotly_chart(fig)
        with right:
            st.markdown("**Channel mix**")
            ch = current.groupby("channel").size().reset_index(name="tickets")
            st.plotly_chart(px.pie(ch, names="channel", values="tickets", hole=0.45))

        st.markdown("**Late-delivery tickets by country**")
        ld_c = current[current["issue_type"] == "Late delivery"].groupby("country").size().rename("This period")
        ld_p = previous[previous["issue_type"] == "Late delivery"].groupby("country").size().rename("Previous period")
        ld = pd.concat([ld_p, ld_c], axis=1).fillna(0).reset_index().melt(id_vars="country")
        fig = px.bar(ld, x="country", y="value", color="variable", barmode="group")
        fig.update_layout(xaxis_title=None, yaxis_title="Tickets", legend_title=None)
        st.plotly_chart(fig)

    with tab_speed:
        left, right = st.columns(2)
        with left:
            st.markdown("**Avg first response by channel (hours)**")
            frt = current.groupby("channel")["first_response_hours"].mean().sort_values().reset_index()
            fig = px.bar(frt, x="first_response_hours", y="channel", orientation="h")
            fig.add_vline(x=t_frt, line_dash="dash", annotation_text="target")
            fig.update_layout(xaxis_title="Hours", yaxis_title=None)
            st.plotly_chart(fig)
        with right:
            st.markdown("**Avg resolution time by issue type (hours)**")
            res = current.groupby("issue_type")["resolution_hours"].mean().sort_values().reset_index()
            fig = px.bar(res, x="resolution_hours", y="issue_type", orientation="h")
            fig.add_vline(x=t_res, line_dash="dash", annotation_text="target")
            fig.update_layout(xaxis_title="Hours", yaxis_title=None)
            st.plotly_chart(fig)

        st.markdown("**First response within target, by channel (%)**")
        sla = (current.groupby("channel")["sla_ok"].mean() * 100).sort_values().reset_index()
        fig = px.bar(sla, x="sla_ok", y="channel", orientation="h")
        fig.update_layout(xaxis_title="% of tickets", yaxis_title=None, xaxis_range=[0, 100])
        st.plotly_chart(fig)

    with tab_csat:
        rated = current.dropna(subset=["csat"])
        if rated.empty:
            st.info("No CSAT ratings in this period.")
        else:
            st.caption(f"{len(rated):,} rated tickets out of {len(current):,} in this period.")
            left, right = st.columns(2)
            with left:
                st.markdown("**CSAT by issue type**")
                cs = rated.groupby("issue_type")["csat"].mean().sort_values().reset_index()
                fig = px.bar(cs, x="csat", y="issue_type", orientation="h")
                fig.add_vline(x=t_csat, line_dash="dash", annotation_text="target")
                fig.update_layout(xaxis_title="Avg CSAT", yaxis_title=None, xaxis_range=[1, 5])
                st.plotly_chart(fig)
            with right:
                st.markdown("**Rating distribution**")
                dist = rated["csat"].astype(int).value_counts().reindex([1, 2, 3, 4, 5], fill_value=0).reset_index()
                dist.columns = ["rating", "tickets"]
                fig = px.bar(dist, x="rating", y="tickets")
                fig.update_layout(xaxis_title="Rating", yaxis_title="Tickets")
                st.plotly_chart(fig)

            st.markdown("**Weekly CSAT**")
            fig = px.line(w.reset_index(), x="created_date", y="csat", markers=True)
            fig.update_layout(xaxis_title=None, yaxis_title="Avg CSAT")
            st.plotly_chart(fig)

    with tab_backlog:
        unresolved = current[current["status"].isin(["Open", "Escalated"])].copy()
        high = unresolved[unresolved["priority"].isin(["Urgent", "High"])]
        c = st.columns(3)
        c[0].metric("Open tickets", f"{(unresolved['status'] == 'Open').sum():,}")
        c[1].metric("Escalated", f"{(unresolved['status'] == 'Escalated').sum():,}")
        c[2].metric("High / urgent unresolved", f"{len(high):,}")

        st.markdown("**Unresolved tickets (most urgent first)**")
        order = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}
        unresolved["age_days"] = (tickets["created_date"].max() - unresolved["created_date"]).dt.days
        unresolved = unresolved.sort_values(
            ["priority", "created_date"], key=lambda s: s.map(order) if s.name == "priority" else s
        )
        st.dataframe(
            unresolved[["ticket_id", "created_date", "age_days", "issue_type", "priority",
                        "channel", "country", "status", "agent"]].head(200),
            hide_index=True,
        )

        st.markdown("**Agent performance**")
        ag = current.groupby("agent").agg(
            tickets=("ticket_id", "count"),
            avg_first_response_h=("first_response_hours", "mean"),
            avg_resolution_h=("resolution_hours", "mean"),
            avg_csat=("csat", "mean"),
            unresolved=("status", lambda s: (s != "Resolved").sum()),
        ).reset_index().sort_values("tickets", ascending=False)
        st.dataframe(
            ag, hide_index=True,
            column_config={
                "avg_first_response_h": st.column_config.NumberColumn("First response (h)", format="%.1f"),
                "avg_resolution_h": st.column_config.NumberColumn("Resolution (h)", format="%.1f"),
                "avg_csat": st.column_config.NumberColumn("CSAT", format="%.2f"),
            },
        )