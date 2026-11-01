from sim_engine import (
    initialize_simulation,
    get_state,
    get_products,
    get_tasks,
    get_metrics_history,
)

print("\n=== TEST 1: INITIALIZE SIMULATION ===")
initialize_simulation()
print("Initialization completed.")

print("\n=== TEST 2: SIMULATION STATE ===")
print(get_state())

print("\n=== TEST 3: PRODUCTS ===")
products = get_products()
print(f"Products loaded: {len(products)}")
print(products[:3])

print("\n=== TEST 4: TASKS ===")
tasks = get_tasks("CEO")
print(f"Tasks found: {len(tasks)}")
print(tasks[:3])

print("\n=== TEST 5: METRICS HISTORY ===")
history = get_metrics_history()
print(f"History entries: {len(history)}")
print(history[:3])

print("\n=== ALL TESTS COMPLETED ===")