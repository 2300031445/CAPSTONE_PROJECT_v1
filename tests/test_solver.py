
import pandas as pd

from src.solver import solve_cvrp


def make_scenario(vehicle_capacity=20, demands=(3, 4)):
    depot = {
        "depot_id": "DEPOT_0",
        "latitude": 20.0,
        "longitude": 0.0,
    }

    vehicles = pd.DataFrame([
        {
            "vehicle_id": "V01",
            "capacity": vehicle_capacity,
            "available_from": 480,
            "available_until": 1080,
        }
    ])

    customers = pd.DataFrame([
        {
            "customer_id": f"C{i + 1:03d}",
            "latitude": 20.01 + i * 0.01,
            "longitude": 0.01 + i * 0.01,
            "demand": demand,
            "service_minutes": 10,
            "window_start": 480,
            "window_end": 1080,
        }
        for i, demand in enumerate(demands)
    ])

    return depot, vehicles, customers


def test_solver_assigns_every_customer():
    depot, vehicles, customers = make_scenario()

    result = solve_cvrp(
        depot, vehicles, customers, time_limit_seconds=2
    )

    assert result["status"] == "Success"

    assigned = [
        customer_id
        for route in result["routes"]
        for customer_id in route["customer_stops"]
    ]

    assert sorted(assigned) == sorted(customers["customer_id"].tolist())


def test_route_load_does_not_exceed_capacity():
    depot, vehicles, customers = make_scenario(
        vehicle_capacity=10,
        demands=(3, 4, 2),
    )

    result = solve_cvrp(
        depot, vehicles, customers, time_limit_seconds=2
    )

    assert result["status"] == "Success"

    for route in result["routes"]:
        assert route["load"] <= route["capacity"]


def test_insufficient_capacity_is_infeasible():
    depot, vehicles, customers = make_scenario(
        vehicle_capacity=5,
        demands=(4, 4),
    )

    result = solve_cvrp(
        depot, vehicles, customers, time_limit_seconds=2
    )

    assert result["status"].startswith("Infeasible")


def test_zero_vehicles_returns_cleanly():
    depot, vehicles, customers = make_scenario()
    vehicles = vehicles.iloc[0:0].copy()

    result = solve_cvrp(
        depot, vehicles, customers, time_limit_seconds=2
    )

    assert result["status"] == "No vehicles"
    assert result["routes"] == []


def test_solver_respects_customer_time_window():
    import pandas as pd

    from src.solver import solve_cvrp

    depot = {
        "depot_id": "DEPOT_0",
        "latitude": 20.0,
        "longitude": 0.0,
    }

    vehicles = pd.DataFrame([{
        "vehicle_id": "V01",
        "capacity": 10,
        "available_from": 480,
        "available_until": 1080,
    }])

    customers = pd.DataFrame([{
        "customer_id": "C001",
        "latitude": 20.01,
        "longitude": 0.01,
        "demand": 1,
        "service_minutes": 10,
        "window_start": 600,
        "window_end": 720,
    }])

    result = solve_cvrp(
        depot,
        vehicles,
        customers,
        time_limit_seconds=2,
    )

    assert result["status"] == "Success"
    assert any(
        "C001" in route["stops"]
        for route in result["routes"]
    )


def test_solver_rejects_customer_window_after_vehicle_shift():
    import pandas as pd

    from src.solver import solve_cvrp

    depot = {
        "depot_id": "DEPOT_0",
        "latitude": 20.0,
        "longitude": 0.0,
    }

    vehicles = pd.DataFrame([{
        "vehicle_id": "V01",
        "capacity": 10,
        "available_from": 480,
        "available_until": 600,
    }])

    customers = pd.DataFrame([{
        "customer_id": "C001",
        "latitude": 20.01,
        "longitude": 0.01,
        "demand": 1,
        "service_minutes": 10,
        "window_start": 900,
        "window_end": 1000,
    }])

    result = solve_cvrp(
        depot,
        vehicles,
        customers,
        time_limit_seconds=2,
    )

    assert result["status"] == "No feasible solution found"


