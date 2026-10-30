import numpy as np
import pandas as pd
from faker import Faker

rng = np.random.default_rng(42)
fake = Faker()
Faker.seed(42)

N_ORDERS = 50_000
N_CUSTOMERS = 8_000

# ---------- Products (with unit cost) ----------
products = pd.DataFrame({
    "product": [f"Product {i:03d}" for i in range(60)],
    "category": rng.choice(["Home", "Electronics", "Fashion", "Beauty", "Sports"], 60),
    "price": rng.lognormal(3.2, 0.6, 60).round(2),
})

# unit cost as a share of price, by category (assumptions)
cost_factor = {"Home": 0.65, "Electronics": 0.80, "Fashion": 0.50, "Beauty": 0.40, "Sports": 0.60}
products["unit_cost"] = (
    products["price"] * products["category"].map(cost_factor) * rng.normal(1, 0.08, 60)
).round(2)

# a few loss-making products so the dashboard has something to flag
loss_idx = rng.choice(60, 4, replace=False)
products.loc[loss_idx, "unit_cost"] = (
    products.loc[loss_idx, "price"] * rng.uniform(1.02, 1.15, 4)
).round(2)

# ---------- Customers ----------
customers = pd.DataFrame({
    "customer_id": range(1, N_CUSTOMERS + 1),
    "country": rng.choice(
        ["India", "USA", "UK", "Germany", "UAE"], N_CUSTOMERS,
        p=[0.4, 0.25, 0.15, 0.1, 0.1],
    ),
})

# ---------- Orders ----------
dates = pd.date_range("2025-01-01", "2026-09-30")
weights = np.linspace(1, 1.8, len(dates)) * np.where(dates.month >= 10, 1.5, 1.0)
weights /= weights.sum()

orders = pd.DataFrame({
    "order_id": range(100_000, 100_000 + N_ORDERS),
    "order_date": rng.choice(dates, N_ORDERS, p=weights),
    "customer_id": rng.integers(1, N_CUSTOMERS + 1, N_ORDERS),
    "product": rng.choice(products["product"], N_ORDERS, p=rng.dirichlet(np.ones(60) * 0.5)),
    "quantity": rng.choice([1, 2, 3, 4], N_ORDERS, p=[0.6, 0.25, 0.1, 0.05]),
    "channel": rng.choice(["Organic", "Ads", "Email", "Social"], N_ORDERS, p=[0.4, 0.3, 0.2, 0.1]),
})

df = orders.merge(products, on="product").merge(customers, on="customer_id")

# ---------- Revenue and costs ----------
shipping_base = {"India": 2.5, "USA": 7.0, "UK": 6.0, "Germany": 6.5, "UAE": 5.0}
marketing_per_order = {"Organic": 0.0, "Ads": 6.0, "Email": 1.0, "Social": 3.5}

df["revenue"] = (df["price"] * df["quantity"]).round(2)
df["cogs"] = (df["unit_cost"] * df["quantity"]).round(2)
df["shipping_cost"] = (df["country"].map(shipping_base) + 0.5 * (df["quantity"] - 1)).round(2)
df["marketing_cost"] = df["channel"].map(marketing_per_order)
df["total_cost"] = (df["cogs"] + df["shipping_cost"] + df["marketing_cost"]).round(2)
df["profit"] = (df["revenue"] - df["total_cost"]).round(2)

df = df.sort_values("order_date").reset_index(drop=True)
df.to_csv("orders.csv", index=False)
print(df.head(), f"\n{len(df)} rows saved to orders.csv")
print(f"Overall margin: {df['profit'].sum() / df['revenue'].sum() * 100:.1f}%")