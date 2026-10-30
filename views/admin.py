import pandas as pd
import plotly.express as px
import streamlit as st

from audit import read_log
from auth import load_users


def render(_filters=None):
    user = st.session_state.get("user")
    if not user or user["role"] != "CEO":  # defense in depth, app.py checks too
        st.error("Only the CEO can open Admin & Audit.")
        return

    st.title("🔐 Admin & Audit")
    st.caption("Accounts and activity for this NovaCart workspace. Times are in UTC.")

    users = pd.DataFrame(load_users())[["user_id", "name", "email", "role", "org_id"]]
    log = read_log()

    week_ago = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    recent = log[log["timestamp_utc"] >= week_ago] if not log.empty else log

    c = st.columns(4)
    c[0].metric("User accounts", len(users))
    c[1].metric("Sign-ins (7 days)", int((recent["event"] == "LOGIN_SUCCESS").sum()) if not recent.empty else 0)
    c[2].metric("Failed sign-ins (7 days)", int((recent["event"] == "LOGIN_FAILED").sum()) if not recent.empty else 0)
    c[3].metric("Access denied (7 days)", int((recent["event"] == "ACCESS_DENIED").sum()) if not recent.empty else 0)

    tab_log, tab_users = st.tabs(["Audit log", "Users"])

    with tab_log:
        if log.empty:
            st.info("No activity logged yet.")
        else:
            events = sorted(log["event"].unique())
            chosen = st.multiselect("Event types", events, default=events)
            shown = log[log["event"].isin(chosen)]

            daily = (
                shown.assign(day=shown["timestamp_utc"].dt.floor("D"))
                .groupby(["day", "event"]).size().reset_index(name="count")
            )
            fig = px.bar(daily, x="day", y="count", color="event")
            fig.update_layout(xaxis_title=None, yaxis_title="Events", legend_title=None)
            st.plotly_chart(fig)

            failed = log[log["event"] == "LOGIN_FAILED"]
            if not failed.empty:
                st.markdown("**Failed sign-ins by email**")
                st.dataframe(
                    failed.groupby("email").size().sort_values(ascending=False).reset_index(name="failures"),
                    hide_index=True,
                )

            st.markdown("**Latest events**")
            st.dataframe(shown.head(500), hide_index=True)
            st.download_button("Download full audit log (CSV)", log.to_csv(index=False),
                               file_name="audit_log.csv")

    with tab_users:
        st.dataframe(users, hide_index=True)
        st.caption("Password hashes are never shown in the app.")