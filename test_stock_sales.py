"""
Test: daily sales consume simulation stock (NOVA-P2-003, step 1).

Run from the project root:

    uv run python test_stock_sales.py

SAFE: works on temporary copies of company.db only.
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

import sim_engine as sim  # noqa: E402

CEO = {"user_id": "USR-001", "role": "CEO"}
MANAGER = {"user_id": "USR-004", "role": "Inventory Manager"}

passed = failed = 0


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def stocks(db):
    c = sqlite3.connect(db)
    try:
        return dict(c.execute(
            "SELECT product_id, stock FROM simulation_products"
        ).fetchall())
    finally:
        c.close()


def demand(db):
    c = sqlite3.connect(db)
    try:
        return dict(c.execute(
            "SELECT product_id, units_sold_30d FROM simulation_products"
        ).fetchall())
    finally:
        c.close()


def fresh_copy(folder, name):
    dst = folder / name
    shutil.copy(PROJECT / "company.db", dst)
    return dst


def main():
    folder = Path(tempfile.mkdtemp())
    a = fresh_copy(folder, "a.db")
    b = fresh_copy(folder, "b.db")

    print("TEST 1: one day of sales reduces stock")
    before = stocks(a)
    dem = demand(a)
    sim.advance_day(CEO, a)
    after = stocks(a)

    check("no product gained stock",
          all(after[k] <= before[k] for k in before))
    check("no negative stock", all(v >= 0 for v in after.values()))
    check("total stock went down",
          sum(after.values()) < sum(before.values()),
          f"{sum(before.values())} -> {sum(after.values())}")
    check("products with zero demand are untouched",
          all(after[k] == before[k] for k in before if dem[k] == 0))
    sold = sum(before[k] - after[k] for k in before)
    check("units sold are plausible (50 to 400 per day)",
          50 <= sold <= 400, f"sold {sold}")

    print("\nTEST 2: same day, same start -> same result")
    sim.advance_day(CEO, b)
    check("deterministic", stocks(a) == stocks(b))

    print("\nTEST 3: stock never goes below zero over 60 days")
    for _ in range(60):
        sim.advance_day(CEO, a)
    check("no negative stock after 60 days",
          all(v >= 0 for v in stocks(a).values()))

    print("\nTEST 4: only the CEO can advance the day")
    c_before = stocks(b)
    try:
        sim.advance_day(MANAGER, b)
        check("manager blocked", False, "no exception")
    except PermissionError:
        check("manager blocked", True)
    check("blocked attempt did not change stock", stocks(b) == c_before)

    print("\nTEST 5: restocking after sales still works")
    c = sqlite3.connect(b)
    low = c.execute(
        "SELECT product, stock FROM simulation_products "
        "WHERE stock < reorder_level AND reorder_level > 0 LIMIT 1"
    ).fetchone()
    c.close()
    if low:
        name, old = low
        sim.record_decision(MANAGER, "reorder_product", name, db_path=b)
        c = sqlite3.connect(b)
        new = c.execute(
            "SELECT stock FROM simulation_products WHERE product=?", (name,)
        ).fetchone()[0]
        c.close()
        check("restock raises stock", new > old, f"{old} -> {new}")
    else:
        print("  (no low-stock product to restock)")

    print(f"\nRESULT: {passed} passed, {failed} failed")
    shutil.rmtree(folder, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()