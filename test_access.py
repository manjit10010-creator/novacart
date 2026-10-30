from data_access import ACCESS, can_access, columns_for

ROLES = ["CEO", "Finance Manager", "Marketing Manager", "Inventory Manager", "Customer Support Manager"]
DATASETS = ["orders", "marketing", "inventory", "returns", "tickets"]

EXPECTED_ACCESS = {
    "CEO": {"orders", "marketing", "inventory", "returns", "tickets"},
    "Finance Manager": {"orders", "returns"},
    "Marketing Manager": {"orders", "marketing"},
    "Inventory Manager": {"orders", "inventory", "returns"},
    "Customer Support Manager": {"orders", "tickets"},
}
SENSITIVE_ORDER_COLUMNS = {"profit", "total_cost", "cogs", "unit_cost", "shipping_cost", "marketing_cost"}

failures = []

# 1. Dataset access matrix
for role in ROLES:
    for ds in DATASETS:
        allowed = can_access(role, ds)
        if allowed != (ds in EXPECTED_ACCESS[role]):
            failures.append(f"{role} / {ds}: expected {ds in EXPECTED_ACCESS[role]}, got {allowed}")

# 2. Roles other than CEO and Finance must never see cost or profit columns
for role in ROLES:
    cols = columns_for(role, "orders")
    if role not in ("CEO", "Finance Manager") and cols is not None:
        leaked = SENSITIVE_ORDER_COLUMNS & set(cols)
        if role == "Marketing Manager":
            leaked -= {"marketing_cost"}  # not granted either, checked below
        if leaked:
            failures.append(f"{role} can see sensitive order columns: {sorted(leaked)}")
if "marketing_cost" in (columns_for("Marketing Manager", "orders") or []):
    failures.append("Marketing Manager shouldn't see order-level marketing_cost")

# 3. Unknown roles get nothing
for ds in DATASETS:
    if can_access("Intern", ds):
        failures.append(f"Unknown role has access to {ds}")

# 4. columns_for must raise when there is no access
try:
    columns_for("Marketing Manager", "tickets")
    failures.append("columns_for did not raise for a denied dataset")
except PermissionError:
    pass

# Print a readable matrix
print(f"{'Role':<28}" + "".join(f"{d:<11}" for d in DATASETS))
for role in ROLES:
    print(f"{role:<28}" + "".join(f"{'✅' if can_access(role, d) else '❌':<11}" for d in DATASETS))

if failures:
    print("\nFAILED:")
    for item in failures:
        print(" -", item)
    raise SystemExit(1)
print("\nAll access tests passed.")