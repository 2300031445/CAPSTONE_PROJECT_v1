
from src.solver import haversine_meters


def build_simulation(
    routes,
    customers,
    depot,
    average_speed_kmh=35,
    start_time_minutes=480,
    vehicle_start_times=None,
):
    """Build simulated travel legs and delivery service events."""
    if vehicle_start_times is None:
        vehicle_start_times = {}
    customer_lookup = {
        row["customer_id"]: row
        for _, row in customers.iterrows()
    }

    schedules = []
    service_events = {}
    max_duration = 0.0

    for route in routes:
        stops = route["stops"]

        # The upgraded solver provides the actual coordinates for
        # every stop, including a vehicle-specific starting point.
        if "coordinates" in route:
            coordinates = route["coordinates"]
        else:
            coordinates = [
                (
                    depot["latitude"],
                    depot["longitude"],
                )
                for _ in stops
            ]

        legs = []
        services = []
        current_time = float(
            vehicle_start_times.get(
                route["vehicle_id"],
                start_time_minutes,
            )
        )

        for index in range(1, len(stops)):
            from_id = stops[index - 1]
            to_id = stops[index]

            from_lat, from_lon = coordinates[index - 1]
            to_lat, to_lon = coordinates[index]

            distance_m = haversine_meters(
                from_lat, from_lon, to_lat, to_lon
            )

            travel_minutes = (
                distance_m / 1000 / average_speed_kmh * 60
            )

            departure = current_time
            arrival = departure + travel_minutes

            legs.append({
                "from_id": from_id,
                "to_id": to_id,
                "from_lat": from_lat,
                "from_lon": from_lon,
                "to_lat": to_lat,
                "to_lon": to_lon,
                "depart": departure,
                "arrive": arrival,
            })

            current_time = arrival


            if to_id in customer_lookup:
                customer = customer_lookup[to_id]

                service_minutes = float(
                    customer["service_minutes"]
                )

                window_start = float(
                    customer.get("window_start", 0)
                )

                # Vehicles may arrive early and wait for the
                # delivery window to open.
                arrival = current_time
                service_start = max(arrival, window_start)
                service_end = service_start + service_minutes

                event = {
                    "customer_id": to_id,
                    "arrival": arrival,
                    "service_start": service_start,
                    "service_end": service_end,
                    "waiting_minutes": service_start - arrival,
                    "vehicle_id": route["vehicle_id"],
                }

                services.append(event)
                service_events[to_id] = event
                current_time = service_end


        schedules.append({
            "vehicle_id": route["vehicle_id"],
            "legs": legs,
            "services": services,
            "duration_minutes": current_time,
        })

        max_duration = max(max_duration, current_time)

    return {
        "schedules": schedules,
        "service_events": service_events,
        "duration_minutes": max_duration,
        "average_speed_kmh": average_speed_kmh,
    }



def shift_schedule(schedule, offset):
    """Shift a schedule's timeline without changing its geometry."""
    offset = float(offset)

    for leg in schedule["legs"]:
        leg["depart"] += offset
        leg["arrive"] += offset

    for event in schedule["services"]:
        event["arrival"] += offset

        if "service_start" in event:
            event["service_start"] += offset

        event["service_end"] += offset

    schedule["duration_minutes"] += offset



def merge_reoptimized_simulation(
    old_simulation,
    new_simulation,
    customers,
    current_minute,
    disruption_type=None,
    selected_vehicle=None,
    delay_minutes=0,
    schedules_are_absolute=False,
):
    """Merge a revised plan with protected delivery history."""

    current_minute = float(current_minute)
    old_events = old_simulation["service_events"]

    completed = {
        customer_id
        for customer_id, event in old_events.items()
        if current_minute >= event["service_end"]
    }

    in_service = {
        customer_id
        for customer_id, event in old_events.items()
        if event.get("service_start", event["arrival"]) <= current_minute < event["service_end"]
    }

    in_service_remaining = {
        event["vehicle_id"]: max(
            0.0,
            float(event["service_end"]) - current_minute,
        )
        for customer_id, event in old_events.items()
        if customer_id in in_service
    }

    # Shift only relative schedules. Absolute schedules already
    # include each vehicle's start time, service remainder, and delay.
    for schedule in new_simulation["schedules"]:
        if not schedules_are_absolute:
            shift_schedule(schedule, current_minute)

            vehicle_id = schedule["vehicle_id"]
            service_remaining = in_service_remaining.get(
                vehicle_id,
                0.0,
            )

            if service_remaining > 0:
                shift_schedule(schedule, service_remaining)

            if (
                disruption_type == "Vehicle delay"
                and vehicle_id == selected_vehicle
            ):
                shift_schedule(schedule, float(delay_minutes))

    # Preserve completed and active deliveries that still exist.
    protected_customers = completed | in_service
    current_customer_ids = set(customers["customer_id"])

    merged_events = {
        customer_id: event_data
        for customer_id, event_data in old_events.items()
        if customer_id in protected_customers
        and customer_id in current_customer_ids
    }

    merged_events.update(new_simulation["service_events"])
    new_simulation["service_events"] = merged_events

    new_simulation["duration_minutes"] = max(
        [current_minute]
        + [
            schedule["duration_minutes"]
            for schedule in new_simulation["schedules"]
        ]
        + [
            event["service_end"]
            for event in merged_events.values()
        ]
    )

    return new_simulation

def vehicle_position(schedule, minute, depot):
    """Interpolate vehicle coordinates at a simulated minute."""

    legs = schedule["legs"]

    if not legs:
        return depot["latitude"], depot["longitude"]

    for leg in legs:
        if minute < leg["depart"]:
            return leg["from_lat"], leg["from_lon"]

        if leg["depart"] <= minute < leg["arrive"]:
            duration = leg["arrive"] - leg["depart"]

            fraction = (
                (minute - leg["depart"]) / duration
                if duration > 0
                else 1.0
            )

            latitude = leg["from_lat"] + fraction * (
                leg["to_lat"] - leg["from_lat"]
            )
            longitude = leg["from_lon"] + fraction * (
                leg["to_lon"] - leg["from_lon"]
            )

            return latitude, longitude

    last_leg = legs[-1]
    return last_leg["to_lat"], last_leg["to_lon"]


def customer_status(customer_id, minute, service_events):
    """Return a customer's current simulated service status."""

    event = service_events.get(customer_id)

    if event is None:
        return "Unassigned"

    if minute < event.get("service_start", event["arrival"]):
        return "Pending"

    if minute < event["service_end"]:
        return "Being serviced"

    return "Delivered"
