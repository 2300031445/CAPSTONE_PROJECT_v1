
import numpy as np
import pandas as pd


def generate_scenario(
    num_vehicles: int = 4,
    num_customers: int = 20,
    seed: int = 42,
):
    """Generate a reproducible synthetic fleet-routing scenario."""

    rng = np.random.default_rng(seed)

    # Synthetic coordinates for visualisation only.
    # These are not real customer addresses.
    depot_lat = 20.0
    depot_lon = 0.0

    depot = {
        "depot_id": "DEPOT_0",
        "name": "Central Depot",
        "latitude": depot_lat,
        "longitude": depot_lon,
    }

    vehicle_rows = []

    for i in range(num_vehicles):
        vehicle_rows.append({
            "vehicle_id": f"V{i + 1:02d}",
            "capacity": int(rng.integers(60, 101)),
            "available_from": 8 * 60,
            "available_until": 18 * 60,
        })

    vehicles = pd.DataFrame(vehicle_rows)

    customer_rows = []

    for i in range(num_customers):
        window_start = int(rng.integers(8 * 60, 15 * 60))

        customer_rows.append({
            "customer_id": f"C{i + 1:03d}",
            "latitude": depot_lat + float(rng.uniform(-0.15, 0.15)),
            "longitude": depot_lon + float(rng.uniform(-0.15, 0.15)),
            "demand": int(rng.integers(1, 9)),
            "service_minutes": int(rng.integers(10, 31)),
            "window_start": window_start,
            "window_end": min(window_start + 180, 18 * 60),
        })

    customers = pd.DataFrame(customer_rows)

    return depot, vehicles, customers
