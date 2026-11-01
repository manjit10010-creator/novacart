
import streamlit as st
import pandas as pd
import plotly.express as px

from sim_engine import (
    get_state,
    get_tasks,
    get_products,
    get_metrics_history,
    get_decisions,
    advance_day,
    record_decision,
)


def render(_filters=None):
    """Render the NovaCart business simulation."""

    user = st.session_state.get("user")

    if not user:
        st.error("Please sign in to access the simulation.")
        return

    role = user["role"]

    st.title("NovaCart Business Simulation")
    st.caption(
        "Manage business operations, respond to events, "
        "and observe the impact of management decisions."
    )

    # Only supported roles can use the simulation.
    if role not in {
        "CEO",
        "Marketing Manager",
        "Finance Manager",
        "Inventory Manager",
        "Customer Support Manager",
    }:
        st.error("Your role cannot access the simulation.")
        return

    # Retrieve persistent simulation data.
    state = get_state()
    tasks = get_tasks(role)
    products = get_products()
    history = get_metrics_history()
    decisions = get_decisions(role)

    latest = state.get("latest_metrics")

    # -------------------------------------------------
    # SIMULATION HEADER
    # -------------------------------------------------

    st.subheader(
        f"Simulation Day {state['current_day']}"
    )

    st.write(
        f"Simulated date: **{state['simulated_date']}**"
    )

    # -------------------------------------------------
    # COMPANY METRICS
    # -------------------------------------------------

    if role == "CEO":
        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Company Cash",
            f"${state['cash_balance']:,.2f}",
        )

        col2.metric(
            "Cumulative Revenue",
            f"${state['cumulative_revenue']:,.2f}",
        )

        col3.metric(
            "Cumulative Profit",
            f"${state['cumulative_profit']:,.2f}",
        )

        if latest:
            st.subheader("Latest Daily Performance")

            cols = st.columns(5)

            cols[0].metric(
                "Orders",
                f"{latest['orders']:,}",
            )

            cols[1].metric(
                "Revenue",
                f"${latest['revenue']:,.2f}",
            )

            cols[2].metric(
                "Profit",
                f"${latest['profit']:,.2f}",
            )

            cols[3].metric(
                "Support Tickets",
                f"{latest['tickets']:,}",
            )

            cols[4].metric(
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

    # -------------------------------------------------
    # CEO SIMULATION CONTROL
    # -------------------------------------------------

    if role == "CEO":
        st.divider()
        st.subheader("Simulation Controls")

        st.warning(
            "Advancing the simulation creates a new business day "
            "and generates operational events. This action changes "
            "the persistent simulation database."
        )

        if st.button(
            "Advance Simulation Day",
            type="primary",
            use_container_width=True,
        ):
            try:
                result = advance_day(user)

                st.success(
                    f"Simulation advanced to Day {result['day']}."
                )

                st.json(result)
                st.rerun()

            except Exception as error:
                st.error(f"Could not advance simulation: {error}")

         # -------------------------------------------------
    # INVENTORY PROCUREMENT
    # -------------------------------------------------

    if role in {"CEO", "Inventory Manager"}:
        st.divider()
        st.subheader("Inventory Procurement")

        st.caption(
            "Purchase inventory to replenish products "
            "that are running low."
        )

        # Identify products that need replenishment.
        low_stock_products = [
            product for product in products
            if product["stock"] <= product["reorder_level"]
        ]

        if low_stock_products:

            product_options = {
                (
                    f"{product['product']} | "
                    f"Stock: {product['stock']} | "
                    f"Reorder level: {product['reorder_level']}"
                ): product["product"]
                for product in low_stock_products
            }

            selected_product_label = st.selectbox(
                "Select a product to restock",
                options=list(product_options.keys()),
            )

            selected_product_name = product_options[
                selected_product_label
            ]

            selected_product = next(
                product for product in low_stock_products
                if product["product"] == selected_product_name
            )

            # Calculate the recommended purchase quantity.
            recommended_quantity = max(
                selected_product["reorder_level"] * 2
                - selected_product["stock"],
                selected_product["reorder_level"],
                10,
            )

            estimated_cost = (
                recommended_quantity
                * selected_product["unit_cost"]
            )

            st.write(
                f"**Recommended quantity:** "
                f"{recommended_quantity} units"
            )

            st.write(
                f"**Unit cost:** "
                f"${selected_product['unit_cost']:,.2f}"
            )

            st.write(
                f"**Estimated purchase cost:** "
                f"${estimated_cost:,.2f}"
            )

            st.write(
                f"**Available company cash:** "
                f"${state['cash_balance']:,.2f}"
            )

            if estimated_cost > state["cash_balance"]:
                st.error(
                    "Insufficient company cash for this purchase."
                )

            else:
                if st.button(
                    "Place Restock Order",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        result = record_decision(
                            actor=user,
                            decision_type="reorder_product",
                            value=selected_product_name,
                            rationale=(
                                "Restocking low inventory "
                                "through the Business Simulation."
                            ),
                        )

                        st.success(result["effect_summary"])
                        st.rerun()

                    except Exception as error:
                        st.error(
                            f"Could not place restock order: {error}"
                        )

        else:
            st.success(
                "All products currently have sufficient stock."
            )
     
    # -------------------------------------------------
    # OPERATIONAL TASKS
    # -------------------------------------------------

    st.divider()
    st.subheader("Operational Tasks")

    if tasks:
        task_df = pd.DataFrame(tasks)

        visible_columns = [
            column
            for column in [
                "task_id",
                "department",
                "title",
                "priority",
                "status",
                "description",
            ]
            if column in task_df.columns
        ]

        st.dataframe(
            task_df[visible_columns],
            use_container_width=True,
            hide_index=True,
        )

        pending_tasks = [
            task for task in tasks
            if task["status"] != "Completed"
        ]

        if pending_tasks:
            st.markdown("### Complete a task")

            task_options = {
                f"#{task['task_id']} | {task['title']}": task["task_id"]
                for task in pending_tasks
            }

            selected_task = st.selectbox(
                "Select a task",
                options=list(task_options.keys()),
            )

            rationale = st.text_input(
                "Completion notes (optional)"
            )

            if st.button("Mark task as completed"):
                try:
                    result = record_decision(
                        actor=user,
                        decision_type="complete_task",
                        value=task_options[selected_task],
                        rationale=rationale,
                    )

                    st.success(result["effect_summary"])
                    st.rerun()

                except Exception as error:
                    st.error(f"Could not complete task: {error}")

        else:
            st.success("There are no pending tasks.")

    else:
        st.info(
            "No operational tasks have been generated yet. "
            "The CEO can advance the simulation to generate events."
        )

    # -------------------------------------------------
    # PERFORMANCE HISTORY
    # -------------------------------------------------

    if role == "CEO" and history:
        st.divider()
        st.subheader("Business Performance History")

        history_df = pd.DataFrame(history)

        if "revenue" in history_df.columns:
            fig = px.line(
                history_df,
                x="day",
                y="revenue",
                markers=True,
                title="Daily Revenue",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        if "profit" in history_df.columns:
            fig = px.line(
                history_df,
                x="day",
                y="profit",
                markers=True,
                title="Daily Profit",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

    # -------------------------------------------------
    # DECISION HISTORY
    # -------------------------------------------------

    st.divider()
    st.subheader("Management Decision History")

    if decisions:
        decision_df = pd.DataFrame(decisions)

        preferred_columns = [
            column
            for column in [
                "day",
                "actor_role",
                "department",
                "decision_type",
                "decision_value",
                "rationale",
                "effect_summary",
                "created_at",
            ]
            if column in decision_df.columns
        ]

        st.dataframe(
            decision_df[preferred_columns],
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.info("No management decisions have been recorded yet.")
