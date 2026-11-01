"""
Test: itemised daily costs, payroll, ad spend, cash and overdraft
(NOVA-P2-003, step B).

Run from the project root:

    uv run python test_costs.py

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
MARKETING = {"user_id": "USR-002", "role": "Marketing Manager"}
SUPPORT = {"user_id": "USR-005", "role": "Customer Support Manager"}
INVENTORY = {"user_id": "USR-004", "role": "Inventory Manager"}

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


def fresh(folder, name):
    dst = folder / name
    shutil.copy(PROJECT / "company.db", dst)
    sim.initialize_simulation(dst)
    return dst


def costs_by_name(db, day):
    return {c["category"]: c["amount"] for c in sim.get_daily_costs(day, db)}


def one_day(db):
    cash_before = sim.get_state(db)["cash_balance"]
    sim.advance_day(CEO, db)
    state = sim.get_state(db)
    return state["latest_metrics"], cash_before, state["cash_balance"]


def main():
    folder = Path(tempfile.mkdtemp())

    # ------------------------------------------------------------
    print("TEST 1: every day has itemised costs that add up")
    a = fresh(folder, "a.db")
    m, cash_before, cash_after = one_day(a)
    costs = costs_by_name(a, m["day"])

    expected = {
        "COGS", "Shipping & packaging", "Payment & platform fees",
        "Returns & damaged goods", "Advertising", "Payroll", "Rent",
        "Cloud & hosting", "Software subscriptions", "Overdraft interest",
    }
    check("all cost lines present", expected <= set(costs), str(set(costs)))
    check("COGS line matches daily metrics", abs(costs["COGS"] - m["cogs"]) < 0.02)
    check("profit = revenue - all costs",
          abs(m["profit"] - (m["revenue"] - sum(costs.values()))) < 0.05,
          f"{m['profit']} vs {m['revenue'] - sum(costs.values()):.2f}")
    check("cash change = revenue - costs other than COGS",
          abs((cash_after - cash_before)
              - (m["revenue"] - (sum(costs.values()) - costs["COGS"]))) < 0.05,
          f"{cash_after - cash_before:.2f}")
    check("shipping = orders x $5.10",
          abs(costs["Shipping & packaging"] - m["orders"] * 5.10) < 0.05)
    check("fees = 4% of revenue",
          abs(costs["Payment & platform fees"] - m["revenue"] * 0.04) < 0.05)
    check("returns = 6.4% of revenue",
          abs(costs["Returns & damaged goods"] - m["revenue"] * 0.064) < 0.05)
    check("default day is profitable but thin (0% to 15% margin)",
          0 < m["profit"] / m["revenue"] < 0.15,
          f"{m['profit'] / m['revenue']:.1%}")

    # ------------------------------------------------------------
    print("\nTEST 2: inventory is not charged to cash twice")
    check("cash rises on a normal day when nothing is restocked",
          cash_after > cash_before, f"{cash_before} -> {cash_after}")

    # ------------------------------------------------------------
    print("\nTEST 3: payroll follows support staffing")
    b = fresh(folder, "b.db")
    state = sim.get_state(b)
    sim.record_decision(SUPPORT, "set_support_staffing", 12, db_path=b)
    m12, _, _ = one_day(b)
    pay12 = costs_by_name(b, m12["day"])["Payroll"]

    c = fresh(folder, "c.db")
    sim.record_decision(SUPPORT, "set_support_staffing", 40, db_path=c)
    m40, _, _ = one_day(c)
    pay40 = costs_by_name(c, m40["day"])["Payroll"]

    non_support = rows(
        b, "SELECT COUNT(*) n FROM employees WHERE department != 'Customer Support'"
    )[0]["n"]
    check("payroll at 12 agents = other staff x $1 + 12 x $2",
          abs(pay12 - (non_support * 1.0 + 12 * 2.0)) < 0.01, f"{pay12}")
    check("28 more agents cost exactly $56 more a day",
          abs((pay40 - pay12) - 56.0) < 0.01, f"{pay40 - pay12}")

    # ------------------------------------------------------------
    print("\nTEST 4: ad spend has a sweet spot")
    results = {}
    for spend in (0, 200, 2000):
        d = fresh(folder, f"ad{spend}.db")
        sim.record_decision(CEO, "set_marketing_budget", spend, db_path=d)
        m, _, _ = one_day(d)
        results[spend] = m
        check(f"ad spend ${spend} is charged as advertising cost",
              abs(costs_by_name(d, m["day"])["Advertising"] - spend) < 0.01)
    check("some advertising brings more revenue than none",
          results[200]["revenue"] > results[0]["revenue"])
    check("$200 earns more profit than $0", results[200]["profit"] > results[0]["profit"])
    check("$2,000 loses money compared with $200",
          results[2000]["profit"] < results[200]["profit"])

    check("new databases start at the $200 default",
          sim.get_state(fresh(folder, "default.db"))["marketing_budget"] == 200.0)

    # ------------------------------------------------------------
    print("\nTEST 5: overdraft interest")
    e = fresh(folder, "e.db")
    execute(e, "UPDATE simulation_state SET cash_balance = -20000 WHERE id = 1")
    m, cash_before, cash_after = one_day(e)
    ec = costs_by_name(e, m["day"])
    interest = ec["Overdraft interest"]
    # Cash after the day's trading, before interest is charged:
    pre_interest = cash_before + m["revenue"] - (
        sum(ec.values()) - ec["COGS"] - interest
    )
    check("balance is still negative after a day of trading", pre_interest < 0,
          f"{pre_interest:.2f}")
    check("interest = 0.1% of the overdrawn balance",
          abs(interest - (-pre_interest * 0.001)) < 0.02,
          f"${interest} vs ${-pre_interest * 0.001:.2f}")
    check("interest lowers profit",
          abs(m["profit"] - (m["revenue"] - sum(ec.values()))) < 0.05)
    check("interest is taken out of cash",
          abs(cash_after - (pre_interest - interest)) < 0.05)

    f = fresh(folder, "f.db")
    m, _, _ = one_day(f)
    check("no interest when cash is positive",
          costs_by_name(f, m["day"])["Overdraft interest"] == 0)

    # ------------------------------------------------------------
    print("\nTEST 6: who may change settings")
    g = fresh(folder, "g.db")
    for actor, decision, value, label in (
        (MARKETING, "set_marketing_budget", 300, "Marketing Manager cannot set ad spend"),
        (INVENTORY, "set_support_staffing", 10, "Inventory Manager cannot set staffing"),
        (SUPPORT, "set_marketing_budget", 300, "Support Manager cannot set ad spend"),
    ):
        try:
            sim.record_decision(actor, decision, value, db_path=g)
            check(label, False, "no exception")
        except PermissionError:
            check(label, True)
    sim.record_decision(SUPPORT, "set_support_staffing", 20, db_path=g)
    check("Support Manager can set staffing",
          sim.get_state(g)["support_staffing"] == 20)

    # ------------------------------------------------------------
    print("\nTEST 7: 30 days with sensible restocking stays healthy")
    h = fresh(folder, "h.db")
    for _ in range(30):
        for p in sim.get_products(h):
            if p["stock"] <= p["reorder_level"] and p["reorder_level"] > 0:
                try:
                    sim.record_decision(INVENTORY, "reorder_product", p["product"], db_path=h)
                except ValueError:
                    pass
        sim.advance_day(CEO, h)
    hist = sim.get_metrics_history(h)[-30:]
    avg_profit = sum(r["profit"] for r in hist) / len(hist)
    lost = sum(r["lost_revenue"] for r in hist)
    check("average daily profit is positive but modest ($50-$600)",
          50 < avg_profit < 600, f"${avg_profit:.0f}")
    check("restocking keeps lost sales small", lost < 3000, f"${lost:.0f}")

    print(f"\nRESULT: {passed} passed, {failed} failed")
    shutil.rmtree(folder, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()