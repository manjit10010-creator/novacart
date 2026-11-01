"""
End-to-end test of the NovaCart procurement (restock) workflow.

Run from the project root (the folder containing sim_engine.py):

    uv run python test_procurement.py

SAFE: the test copies company.db to a temporary file and never touches
your real database.
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

import sim_engine as sim  # noqa: E402

INVENTORY_MGR = {"user_id": "USR-004", "role": "Inventory Manager"}
MARKETING_MGR = {"user_id": "USR-002", "role": "Marketing Manager"}
CEO = {"user_id": "USR-001", "role": "CEO"}

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def snapshot(db, product_name):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    try:
        return {
            "cash": c.execute(
                "SELECT cash_balance FROM simulation_state WHERE id=1"
            ).fetchone()[0],
            "product": dict(
                c.execute(
                    "SELECT * FROM simulation_products WHERE product=?",
                    (product_name,),
                ).fetchone()
            ),
            "po_count": c.execute(
                "SELECT COUNT(*) FROM simulation_purchase_orders"
            ).fetchone()[0],
            "decision_count": c.execute(
                "SELECT COUNT(*) FROM simulation_decisions"
            ).fetchone()[0],
            "open_tasks": [
                dict(r)
                for r in c.execute(
                    "SELECT task_id, status FROM simulation_tasks "
                    "WHERE product_id=? ORDER BY task_id",
                    (
                        c.execute(
                            "SELECT product_id FROM simulation_products "
                            "WHERE product=?",
                            (product_name,),
                        ).fetchone()[0],
                    ),
                )
            ],
        }
    finally:
        c.close()


def main():
    tmp = Path(tempfile.mkdtemp()) / "company_test.db"
    shutil.copy(PROJECT / "company.db", tmp)

    # Pick a product that currently has an OPEN restock task so we can
    # prove the task flips to Completed. Falls back to Product 015.
    c = sqlite3.connect(tmp)
    row = c.execute(
        """
        SELECT p.product FROM simulation_tasks t
        JOIN simulation_products p ON p.product_id = t.product_id
        WHERE t.status IN ('Open','In progress') AND p.reorder_level > 0
        ORDER BY p.product LIMIT 1
        """
    ).fetchone()
    c.close()
    target = row[0] if row else "Product 015"
    print(f"Target product: {target}\n")

    # ------------------------------------------------------------
    print("TEST 1: schema + SKU integrity")
    c = sqlite3.connect(tmp)
    n, n_id, n_distinct = c.execute(
        "SELECT COUNT(*), COUNT(product_id), COUNT(DISTINCT product_id) "
        "FROM simulation_products"
    ).fetchone()
    c.close()
    check("every product has a SKU", n == n_id, f"{n} vs {n_id}")
    check("SKUs are unique", n_id == n_distinct)

    # ------------------------------------------------------------
    print("\nTEST 2: successful restock")
    before = snapshot(tmp, target)
    p = before["product"]
    exp_qty = max(p["reorder_level"] * 2 - p["stock"], p["reorder_level"], 10)
    exp_cost = exp_qty * p["unit_cost"]

    result = sim.record_decision(
        INVENTORY_MGR, "reorder_product", target,
        rationale="e2e test", db_path=tmp,
    )
    after = snapshot(tmp, target)

    check("PO row created", after["po_count"] == before["po_count"] + 1)
    check("stock increased by expected qty",
          after["product"]["stock"] == p["stock"] + exp_qty,
          f"{p['stock']} -> {after['product']['stock']} (exp +{exp_qty})")
    check("cash reduced by expected cost",
          abs((before["cash"] - after["cash"]) - exp_cost) < 0.005,
          f"delta {before['cash'] - after['cash']:.2f} vs {exp_cost:.2f}")
    check("decision logged", after["decision_count"] == before["decision_count"] + 1)
    check("linked tasks all Completed",
          all(t["status"] == "Completed" for t in after["open_tasks"]),
          str(after["open_tasks"]))

    c = sqlite3.connect(tmp)
    c.row_factory = sqlite3.Row
    po = c.execute(
        "SELECT * FROM simulation_purchase_orders ORDER BY purchase_order_id DESC LIMIT 1"
    ).fetchone()
    c.close()
    check("PO fields correct",
          po["product_id"] == p["product_id"]
          and po["quantity"] == exp_qty
          and abs(po["total_cost"] - exp_cost) < 0.005
          and po["created_by_role"] == "Inventory Manager"
          and po["status"] == "Received",
          dict(po).__repr__())

    # ------------------------------------------------------------
    print("\nTEST 3: permissions (no state change on denial)")
    before = snapshot(tmp, target)
    try:
        sim.record_decision(MARKETING_MGR, "reorder_product", target, db_path=tmp)
        check("Marketing Manager blocked", False, "no exception raised")
    except PermissionError:
        check("Marketing Manager blocked", True)
    after = snapshot(tmp, target)
    check("nothing changed after denial",
          before["cash"] == after["cash"]
          and before["po_count"] == after["po_count"]
          and before["product"]["stock"] == after["product"]["stock"])

    # ------------------------------------------------------------
    print("\nTEST 4: insufficient cash is rejected atomically")
    c = sqlite3.connect(tmp)
    c.execute("UPDATE simulation_state SET cash_balance = 1 WHERE id = 1")
    c.commit()
    c.close()
    before = snapshot(tmp, target)
    try:
        sim.record_decision(CEO, "reorder_product", target, db_path=tmp)
        check("rejected for low cash", False, "no exception raised")
    except ValueError:
        check("rejected for low cash", True)
    after = snapshot(tmp, target)
    check("no PO / stock / cash change on rejection",
          before["cash"] == after["cash"]
          and before["po_count"] == after["po_count"]
          and before["product"]["stock"] == after["product"]["stock"]
          and before["decision_count"] == after["decision_count"])

    # ------------------------------------------------------------
    print("\nTEST 5: unknown product")
    try:
        sim.record_decision(CEO, "reorder_product", "Product 999", db_path=tmp)
        check("unknown product rejected", False, "no exception raised")
    except ValueError:
        check("unknown product rejected", True)

    # ------------------------------------------------------------
    print("\nTEST 6: complete_task on a restock task (loophole check)")
    c = sqlite3.connect(tmp)
    c.execute("UPDATE simulation_state SET cash_balance = 500000 WHERE id = 1")
    t = c.execute(
        """
        SELECT task_id, product_id FROM simulation_tasks
        WHERE title LIKE 'Restock%' AND status IN ('Open','In progress')
        LIMIT 1
        """
    ).fetchone()
    c.commit()
    c.close()
    if t:
        task_id, pid = t
        c = sqlite3.connect(tmp)
        stock_before = c.execute(
            "SELECT stock FROM simulation_products WHERE product_id=?", (pid,)
        ).fetchone()[0]
        c.close()
        try:
            sim.record_decision(INVENTORY_MGR, "complete_task", task_id, db_path=tmp)
            c = sqlite3.connect(tmp)
            stock_after = c.execute(
                "SELECT stock FROM simulation_products WHERE product_id=?", (pid,)
            ).fetchone()[0]
            c.close()
            check("restock task cannot be closed without buying stock",
                  stock_after != stock_before,
                  f"task #{task_id} closed, stock unchanged ({stock_before})")
        except (ValueError, PermissionError):
            check("restock task cannot be closed without buying stock", True)
    else:
        print("  (no open restock task left to test)")

    print(f"\nRESULT: {passed} passed, {failed} failed")
    shutil.rmtree(tmp.parent, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()