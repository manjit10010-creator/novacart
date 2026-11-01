import plotly.express as px
import streamlit as st

from company_db import ROLE_DEPT, load_workforce
from presence import STATUS_COLORS, STATUS_ORDER
from views.workforce import clock_picker, shift_text


def render(_filters=None):
    user = st.session_state.get("user")
    dept = ROLE_DEPT.get(user["role"]) if user else None
    if not dept:
        st.error("This page is for department managers.")
        return

    when = clock_picker("team")
    emps = load_workforce(when)  # already limited to this manager's department

    st.title(f"🧑‍🤝‍🧑 My Team: {dept}")
    st.caption(f"Simulated employees (synthetic data). Showing {when:%A %d %b %Y, %H:%M} IST.")

    total = len(emps)
    logged = int(emps["logged_in"].sum())
    counts = emps["status"].value_counts()
    c = st.columns(4)
    c[0].metric("People", total)
    c[1].metric("Logged in", logged, f"{logged / total * 100:.0f}%")
    c[2].metric("In a meeting", int(counts.get("In a meeting", 0)))
    c[3].metric("On leave today", int(counts.get("On leave", 0)))

    by_team = emps.groupby(["team", "status"]).size().reset_index(name="people")
    fig = px.bar(
        by_team, x="people", y="team", color="status", orientation="h",
        category_orders={"status": STATUS_ORDER}, color_discrete_map=STATUS_COLORS,
    )
    fig.update_layout(xaxis_title="People", yaxis_title=None, legend_title=None)
    st.plotly_chart(fig)

    st.markdown("**Roster**")
    teams = st.multiselect("Team", sorted(emps["team"].unique()))
    shown = emps[emps["team"].isin(teams)] if teams else emps
    names = emps.set_index("employee_id")["name"]
    view = shown.assign(manager=shown["manager_id"].map(names).fillna("CEO"), shift=shown.apply(shift_text, axis=1))
    st.dataframe(
        view[["employee_id", "name", "team", "title", "manager", "shift", "work_mode", "status"]],
        hide_index=True,
    )