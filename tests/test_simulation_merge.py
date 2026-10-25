
import pandas as pd
import pytest

from src.simulation import (
    build_simulation,
    merge_reoptimized_simulation,
)


def make_customers():
    return pd.DataFrame({
        "customer_id": ["C001", "C002", "C003", "C004"],
        "demand": [1, 1, 1, 1],
    })


def make_old_simulation():
    return {
        "schedules": [],
        "service_events": {
            "C001": {
                "customer_id": "C001",
                "arrival": 5.0,
                "service_end": 15.0,
                "vehicle_id": "V01",
            },
            "C002": {
                "customer_id": "C002",
                "arrival": 18.0,
                "service_end": 28.0,
                "vehicle_id": "V01",
            },
            "C004": {
                "customer_id": "C004",
                "arrival": 10.0,
                "service_end": 14.0,
                "vehicle_id": "V02",
            },
        },
        "duration_minutes": 28.0,
    }


def make_new_simulation():
    return {
        "schedules": [
            {
                "vehicle_id": "V01",
                "legs": [
                    {"depart": 0.0, "arrive": 5.0},
                ],
                "services": [
                    {
                        "customer_id": "C003",
                        "arrival": 5.0,
                        "service_end": 10.0,
                        "vehicle_id": "V01",
                    }
                ],
                "duration_minutes": 10.0,
            },
            {
                "vehicle_id": "V02",
                "legs": [
                    {"depart": 0.0, "arrive": 8.0},
                ],
                "services": [
                    {
                        "customer_id": "C004",
                        "arrival": 8.0,
                        "service_end": 12.0,
                        "vehicle_id": "V02",
                    }
                ],
                "duration_minutes": 12.0,
            },
        ],
        "service_events": {
            "C003": {
                "customer_id": "C003",
                "arrival": 5.0,
                "service_end": 10.0,
                "vehicle_id": "V01",
            },
            "C004": {
                "customer_id": "C004",
                "arrival": 8.0,
                "service_end": 12.0,
                "vehicle_id": "V02",
            },
        },
        "duration_minutes": 12.0,
        "average_speed_kmh": 35,
    }


def test_merge_preserves_completed_delivery_timestamps():
    old = make_old_simulation()
    new = make_new_simulation()
    original_event = old["service_events"]["C001"].copy()

    result = merge_reoptimized_simulation(
        old, new, make_customers(), current_minute=20
    )

    assert result["service_events"]["C001"] == original_event


def test_merge_preserves_in_progress_delivery():
    old = make_old_simulation()
    new = make_new_simulation()
    original_event = old["service_events"]["C002"].copy()

    result = merge_reoptimized_simulation(
        old, new, make_customers(), current_minute=20
    )

    assert result["service_events"]["C002"] == original_event


def test_merge_shifts_revised_route_to_current_time():
    result = merge_reoptimized_simulation(
        make_old_simulation(),
        make_new_simulation(),
        make_customers(),
        current_minute=20,
    )

    # V02 has no active service, so its route is shifted by 20 minutes.
    schedule = next(
        s for s in result["schedules"]
        if s["vehicle_id"] == "V02"
    )

    assert schedule["legs"][0]["depart"] == pytest.approx(20.0)
    assert schedule["legs"][0]["arrive"] == pytest.approx(28.0)
    assert schedule["services"][0]["arrival"] == pytest.approx(28.0)


def test_active_service_delays_only_its_own_vehicle():
    result = merge_reoptimized_simulation(
        make_old_simulation(),
        make_new_simulation(),
        make_customers(),
        current_minute=20,
    )

    v01 = next(
        s for s in result["schedules"]
        if s["vehicle_id"] == "V01"
    )
    v02 = next(
        s for s in result["schedules"]
        if s["vehicle_id"] == "V02"
    )

    # V01 must finish C002 at minute 28 before starting its revised route.
    assert v01["legs"][0]["depart"] == pytest.approx(28.0)
    assert v01["services"][0]["arrival"] == pytest.approx(33.0)

    # V02 is not held up by V01's active service.
    assert v02["legs"][0]["depart"] == pytest.approx(20.0)


def test_vehicle_delay_is_applied_once_to_selected_vehicle():
    result = merge_reoptimized_simulation(
        make_old_simulation(),
        make_new_simulation(),
        make_customers(),
        current_minute=20,
        disruption_type="Vehicle delay",
        selected_vehicle="V02",
        delay_minutes=7,
    )

    v01 = next(
        s for s in result["schedules"]
        if s["vehicle_id"] == "V01"
    )
    v02 = next(
        s for s in result["schedules"]
        if s["vehicle_id"] == "V02"
    )

    assert v01["legs"][0]["depart"] == pytest.approx(28.0)
    assert v02["legs"][0]["depart"] == pytest.approx(27.0)
    assert v02["legs"][0]["arrive"] == pytest.approx(35.0)


def test_merge_excludes_cancelled_customer_from_protected_history():
    customers = make_customers()
    customers = customers[
        customers["customer_id"] != "C001"
    ].copy()

    result = merge_reoptimized_simulation(
        make_old_simulation(),
        make_new_simulation(),
        customers,
        current_minute=20,
    )

    assert "C001" not in result["service_events"]
    assert "C002" in result["service_events"]
    assert "C003" in result["service_events"]


def test_merge_duration_covers_all_service_events():
    result = merge_reoptimized_simulation(
        make_old_simulation(),
        make_new_simulation(),
        make_customers(),
        current_minute=20,
    )

    assert result["duration_minutes"] >= max(
        event["service_end"]
        for event in result["service_events"].values()
    )

def test_reoptimization_does_not_apply_time_window_twice():
    customers = pd.DataFrame([{
        "customer_id": "C001",
        "latitude": 0.0,
        "longitude": 0.0,
        "demand": 1,
        "service_minutes": 10,
        "window_start": 600,
        "window_end": 900,
    }])

    depot = {
        "depot_id": "DEPOT",
        "latitude": 0.0,
        "longitude": 0.0,
    }

    route = {
        "vehicle_id": "V01",
        "stops": ["DEPOT", "C001"],
        "coordinates": [
            (0.0, 0.0),
            (0.0, 0.0),
        ],
    }

    old_simulation = {
        "schedules": [],
        "service_events": {},
        "duration_minutes": 600.0,
    }

    new_simulation = build_simulation(
        [route],
        customers,
        depot,
        start_time_minutes=600,
    )

    result = merge_reoptimized_simulation(
        old_simulation=old_simulation,
        new_simulation=new_simulation,
        customers=customers,
        current_minute=600,
        schedules_are_absolute=True,
    )

    event = result["service_events"]["C001"]

    assert event["service_start"] == pytest.approx(600.0)
    assert event["service_end"] == pytest.approx(610.0)

def test_merge_does_not_shift_absolute_schedules():
    old_simulation = {
        "schedules": [],
        "service_events": {},
        "duration_minutes": 700,
    }

    schedule = {
        "vehicle_id": "V01",
        "duration_minutes": 720,
        "legs": [],
        "services": [],
    }

    new_simulation = {
        "schedules": [schedule],
        "service_events": {},
        "duration_minutes": 720,
    }

    customers = pd.DataFrame(columns=["customer_id"])

    merged = merge_reoptimized_simulation(
        old_simulation=old_simulation,
        new_simulation=new_simulation,
        customers=customers,
        current_minute=650,
        schedules_are_absolute=True,
    )

    assert merged["schedules"][0]["duration_minutes"] == 720