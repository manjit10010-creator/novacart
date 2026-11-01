import streamlit as st

from audit import log_event
from auth import allowed_views, logout, require_login
from common import load_orders, sidebar_filters
from views import admin, ceo, finance, game_view, inventory, marketing, support, team, workforce

st.set_page_config(page_title="NovaCart KPI Dashboard", page_icon="📈", layout="wide")

user = require_login()  # shows the login screen and stops until signed in

VIEWS = {
    "Executive Overview": ceo.render,
    "Business Simulation": game_view.render,
    "Marketing": marketing.render,
    "Finance": finance.render,
    "Inventory": inventory.render,
    "Customer Support": support.render,
    "Workforce": workforce.render,
    "My Team": team.render,
    "Admin & Audit": admin.render,
}
VIEWS_WITHOUT_FILTERS = {
    "Admin & Audit",
    "Workforce",
    "My Team",
    "Business Simulation",
}

st.sidebar.title("🛒 NovaCart")
st.sidebar.markdown(f"**{user['name']}**")
st.sidebar.caption(f"{user['role']} · {user['user_id']} · {user['org_id']}")
st.sidebar.button("Sign out", on_click=logout)
st.sidebar.divider()

allowed = allowed_views(user["role"])
if not allowed:
    st.error("Your account has no dashboards assigned. Contact an administrator.")
    st.stop()

# Only people with more than one dashboard get a switcher
view = st.sidebar.radio("Dashboard", allowed) if len(allowed) > 1 else allowed[0]

# Final check: never render a view the role isn't allowed to open
if view not in allowed:
    log_event("ACCESS_DENIED", f"view={view}")
    st.error("You don't have access to this dashboard.")
    st.stop()

# Log a dashboard open once, not on every filter change
if st.session_state.get("last_view") != view:
    log_event("VIEW_OPENED", view)
    st.session_state["last_view"] = view

try:
    filters = None
    if view not in VIEWS_WITHOUT_FILTERS:
        st.sidebar.divider()
        filters = sidebar_filters(load_orders())
        st.sidebar.divider()
    VIEWS[view](filters)
except PermissionError as err:
    st.error(str(err))