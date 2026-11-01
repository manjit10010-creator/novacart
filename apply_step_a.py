"""
NOVA-P2-003 Step A: bottom-up daily sales, COGS and lost sales.

Run ONCE from the project root (the folder containing sim_engine.py):

    python apply_step_a.py

What it does:
  1. Backs up sim_engine.py and views/game_view.py (*.bak_stepA).
  2. Applies the edits. If ANY anchor text is not found exactly once,
     nothing is written and your files stay untouched.
  3. Re-running it is safe: it detects that the edit is already applied.

Afterwards run:
    uv run python test_sales_engine.py
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SIM = ROOT / "sim_engine.py"
VIEW = ROOT / "views" / "game_view.py"

sim_text = SIM.read_text(encoding="utf-8")
view_text = VIEW.read_text(encoding="utf-8")

if "_read_unit_prices" in sim_text:
    print("Step A already applied to sim_engine.py. Nothing to do.")
    sys.exit(0)

s = sim_text


def rep(old, new):
    global s
    if s.count(old) != 1:
        print(f"STOPPED: expected anchor not found exactly once ({s.count(old)} matches):")
        print(old[:120])
        print("No files were changed.")
        sys.exit(1)
    s = s.replace(old, new)

# ---- EDIT 1: helper for selling prices, placed above _migrate_simulation_schema
rep('''def _migrate_simulation_schema(connection):''','''def _read_unit_prices():
    """
    Average selling price per product over the latest 30 days
    of historical orders (revenue divided by units sold).
    """

    prices = {}

    if not ORDERS_PATH.exists():
        return prices

    try:
        with open(
            ORDERS_PATH, "r", newline="", encoding="utf-8-sig"
        ) as file:
            rows = list(csv.DictReader(file))

        parsed = []

        for row in rows:
            try:
                parsed.append((
                    datetime.strptime(
                        row["order_date"][:10], "%Y-%m-%d"
                    ).date(),
                    row["product"],
                    float(row["revenue"]),
                    float(row["quantity"]),
                ))
            except (KeyError, ValueError, TypeError):
                continue

        if not parsed:
            return prices

        cutoff = max(r[0] for r in parsed) - timedelta(days=29)

        totals = {}

        for order_date, product, revenue, quantity in parsed:
            if order_date >= cutoff:
                money, units = totals.get(product, (0.0, 0.0))
                totals[product] = (money + revenue, units + quantity)

        for product, (money, units) in totals.items():
            if units > 0:
                prices[product] = money / units

    except (OSError, csv.Error):
        pass

    return prices


def _migrate_simulation_schema(connection):''')

# ---- EDIT 2: end of _migrate_simulation_schema: new columns + price backfill
rep('''            created_by_role TEXT NOT NULL,
            day INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            received_at TEXT
        )
        """
    )
