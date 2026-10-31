import pandas as pd
import pytest

from src.disruptions import (
    add_urgent_customer,
    cancel_customer,
    create_disruption,
    get_completed_customers,
    get_remaining_customers,
)


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
        {
            "customer_id": "C003",
            "latitude": 20.03,
            "longitude": 0.03,
            "demand": 2,
            "service_minutes": 15,
            "window_start": 480,
            "window_end": 1080,
        },
    ])


def make_simulation():
    return {
        "service_events": {
            "C001": {
                "customer_id": "C001",
                "arrival": 5,
                "service_end": 15,
                "vehicle_id": "V01",
            },
            "C002": {
                "customer_id": "C002",
                "arrival": 20,
                "service_end": 30,
                "vehicle_id": "V01",
            },
        }
    }


def test_get_completed_customers_returns_only_finished_deliveries():
    simulation = make_simulation()

    completed = get_completed_customers(simulation, 20)

    assert completed == {"C001"}


def test_customer_is_completed_exactly_at_service_end():
    simulation = make_simulation()

    assert get_completed_customers(simulation, 15) == {"C001"}


def test_customer_is_not_completed_before_service_end():
    simulation = make_simulation()

    assert get_completed_customers(simulation, 14) == set()


def test_get_remaining_customers_preserves_uncompleted_deliveries():
    customers = make_customers()
    simulation = make_simulation()

    remaining = get_remaining_customers(
        customers,
        simulation,
        minute=20,
    )

    assert set(remaining["customer_id"]) == {"C002", "C003"}
    assert len(remaining) == 2
    assert len(customers) == 3


def test_get_remaining_customers_handles_no_completed_deliveries():
    customers = make_customers()
    simulation = make_simulation()

    remaining = get_remaining_customers(
        customers,
        simulation,
        minute=0,
    )

    assert set(remaining["customer_id"]) == {
        "C001",
        "C002",
        "C003",
    }


def test_create_disruption_records_expected_fields():
    event = create_disruption(
        disruption_type="Vehicle breakdown",
        description="Vehicle V01 has broken down",
        minute=125,
        vehicle_id="V01",
    )

    assert event["type"] == "Vehicle breakdown"
    assert event["description"] == "Vehicle V01 has broken down"
    assert event["simulation_minute"] == 125.0
    assert event["vehicle_id"] == "V01"
    assert event["customer_id"] is None
    assert event["status"] == "Recorded"
    assert event["event_id"].startswith("EVT-")


def test_create_disruption_records_customer_cancellation():
    event = create_disruption(
        disruption_type="Customer cancellation",
        description="C002 cancelled",
        minute=90,
        customer_id="C002",
    )

    assert event["customer_id"] == "C002"
    assert event["vehicle_id"] is None
    assert event["simulation_minute"] == 90.0


def test_add_urgent_customer_adds_one_valid_customer():
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
    assert 1 <= urgent["demand"] <= 5
    assert 10 <= urgent["service_minutes"] <= 20
    assert urgent["window_start"] == 480
    assert urgent["window_end"] == 1080

    assert abs(urgent["latitude"] - depot["latitude"]) <= 0.08
    assert abs(urgent["longitude"] - depot["longitude"]) <= 0.08


def test_add_urgent_customer_is_reproducible():
    customers = make_customers()
    depot = {"latitude": 20.0, "longitude": 0.0}

    _, first = add_urgent_customer(
        customers, depot, next_number=2, seed=99
    )
    _, second = add_urgent_customer(
        customers, depot, next_number=2, seed=99
    )

    assert first == second


def test_cancel_customer_removes_only_selected_customer():
    customers = make_customers()

    updated = cancel_customer(customers, "C002")

    assert set(updated["customer_id"]) == {"C001", "C003"}
    assert len(updated) == 2
    assert len(customers) == 3


def test_cancel_customer_does_not_change_original_dataframe():
    customers = make_customers()
    original_ids = customers["customer_id"].tolist()

    cancel_customer(customers, "C001")

    assert customers["customer_id"].tolist() == original_ids


def test_cancel_unknown_customer_raises_value_error():
    customers = make_customers()

    with pytest.raises(
        ValueError,
        match="Customer C999 does not exist",
    ):
        cancel_customer(customers, "C999")

def test_cancel_customer_removes_only_selected_customer():
    import pandas as pd

    from src.disruptions import cancel_customer

    customers = pd.DataFrame([
        {"customer_id": "C001", "demand": 3},
        {"customer_id": "C002", "demand": 4},
        {"customer_id": "C003", "demand": 2},
    ])

    result = cancel_customer(customers, "C002")

    assert result["customer_id"].tolist() == ["C001", "C003"]
    assert customers["customer_id"].tolist() == ["C001", "C002", "C003"]

def test_cancel_customer_removes_only_selected_customer():
    import pandas as pd
    from src.disruptions import cancel_customer

    customers = pd.DataFrame([
        {"customer_id": "C001", "demand": 3},
        {"customer_id": "C002", "demand": 4},
        {"customer_id": "C003", "demand": 2},
    ])

    result = cancel_customer(customers, "C002")

    assert result["customer_id"].tolist() == ["C001", "C003"]
    assert customers["customer_id"].tolist() == ["C001", "C002", "C003"]