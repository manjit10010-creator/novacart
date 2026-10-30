import hashlib
import json
import secrets

ITERATIONS = 200_000
ORG_ID = "ORG-1001"

# (user_id, name, email, role, demo password)
DEMO_USERS = [
    ("USR-001", "Aarav Mehta", "ceo@novacart.example", "CEO", "Demo@CEO2026"),
    ("USR-002", "Priya Nair", "marketing@novacart.example", "Marketing Manager", "Demo@Mkt2026"),
    ("USR-003", "Rohan Iyer", "finance@novacart.example", "Finance Manager", "Demo@Fin2026"),
    ("USR-004", "Sneha Rao", "inventory@novacart.example", "Inventory Manager", "Demo@Inv2026"),
]


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


users = []
for user_id, name, email, role, password in DEMO_USERS:
    salt = secrets.token_bytes(16)
    users.append({
        "user_id": user_id,
        "org_id": ORG_ID,
        "name": name,
        "email": email,
        "role": role,
        "salt": salt.hex(),
        "password_hash": hash_password(password, salt),
    })

with open("users.json", "w") as f:
    json.dump(users, f, indent=2)

print(f"Created users.json with {len(users)} demo accounts")