"""
NovaCart Phase 2: Simulation Engine

Responsibilities:
    1. Persist simulation state.
    2. Advance the simulated business day.
    3. Generate operational tasks.
    4. Apply management decisions.
    5. Track daily business metrics.
    6. Enforce role-based permissions.

This module contains business logic only.
It does not import Streamlit.
"""

import csv
import math
import random
from functools import lru_cache
import sqlite3

from datetime import date, datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------
# 1. PROJECT CONFIGURATION
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "company.db"
INVENTORY_PATH = BASE_DIR / "inventory.csv"
ORDERS_PATH = BASE_DIR / "orders.csv"

# Daily operating-cost assumptions, scaled to NovaCart's size.
# Salaries are deliberately scaled down: NovaCart earns about
# $3,900 a day, so real pay for 200 people would bankrupt it.
SHIPPING_PER_ORDER = 5.10            # courier + packaging per order
PAYMENT_FEE_RATE = 0.040             # gateway (~2.5%) + marketplace (~1.5%)
RETURNS_RATE = 0.064                 # refunds + damaged goods (Finance page: 6.4%)
PAY_PER_STAFF_DAY = 1.00             # simulated pay per employee per day
PAY_PER_SUPPORT_AGENT_DAY = 2.00     # per ACTIVE support agent per day
OVERHEADS_PER_DAY = {
    "Rent": 50.0,
    "Cloud & hosting": 25.0,
    "Software subscriptions": 25.0,
}
OVERDRAFT_DAILY_RATE = 0.001         # interest on a negative cash balance
DEFAULT_AD_SPEND = 200.0             # daily ad spend a new company starts with


DEPARTMENT_BY_ROLE = {
    "Marketing Manager": "Marketing",
    "Finance Manager": "Finance",
    "Inventory Manager": "Inventory & Warehouse",
    "Customer Support Manager": "Customer Support",
}

SUPPORTED_ROLES = {
    "CEO",
    *DEPARTMENT_BY_ROLE.keys(),
}


# ---------------------------------------------------------
# 2. DATABASE CONNECTION
# ---------------------------------------------------------

