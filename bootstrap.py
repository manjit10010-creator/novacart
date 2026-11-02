"""
First-start data builder (for hosting and fresh clones).

Does NOT import Streamlit. app.py calls build_if_empty() once at start-up.

  * Nothing exists yet  -> runs setup_demo.py to create the demo data.
  * Everything exists   -> does nothing (your own machine).
  * Only some files     -> does NOT touch anything; reports "partial".
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED = [
    "orders.csv",
    "marketing_daily.csv",
    "inventory.csv",
    "returns.csv",
    "tickets.csv",
    "users.json",
    "company.db",
]


def data_status(root=None):
    """Return ("ready" | "empty" | "partial", list_of_missing_files)."""
    root = Path(root or ROOT)
    missing = [name for name in REQUIRED if not (root / name).exists()]
    if not missing:
        return "ready", []
    if len(missing) == len(REQUIRED):
        return "empty", missing
    return "partial", missing


def build_if_empty(root=None):
    """Return "ready", "built", "partial" or "failed"."""
    root = Path(root or ROOT)
    status, _missing = data_status(root)

    if status == "ready":
        return "ready"
    if status == "partial":
        return "partial"

    result = subprocess.run(
        [sys.executable, str(root / "setup_demo.py")],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        return "failed"

    return "built" if data_status(root)[0] == "ready" else "failed"