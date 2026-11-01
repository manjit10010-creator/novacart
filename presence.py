import random
from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

STATUS_ORDER = ["Online", "In a meeting", "Away", "Offline", "On leave"]
LOGGED_IN = {"Online", "In a meeting", "Away"}
STATUS_COLORS = {
    "Online": "#2ca02c",
    "In a meeting": "#1f77b4",
    "Away": "#ff7f0e",
    "Offline": "#9aa0a6",
    "On leave": "#9467bd",
}


def now_ist() -> datetime:
    return datetime.now(IST)


def status_at(emp, when: datetime) -> str:
    """Status of one employee at a given moment (deterministic, so it's stable between refreshes)."""
    day_rng = random.Random(f"{emp['employee_id']}|{when.date()}")
    works_weekend = day_rng.random() < 0.30 and emp["department"] == "Customer Support"
    on_leave = day_rng.random() > emp["reliability"]
    start = emp["shift_start"] + day_rng.uniform(-0.4, 0.6)   # arrives a bit early or late
    end = emp["shift_end"] + day_rng.uniform(-0.5, 0.8)
    lunch_start = start + 3.5 + day_rng.uniform(0, 1.5)

    if when.weekday() >= 5 and not works_weekend:
        return "Offline"
    if on_leave:
        return "On leave"

    hour = when.hour + when.minute / 60
    if not (start <= hour < end):
        return "Offline"
    if lunch_start <= hour < lunch_start + 0.75:
        return "Away"

    block = random.Random(f"{emp['employee_id']}|{when.date()}|{int(hour * 4)}").random()
    if block < 0.07:
        return "Away"          # short break
    if block < 0.22:
        return "In a meeting"
    return "Online"


def hourly_logged_in(employees, day) -> list[dict]:
    """How many people are logged in at half past each hour of a given day."""
    rows = []
    for h in range(24):
        when = datetime.combine(day, time(h, 30), tzinfo=IST)
        statuses = employees.apply(lambda r: status_at(r, when), axis=1)
        rows.append({"hour": h, "logged_in": int(statuses.isin(LOGGED_IN).sum())})
    return rows