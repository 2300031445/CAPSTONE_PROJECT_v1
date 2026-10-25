from datetime import datetime

import numpy as np
import pandas as pd


def get_completed_customers(simulation, minute):
    """Return customers whose service finished by the current time."""
    return {
        customer_id
        for customer_id, event in simulation["service_events"].items()
        if minute >= event["service_end"]
    }


def get_remaining_customers(customers, simulation, minute):
    """Return deliveries that have not been completed."""
    completed = get_completed_customers(simulation, minute)

    return customers[
        ~customers["customer_id"].isin(completed)
    ].copy()


def create_disruption(
    disruption_type,
    description,
    minute,
    vehicle_id=None,
    customer_id=None,
):
    """Create a consistent, timestamped simulation event."""
    return {
        "event_id": f"EVT-{datetime.now().strftime('%H%M%S%f')}",
        "type": disruption_type,
        "description": description,
        "simulation_minute": float(minute),
        "vehicle_id": vehicle_id,
        "customer_id": customer_id,
        "status": "Recorded",
    }

def add_urgent_customer(customers, depot, next_number, seed=99):
    """Create a reproducible urgent delivery with a unique customer ID."""
    rng = np.random.default_rng(seed + next_number)

    existing_ids = set(customers["customer_id"].astype(str))

    # Skip IDs that already exist in the scenario.
    candidate_number = next_number
    while f"URGENT_{candidate_number:03d}" in existing_ids:
        candidate_number += 1

    new_customer = {
        "customer_id": f"URGENT_{candidate_number:03d}",
        "latitude": float(
            depot["latitude"] + rng.uniform(-0.08, 0.08)
        ),
        "longitude": float(
            depot["longitude"] + rng.uniform(-0.08, 0.08)
        ),
        "demand": int(rng.integers(1, 6)),
        "service_minutes": int(rng.integers(10, 21)),
        "window_start": 8 * 60,
        "window_end": 18 * 60,
    }

    updated_customers = pd.concat(
        [customers, pd.DataFrame([new_customer])],
        ignore_index=True,
    )

    return updated_customers, new_customer


def cancel_customer(customers, customer_id):
    """Remove a customer from the outstanding customer table."""
    if customer_id not in set(customers["customer_id"]):
        raise ValueError(f"Customer {customer_id} does not exist.")

    return customers[
        customers["customer_id"] != customer_id
    ].copy()