def _connect(db_path=None):
    """
    Open a database connection.

    Using a separate set of simulation tables allows us
    to preserve existing Phase 1 tables.
    """

    path = db_path or DB_PATH

    connection = sqlite3.connect(
        str(path),
        timeout=15,
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# ---------------------------------------------------------
# 3. BASELINE BUSINESS METRICS
# ---------------------------------------------------------

@lru_cache(maxsize=1)
def _read_baseline():
    """
    Read historical order data when available.

    If the CSV format differs from the expected format,
    use clearly defined demo defaults instead.
    """

    default = {
        "orders": 150,
        "revenue": 9000.0,
        "profit": 1800.0,
        "tickets": 20,
        "csat": 4.2,
        "base_date": date.today().isoformat(),
    }

    if not ORDERS_PATH.exists():
        return default

    try:
        with open(
            ORDERS_PATH,
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            rows = list(csv.DictReader(file))

        if not rows:
            return default

        # Find commonly used column names.
        columns = {
            name.lower().strip(): name
            for name in rows[0].keys()
            if name
        }

        date_column = columns.get("order_date")
        revenue_column = columns.get("revenue")
        profit_column = columns.get("profit")

        if not (
            date_column
            and revenue_column
            and profit_column
        ):
            return default

        valid_rows = []

        for row in rows:
            try:
                order_date = datetime.strptime(
                    row[date_column][:10],
                    "%Y-%m-%d",
                ).date()

                revenue = float(
                    row[revenue_column]
                )

                profit = float(
                    row[profit_column]
                )

                valid_rows.append({
                    "date": order_date,
                    "revenue": revenue,
                    "profit": profit,
                })

            except (ValueError, TypeError):
                continue

        if not valid_rows:
            return default

        latest_date = max(
            row["date"]
            for row in valid_rows
        )

        start_date = latest_date - timedelta(days=29)

        recent = [
            row
            for row in valid_rows
            if start_date <= row["date"] <= latest_date
        ]

        if not recent:
            return default

        daily_totals = {}

        for row in recent:
            key = row["date"]

            if key not in daily_totals:
                daily_totals[key] = {
                    "orders": 0,
                    "revenue": 0.0,
                    "profit": 0.0,
                }

            daily_totals[key]["orders"] += 1

            daily_totals[key]["revenue"] += (
                row["revenue"]
            )

            daily_totals[key]["profit"] += (
                row["profit"]
            )

        number_of_days = len(daily_totals)

        return {
            "orders": sum(
                day["orders"]
                for day in daily_totals.values()
            ) / number_of_days,

            "revenue": sum(
                day["revenue"]
                for day in daily_totals.values()
            ) / number_of_days,

            "profit": sum(
                day["profit"]
                for day in daily_totals.values()
            ) / number_of_days,

            "tickets": default["tickets"],
            "csat": default["csat"],
            "base_date": latest_date.isoformat(),
        }

    except (OSError, csv.Error):
        return default


# ---------------------------------------------------------
# 4. INITIALIZE SIMULATION DATABASE
# ---------------------------------------------------------

def initialize_simulation(db_path=None):
    """
    Create simulation tables if they do not already exist.

    Running this function repeatedly must not reset
    the player's progress.
    """

    baseline = _read_baseline()

    connection = _connect(db_path)

    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS simulation_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),

                current_day INTEGER NOT NULL DEFAULT 0,
                simulated_date TEXT NOT NULL,

                cash_balance REAL NOT NULL DEFAULT 500000,

                marketing_budget REAL NOT NULL DEFAULT 1000,

                support_staffing INTEGER NOT NULL DEFAULT 12,

                cumulative_revenue REAL NOT NULL DEFAULT 0,

                cumulative_profit REAL NOT NULL DEFAULT 0,

                customer_satisfaction REAL NOT NULL DEFAULT 4.2,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );


            CREATE TABLE IF NOT EXISTS simulation_daily_metrics (
                day INTEGER PRIMARY KEY,

                simulated_date TEXT NOT NULL,

                orders INTEGER NOT NULL,
                revenue REAL NOT NULL,
                profit REAL NOT NULL,

                tickets INTEGER NOT NULL,
                csat REAL NOT NULL,

                stock_alerts INTEGER NOT NULL,

                marketing_budget REAL NOT NULL,
                support_staffing INTEGER NOT NULL,

                created_at TEXT NOT NULL
            );


            CREATE TABLE IF NOT EXISTS simulation_tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,

                day_created INTEGER NOT NULL,

                department TEXT NOT NULL,

                title TEXT NOT NULL,
                description TEXT NOT NULL,

                priority TEXT NOT NULL DEFAULT 'Medium',

                status TEXT NOT NULL DEFAULT 'Open',

                assigned_to TEXT,

                estimated_impact REAL NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,

                completed_at TEXT
            );


            CREATE TABLE IF NOT EXISTS simulation_decisions (
                decision_id INTEGER PRIMARY KEY AUTOINCREMENT,

                day INTEGER NOT NULL,

                actor_user_id TEXT,

                actor_role TEXT NOT NULL,

                department TEXT NOT NULL,

                decision_type TEXT NOT NULL,

                decision_value TEXT NOT NULL,

                rationale TEXT,

                effect_summary TEXT,

                created_at TEXT NOT NULL
            );


            CREATE TABLE IF NOT EXISTS simulation_products (
                product TEXT PRIMARY KEY,

                category TEXT NOT NULL,

                unit_cost REAL NOT NULL,

                stock INTEGER NOT NULL,

                reorder_level INTEGER NOT NULL,

                units_sold_30d INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        now = datetime.now().isoformat(
            timespec="seconds"
        )

        existing = connection.execute(
            """
            SELECT id
            FROM simulation_state
            WHERE id = 1
            """
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO simulation_state (
                    id,
                    current_day,
                    simulated_date,
                    cash_balance,
                    marketing_budget,
                    support_staffing,
                    cumulative_revenue,
                    cumulative_profit,
                    customer_satisfaction,
                    created_at,
                    updated_at
                )
                VALUES (
                    1, 0, ?, 500000, 1000, 12,
                    0, 0, ?, ?, ?
                )
                """,
                (
                    baseline["base_date"],
                    baseline["csat"],
                    now,
                    now,
                ),
            )

        _load_inventory(connection)

        _migrate_simulation_schema(connection)

        connection.commit()

    finally:
        connection.close()


def _read_unit_prices():
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


def _migrate_simulation_schema(connection):
    """
    Safely add product IDs and procurement relationships
    to existing simulation databases.
    """

    # Inspect existing product columns.
    product_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(simulation_products)"
        ).fetchall()
    }

    if "product_id" not in product_columns:
        connection.execute(
            """
            ALTER TABLE simulation_products
            ADD COLUMN product_id TEXT
            """
        )

    # Inspect existing task columns.
    task_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(simulation_tasks)"
        ).fetchall()
    }

    if "product_id" not in task_columns:
        connection.execute(
            """
            ALTER TABLE simulation_tasks
            ADD COLUMN product_id TEXT
            """
        )

    # Assign permanent IDs to existing products.
    products = connection.execute(
        """
        SELECT product
        FROM simulation_products
        ORDER BY product
        """
    ).fetchall()

    for index, row in enumerate(products, start=1):
        product_id = f"SKU-{index:03d}"

        connection.execute(
            """
            UPDATE simulation_products
            SET product_id = ?
            WHERE product = ?
              AND product_id IS NULL
            """,
            (product_id, row["product"]),
        )
        # Link existing restock tasks to their products by name.
    connection.execute(
        """
        UPDATE simulation_tasks
        SET product_id = (
            SELECT p.product_id
            FROM simulation_products p
            WHERE 'Restock ' || p.product = simulation_tasks.title
        )
        WHERE product_id IS NULL
          AND title LIKE 'Restock %'
        """
    )    

    # Create purchase order records.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS simulation_purchase_orders (
            purchase_order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_cost REAL NOT NULL,
            total_cost REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Received',
            created_by TEXT,
            created_by_role TEXT NOT NULL,
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

    # Itemised daily costs (one row per cost line per day).
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS simulation_daily_costs (
            day INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            PRIMARY KEY (day, category)
        )
        """
    )

    # The old default ad budget ($1,000) loses money under real costs.
    # Move it to the new default, but only if nobody chose it on purpose.
    connection.execute(
        """
        UPDATE simulation_state
        SET marketing_budget = ?
        WHERE id = 1
          AND marketing_budget = 1000
          AND NOT EXISTS (
              SELECT 1
              FROM simulation_decisions
              WHERE decision_type = 'set_marketing_budget'
          )
        """,
        (DEFAULT_AD_SPEND,),
    )


# ---------------------------------------------------------
# 5. LOAD INVENTORY INTO SIMULATION
# ---------------------------------------------------------

def _load_inventory(connection):
    """
    Copy inventory into simulation-owned tables.

    Existing Phase 1 inventory data is not modified.
    """

    existing_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM simulation_products
        """
    ).fetchone()[0]

    if existing_count > 0:
        return

    if not INVENTORY_PATH.exists():
        return

    try:
        with open(
            INVENTORY_PATH,
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                normalized = {
                    key.lower().strip(): value
                    for key, value in row.items()
                    if key
                }

                product = normalized.get("product")

                if not product:
                    continue

                try:
                    category = normalized.get(
                        "category", "General"
                    )

                    unit_cost = float(
                        normalized.get("unit_cost", 10)
                    )

                    stock = int(
                        float(normalized.get("stock", 0))
                    )

                    reorder_level = int(
                        float(
                            normalized.get(
                                "reorder_level", 10
                            )
                        )
                    )

                    units_sold = int(
                        float(
                            normalized.get(
                                "units_sold_30d", 0
                            )
                        )
                    )

                    connection.execute(
                        """
                        INSERT OR IGNORE INTO simulation_products (
                            product,
                            category,
                            unit_cost,
                            stock,
                            reorder_level,
                            units_sold_30d
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            product,
                            category,
                            unit_cost,
                            stock,
                            reorder_level,
                            units_sold,
                        ),
                    )

                except (ValueError, TypeError):
                    continue

    except (OSError, csv.Error):
        return


