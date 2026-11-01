import json
import random
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

SEED = 2026
random.seed(SEED)
Faker.seed(SEED)
fake = Faker("en_IN")

DAY, EARLY, LATE = (9, 18), (6, 15), (14, 23)

DEPARTMENTS = {
    "Marketing": {
        "size": 28, "head_title": "Head of Marketing", "head_email": "marketing@novacart.example",
        "teams": [("Performance Ads", DAY), ("Content & SEO", DAY), ("Email & CRM", DAY), ("Social Media", DAY)],
        "titles": ["Marketing Executive", "Content Writer", "SEO Specialist", "Campaign Analyst", "Graphic Designer"],
    },
    "Finance": {
        "size": 18, "head_title": "Head of Finance", "head_email": "finance@novacart.example",
        "teams": [("Accounting", DAY), ("Payments & Reconciliation", DAY)],
        "titles": ["Accountant", "Financial Analyst", "Accounts Executive", "Payments Specialist"],
    },
    "Inventory & Warehouse": {
        "size": 40, "head_title": "Head of Inventory & Warehouse", "head_email": "inventory@novacart.example",
        "teams": [("Receiving & Stock", DAY), ("Picking & Packing (Early)", EARLY),
                  ("Picking & Packing (Late)", LATE), ("Dispatch", DAY)],
        "titles": ["Warehouse Associate", "Stock Controller", "Packer", "Forklift Operator", "Dispatch Coordinator"],
    },
    "Customer Support": {
        "size": 56, "head_title": "Head of Customer Support", "head_email": "support@novacart.example",
        "teams": [("Chat Support (Early)", EARLY), ("Chat Support (Late)", LATE), ("Phone Support", DAY),
                  ("Email & Social Support", DAY), ("Escalations", DAY)],
        "titles": ["Support Agent", "Senior Support Agent", "Customer Care Executive", "Escalation Specialist"],
    },
    "E-commerce Operations": {
        "size": 24, "head_title": "Head of E-commerce Operations", "head_email": None,
        "teams": [("Order Management", DAY), ("Catalog & Pricing", DAY), ("Merchant Operations", DAY)],
        "titles": ["Operations Executive", "Catalog Specialist", "Pricing Analyst", "Order Coordinator"],
    },
    "Product & Analytics": {
        "size": 14, "head_title": "Head of Product & Analytics", "head_email": None,
        "teams": [("Product", DAY), ("Data & Analytics", DAY)],
        "titles": ["Product Analyst", "Data Analyst", "UX Researcher", "Business Analyst"],
    },
    "IT & Engineering": {
        "size": 12, "head_title": "Head of Engineering", "head_email": None,
        "teams": [("Platform", DAY), ("Security & DevOps", DAY)],
        "titles": ["Software Engineer", "DevOps Engineer", "QA Engineer", "Systems Administrator"],
    },
    "HR & Admin": {
        "size": 7, "head_title": "Head of People & Admin", "head_email": None,
        "teams": [("People Operations", DAY)],
        "titles": ["HR Executive", "Recruiter", "Admin Coordinator", "Payroll Executive"],
    },
}

users_file = Path("users.json")
users_by_email = (
    {u["email"]: u for u in json.loads(users_file.read_text())} if users_file.exists() else {}
)

employees: list[dict] = []
used_emails: set[str] = set()
linked = 0


def unique_email(first: str, last: str) -> str:
    base = re.sub(r"[^a-z]", "", first.lower()) + "." + re.sub(r"[^a-z]", "", last.lower())
    email, n = f"{base}@novacart.example", 1
    while email in used_emails:
        n += 1
        email = f"{base}{n}@novacart.example"
    return email


def add_person(dept, team, title, level, manager_id, shift, email=None):
    global linked
    emp_id = f"EMP-{len(employees) + 1:04d}"
    user = users_by_email.get(email) if email else None
    if user:
        name, mail, user_id = user["name"], user["email"], user["user_id"]
        linked += 1
    else:
        first, last = fake.first_name(), fake.last_name()
        name, mail, user_id = f"{first} {last}", unique_email(first, last), None
    used_emails.add(mail)
    hire = date(2019, 1, 1) + timedelta(days=random.randint(0, (date(2026, 9, 30) - date(2019, 1, 1)).days))
    mode = "On-site" if dept == "Inventory & Warehouse" else random.choices(
        ["Office", "Hybrid", "Remote"], [0.4, 0.4, 0.2])[0]
    employees.append({
        "employee_id": emp_id, "name": name, "email": mail, "user_id": user_id,
        "department": dept, "team": team, "title": title, "level": level,
        "manager_id": manager_id, "hire_date": hire.isoformat(),
        "shift_start": float(shift[0]), "shift_end": float(shift[1]),
        "work_mode": mode, "reliability": round(random.uniform(0.88, 0.99), 3),
    })
    return emp_id


ceo_id = add_person("Executive", "Leadership", "CEO", "CEO", None, DAY, email="ceo@novacart.example")

for dept, cfg in DEPARTMENTS.items():
    head_id = add_person(dept, "Leadership", cfg["head_title"], "Department Head", ceo_id, DAY,
                         email=cfg["head_email"])
    remaining = cfg["size"] - 1
    base, extra = divmod(remaining, len(cfg["teams"]))
    for i, (team, shift) in enumerate(cfg["teams"]):
        size = base + (1 if i < extra else 0)
        mgr_id = add_person(dept, team, f"Team Lead, {team}", "Team Manager", head_id, shift)
        for _ in range(size - 1):
            add_person(dept, team, random.choice(cfg["titles"]), "Employee", mgr_id, shift)

df = pd.DataFrame(employees)
assert len(df) == 200, f"Expected 200 employees, got {len(df)}"

with sqlite3.connect("company.db") as con:
    df.to_sql("employees", con, if_exists="replace", index=False)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_emp_id ON employees(employee_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_emp_dept ON employees(department)")

print(f"company.db created with {len(df)} employees ({linked} linked to demo login accounts)\n")
print(df.groupby("department").size().sort_values(ascending=False).to_string())
print("\n" + df["level"].value_counts().to_string())