"""Streamlit panel: CEO-only 'Reset simulation' (all logic is in demo_tools.py)."""

import streamlit as st

from demo_tools import reset_simulation


def render_demo_tools(user):
    if user.get("role") != "CEO":
        return

    with st.expander("Demo tools"):
        st.caption(
            "Start the simulation again from Day 0. A backup of company.db "
            "is saved first, so nothing is lost permanently."
        )
        confirmed = st.checkbox(
            "I understand this erases simulation progress",
            key="reset_sim_confirm",
        )
        if st.button("Reset simulation", disabled=not confirmed, key="reset_sim_button"):
            try:
                backup = reset_simulation(user["role"])
            except Exception as error:
                st.error(f"Could not reset: {error}")
                return
            st.success(f"Simulation reset to Day 0. Backup saved as {backup}.")
            st.session_state["reset_sim_confirm"] = False
            st.rerun()