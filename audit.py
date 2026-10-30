import csv
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

LOG_FILE = Path("audit_log.csv")
FIELDS = ["timestamp_utc", "user_id", "email", "role", "event", "detail"]


def _safe(value) -> str:
    """Stop spreadsheet apps from treating logged text as a formula."""
    s = str(value or "")
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def log_event(event: str, detail: str = "", user: dict | None = None, email: str = "") -> None:
    """Append one line to the audit log. Never log passwords."""
    user = user or st.session_state.get("user") or {}
    is_new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "user_id": _safe(user.get("user_id", "")),
            "email": _safe(user.get("email", email)),
            "role": _safe(user.get("role", "")),
            "event": event,
            "detail": _safe(detail),
        })


def read_log() -> pd.DataFrame:
    if not LOG_FILE.exists():
        return pd.DataFrame(columns=FIELDS)
    df = pd.read_csv(LOG_FILE).fillna("")
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.sort_values("timestamp_utc", ascending=False)