def test_solver_respects_vehicle_state_current_time():
    depot, vehicles, customers = make_scenario(demands=(3,))

    vehicles.loc[0, "available_from"] = 480

    vehicle_states = {
        "V01": {
            "latitude": depot["latitude"],
            "longitude": depot["longitude"],
            "available": True,
            "remaining_capacity": 20,
            "current_time": 600,
        }
    }

    result = solve_cvrp(
        depot,
        vehicles,
        customers,
        time_limit_seconds=2,
        vehicle_states=vehicle_states,
    )

    assert result["status"] == "Success"
    assert any(
        "C001" in route["customer_stops"]
        for route in result["routes"]
    )


def test_solver_rejects_window_before_vehicle_state_start_time():
    depot, vehicles, customers = make_scenario(demands=(3,))

    customers.loc[0, "window_start"] = 480
    customers.loc[0, "window_end"] = 550

    vehicle_states = {
        "V01": {
            "latitude": depot["latitude"],
            "longitude": depot["longitude"],
            "available": True,
            "remaining_capacity": 20,
            "current_time": 600,
        }
    }

    result = solve_cvrp(
        depot,
        vehicles,
        customers,
        time_limit_seconds=2,
        vehicle_states=vehicle_states,
    )

    assert result["status"] == "No feasible solution found"


def test_solver_returns_stop_times_for_customer_deliveries():
    depot, vehicles, customers = make_scenario(demands=(3,))

    result = solve_cvrp(
        depot,
        vehicles,
        customers,
        time_limit_seconds=2,
    )

    assert result["status"] == "Success"

    route = next(
        route
        for route in result["routes"]
        if "C001" in route["customer_stops"]
    )

    customer_time = next(
        stop
        for stop in route["stop_times"]
        if stop["stop_id"] == "C001"
    )

    assert customer_time["service_start"] >= 480
    assert customer_time["service_end"] == (
        customer_time["service_start"] + 10
    )


def test_solver_stop_times_respect_vehicle_state_start_time():
    depot, vehicles, customers = make_scenario(demands=(3,))

    vehicle_states = {
        "V01": {
            "latitude": depot["latitude"],
            "longitude": depot["longitude"],
            "available": True,
            "remaining_capacity": 20,
            "current_time": 600,
        }
    }

    result = solve_cvrp(
        depot,
        vehicles,
        customers,
        time_limit_seconds=2,
        vehicle_states=vehicle_states,
    )

    assert result["status"] == "Success"

    route = next(
        route
        for route in result["routes"]
        if "C001" in route["customer_stops"]
    )

    start_time = route["stop_times"][0]["time_minute"]

    customer_time = next(
        stop
        for stop in route["stop_times"]
        if stop["stop_id"] == "C001"
    )

    assert start_time == 600
    assert customer_time["service_start"] >= start_time


def test_solver_rejects_vehicle_state_after_shift_end():
    depot, vehicles, customers = make_scenario(demands=(3,))

    vehicles.loc[0, "available_until"] = 550

    vehicle_states = {
        "V01": {
            "latitude": depot["latitude"],
            "longitude": depot["longitude"],
            "available": True,
            "remaining_capacity": 20,
            "current_time": 600,
        }
    }

    result = solve_cvrp(
        depot,
        vehicles,
        customers,
        vehicle_states=vehicle_states,
    )

    assert result["status"] == (
        "Infeasible: vehicle current time is after shift end"
    )
    assert result["routes"] == []
    assert result["total_distance_m"] == 0


def test_solver_rejects_route_that_cannot_finish_within_shift():
    depot, vehicles, customers = make_scenario(demands=(3,))

    vehicles.loc[0, "available_from"] = 480
    vehicles.loc[0, "available_until"] = 481

    result = solve_cvrp(
        depot,
        vehicles,
        customers,
    )

    assert result["status"] != "Success"
    assert result["routes"] == []
