
import pandas as pd

from src.reoptimization import reoptimize_remaining


def make_inputs():
    depot = {
        "depot_id": "DEPOT_0",
        "latitude": 20.0,
        "longitude": 0.0,
    }

    vehicles = pd.DataFrame([
        {
            "vehicle_id": "V01",
            "capacity": 8,
            "available_from": 480,
            "available_until": 1080,
        }
    ])

    customers = pd.DataFrame([
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

    simulation = {
        "schedules": [
            {
                "vehicle_id": "V01",
                "legs": [],
                "services": [],
                "duration_minutes": 30,
            }
        ],
        "service_events": {
            "C001": {
                "customer_id": "C001",
                "arrival": 5,
                "service_end": 15,
                "vehicle_id": "V01",
            }
        },
        "duration_minutes": 30,
        "average_speed_kmh": 35,
    }

    return depot, vehicles, customers, simulation


def test_completed_delivery_reduces_remaining_capacity():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot, vehicles, customers, simulation,
        current_minute=20,
    )

    state = result["vehicle_states"]["V01"]

    assert state["remaining_capacity"] == 4
    assert state["available"] is True


def test_completed_customer_is_not_reassigned():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot, vehicles, customers, simulation,
        current_minute=20,
    )

    remaining_ids = set(
        result["remaining_customers"]["customer_id"]
    )

    assert "C001" not in remaining_ids
    assert "C002" in remaining_ids

    assigned_ids = {
        customer_id
        for route in result["solution"]["routes"]
        for customer_id in route["customer_stops"]
    }

    assert "C001" not in assigned_ids


def test_vehicle_breakdown_excludes_its_capacity():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=20,
        unavailable_vehicles={"V01"},
    )

    state = result["vehicle_states"]["V01"]

    assert state["available"] is False
    assert state["remaining_capacity"] == 0
    assert result["solution"]["status"].startswith("Infeasible")

def test_in_progress_customer_is_not_reassigned():
    depot, vehicles, customers, simulation = make_inputs()

    # C001 is currently being serviced from minute 5 to minute 15.
    result = reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=10,
    )

    remaining_ids = set(
        result["remaining_customers"]["customer_id"]
    )

    assert "C001" not in remaining_ids
    assert "C002" in remaining_ids

    assert "C001" in result["in_service_customers"]

    assigned_ids = {
        customer_id
        for route in result["solution"]["routes"]
        for customer_id in route["customer_stops"]
    }

    assert "C001" not in assigned_ids


def test_in_progress_delivery_reduces_remaining_capacity():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=10,
    )

    # V01 has capacity 8. C001's demand of 4 is committed
    # to the delivery currently in progress.
    assert (
        result["vehicle_states"]["V01"]["remaining_capacity"]
        == 4
    )


def test_in_service_customer_is_not_marked_completed():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=10,
    )

    assert "C001" not in result["completed_customers"]
    assert "C001" in result["in_service_customers"]

def test_customer_is_completed_exactly_at_service_end():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=15,
    )

    assert "C001" in result["completed_customers"]
    assert "C001" not in result["in_service_customers"]
    assert "C001" not in set(
        result["remaining_customers"]["customer_id"]
    )


def test_customer_is_in_service_exactly_at_arrival():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=5,
    )

    assert "C001" in result["in_service_customers"]
    assert "C001" not in result["completed_customers"]
    assert "C001" not in set(
        result["remaining_customers"]["customer_id"]
    )


def test_capacity_is_not_reduced_before_customer_arrival():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=4,
    )

    assert (
        result["vehicle_states"]["V01"]["remaining_capacity"]
        == 8
    )

    assert "C001" not in result["completed_customers"]
    assert "C001" not in result["in_service_customers"]
    assert "C001" in set(
        result["remaining_customers"]["customer_id"]
    )

def test_reoptimization_passes_current_vehicle_position(monkeypatch):
    import src.reoptimization as reoptimization

    depot, vehicles, customers, simulation = make_inputs()

    expected_position = (20.015, 0.015)

    monkeypatch.setattr(
        reoptimization,
        "vehicle_position",
        lambda schedule, minute, depot: expected_position,
    )

    captured = {}

    def fake_solve_cvrp(**kwargs):
        captured.update(kwargs)
        return {"status": "Success", "routes": []}

    monkeypatch.setattr(
        reoptimization,
        "solve_cvrp",
        fake_solve_cvrp,
    )

    result = reoptimization.reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=10,
    )

    state = result["vehicle_states"]["V01"]

    assert state["latitude"] == expected_position[0]
    assert state["longitude"] == expected_position[1]
    assert state["available"] is True
    assert captured["vehicle_states"]["V01"] == state


