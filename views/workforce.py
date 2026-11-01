from datetime import datetime, time

import pandas as pd
import plotly.express as px
import streamlit as st

from company_db import load_workforce
from presence import IST, STATUS_COLORS, STATUS_ORDER, hourly_logged_in, now_ist


def clock_picker(key: str) -> datetime:
    """Live clock, or a simulated date/time so you can demo 3am vs 11am."""
    st.sidebar.header("Company clock")
    mode = st.sidebar.radio("Clock", ["Live (IST)", "Simulated"], key=f"{key}_mode", horizontal=True)
    if mode.startswith("Live"):
        st.sidebar.button("Refresh", key=f"{key}_refresh")
        return now_ist()
    d = st.sidebar.date_input("Date", value=now_ist().date(), key=f"{key}_date")
    t = st.sidebar.time_input("Time (IST)", value=time(11, 0), key=f"{key}_time")
    return datetime.combine(d, t, tzinfo=IST)


def shift_text(row) -> str:
    return f"{int(row['shift_start']):02d}:00–{int(row['shift_end']):02d}:00"


def render(_filters=None):
    user = st.session_state.get("user")
    if not user or user["role"] != "CEO":
        st.error("Only the CEO can open the Workforce dashboard.")
        return

    when = clock_picker("ceo")
    emps = load_workforce(when)

    st.title("👥 Workforce")
    st.caption(
        "Simulated NovaCart employees (synthetic data). "
        f"Showing {when:%A %d %b %Y, %H:%M} IST."
    )

    total = len(emps)
    logged = int(emps["logged_in"].sum())
    counts = emps["status"].value_counts()

    c = st.columns(5)
    c[0].metric("Employees", total)
    c[1].metric("Logged in", logged, f"{logged / total * 100:.0f}%")
    c[2].metric("Not logged in", total - logged)
    c[3].metric("In a meeting", int(counts.get("In a meeting", 0)))
    c[4].metric("On leave today", int(counts.get("On leave", 0)))
    st.progress(logged / total)

    tab_now, tab_day, tab_dir, tab_org = st.tabs(
        ["Logged in now", "Today's pattern", "Directory", "Organization"]
    )

    with tab_now:
        by_dept = emps.groupby(["department", "status"]).size().reset_index(name="employees")
        fig = px.bar(
            by_dept, x="employees", y="department", color="status", orientation="h",
            category_orders={"status": STATUS_ORDER}, color_discrete_map=STATUS_COLORS,
        )
        fig.update_layout(xaxis_title="Employees", yaxis_title=None, legend_title=None)
        st.plotly_chart(fig)

        st.markdown("**Logged in by department**")
        dept_tbl = emps.groupby("department").agg(
            employees=("employee_id", "count"), logged_in=("logged_in", "sum")
        ).reset_index()
        dept_tbl["not_logged_in"] = dept_tbl["employees"] - dept_tbl["logged_in"]
        dept_tbl["logged_in_pct"] = dept_tbl["logged_in"] / dept_tbl["employees"] * 100
        st.dataframe(
            dept_tbl.sort_values("employees", ascending=False), hide_index=True,
            column_config={"logged_in_pct": st.column_config.ProgressColumn(
                "Logged in %", format="%.0f%%", min_value=0, max_value=100)},
        )

    with tab_day:
        curve = pd.DataFrame(hourly_logged_in(emps, when.date()))
        fig = px.line(curve, x="hour", y="logged_in", markers=True)
        fig.add_vline(x=when.hour + when.minute / 60, line_dash="dash", annotation_text="selected time")
        fig.update_layout(xaxis_title="Hour of day (IST)", yaxis_title="Logged in", xaxis=dict(dtick=2))
        st.plotly_chart(fig)
        st.caption("Early shifts start at 06:00 and late shifts run until 23:00, so coverage rises and falls through the day.")

    with tab_dir:
        left, right, search = st.columns([2, 2, 2])
        depts = left.multiselect("Department", sorted(emps["department"].unique()))
        statuses = right.multiselect("Status", STATUS_ORDER)
        query = search.text_input("Search name or team")

        shown = emps
        if depts:
            shown = shown[shown["department"].isin(depts)]
        if statuses:
            shown = shown[shown["status"].isin(statuses)]
        if query:
            q = query.lower()
            shown = shown[shown["name"].str.lower().str.contains(q) | shown["team"].str.lower().str.contains(q)]

        names = emps.set_index("employee_id")["name"]
        view = shown.assign(manager=shown["manager_id"].map(names).fillna("—"), shift=shown.apply(shift_text, axis=1))
        st.dataframe(
            view[["employee_id", "name", "department", "team", "title", "manager", "shift", "work_mode", "status"]],
            hide_index=True,
        )
        st.caption(f"{len(shown)} of {total} employees")

    with tab_org:
        heads = emps[emps["level"] == "Department Head"].set_index("department")["name"]
        org = emps.groupby("department").agg(
            headcount=("employee_id", "count"),
            logged_in=("logged_in", "sum"),
            teams=("team", lambda s: s[s != "Leadership"].nunique()),
        ).reset_index()
        org["head"] = org["department"].map(heads).fillna("—")
        st.dataframe(org[["department", "head", "teams", "headcount", "logged_in"]], hide_index=True)

        st.markdown("**Teams and their managers**")
        mgrs = emps[emps["level"] == "Team Manager"].copy()
        sizes = emps[emps["level"].isin(["Team Manager", "Employee"])].groupby(["department", "team"]).size()
        mgrs["team_size"] = [sizes[(d, t)] for d, t in zip(mgrs["department"], mgrs["team"])]
        st.dataframe(mgrs[["department", "team", "name", "team_size", "status"]], hide_index=True)