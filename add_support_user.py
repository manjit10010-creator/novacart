from auth import register_user

ok, msg = register_user(
    "Meera Joshi", "support@novacart.example",
    "Demo@Sup2026", "Demo@Sup2026", "Customer Support Manager",
)
print(msg)