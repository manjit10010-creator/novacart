import numpy as np
import pandas as pd

rng = np.random.default_rng(11)
orders = pd.read_csv("orders.csv", parse_dates=["order_date"])
max_date = orders["order_date"].max()

# About 14% of orders lead to a support ticket
n = int(len(orders) * 0.14)
t = orders.sample(n, random_state=11).reset_index(drop=True)
t = t[["order_id", "customer_id", "country", "category", "order_date"]]

created = t["order_date"] + pd.to_timedelta(rng.integers(0, 11, n), unit="D")
t["created_date"] = created.where(created <= max_date, max_date)

# ---------- Issue type depends on the product category ----------
issue_types = ["Order status", "Late delivery", "Refund request", "Return request",
               "Product defect", "Payment issue", "Other"]
issue_probs = {
    "Electronics": [0.15, 0.20, 0.10, 0.10, 0.28, 0.10, 0.07],
    "Fashion":     [0.15, 0.20, 0.12, 0.30, 0.05, 0.08, 0.10],
    "Home":        [0.18, 0.25, 0.10, 0.12, 0.15, 0.10, 0.10],
    "Beauty":      [0.20, 0.22, 0.12, 0.15, 0.12, 0.09, 0.10],
    "Sports":      [0.18, 0.22, 0.12, 0.15, 0.13, 0.10, 0.10],
}
t["issue_type"] = [rng.choice(issue_types, p=issue_probs[c]) for c in t["category"]]

# A late-delivery problem in the UK and Germany over the last 30 days, so alerts have a story
recent = t["created_date"] > max_date - pd.Timedelta(days=30)
spike = recent & t["country"].isin(["UK", "Germany"]) & (rng.random(n) < 0.35)
t.loc[spike, "issue_type"] = "Late delivery"

# ---------- Channel, priority, agent ----------
t["channel"] = rng.choice(["Email", "Chat", "Phone", "Social"], n, p=[0.40, 0.35, 0.15, 0.10])
t["priority"] = rng.choice(["Low", "Medium", "High", "Urgent"], n, p=[0.30, 0.50, 0.15, 0.05])
t["agent"] = rng.choice(["Meera", "Karan", "Ananya", "Vikram", "Divya", "Arjun"], n)

# ---------- Response and resolution times (hours) ----------
frt_median = {"Chat": 0.15, "Phone": 0.05, "Email": 4.0, "Social": 2.5}
frt = t["channel"].map(frt_median) * rng.lognormal(0, 0.7, n)

res_base = {"Order status": 2, "Late delivery": 30, "Refund request": 24, "Return request": 36,
            "Product defect": 48, "Payment issue": 20, "Other": 12}
res = t["issue_type"].map(res_base) * rng.lognormal(0, 0.5, n) + frt
res = np.where(spike, res * 1.4, res)  # the late-delivery problem also slows resolution

# ---------- Status ----------
age_days = (max_date - t["created_date"]).dt.days
open_p = np.where(age_days <= 3, 0.35, np.where(age_days <= 14, 0.06, 0.01))
r = rng.random(n)
t["status"] = np.where(r < open_p, "Open", np.where(r < open_p + 0.05, "Escalated", "Resolved"))
resolved = t["status"] == "Resolved"

# ---------- Customer satisfaction (only some resolved tickets get a rating) ----------
score = np.clip(np.round(4.6 - 0.012 * res - 0.4 * (frt > 8) + rng.normal(0, 0.8, n)), 1, 5)
t["csat"] = np.where(resolved & (rng.random(n) < 0.55), score, np.nan)

t["first_response_hours"] = frt.round(2)
t["resolution_hours"] = np.where(resolved, res, np.nan).round(1)

# ---------- Repeat contact: same customer wrote again within 14 days ----------
t = t.sort_values("created_date").reset_index(drop=True)
prev = t.groupby("customer_id")["created_date"].shift(1)
t["repeat_contact"] = ((t["created_date"] - prev).dt.days <= 14).fillna(False)

t["ticket_id"] = [f"TCK-{50000 + i}" for i in range(len(t))]
cols = ["ticket_id", "created_date", "order_id", "customer_id", "country", "category",
        "issue_type", "channel", "priority", "agent", "status",
        "first_response_hours", "resolution_hours", "csat", "repeat_contact"]
t[cols].to_csv("tickets.csv", index=False)

print(f"tickets.csv: {len(t):,} tickets")
print(f"Avg first response: {t['first_response_hours'].mean():.1f} h | "
      f"avg resolution: {t['resolution_hours'].mean():.1f} h | avg CSAT: {t['csat'].mean():.2f}")
print(t["status"].value_counts().to_string())