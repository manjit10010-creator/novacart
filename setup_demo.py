"""
One-command setup for NovaCart (fresh clone or full rebuild).

    uv run python setup_demo.py            # first-time setup
    uv run python setup_demo.py --force    # rebuild everything from scratch

What it does, in order (these are your existing scripts):
    1. generate_data.py          -> orders.csv
    2. generate_extra_data.py    -> marketing_daily.csv, inventory.csv, returns.csv
    3. generate_support_data.py  -> tickets.csv
    4. create_users.py           -> users.json (4 demo accounts)
    5. add_support_user.py       -> adds the Customer Support Manager account
    6. build_company.py          -> company.db (200 employees)
    7. creates the simulation tables inside company.db

SAFE: if any generated file already exists it STOPS and changes nothing.
With --force it first MOVES the old files into demo_backup_<timestamp>/
(it never deletes them), then rebuilds. That includes your simulation
progress in company.db, so only use --force when you want a clean start.
"""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    "generate_data.py",
    "generate_extra_data.py",
    "generate_support_data.py",
    "create_users.py",
    "add_support_user.py",
    "build_company.py",
]

GENERATED = [
    "orders.csv",
    "marketing_daily.csv",
    "inventory.csv",
    "returns.csv",
    "tickets.csv",
    "users.json",
    "company.db",
    "audit_log.csv",
]


def main():
    force = "--force" in sys.argv[1:]

    existing = [name for name in GENERATED if (ROOT / name).exists()]

    if existing and not force:
        print("STOPPED: these files already exist, so nothing was changed:")
        for name in existing:
            print(f"  - {name}")
        print("\nTo rebuild from scratch (old files are moved to a backup folder,")
        print("not deleted), run:  uv run python setup_demo.py --force")
        return 1

    if existing:
        backup = ROOT / f"demo_backup_{datetime.now():%Y%m%d_%H%M%S}"
        backup.mkdir()
        for name in existing:
            shutil.move(str(ROOT / name), str(backup / name))
        print(f"Old files moved to {backup.name}/\n")

    for number, script in enumerate(STEPS, start=1):
        print(f"[{number}/{len(STEPS) + 1}] {script}")
        result = subprocess.run([sys.executable, script], cwd=ROOT)
        if result.returncode != 0:
            print(f"\nSTOPPED: {script} failed (exit code {result.returncode}).")
            print("Fix the error above, then run this command again with --force.")
            return result.returncode

    print(f"[{len(STEPS) + 1}/{len(STEPS) + 1}] simulation tables")
    sys.path.insert(0, str(ROOT))
    import sim_engine

    state = sim_engine.get_state()
    print(f"Simulation ready: day {state['current_day']}, "
          f"cash ${state['cash_balance']:,.2f}")

    print("\nDone. Start the app with:  uv run streamlit run app.py")
    print("Sign in with the demo accounts shown on the login page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())