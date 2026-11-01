import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path

import streamlit as st

from audit import log_event

USERS_FILE = Path("users.json")
ITERATIONS = 200_000  # must match create_users.py
MAX_FAILED_ATTEMPTS = 5
MIN_PASSWORD_LENGTH = 8
ORG_ID = "ORG-1001"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Roles people can pick when creating an account (CEO accounts are created by an admin only)
SELF_SIGNUP_ROLES = [
    "Marketing Manager",
    "Finance Manager",
    "Inventory Manager",
    "Customer Support Manager",
]

# Which dashboards each role may open
ROLE_VIEWS = {
    "CEO": [
        "Executive Overview", "Marketing", "Finance",
        "Inventory", "Customer Support", "Workforce",
        "Admin & Audit", "Business Simulation"
    ],
    "Marketing Manager": ["Marketing", "My Team", "Business Simulation"],
    "Finance Manager": ["Finance", "My Team", "Business Simulation"],
    "Inventory Manager": ["Inventory", "My Team", "Business Simulation"],
    "Customer Support Manager": ["Customer Support", "My Team", "Business Simulation"],
}


# ---------- User storage ----------
def load_users() -> list:
    if not USERS_FILE.exists():
        return []
    return json.loads(USERS_FILE.read_text())


def save_users(users: list) -> None:
    USERS_FILE.write_text(json.dumps(users, indent=2))


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), ITERATIONS
    ).hex()


# ---------- Sign in ----------
def authenticate(email: str, password: str):
    """Return the user's public profile if the credentials are valid, else None."""
    user = next((u for u in load_users() if u["email"].lower() == email.strip().lower()), None)
    # Hash even for unknown emails so response time doesn't reveal which emails exist
    salt = user["salt"] if user else "00" * 16
    candidate = _hash(password, salt)
    if user and hmac.compare_digest(candidate, user["password_hash"]):
        return {k: user[k] for k in ("user_id", "org_id", "name", "email", "role")}
    return None


# ---------- Sign up ----------
def register_user(name: str, email: str, password: str, confirm: str, role: str):
    """Create a new account. Returns (success, message)."""
    name, email = name.strip(), email.strip().lower()

    if not name:
        return False, "Please enter your name."
    if not EMAIL_RE.match(email):
        return False, "Please enter a valid email address."
    if role not in SELF_SIGNUP_ROLES:
        return False, "That role can't be selected during sign-up."
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password != confirm:
        return False, "Passwords don't match."

    users = load_users()
    if any(u["email"].lower() == email for u in users):
        return False, "An account with this email already exists."

    next_num = max((int(u["user_id"].split("-")[1]) for u in users), default=0) + 1
    salt = secrets.token_bytes(16).hex()
    users.append({
        "user_id": f"USR-{next_num:03d}",
        "org_id": ORG_ID,
        "name": name,
        "email": email,
        "role": role,
        "salt": salt,
        "password_hash": _hash(password, salt),
    })
    save_users(users)
    return True, f"Account created. Your user ID is USR-{next_num:03d}. You can now sign in."


# ---------- Access helpers ----------
def allowed_views(role: str) -> list:
    return ROLE_VIEWS.get(role, [])


def logout():
    log_event("LOGOUT")
    for key in ("user", "last_view"):
        st.session_state.pop(key, None)


# ---------- Login screen ----------
def require_login() -> dict:
    """Show the sign-in / sign-up screen until someone signs in. Returns the signed-in user."""
    if "user" in st.session_state:
        return st.session_state["user"]

    st.title("🛒 NovaCart KPI Dashboard")
    st.caption("Sign in with your company account to see the dashboards for your role.")

    tab_in, tab_up = st.tabs(["Sign in", "Create account"])

    with tab_in:
        failed = st.session_state.get("failed_attempts", 0)
        if failed >= MAX_FAILED_ATTEMPTS:
            st.error("Too many failed attempts. Close this tab and open the app again to retry.")
        else:
            with st.form("login"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in")

            if submitted:
                user = authenticate(email, password)
                if user:
                    st.session_state["user"] = user
                    st.session_state["failed_attempts"] = 0
                    log_event("LOGIN_SUCCESS", user=user)
                    st.rerun()
                else:
                    st.session_state["failed_attempts"] = failed + 1
                    log_event("LOGIN_FAILED", f"attempt {failed + 1}", email=email.strip().lower())
                    if failed + 1 >= MAX_FAILED_ATTEMPTS:
                        log_event("LOGIN_LOCKED", "too many failed attempts", email=email.strip().lower())
                    st.error("Invalid email or password.")

        with st.expander("Demo accounts (portfolio demo with synthetic data)"):
            st.markdown(
                "| Role | Email | Password |\n|---|---|---|\n"
                "| CEO | ceo@novacart.example | Demo@CEO2026 |\n"
                "| Marketing Manager | marketing@novacart.example | Demo@Mkt2026 |\n"
                "| Finance Manager | finance@novacart.example | Demo@Fin2026 |\n"
                "| Inventory Manager | inventory@novacart.example | Demo@Inv2026 |\n"
                "| Customer Support Manager | support@novacart.example | Demo@Sup2026 |"
            )

    with tab_up:
        st.caption("New accounts join NovaCart with the role you choose. CEO accounts are created by an admin.")
        with st.form("signup", clear_on_submit=False):
            name = st.text_input("Full name")
            email = st.text_input("Work email", key="signup_email")
            role = st.selectbox("Department / role", SELF_SIGNUP_ROLES)
            password = st.text_input(
                f"Password (min {MIN_PASSWORD_LENGTH} characters)", type="password", key="signup_pw"
            )
            confirm = st.text_input("Confirm password", type="password")
            created = st.form_submit_button("Create account")

        if created:
            ok, msg = register_user(name, email, password, confirm, role)
            if ok:
                log_event("ACCOUNT_CREATED", f"role={role}", email=email.strip().lower())
            (st.success if ok else st.error)(msg)

    st.stop()