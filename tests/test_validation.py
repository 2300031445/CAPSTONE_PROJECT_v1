
import pandas as pd

from src.validation import (
    validate_time_windows,
    validate_vehicle_shifts,
)

def make_customers():
    return pd.DataFrame([
        {
            "customer_id": "C001",
            "window_start": 10,
            "window_end": 30,
        },
        {
            "customer_id": "C002",
            "window_start": 10,
            "window_end": 30,
        },
        {
            "customer_id": "C003",
            "window_start": 10,
            "window_end": 30,
        },
        {
            "customer_id": "C004",
            "window_start": 10,
            "window_end": 30,
        },
    ])


def make_simulation():
    return {
        "service_events": {
            "C001": {"arrival": 20},
            "C002": {"arrival": 5},
            "C003": {"arrival": 35},
        }
    }


def test_time_window_validator_identifies_early_arrival():
    result = validate_time_windows(make_simulation(), make_customers())

    early = next(
        item for item in result
        if item["customer_id"] == "C002"
    )

    assert early["status"] == "Early"
    assert early["minutes_outside_window"] == 5


def test_time_window_validator_identifies_late_arrival():
    result = validate_time_windows(make_simulation(), make_customers())

    late = next(
        item for item in result
        if item["customer_id"] == "C003"
    )

    assert late["status"] == "Late"
    assert late["minutes_outside_window"] == 5


def test_time_window_validator_accepts_arrival_inside_window():
    result = validate_time_windows(make_simulation(), make_customers())

    assert not any(
        item["customer_id"] == "C001"
        for item in result
    )


def test_time_window_validator_reports_unscheduled_customer():
    result = validate_time_windows(make_simulation(), make_customers())

    unscheduled = next(
        item for item in result
        if item["customer_id"] == "C004"
    )

    assert unscheduled["status"] == "Unscheduled"
    assert unscheduled["service_start"] is None


def test_time_window_validator_accepts_window_boundaries():
    customers = pd.DataFrame([
        {"customer_id": "C001", "window_start": 10, "window_end": 30},
        {"customer_id": "C002", "window_start": 10, "window_end": 30},
    ])
    simulation = {
        "service_events": {
            "C001": {"arrival": 10},
            "C002": {"arrival": 30},
        }
    }

    assert validate_time_windows(simulation, customers) == []


def test_vehicle_shift_validator_accepts_route_ending_on_time():
    simulation = {
        "schedules": [
            {
                "vehicle_id": "V1",
                "duration_minutes": 600,
            }
        ]
    }
    vehicles = pd.DataFrame([
        {"vehicle_id": "V1", "available_until": 600}
    ])

    assert validate_vehicle_shifts(simulation, vehicles) == []


def test_vehicle_shift_validator_reports_late_route():
    simulation = {
        "schedules": [
            {
                "vehicle_id": "V1",
                "duration_minutes": 630,
            }
        ]
    }
    vehicles = pd.DataFrame([
        {"vehicle_id": "V1", "available_until": 600}
    ])

    violations = validate_vehicle_shifts(simulation, vehicles)

    assert violations == [
        {
            "vehicle_id": "V1",
            "route_end": 630.0,
            "shift_end": 600.0,
            "status": "Late",
            "minutes_over_shift": 30.0,
        }
    ]


def test_vehicle_shift_validator_handles_empty_schedules():
    simulation = {"schedules": []}
    vehicles = pd.DataFrame([
        {"vehicle_id": "V1", "available_until": 600}
    ])

    assert validate_vehicle_shifts(simulation, vehicles) == []


def test_time_window_validator_uses_service_start_when_available():
    customers = pd.DataFrame([
        {
            "customer_id": "C001",
            "window_start": 10,
            "window_end": 30,
        }
    ])
    simulation = {
        "service_events": {
            "C001": {
                "arrival": 5,
                "service_start": 12,
                "service_end": 17,
            }
        }
    }

    assert validate_time_windows(simulation, customers) == []


def test_time_window_validator_does_not_flag_service_ending_after_window():
    customers = pd.DataFrame([
        {
            "customer_id": "C001",
            "window_start": 10,
            "window_end": 30,
        }
    ])
    simulation = {
        "service_events": {
            "C001": {
                "arrival": 25,
                "service_start": 25,
                "service_end": 35,
            }
        }
    }

    assert validate_time_windows(simulation, customers) == []
