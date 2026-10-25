
import pandas as pd
import pytest

from src.simulation import build_simulation


def make_customers():
    return pd.DataFrame([
        {
            "customer_id": "C001",
            "latitude": 0.0,
            "longitude": 0.01,
            "demand": 1,
            "service_minutes": 10,
            "window_start": 0,
            "window_end": 1440,
        },
        {
            "customer_id": "C002",
            "latitude": 0.0,
            "longitude": 0.02,
            "demand": 1,
            "service_minutes": 15,
            "window_start": 0,
            "window_end": 1440,
        },
    ])


def make_route():
    return {
        "vehicle_id": "V01",
        "stops": ["DEPOT", "C001", "C002", "DEPOT"],
        "coordinates": [
            (0.0, 0.0),
            (0.0, 0.01),
            (0.0, 0.02),
            (0.0, 0.0),
        ],
    }


def test_build_simulation_creates_service_events_for_customers():
    simulation = build_simulation(
        routes=[make_route()],
        customers=make_customers(),
        depot={"latitude": 0.0, "longitude": 0.0},
    )

    assert set(simulation["service_events"]) == {"C001", "C002"}
    assert simulation["service_events"]["C001"]["vehicle_id"] == "V01"
    assert simulation["service_events"]["C002"]["vehicle_id"] == "V01"


def test_build_simulation_preserves_service_durations():
    simulation = build_simulation(
        routes=[make_route()],
        customers=make_customers(),
        depot={"latitude": 0.0, "longitude": 0.0},
    )

    events = simulation["service_events"]

    assert (
        events["C001"]["service_end"]
        - events["C001"].get(
            "service_start", events["C001"]["arrival"]
        )
    ) == pytest.approx(10.0)

    assert (
        events["C002"]["service_end"] - events["C002"]["arrival"]
    ) == pytest.approx(15.0)


def test_build_simulation_keeps_route_timestamps_sequential():
    simulation = build_simulation(
        routes=[make_route()],
        customers=make_customers(),
        depot={"latitude": 0.0, "longitude": 0.0},
    )

    schedule = simulation["schedules"][0]

    for index in range(1, len(schedule["legs"])):
        previous_leg = schedule["legs"][index - 1]
        current_leg = schedule["legs"][index]

        previous_service = next(
            (
                event
                for event in schedule["services"]
                if event["customer_id"] == previous_leg["to_id"]
            ),
            None,
        )

        expected_departure = (
            previous_service["service_end"]
            if previous_service is not None
            else previous_leg["arrive"]
        )

        assert current_leg["depart"] == pytest.approx(
            expected_departure
        )


def test_build_simulation_duration_covers_all_service_events():
    simulation = build_simulation(
        routes=[make_route()],
        customers=make_customers(),
        depot={"latitude": 0.0, "longitude": 0.0},
    )

    for event in simulation["service_events"].values():
        assert event["service_end"] <= (
            simulation["duration_minutes"] + 1e-9
        )

def test_simulation_starts_at_default_shift_time():
    customers = pd.DataFrame([
        {
            "customer_id": "C001",
            "latitude": 20.1,
            "longitude": 0.1,
            "demand": 1,
            "service_minutes": 10,
        }
    ])

    depot = {
        "depot_id": "DEPOT_0",
        "latitude": 20.0,
        "longitude": 0.0,
    }

    routes = [{
        "vehicle_id": "V01",
        "stops": ["DEPOT_0", "C001", "DEPOT_0"],
        "coordinates": [
            (20.0, 0.0),
            (20.1, 0.1),
            (20.0, 0.0),
        ],
    }]

    simulation = build_simulation(routes, customers, depot)

    event = simulation["service_events"]["C001"]

    assert event.get("service_start", event["arrival"]) >= 480
    assert event["service_end"] > event.get("service_start", event["arrival"])


def test_simulation_waits_for_customer_window():
    import pandas as pd

    from src.simulation import build_simulation

    depot = {
        "depot_id": "DEPOT_0",
        "latitude": 20.0,
        "longitude": 0.0,
    }

    customers = pd.DataFrame([{
        "customer_id": "C001",
        "latitude": 20.001,
        "longitude": 0.001,
        "demand": 1,
        "service_minutes": 10,
        "window_start": 600,
        "window_end": 720,
    }])

    routes = [{
        "vehicle_id": "V01",
        "stops": ["DEPOT_0", "C001", "DEPOT_0"],
        "coordinates": [
            (20.0, 0.0),
            (20.001, 0.001),
            (20.0, 0.0),
        ],
    }]

    simulation = build_simulation(
        routes,
        customers,
        depot,
        average_speed_kmh=35,
        start_time_minutes=480,
    )

    event = simulation["service_events"]["C001"]

    assert event["arrival"] < 600
    assert event["service_start"] == 600
    assert event["service_end"] == 610
    assert event["waiting_minutes"] > 0


def test_simulation_does_not_wait_when_arrival_is_in_window():
    import pandas as pd

    from src.simulation import build_simulation

    depot = {
        "depot_id": "DEPOT_0",
        "latitude": 20.0,
        "longitude": 0.0,
    }

    customers = pd.DataFrame([{
        "customer_id": "C001",
        "latitude": 20.001,
        "longitude": 0.001,
        "demand": 1,
        "service_minutes": 10,
        "window_start": 480,
        "window_end": 720,
    }])

    routes = [{
        "vehicle_id": "V01",
        "stops": ["DEPOT_0", "C001", "DEPOT_0"],
        "coordinates": [
            (20.0, 0.0),
            (20.001, 0.001),
            (20.0, 0.0),
        ],
    }]

    simulation = build_simulation(
        routes,
        customers,
        depot,
        start_time_minutes=480,
    )

    event = simulation["service_events"]["C001"]

    assert event["service_start"] == event["arrival"]
    assert event["waiting_minutes"] == 0


def test_build_simulation_uses_vehicle_start_time():
    customers = pd.DataFrame([
        {
            "customer_id": "C001",
            "latitude": 20.0,
            "longitude": 0.0,
            "demand": 1,
            "service_minutes": 10,
            "window_start": 600,
            "window_end": 900,
        }
    ])

    depot = {
        "depot_id": "DEPOT_0",
        "latitude": 20.0,
        "longitude": 0.0,
    }

    routes = [{
        "vehicle_id": "V01",
        "stops": ["DEPOT_0", "C001", "DEPOT_0"],
        "coordinates": [
            (20.0, 0.0),
            (20.0, 0.0),
            (20.0, 0.0),
        ],
    }]

    simulation = build_simulation(
        routes,
        customers,
        depot,
        start_time_minutes=480,
        vehicle_start_times={"V01": 600},
    )

    event = simulation["service_events"]["C001"]

    assert event["service_start"] == pytest.approx(600)
    assert event["service_end"] == pytest.approx(610)
