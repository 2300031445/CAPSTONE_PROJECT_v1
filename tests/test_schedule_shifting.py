
import copy
import pytest

from app import shift_schedule


def make_schedule():
    return {
        "vehicle_id": "V01",
        "legs": [
            {"depart": 0.0, "arrive": 10.0},
            {"depart": 15.0, "arrive": 25.0},
        ],
        "services": [
            {
                "customer_id": "C001",
                "arrival": 10.0,
                "service_end": 15.0,
            },
            {
                "customer_id": "C002",
                "arrival": 25.0,
                "service_end": 30.0,
            },
        ],
        "duration_minutes": 30.0,
    }


def test_shift_schedule_moves_all_timestamps():
    schedule = make_schedule()

    shift_schedule(schedule, 20.0)

    assert schedule["legs"] == [
        {"depart": 20.0, "arrive": 30.0},
        {"depart": 35.0, "arrive": 45.0},
    ]
    assert schedule["services"] == [
        {
            "customer_id": "C001",
            "arrival": 30.0,
            "service_end": 35.0,
        },
        {
            "customer_id": "C002",
            "arrival": 45.0,
            "service_end": 50.0,
        },
    ]
    assert schedule["duration_minutes"] == 50.0


def test_shift_schedule_preserves_travel_and_service_durations():
    schedule = make_schedule()
    original = copy.deepcopy(schedule)

    shift_schedule(schedule, 17.0)

    for old_leg, new_leg in zip(original["legs"], schedule["legs"]):
        assert new_leg["arrive"] - new_leg["depart"] == (
            old_leg["arrive"] - old_leg["depart"]
        )

    for old_event, new_event in zip(
        original["services"], schedule["services"]
    ):
        assert new_event["service_end"] - new_event.get("service_start", new_event["arrival"]) == (
            old_event["service_end"] - old_event.get("service_start", old_event["arrival"])
        )


def test_shift_schedule_with_zero_offset_changes_nothing():
    schedule = make_schedule()
    original = copy.deepcopy(schedule)

    shift_schedule(schedule, 0.0)

    assert schedule == original


def test_shift_schedule_can_preserve_remaining_service_time():
    schedule = {
        "vehicle_id": "V01",
        "legs": [
            {"depart": 0.0, "arrive": 10.0},
            {"depart": 15.0, "arrive": 25.0},
        ],
        "services": [
            {
                "customer_id": "C001",
                "arrival": 10.0,
                "service_end": 15.0,
            },
            {
                "customer_id": "C002",
                "arrival": 25.0,
                "service_end": 30.0,
            },
        ],
        "duration_minutes": 30.0,
    }

    original = copy.deepcopy(schedule)

    shift_schedule(schedule, 40.0)
    shift_schedule(schedule, 5.0)

    assert schedule["services"][0]["service_end"] == pytest.approx(
        original["services"][0]["service_end"] + 45.0
    )
    assert schedule["duration_minutes"] == pytest.approx(
        original["duration_minutes"] + 45.0
    )


def test_shift_schedule_does_not_change_route_geometry():
    schedule = {
        "vehicle_id": "V01",
        "legs": [
            {
                "from_id": "DEPOT",
                "to_id": "C001",
                "from_lat": 20.0,
                "from_lon": 0.0,
                "to_lat": 20.1,
                "to_lon": 0.1,
                "depart": 0.0,
                "arrive": 10.0,
            }
        ],
        "services": [],
        "duration_minutes": 10.0,
    }

    original_geometry = {
        key: schedule["legs"][0][key]
        for key in (
            "from_id",
            "to_id",
            "from_lat",
            "from_lon",
            "to_lat",
            "to_lon",
        )
    }

    shift_schedule(schedule, 25.0)

    new_geometry = {
        key: schedule["legs"][0][key]
        for key in original_geometry
    }

    assert new_geometry == original_geometry
    assert schedule["legs"][0]["depart"] == pytest.approx(25.0)
    assert schedule["legs"][0]["arrive"] == pytest.approx(35.0)
