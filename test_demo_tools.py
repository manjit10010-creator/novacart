"""
Test: setup_demo.py safety rules and the simulation reset (NOVA-DEMO-001).

Run from the project root:

    uv run python test_demo_tools.py

SAFE: works on temporary copies only. It never touches your files.
"""

import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

import demo_tools  # noqa: E402
import sim_engine as sim  # noqa: E402

CEO = {"user_id": "USR-001", "role": "CEO"}
passed = failed = 0


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def count(db, table):
    c = sqlite3.connect(db)
    try:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        c.close()


def main():
    folder = Path(tempfile.mkdtemp())

    print("Reset simulation")
    db = str(folder / "t.db")
    shutil.copy(PROJECT / "company.db", db)
    sim.advance_day(CEO, db_path=db)
    check("copy has simulation days", count(db, "simulation_daily_metrics") >= 1)
    employees = count(db, "employees")

    for role in ("Marketing Manager", "Finance Manager", "Inventory Manager"):
        try:
            demo_tools.reset_simulation(role, db_path=db)
            check(f"{role} blocked", False)
        except PermissionError:
            check(f"{role} blocked", True)
    check("blocked roles changed nothing", count(db, "simulation_daily_metrics") >= 1)

    backup = demo_tools.reset_simulation("CEO", db_path=db)
    check("backup file created", Path(backup).exists())
    check("backup still has the old days", count(backup, "simulation_daily_metrics") >= 1)
    check("day counter back to 0", sim.get_state(db)["current_day"] == 0)
    check("daily history cleared", count(db, "simulation_daily_metrics") == 0)
    check("decisions cleared", count(db, "simulation_decisions") == 0)
    check("products re-seeded", count(db, "simulation_products") == 60)
    check("employees untouched", count(db, "employees") == employees)

    result = sim.advance_day(CEO, db_path=db)
    check("can advance again after reset", result["day"] == 1)

    print("\nsetup_demo.py refuses to overwrite")
    work = folder / "proj"
    work.mkdir()
    for name in ("setup_demo.py",):
        shutil.copy(PROJECT / name, work / name)
    (work / "orders.csv").write_text("keep me")
    out = subprocess.run([sys.executable, "setup_demo.py"], cwd=work,
                         capture_output=True, text=True)
    check("stops with exit code 1", out.returncode == 1)
    check("names the existing file", "orders.csv" in out.stdout)
    check("did not touch the file", (work / "orders.csv").read_text() == "keep me")

    print(f"\nRESULT: {passed} passed, {failed} failed")
    shutil.rmtree(folder, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()