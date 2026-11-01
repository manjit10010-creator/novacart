"""
Test: bottom-up daily sales, COGS and lost sales (NOVA-P2-003, step A).

Run from the project root:

    uv run python test_sales_engine.py

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


def rows(db, sql, args=()):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute(sql, args).fetchall()]
    finally:
        c.close()


def execute(db, sql, args=()):
    c = sqlite3.connect(db)
    c.execute(sql, args)
    c.commit()
    c.close()


def fresh(folder, name, source="company.db"):
    dst = folder / name
    shutil.copy(PROJECT / source, dst)
    return dst


def products(db):
    return {
        r["product_id"]: r
        for r in rows(db, "SELECT * FROM simulation_products")
    }


def main():
    folder = Path(tempfile.mkdtemp())

    # ------------------------------------------------------------
    print("TEST 1: one day of sales is internally consistent")
    a = fresh(folder, "a.db")
    sim.initialize_simulation(a)
    before = products(a)
    sim.advance_day(CEO, a)
    after = products(a)
    day = rows(a, "SELECT * FROM simulation_daily_metrics ORDER BY day DESC LIMIT 1")[0]

    diff = {k: before[k]["stock"] - after[k]["stock"] for k in before}
    units = sum(diff.values())
    rev = sum(diff[k] * before[k]["unit_price"] for k in before)
    cogs = sum(diff[k] * before[k]["unit_cost"] for k in before)

    check("all products have a selling price",
          all(p["unit_price"] and p["unit_price"] > 0 for p in before.values()))
    check("units_sold matches stock removed", day["units_sold"] == units,
          f"{day['units_sold']} vs {units}")
    check("revenue = sum(units sold x price)", abs(day["revenue"] - rev) < 0.05,
          f"{day['revenue']} vs {rev:.2f}")
    check("cogs = sum(units sold x unit cost)", abs(day["cogs"] - cogs) < 0.05,
          f"{day['cogs']} vs {cogs:.2f}")
    check("prices are above cost (healthy margin)", rev > cogs)
    check("daily revenue is in a believable range (2k-6k)", 2000 <= day["revenue"] <= 6000,
          f"{day['revenue']}")
    check("profit is below gross profit (running costs are deducted)",
          day["profit"] < day["revenue"] - day["cogs"],
          f"profit {day['profit']} vs gross {day['revenue'] - day['cogs']:.2f}")
    check("orders about units / 1.6",
          abs(day["orders"] - units / 1.6) <= 1, f"{day['orders']} vs {units/1.6:.1f}")

    # ------------------------------------------------------------
    print("\nTEST 2: stock-outs create lost sales")
    b = fresh(folder, "b.db")
    sim.initialize_simulation(b)
    execute(b, "UPDATE simulation_products SET stock = 0")
    sim.advance_day(CEO, b)
    day = rows(b, "SELECT * FROM simulation_daily_metrics ORDER BY day DESC LIMIT 1")[0]
    check("no stock -> no units sold", day["units_sold"] == 0)
    check("no stock -> revenue is zero", day["revenue"] == 0)
    check("no stock -> lost sales recorded",
          day["units_lost"] > 50 and day["lost_revenue"] > 1000,
          f"{day['units_lost']} units, ${day['lost_revenue']}")
    check("profit is not positive with no sales", day["profit"] <= 0)

    # ------------------------------------------------------------
    print("\nTEST 3: restocking recovers sales")
    c_db = fresh(folder, "c.db")
    sim.initialize_simulation(c_db)
    execute(c_db, "UPDATE simulation_products SET stock = 0")
    sim.advance_day(CEO, c_db)
    lost_day = rows(c_db, "SELECT * FROM simulation_daily_metrics ORDER BY day DESC LIMIT 1")[0]
    names = [
        r["product"]
        for r in rows(c_db, "SELECT product FROM simulation_products ORDER BY units_sold_30d DESC LIMIT 10")
    ]
    for n in names:
        sim.record_decision(MANAGER, "reorder_product", n, db_path=c_db)
    sim.advance_day(CEO, c_db)
    next_day = rows(c_db, "SELECT * FROM simulation_daily_metrics ORDER BY day DESC LIMIT 1")[0]
    check("restocked best sellers sell again",
          next_day["revenue"] > lost_day["revenue"],
          f"{lost_day['revenue']} -> {next_day['revenue']}")

    # ------------------------------------------------------------
    print("\nTEST 4: repeatable and safe")
    d1 = fresh(folder, "d1.db")
    d2 = fresh(folder, "d2.db")
    sim.advance_day(CEO, d1)
    sim.advance_day(CEO, d2)
    q = "SELECT revenue, profit, orders, units_sold, units_lost FROM simulation_daily_metrics ORDER BY day"
    check("same start -> same day result", rows(d1, q) == rows(d2, q))
    before = rows(d1, q)
    try:
        sim.advance_day(MANAGER, d1)
        check("manager blocked", False, "no exception")
    except PermissionError:
        check("manager blocked", True)
    check("blocked attempt changed nothing", rows(d1, q) == before)

    for _ in range(60):
        sim.advance_day(CEO, d1)
    check("stock never negative over 60 days",
          all(r["stock"] >= 0 for r in products(d1).values()))

    # ------------------------------------------------------------
    print("\nTEST 5: migration on an older database")
    old = fresh(folder, "old.db", "company_backup_before_procurement.db")
    sim.initialize_simulation(old)
    sim.initialize_simulation(old)  # second run must be harmless
    cols = {r["name"] for r in rows(old, "PRAGMA table_info(simulation_daily_metrics)")}
    check("new metric columns exist",
          {"units_sold", "units_lost", "lost_revenue", "cogs"} <= cols)
    check("old products got prices",
          all(p["unit_price"] for p in products(old).values()))
    sim.advance_day(CEO, old)
    check("old database can advance a day", True)

    print(f"\nRESULT: {passed} passed, {failed} failed")
    shutil.rmtree(folder, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()