import pandas as pd
import pytest

from src.metrics import (
    calculate_metrics,
    calculate_remaining_distance_m,
)
from src.solver import haversine_meters


def make_inputs():
    customers = pd.DataFrame([
        {"customer_id": "C1", "demand": 4},
        {"customer_id": "C2", "demand": 3},
    ])
    vehicles = pd.DataFrame([
        {"vehicle_id": "V1", "capacity": 10},
    ])
    solution = {
        "status": "Success",
        "runtime_seconds": 0.5,
        "routes": [
            {
                "vehicle_id": "V1",
                "customer_stops": ["C1"],
                "distance_m": 2000,
            },
        ],
    }
    return solution, customers, vehicles


def test_metrics_for_successful_solution():
    customers = pd.DataFrame([
        {"customer_id": "C001", "demand": 4},
        {"customer_id": "C002", "demand": 6},
        {"customer_id": "C003", "demand": 3},
    ])
    vehicles = pd.DataFrame([
        {"vehicle_id": "V01", "capacity": 10},
        {"vehicle_id": "V02", "capacity": 10},
    ])
    solution = {
        "status": "Success",
        "runtime_seconds": 0.25,
        "routes": [
            {
                "vehicle_id": "V01",
                "customer_stops": ["C001", "C002"],
                "distance_m": 5000,
                "capacity": 10,
            }
        ],
    }

    metrics = calculate_metrics(solution, customers, vehicles)

    assert metrics["total_distance_km"] == pytest.approx(5.0)
    assert metrics["vehicles_used"] == 1
    assert metrics["assigned_customers"] == 2
    assert metrics["unassigned_customers"] == 1
    assert metrics["assignment_rate_percent"] == pytest.approx(200 / 3)
    assert metrics["assigned_demand"] == 10
    assert metrics["fleet_utilization_percent"] == pytest.approx(50.0)


def test_metrics_handle_empty_scenario():
    customers = pd.DataFrame(columns=["customer_id", "demand"])
    vehicles = pd.DataFrame(columns=["vehicle_id", "capacity"])

    metrics = calculate_metrics(
        {"status": "Success", "routes": []},
        customers,
        vehicles,
    )

    assert metrics["total_distance_km"] == 0
    assert metrics["vehicles_used"] == 0
    assert metrics["total_customers"] == 0
    assert metrics["unassigned_customers"] == 0
    assert metrics["assignment_rate_percent"] == 100.0
    assert metrics["fleet_utilization_percent"] == 0.0


def test_remaining_distance_counts_only_untravelled_distance():
    simulation = {
        "schedules": [{
            "vehicle_id": "V01",
            "legs": [{
                "from_lat": 20.0,
                "from_lon": 0.0,
                "to_lat": 20.01,
                "to_lon": 0.0,
                "depart": 0.0,
                "arrive": 10.0,
            }],
        }],
    }

    full_distance = haversine_meters(20.0, 0.0, 20.01, 0.0)
    remaining = calculate_remaining_distance_m(simulation, 5.0)

    assert remaining == pytest.approx(full_distance / 2, rel=0.001)


def test_remaining_distance_is_zero_after_all_legs_finish():
    simulation = {
        "schedules": [{
            "legs": [{
                "depart": 0,
                "arrive": 10,
                "from_lat": 20.0,
                "from_lon": 0.0,
                "to_lat": 20.1,
                "to_lon": 0.1,
            }],
        }],
    }

    assert calculate_remaining_distance_m(simulation, 10) == 0.0


def test_remaining_distance_counts_future_legs():
    simulation = {
        "schedules": [{
            "legs": [{
                "depart": 10,
                "arrive": 20,
                "from_lat": 20.0,
                "from_lon": 0.0,
                "to_lat": 20.1,
                "to_lon": 0.1,
            }],
        }],
    }

    assert calculate_remaining_distance_m(simulation, 5) > 0


def test_remaining_distance_is_zero_for_empty_simulation():
    assert calculate_remaining_distance_m(
        {"schedules": []}, 10
    ) == 0.0


def test_metrics_count_unassigned_customers():
    solution, customers, vehicles = make_inputs()

    metrics = calculate_metrics(solution, customers, vehicles)

    assert metrics["assigned_customers"] == 1
    assert metrics["unassigned_customers"] == 1
    assert metrics["assigned_demand"] == 4


def test_metrics_detect_duplicate_and_invalid_assignments():
    solution, customers, vehicles = make_inputs()
    solution["routes"].append({
        "vehicle_id": "V2",
        "customer_stops": ["C1", "C999"],
        "distance_m": 1000,
    })

    metrics = calculate_metrics(solution, customers, vehicles)

    assert metrics["assigned_customers"] == 1
    assert metrics["unassigned_customers"] == 1
    assert metrics["duplicate_customer_assignments"] == 1
    assert metrics["invalid_customer_assignments"] == 1


def test_metrics_handle_completely_empty_dataframes():
    metrics = calculate_metrics(
        {"status": "Success", "routes": []},
        pd.DataFrame(),
        pd.DataFrame(),
    )

    assert metrics["total_customers"] == 0
    assert metrics["assigned_customers"] == 0
    assert metrics["unassigned_customers"] == 0
    assert metrics["assignment_rate_percent"] == 100.0
    assert metrics["fleet_utilization_percent"] == 0.0