# ---------------------------------------------------------
# 6. READ SIMULATION STATE
# ---------------------------------------------------------

def get_state(db_path=None):
    """
    Return the current persistent simulation state.
    """

    initialize_simulation(db_path)

    connection = _connect(db_path)

    try:
        row = connection.execute(
            """
            SELECT *
            FROM simulation_state
            WHERE id = 1
            """
        ).fetchone()

        state = dict(row)

        latest = connection.execute(
            """
            SELECT *
            FROM simulation_daily_metrics
            ORDER BY day DESC
            LIMIT 1
            """
        ).fetchone()

        state["latest_metrics"] = (
            dict(latest)
            if latest
            else None
        )

        return state

    finally:
        connection.close()


# ---------------------------------------------------------
# 7. READ PRODUCTS
# ---------------------------------------------------------

def get_products(db_path=None):
    """
    Return simulation inventory ordered by stock risk.
    """

    initialize_simulation(db_path)

    connection = _connect(db_path)

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM simulation_products
            ORDER BY
                CAST(stock AS REAL)
                / MAX(reorder_level, 1)
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        connection.close()


# ---------------------------------------------------------
# 8. READ OPERATIONAL TASKS
# ---------------------------------------------------------

def get_tasks(
    role,
    db_path=None,
    status=None,
):
    """
    CEO sees all tasks.

    Department managers see only their own department.
    """

    if role not in SUPPORTED_ROLES:
        raise PermissionError(
            "This role cannot access simulation tasks."
        )

    initialize_simulation(db_path)

    connection = _connect(db_path)

    try:
        query = """
            SELECT *
            FROM simulation_tasks
        """

        conditions = []
        parameters = []

        if role != "CEO":
            conditions.append(
                "department = ?"
            )

            parameters.append(
                DEPARTMENT_BY_ROLE[role]
            )

        if status and status != "All":
            conditions.append(
                "status = ?"
            )

            parameters.append(status)

        if conditions:
            query += " WHERE " + " AND ".join(
                conditions
            )

        query += """
            ORDER BY
                CASE priority
                    WHEN 'Critical' THEN 0
                    WHEN 'High' THEN 1
                    WHEN 'Medium' THEN 2
                    ELSE 3
                END,
                task_id DESC
        """

        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        connection.close()