''','''            created_by_role TEXT NOT NULL,
            day INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            received_at TEXT
        )
        """
    )

    # Selling price per product.
    product_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(simulation_products)"
        ).fetchall()
    }

    if "unit_price" not in product_columns:
        connection.execute(
            "ALTER TABLE simulation_products ADD COLUMN unit_price REAL"
        )

    unpriced = connection.execute(
        """
        SELECT product, unit_cost
        FROM simulation_products
        WHERE unit_price IS NULL
        """
    ).fetchall()

    # Only read the orders file when a product still needs a price.
    prices = _read_unit_prices() if unpriced else {}

    for row in unpriced:
        connection.execute(
            """
            UPDATE simulation_products
            SET unit_price = ?
            WHERE product = ?
            """,
            (
                round(prices.get(row["product"], row["unit_cost"] * 1.76), 2),
                row["product"],
            ),
        )

    # Daily sales detail columns.
    metric_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(simulation_daily_metrics)"
        ).fetchall()
    }

    for column, definition in (
        ("units_sold", "INTEGER NOT NULL DEFAULT 0"),
        ("units_lost", "INTEGER NOT NULL DEFAULT 0"),
        ("lost_revenue", "REAL NOT NULL DEFAULT 0"),
        ("cogs", "REAL NOT NULL DEFAULT 0"),
    ):
        if column not in metric_columns:
            connection.execute(
                f"ALTER TABLE simulation_daily_metrics "
                f"ADD COLUMN {column} {definition}"
            )
''')

# ---- EDIT 3: replace marketing_factor ... profit with bottom-up sales
a=s.index("        marketing_factor = max(\n")
b=s.index("        tickets = max(\n")
new_block='''        marketing_factor = max(
            0.75,
            min(
                1.25,
                1 + (budget - 1000) / 10000,
            ),
        )

        staffing_factor = max(
            0.75,
            min(
                1.08,
                0.90 + staffing * 0.008,
            ),
        )

        demand_factor = 1 + rng.uniform(
            -0.06,
            0.08,
        )

        # Daily sales: each product sells up to what it has in stock.
        # Demand above available stock becomes lost sales.
        sales_rng = random.Random(909000 + day)

        selling_products = connection.execute(
            """
            SELECT product_id, stock, unit_cost, unit_price,
                   units_sold_30d
            FROM simulation_products
            """
        ).fetchall()

        units_sold_total = 0
        units_lost_total = 0
        revenue = 0.0
        cogs = 0.0
        lost_revenue = 0.0

        for item in selling_products:
            expected_units = (
                item["units_sold_30d"] / 30
                * demand_factor
                * marketing_factor
            )

            demand_units = int(expected_units)

            if sales_rng.random() < expected_units - demand_units:
                demand_units += 1

            units_sold = min(demand_units, item["stock"])
            units_lost = demand_units - units_sold

            units_sold_total += units_sold
            units_lost_total += units_lost
            revenue += units_sold * item["unit_price"]
            cogs += units_sold * item["unit_cost"]
            lost_revenue += units_lost * item["unit_price"]

            if units_sold > 0:
                connection.execute(
                    """
                    UPDATE simulation_products
                    SET stock = stock - ?
                    WHERE product_id = ?
                    """,
                    (units_sold, item["product_id"]),
                )

        # About 1.6 units per order in the historical data.
        orders = max(1, round(units_sold_total / 1.6))

        # Temporary flat rate for shipping, fees and ad spend
        # (about 17.5% of revenue in the historical data).
        # Step B replaces this with itemised costs.
        other_costs = revenue * 0.175

        profit = (
            revenue
            - cogs
            - other_costs
            - max(0, budget - 1000) * 0.18
        )

'''
s=s[:a]+new_block+s[b:]

# ---- EDIT 4: remove the separate stock-selling block (now done above)
c=s.index("        # Sell stock: each product loses units based on its daily demand.\n")
d=s.index("        # Generate tasks for products with low stock.\n")
s=s[:c]+s[d:]

# ---- EDIT 5: store the new columns
rep('''                stock_alerts,
                marketing_budget,
                support_staffing,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,''','''                stock_alerts,
                marketing_budget,
                support_staffing,
                created_at,
                units_sold,
                units_lost,
                lost_revenue,
                cogs
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,''')
rep('''                budget,
                staffing,
                now,
            ),
        )

        # Update the persistent company state.''','''                budget,
                staffing,
                now,
                units_sold_total,
                units_lost_total,
                round(lost_revenue, 2),
                round(cogs, 2),
            ),
        )

        # Update the persistent company state.''')
rep("""import csv
import random""","""import csv
import random
from functools import lru_cache""")
rep("def _read_baseline():","@lru_cache(maxsize=1)\ndef _read_baseline():")

sim_new = s

# ---- game_view.py: show units sold and lost sales
s = view_text
rep("""            cols[4].metric(
                "Customer Satisfaction",
                f"{latest['csat']:.2f}/5",
            )
""","""            cols[4].metric(
                "Customer Satisfaction",
                f"{latest['csat']:.2f}/5",
            )

            sales_cols = st.columns(3)

            sales_cols[0].metric(
                "Units Sold",
                f"{latest.get('units_sold', 0):,}",
            )

            sales_cols[1].metric(
                "Lost Sales (units)",
                f"{latest.get('units_lost', 0):,}",
            )

            sales_cols[2].metric(
                "Lost Revenue",
                f"${latest.get('lost_revenue', 0):,.2f}",
            )
""")
view_new = s

shutil.copy(SIM, str(SIM) + ".bak_stepA")
shutil.copy(VIEW, str(VIEW) + ".bak_stepA")
SIM.write_text(sim_new, encoding="utf-8")
VIEW.write_text(view_new, encoding="utf-8")
print("Step A applied. Backups: sim_engine.py.bak_stepA, views/game_view.py.bak_stepA")