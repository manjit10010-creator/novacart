import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
orders = pd.read_csv("orders.csv", parse_dates=["order_date"])

# ---------- 1. Marketing: daily traffic and spend by channel ----------
daily = (
    orders.groupby(["order_date", "channel"])
    .agg(orders=("order_id", "nunique"), revenue=("revenue", "sum"),
         ad_spend=("marketing_cost", "sum"))
    .reset_index()
)

conv_rate = {"Organic": 0.030, "Ads": 0.020, "Email": 0.050, "Social": 0.015}
ctr = {"Organic": 0.040, "Ads": 0.020, "Email": 0.080, "Social": 0.010}

noise = rng.normal(1, 0.10, len(daily))
daily["visits"] = (daily["orders"] / daily["channel"].map(conv_rate) * noise).round().astype(int)
daily["impressions"] = (daily["visits"] / daily["channel"].map(ctr)).round().astype(int)
daily["clicks"] = daily["visits"]
daily.to_csv("marketing_daily.csv", index=False)

# ---------- 2. Inventory: current stock per product ----------
max_date = orders["order_date"].max()
last30 = orders[orders["order_date"] > max_date - pd.Timedelta(days=30)]
sold = last30.groupby("product")["quantity"].sum()

inv = orders.drop_duplicates("product")[["product", "category", "unit_cost"]].copy()
inv["units_sold_30d"] = inv["product"].map(sold).fillna(0).astype(int)
daily_rate = inv["units_sold_30d"] / 30
inv["stock"] = (daily_rate * rng.uniform(2, 60, len(inv))).round().astype(int)
inv["reorder_level"] = (daily_rate * 14).round().astype(int)  # 2 weeks of cover
inv["days_of_stock"] = (inv["stock"] / daily_rate.replace(0, np.nan)).round(1)
inv.to_csv("inventory.csv", index=False)

# ---------- 3. Returns ----------
return_prob = {"Fashion": 0.12, "Electronics": 0.08, "Home": 0.05, "Beauty": 0.04, "Sports": 0.05}
is_return = rng.random(len(orders)) < orders["category"].map(return_prob)
returns = orders[is_return][["order_id", "order_date", "product", "category", "country", "revenue"]].copy()
returns["return_date"] = returns["order_date"] + pd.to_timedelta(rng.integers(3, 22, len(returns)), unit="D")
returns["reason"] = rng.choice(
    ["Wrong size/fit", "Defective", "Not as described", "Changed mind", "Late delivery"],
    len(returns), p=[0.3, 0.2, 0.2, 0.2, 0.1],
)
returns = returns.rename(columns={"revenue": "refund_amount"})
returns.to_csv("returns.csv", index=False)

print(f"marketing_daily.csv: {len(daily):,} rows")
print(f"inventory.csv: {len(inv)} products, {(inv['stock'] <= inv['reorder_level']).sum()} at or below reorder level")
print(f"returns.csv: {len(returns):,} returns ({len(returns) / len(orders) * 100:.1f}% of orders)")