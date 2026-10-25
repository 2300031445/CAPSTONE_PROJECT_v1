
import pandas as pd

from src.disruptions import add_urgent_customer, cancel_customer


def make_customers():
    return pd.DataFrame([
        {
            "customer_id": "C001",
            "latitude": 20.01,
            "longitude": 0.01,
            "demand": 4,
            "service_minutes": 10,
            "window_start": 480,
            "window_end": 1080,
        },
        {
            "customer_id": "C002",
            "latitude": 20.02,
            "longitude": 0.02,
            "demand": 3,
            "service_minutes": 10,
            "window_start": 480,
            "window_end": 1080,
        },
    ])


def test_urgent_delivery_adds_new_customer():
    customers = make_customers()
    depot = {"latitude": 20.0, "longitude": 0.0}

    updated, urgent = add_urgent_customer(
        customers,
        depot,
        next_number=1,
    )

    assert len(updated) == len(customers) + 1
    assert urgent["customer_id"] == "URGENT_001"
    assert urgent["customer_id"] in set(updated["customer_id"])


def test_urgent_delivery_does_not_modify_existing_customers():
    customers = make_customers()
    original = customers.copy(deep=True)
    depot = {"latitude": 20.0, "longitude": 0.0}

    add_urgent_customer(customers, depot, next_number=1)

    pd.testing.assert_frame_equal(customers, original)


def test_sequential_urgent_deliveries_have_unique_ids():
    customers = make_customers()
    depot = {"latitude": 20.0, "longitude": 0.0}

    updated, first = add_urgent_customer(
        customers, depot, next_number=1
    )
    updated, second = add_urgent_customer(
        updated, depot, next_number=2
    )

    assert first["customer_id"] != second["customer_id"]
    assert updated["customer_id"].is_unique
    assert len(updated) == len(customers) + 2


def test_cancelling_customer_does_not_remove_urgent_delivery():
    customers = make_customers()
    depot = {"latitude": 20.0, "longitude": 0.0}

    updated, urgent = add_urgent_customer(
        customers, depot, next_number=1
    )
    updated = cancel_customer(updated, "C001")

    assert urgent["customer_id"] in set(updated["customer_id"])
    assert "C001" not in set(updated["customer_id"])


def test_urgent_delivery_skips_existing_urgent_id():
    customers = make_customers()
    customers.loc[len(customers)] = {
        "customer_id": "URGENT_001",
        "latitude": 20.04,
        "longitude": 0.04,
        "demand": 2,
        "service_minutes": 10,
        "window_start": 480,
        "window_end": 1080,
    }
    depot = {"latitude": 20.0, "longitude": 0.0}

    updated, urgent = add_urgent_customer(
        customers,
        depot,
        next_number=1,
    )

    assert urgent["customer_id"] == "URGENT_002"
    assert updated["customer_id"].is_unique


def test_urgent_delivery_skips_multiple_existing_ids():
    customers = make_customers()
    for customer_id in ["URGENT_001", "URGENT_002"]:
        customers.loc[len(customers)] = {
            "customer_id": customer_id,
            "latitude": 20.04,
            "longitude": 0.04,
            "demand": 2,
            "service_minutes": 10,
            "window_start": 480,
            "window_end": 1080,
        }

    depot = {"latitude": 20.0, "longitude": 0.0}
    updated, urgent = add_urgent_customer(
        customers,
        depot,
        next_number=1,
    )

    assert urgent["customer_id"] == "URGENT_003"
    assert updated["customer_id"].is_unique
