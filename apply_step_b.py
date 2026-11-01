"""
NOVA-P2-003 Step B: daily operating costs, payroll, ad spend, cash
fix and overdraft interest, plus a Company Settings panel.

Run ONCE from the project root (the folder containing sim_engine.py),
after Step A has been applied:

    python apply_step_b.py

What it does:
  1. Checks every edit point exists exactly once. If anything is
     missing, NOTHING is written and your files stay untouched.
  2. Backs up sim_engine.py and views/game_view.py (*.bak_stepB).
  3. Applies the edits. Re-running is safe (it detects Step B).

Afterwards run:
    uv run python test_costs.py
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SIM = ROOT / "sim_engine.py"
VIEW = ROOT / "views" / "game_view.py"

sim_text = SIM.read_text(encoding="utf-8")
view_text = VIEW.read_text(encoding="utf-8")

if "simulation_daily_costs" in sim_text:
    print("Step B already applied. Nothing to do.")
    sys.exit(0)

if "_read_unit_prices" not in sim_text:
    print("STOPPED: Step A is not applied yet. Run apply_step_a.py first.")
    sys.exit(1)

SIM_EDITS = []   # (old, new)
VIEW_EDITS = []

# ---------- sim_engine.py ----------
SIM_EDITS.append(("import csv\nimport random\n", "import csv\nimport math\nimport random\n"))

SIM_EDITS.append(('ORDERS_PATH = BASE_DIR / "orders.csv"\n', '''ORDERS_PATH = BASE_DIR / "orders.csv"

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
'''))

SIM_EDITS.append(("def advance_day(\n    actor,\n    db_path=None,\n):", '''def _marketing_factor(ad_spend):
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
):'''))

SIM_EDITS.append(('''        marketing_factor = max(
            0.75,
            min(
                1.25,
                1 + (budget - 1000) / 10000,
            ),
        )
''', '''        marketing_factor = _marketing_factor(budget)
'''))

SIM_EDITS.append(('''        # Temporary flat rate for shipping, fees and ad spend
        # (about 17.5% of revenue in the historical data).
        # Step B replaces this with itemised costs.
        other_costs = revenue * 0.175

        profit = (
            revenue
            - cogs
            - other_costs
            - max(0, budget - 1000) * 0.18
        )
''', '''        # Daily operating costs.
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
'''))

SIM_EDITS.append(('''        # Cash is persistent and changes each simulated day.
        cash = (
            float(state["cash_balance"])
            + profit
            - max(0, budget - 1000)
        )

''', ''))

SIM_EDITS.append(("        # Update the persistent company state.\n", '''        # Store the itemised daily costs.
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
'''))

SIM_EDITS.append(('''        if column not in metric_columns:
            connection.execute(
                f"ALTER TABLE simulation_daily_metrics "
                f"ADD COLUMN {column} {definition}"
            )
''', '''        if column not in metric_columns:
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
'''))

SIM_EDITS.append(('''# ---------------------------------------------------------
# 10. INTERNAL TASK CREATION''', '''def get_daily_costs(day=None, db_path=None):
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
# 10. INTERNAL TASK CREATION'''))

# ---------- views/game_view.py ----------
VIEW_EDITS.append(("    get_decisions,\n    advance_day,\n", "    get_decisions,\n    get_daily_costs,\n    advance_day,\n"))

VIEW_EDITS.append(('''            sales_cols[2].metric(
                "Lost Revenue",
                f"${latest.get('lost_revenue', 0):,.2f}",
            )
''', '''            sales_cols[2].metric(
                "Lost Revenue",
                f"${latest.get('lost_revenue', 0):,.2f}",
            )

            with st.expander("Latest day profit and loss"):
                cost_rows = get_daily_costs(latest["day"])

                if cost_rows:
                    pnl = pd.DataFrame(cost_rows)[["category", "amount"]]
                    pnl.columns = ["Cost item", "Amount ($)"]

                    st.dataframe(pnl, hide_index=True)

                    st.write(
                        f"**Revenue:** ${latest['revenue']:,.2f}  |  "
                        f"**Total costs:** ${pnl['Amount ($)'].sum():,.2f}  |  "
                        f"**Profit:** ${latest['profit']:,.2f}"
                    )
                else:
                    st.info(
                        "No itemised costs for this day "
                        "(it was simulated before costs were added)."
                    )
'''))

VIEW_EDITS.append(('''    if role in {"CEO", "Inventory Manager"}:
        st.divider()
        st.subheader("Inventory Procurement")
''', '''    if role in {"CEO", "Customer Support Manager"}:
        st.divider()
        st.subheader("Company Settings")

        st.caption(
            "Ad spend and support staffing change daily costs "
            "and results from the next simulated day."
        )

        settings_cols = st.columns(2)

        if role == "CEO":
            with settings_cols[0]:
                new_ad_spend = st.number_input(
                    "Daily ad spend ($)",
                    min_value=0,
                    max_value=10000,
                    value=int(state["marketing_budget"]),
                    step=50,
                )

                if st.button("Update ad spend"):
                    try:
                        result = record_decision(
                            actor=user,
                            decision_type="set_marketing_budget",
                            value=new_ad_spend,
                            rationale="Set from Company Settings.",
                        )

                        st.success(result["effect_summary"])
                        st.rerun()

                    except Exception as error:
                        st.error(f"Could not update ad spend: {error}")

        with settings_cols[1]:
            new_agents = st.number_input(
                "Active support agents",
                min_value=1,
                max_value=56,
                value=int(state["support_staffing"]),
                step=1,
            )

            if st.button("Update support staffing"):
                try:
                    result = record_decision(
                        actor=user,
                        decision_type="set_support_staffing",
                        value=new_agents,
                        rationale="Set from Company Settings.",
                    )

                    st.success(result["effect_summary"])
                    st.rerun()

                except Exception as error:
                    st.error(f"Could not update staffing: {error}")

    if role in {"CEO", "Inventory Manager"}:
        st.divider()
        st.subheader("Inventory Procurement")
'''))



def apply(edits, text, label):
    for old, new in edits:
        if text.count(old) != 1:
            print(f"STOPPED: {label}: edit point found {text.count(old)} times "
                  f"(expected 1):")
            print(old[:140])
            print("No files were changed.")
            sys.exit(1)
        text = text.replace(old, new)
    return text


sim_new = apply(SIM_EDITS, sim_text, "sim_engine.py")
view_new = apply(VIEW_EDITS, view_text, "views/game_view.py")

shutil.copy(SIM, str(SIM) + ".bak_stepB")
shutil.copy(VIEW, str(VIEW) + ".bak_stepB")
SIM.write_text(sim_new, encoding="utf-8")
VIEW.write_text(view_new, encoding="utf-8")
print("Step B applied. Backups: sim_engine.py.bak_stepB, views/game_view.py.bak_stepB")