# ---------------------------------------------------------
# 9. READ PERFORMANCE HISTORY
# ---------------------------------------------------------

def get_metrics_history(db_path=None):
    """
    Return daily simulation metrics for charts.
    """

    initialize_simulation(db_path)

    connection = _connect(db_path)

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM simulation_daily_metrics
            ORDER BY day
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        connection.close()


def get_daily_costs(day=None, db_path=None):
    """
    Return itemised daily costs.

    With a day number: that day's cost lines.
    Without: every day, oldest first.
    """

    initialize_simulation(db_path)

    connection = _connect(db_path)

    try:
        if day is None:
            rows = connection.execute(
                """
                SELECT *
                FROM simulation_daily_costs
                ORDER BY day, rowid
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM simulation_daily_costs
                WHERE day = ?
                ORDER BY rowid
                """,
                (day,),
            ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


# ---------------------------------------------------------
# 10. INTERNAL TASK CREATION
# ---------------------------------------------------------

def _add_task(
    connection,
    day,
    department,
    title,
    description,
    priority,
    estimated_impact,
    now,
    product_id=None,
):
    """
    Avoid duplicate open tasks with the same title
    for the same department and simulated day.
    """

    existing = connection.execute(
        """
        SELECT task_id
        FROM simulation_tasks
        WHERE day_created = ?
          AND department = ?
          AND title = ?
          AND status IN ('Open', 'In progress')
        """,
        (
            day,
            department,
            title,
        ),
    ).fetchone()

    if existing:
        return

        connection.execute(
        """
        INSERT INTO simulation_tasks (
            day_created,
            department,
            title,
            description,
            priority,
            estimated_impact,
            created_at,
            product_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            day,
            department,
            title,
            description,
            priority,
            float(estimated_impact),
            now,
            product_id,
        ),
    )


# ---------------------------------------------------------
# 11. ADVANCE SIMULATION BY ONE DAY
# ---------------------------------------------------------

def _marketing_factor(ad_spend):
    """
    Demand multiplier from daily ad spend, with diminishing returns.

    About 1.0 at $200 a day. Spending more still adds demand, but
    each extra dollar adds less, so there is a sensible sweet spot.
    """

    return max(
        0.60,
        min(
            1.40,
            0.659 + 0.7 * (1 - math.exp(-ad_spend / 300)),
        ),
    )


def _daily_payroll(connection, support_agents):
    """
    Scaled daily payroll.

    Support is paid per ACTIVE agent (the staffing setting).
    Every other department is paid per employee on record.
    """

    try:
        rows = connection.execute(
            """
            SELECT department, COUNT(*) AS headcount
            FROM employees
            GROUP BY department
            """
        ).fetchall()
    except sqlite3.Error:
        rows = []

    other_staff = sum(
        row["headcount"]
        for row in rows
        if row["department"] != "Customer Support"
    )

    return (
        other_staff * PAY_PER_STAFF_DAY
        + support_agents * PAY_PER_SUPPORT_AGENT_DAY
    )


def advance_day(
    actor,
    db_path=None,
):
    """
    Advance the business simulation by exactly one day.

    Only the CEO can advance global simulation time.

    Daily metrics and generated tasks are committed
    together in a single database transaction.
    """

    if actor.get("role") != "CEO":
        raise PermissionError(
            "Only the CEO can advance the simulation."
        )

    initialize_simulation(db_path)

    baseline = _read_baseline()

    connection = _connect(db_path)

    try:
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        state = connection.execute(
            """
            SELECT *
            FROM simulation_state
            WHERE id = 1
            """
        ).fetchone()

        day = state["current_day"] + 1

        simulated_date = (
            date.fromisoformat(
                state["simulated_date"]
            )
            + timedelta(days=1)
        ).isoformat()

        # Repeatable random sequence for reproducible demos.
        rng = random.Random(
            202600 + day
        )

        budget = float(
            state["marketing_budget"]
        )

        staffing = int(
            state["support_staffing"]
        )

        stock_alerts = connection.execute(
            """
            SELECT COUNT(*)
            FROM simulation_products
            WHERE stock <= reorder_level
            """
        ).fetchone()[0]

        marketing_factor = _marketing_factor(budget)

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

        # Daily operating costs.
        shipping_cost = orders * SHIPPING_PER_ORDER
        fee_cost = revenue * PAYMENT_FEE_RATE
        returns_cost = revenue * RETURNS_RATE
        ad_spend = budget
        payroll = _daily_payroll(connection, staffing)
        overheads = sum(OVERHEADS_PER_DAY.values())

        operating_costs = (
            shipping_cost
            + fee_cost
            + returns_cost
            + ad_spend
            + payroll
            + overheads
        )

        # Inventory is paid for when it is purchased, so COGS reduces
        # profit but must not reduce cash a second time.
        cash = (
            float(state["cash_balance"])
            + revenue
            - operating_costs
        )

        # Overdraft: a negative balance is charged daily interest.
        interest = 0.0

        if cash < 0:
            interest = -cash * OVERDRAFT_DAILY_RATE
            cash -= interest

        profit = (
            revenue
            - cogs
            - operating_costs
            - interest
        )

        tickets = max(
            1,
            round(
                baseline["tickets"]
                * rng.uniform(0.85, 1.18)
            ),
        )

        previous_csat = float(
            state["customer_satisfaction"]
        )

        csat = max(
            1.0,
            min(
                5.0,
                previous_csat
                + (staffing_factor - 1) * 0.25
                + rng.uniform(-0.08, 0.08),
            ),
        )

        now = datetime.now().isoformat(
            timespec="seconds"
        )

        # Store daily performance.
        connection.execute(
            """
            INSERT INTO simulation_daily_metrics (
                day,
                simulated_date,
                orders,
                revenue,
                profit,
                tickets,
                csat,
                stock_alerts,
                marketing_budget,
                support_staffing,
                created_at,
                units_sold,
                units_lost,
                lost_revenue,
                cogs
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day,
                simulated_date,
                orders,
                round(revenue, 2),
                round(profit, 2),
                tickets,
                round(csat, 2),
                stock_alerts,
                budget,
                staffing,
                now,
                units_sold_total,
                units_lost_total,
                round(lost_revenue, 2),
                round(cogs, 2),
            ),
        )

        # Store the itemised daily costs.
        cost_lines = [
            ("COGS", cogs),
            ("Shipping & packaging", shipping_cost),
            ("Payment & platform fees", fee_cost),
            ("Returns & damaged goods", returns_cost),
            ("Advertising", ad_spend),
            ("Payroll", payroll),
        ]

        cost_lines += list(OVERHEADS_PER_DAY.items())
        cost_lines.append(("Overdraft interest", interest))

        connection.executemany(
            """
            INSERT INTO simulation_daily_costs (
                day,
                category,
                amount
            )
            VALUES (?, ?, ?)
            """,
            [
                (day, name, round(amount, 2))
                for name, amount in cost_lines
            ],
        )

        # Update the persistent company state.
        connection.execute(
            """
            UPDATE simulation_state
            SET
                current_day = ?,
                simulated_date = ?,
                cash_balance = ?,
                cumulative_revenue =
                    cumulative_revenue + ?,
                cumulative_profit =
                    cumulative_profit + ?,
                customer_satisfaction = ?,
                updated_at = ?
            WHERE id = 1
            """,
            (
                day,
                simulated_date,
                round(cash, 2),
                round(revenue, 2),
                round(profit, 2),
                round(csat, 2),
                now,
            ),
        )
        # Generate tasks for products with low stock.
        low_stock_products = connection.execute(
            """
            SELECT *
            FROM simulation_products
            WHERE stock <= reorder_level
            ORDER BY
                CAST(stock AS REAL)
                / MAX(reorder_level, 1)
            LIMIT 8
            """
        ).fetchall()

        for product in low_stock_products:

            priority = (
                "Critical"
                if product["stock"] <= 0
                else "High"
            )

            quantity = max(
               product["reorder_level"] * 2
             - product["stock"],
               product["reorder_level"],
               10,
            )

            _add_task(
                connection,
                day,
                "Inventory & Warehouse",
                f"Restock {product['product']}",
                (
                    f"{product['product']} has "
                    f"{product['stock']} units remaining. "
                    f"Reorder level: "
                    f"{product['reorder_level']}. "
                    f"Suggested purchase: {quantity} units."
                ),
                priority,
                quantity * product["unit_cost"] * 0.05,
                now,
                product_id=product["product_id"],
            )

        # Generate customer-support tasks.
        if tickets >= baseline["tickets"] * 1.08:
            _add_task(
                connection,
                day,
                "Customer Support",
                "Handle elevated ticket volume",
                (
                    f"Today's simulated ticket volume "
                    f"is {tickets}. Review workload and "
                    f"response times."
                ),
                "High",
                tickets * 2,
                now,
            )

        # Generate finance tasks when profit falls.
        if profit < baseline["profit"] * 0.85:
            _add_task(
                connection,
                day,
                "Finance",
                "Investigate daily profit decline",
                (
                    f"Today's simulated profit is "
                    f"${profit:,.2f}. Review cost drivers."
                ),
                "High",
                abs(
                    profit - baseline["profit"]
                ),
                now,
            )

        # Generate marketing tasks when revenue falls.
        if revenue < baseline["revenue"] * 0.92:
            _add_task(
                connection,
                day,
                "Marketing",
                "Review campaign performance",
                (
                    "Revenue is below the expected range. "
                    "Review campaign effectiveness and "
                    "marketing budget efficiency."
                ),
                "Medium",
                max(
                    50,
                    baseline["revenue"] - revenue,
                ),
                now,
            )

        connection.commit()

        return {
            "day": day,
            "simulated_date": simulated_date,
            "orders": orders,
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "tickets": tickets,
            "csat": round(csat, 2),
            "stock_alerts": stock_alerts,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ---------------------------------------------------------
# 12. RECORD AND APPLY MANAGEMENT DECISIONS
# ---------------------------------------------------------

def record_decision(
    actor,
    decision_type,
    value,
    rationale="",
    db_path=None,
):
    """
    Apply a management decision and record its effect.

    Supported decisions:
        set_marketing_budget
        set_support_staffing
        reorder_product
        complete_task
    """

    role = actor.get("role", "")

    if role not in SUPPORTED_ROLES:
        raise PermissionError(
            "This role cannot make simulation decisions."
        )

    department = (
        "Executive"
        if role == "CEO"
        else DEPARTMENT_BY_ROLE[role]
    )

    initialize_simulation(db_path)

    connection = _connect(db_path)

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    try:
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        state = connection.execute(
            """
            SELECT *
            FROM simulation_state
            WHERE id = 1
            """
        ).fetchone()

        day = int(
            state["current_day"]
        )

        summary = ""

        # ---------------------------------------------
        # Decision A: Change marketing budget.
        # ---------------------------------------------

        if decision_type == "set_marketing_budget":

            if role != "CEO":
                raise PermissionError(
                    "Only the CEO can change the "
                    "company-wide marketing budget."
                )

            amount = float(value)

            if not 0 <= amount <= 10000:
                raise ValueError(
                    "Marketing budget must be "
                    "between $0 and $10,000."
                )

            connection.execute(
                """
                UPDATE simulation_state
                SET marketing_budget = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    amount,
                    now,
                ),
            )

            department = "Marketing"

            value = str(amount)

            summary = (
                f"Daily marketing budget set to "
                f"${amount:,.2f}. Future simulated "
                f"revenue and costs will be affected."
            )

        # ---------------------------------------------
        # Decision B: Change support staffing.
        # ---------------------------------------------

        elif decision_type == "set_support_staffing":

            if role not in {
                "CEO",
                "Customer Support Manager",
            }:
                raise PermissionError(
                    "Only the CEO or Customer Support "
                    "Manager can change support staffing."
                )

            count = int(value)

            if not 1 <= count <= 56:
                raise ValueError(
                    "Support staffing must be "
                    "between 1 and 56."
                )

            connection.execute(
                """
                UPDATE simulation_state
                SET support_staffing = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    count,
                    now,
                ),
            )

            department = "Customer Support"

            value = str(count)

            summary = (
                f"Support staffing set to {count}. "
                f"Future customer-satisfaction "
                f"calculations will reflect this setting."
            )

        # ---------------------------------------------
        # Decision C: Restock a product.
        # ---------------------------------------------

        elif decision_type == "reorder_product":

            if role not in {
                "CEO",
                "Inventory Manager",
            }:
                raise PermissionError(
                    "Only the CEO or Inventory Manager "
                    "can place a restock order."
                )

            product_name = str(value)

            product = connection.execute(
                """
                SELECT *
                FROM simulation_products
                WHERE product = ?
                """,
                (product_name,),
            ).fetchone()

            if product is None:
                raise ValueError(
                    "Product not found in simulation inventory."
                )

            quantity = max(
                product["reorder_level"] * 2
                - product["stock"],
                product["reorder_level"],
                10,
            )

            cost = (
                quantity
                * product["unit_cost"]
            )

            if cost > state["cash_balance"]:
                raise ValueError(
                    "Insufficient simulated cash "
                    f"for the ${cost:,.2f} restock."
                )

                        # Create a purchase order.
            connection.execute(
                """
                INSERT INTO simulation_purchase_orders (
                    product_id,
                    product_name,
                    quantity,
                    unit_cost,
                    total_cost,
                    status,
                    created_by,
                    created_by_role,
                    day,
                    created_at,
                    received_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product["product_id"],
                    product["product"],
                    quantity,
                    product["unit_cost"],
                    cost,
                    "Received",
                    str(actor.get("user_id", "")),
                    role,
                    day,
                    now,
                    now,
                ),
            )

            # Increase inventory stock.
            connection.execute(
                """
                UPDATE simulation_products
                SET stock = stock + ?
                WHERE product_id = ?
                """,
                (
                    quantity,
                    product["product_id"],
                ),
            )

            # Deduct the purchase cost from company cash.
            connection.execute(
                """
                UPDATE simulation_state
                SET cash_balance = cash_balance - ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    cost,
                    now,
                ),
            )

            # Complete pending tasks linked to this product.
            connection.execute(
                """
                UPDATE simulation_tasks
                SET status = 'Completed',
                    completed_at = ?
                WHERE department = 'Inventory & Warehouse'
                  AND product_id = ?
                  AND status IN ('Open', 'In progress')
                """,
                (
                    now,
                    product["product_id"],
                ),
            )

            department = "Inventory & Warehouse"

            value = (
                f"{product['product']}: "
                f"{quantity} units, "
                f"${cost:.2f}"
            )

            summary = (
                f"Purchased {quantity} units of "
                f"{product['product']} for ${cost:,.2f}. "
                f"Purchase order created, inventory updated, "
                f"and simulated cash deducted."
            )

        # ---------------------------------------------
        # Decision D: Complete an operational task.
        # ---------------------------------------------

        elif decision_type == "complete_task":

            task_id = int(value)

            task = connection.execute(
                """
                SELECT *
                FROM simulation_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

            if task is None:
                raise ValueError(
                    "Task not found."
                )

            if (
                role != "CEO"
                and task["department"] != department
            ):
                raise PermissionError(
                    "You can only complete tasks "
                    "belonging to your department."
                )

            if task["status"] == "Completed":
                raise ValueError(
                    "This task is already completed."
                )
            if task["product_id"] and task["title"].startswith("Restock"):
                raise ValueError(
                    "Restock tasks are completed by placing a "
                    "restock order, not by marking them done."
                )
            
            connection.execute(
                """
                UPDATE simulation_tasks
                SET status = 'Completed',
                    completed_at = ?
                WHERE task_id = ?
                """,
                (
                    now,
                    task_id,
                ),
            )

            department = task["department"]

            summary = (
                f"Task #{task_id} marked as completed."
            )

        else:
            raise ValueError(
                f"Unsupported decision type: "
                f"{decision_type}"
            )

        # ---------------------------------------------
        # Save the decision history.
        # ---------------------------------------------

        connection.execute(
            """
            INSERT INTO simulation_decisions (
                day,
                actor_user_id,
                actor_role,
                department,
                decision_type,
                decision_value,
                rationale,
                effect_summary,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day,
                str(actor.get("user_id", "")),
                role,
                department,
                decision_type,
                str(value),
                rationale.strip(),
                summary,
                now,
            ),
        )

        connection.commit()

        return {
            "day": day,
            "department": department,
            "decision_type": decision_type,
            "decision_value": str(value),
            "effect_summary": summary,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ---------------------------------------------------------
# 13. READ DECISION HISTORY
# ---------------------------------------------------------

def get_decisions(
    role,
    db_path=None,
):
    """
    CEO sees company-wide decision history.

    Department managers see decisions belonging
    to their own department.
    """

    if role not in SUPPORTED_ROLES:
        raise PermissionError(
            "This role cannot access decision history."
        )

    initialize_simulation(db_path)

    connection = _connect(db_path)

    try:
        if role == "CEO":

            rows = connection.execute(
                """
                SELECT *
                FROM simulation_decisions
                ORDER BY decision_id DESC
                LIMIT 100
                """
            ).fetchall()

        else:

            department = (
                DEPARTMENT_BY_ROLE[role]
            )

            rows = connection.execute(
                """
                SELECT *
                FROM simulation_decisions
                WHERE department = ?
                ORDER BY decision_id DESC
                LIMIT 100
                """,
                (department,),
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        connection.close()