def test_unavailable_vehicle_is_not_marked_available_to_solver(
    monkeypatch,
):
    import src.reoptimization as reoptimization

    depot, vehicles, customers, simulation = make_inputs()
    captured = {}

    def fake_solve_cvrp(**kwargs):
        captured.update(kwargs)
        return {"status": "Infeasible", "routes": []}

    monkeypatch.setattr(
        reoptimization,
        "solve_cvrp",
        fake_solve_cvrp,
    )

    result = reoptimization.reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=10,
        unavailable_vehicles={"V01"},
    )

    assert result["vehicle_states"]["V01"]["available"] is False
    assert captured["vehicle_states"]["V01"]["available"] is False
    assert captured["vehicle_states"]["V01"]["remaining_capacity"] == 0


def test_reoptimization_passes_only_remaining_customers_to_solver(
    monkeypatch,
):
    import src.reoptimization as reoptimization

    depot, vehicles, customers, simulation = make_inputs()
    captured = {}

    def fake_solve_cvrp(**kwargs):
        captured.update(kwargs)
        return {"status": "Success", "routes": []}

    monkeypatch.setattr(
        reoptimization,
        "solve_cvrp",
        fake_solve_cvrp,
    )

    result = reoptimization.reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=20,
    )

    expected_ids = set(
        result["remaining_customers"]["customer_id"]
    )
    solver_ids = set(captured["customers"]["customer_id"])

    assert solver_ids == expected_ids
    assert "C001" not in solver_ids
    assert "C002" in solver_ids


def test_vehicle_available_time_includes_remaining_service():
    depot, vehicles, customers, simulation = make_inputs()

    result = reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=10,
    )

    state = result["vehicle_states"]["V01"]

    # C001's service ends at minute 15.
    # At minute 10, the vehicle has 5 minutes of service remaining.
    assert state["current_time"] == 15


def test_reoptimization_passes_urgent_customer_id_to_solver(
    monkeypatch,
):
    import src.reoptimization as reoptimization

    depot, vehicles, customers, simulation = make_inputs()
    captured = {}

    def fake_solve_cvrp(**kwargs):
        captured.update(kwargs)
        return {"status": "Success", "routes": []}

    monkeypatch.setattr(
        reoptimization,
        "solve_cvrp",
        fake_solve_cvrp,
    )

    result = reoptimization.reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=20,
        urgent_customer_id="C002",
    )

    assert captured["urgent_customer_id"] == "C002"
    assert "C002" in set(
        result["remaining_customers"]["customer_id"]
    )


def test_reoptimization_passes_no_urgent_customer_by_default(
    monkeypatch,
):
    import src.reoptimization as reoptimization

    depot, vehicles, customers, simulation = make_inputs()
    captured = {}

    def fake_solve_cvrp(**kwargs):
        captured.update(kwargs)
        return {"status": "Success", "routes": []}

    monkeypatch.setattr(
        reoptimization,
        "solve_cvrp",
        fake_solve_cvrp,
    )

    reoptimization.reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=20,
    )

    assert captured["urgent_customer_id"] is None

def test_cancelled_customer_is_not_passed_to_solver(monkeypatch):
    import src.reoptimization as reoptimization

    depot, vehicles, customers, simulation = make_inputs()
    customers = customers[
        customers["customer_id"] != "C002"
    ].copy()

    captured = {}

    def fake_solve_cvrp(**kwargs):
        captured.update(kwargs)
        return {"status": "Success", "routes": []}

    monkeypatch.setattr(
        reoptimization,
        "solve_cvrp",
        fake_solve_cvrp,
    )

    result = reoptimization.reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=20,
    )

    assert "C002" not in set(
        result["remaining_customers"]["customer_id"]
    )
    assert "C002" not in set(
        captured["customers"]["customer_id"]
    )

def test_cancelled_customer_is_not_passed_to_solver(monkeypatch):
    import src.reoptimization as reoptimization

    depot, vehicles, customers, simulation = make_inputs()
    customers = customers[
        customers["customer_id"] != "C002"
    ].copy()

    captured = {}

    def fake_solve_cvrp(**kwargs):
        captured.update(kwargs)
        return {"status": "Success", "routes": []}

    monkeypatch.setattr(
        reoptimization,
        "solve_cvrp",
        fake_solve_cvrp,
    )

    result = reoptimization.reoptimize_remaining(
        depot,
        vehicles,
        customers,
        simulation,
        current_minute=20,
    )

    assert "C002" not in set(
        result["remaining_customers"]["customer_id"]
    )
    assert "C002" not in set(
        captured["customers"]["customer_id"]
    )