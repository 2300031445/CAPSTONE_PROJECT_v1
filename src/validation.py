
def validate_time_windows(simulation, customers):
    """Report delivery arrivals outside customer time windows.

    Assumes service-event timestamps and customer window boundaries
    use the same time reference and units.
    """
    customer_lookup = {
        row["customer_id"]: row
        for _, row in customers.iterrows()
    }

    violations = []

    for customer_id, customer in customer_lookup.items():
        event = simulation["service_events"].get(customer_id)

        if event is None:
            violations.append({
                "customer_id": customer_id,
                "service_start": None,
                "window_start": float(customer["window_start"]),
                "window_end": float(customer["window_end"]),
                "status": "Unscheduled",
                "minutes_outside_window": None,
            })
            continue

        arrival = float(
            event.get("service_start", event["arrival"])
        )
        window_start = float(customer["window_start"])
        window_end = float(customer["window_end"])

        if arrival < window_start:
            violations.append({
                "customer_id": customer_id,
                "service_start": arrival,
                "window_start": window_start,
                "window_end": window_end,
                "status": "Early",
                "minutes_outside_window": window_start - arrival,
            })

        elif arrival > window_end:
            violations.append({
                "customer_id": customer_id,
                "service_start": arrival,
                "window_start": window_start,
                "window_end": window_end,
                "status": "Late",
                "minutes_outside_window": arrival - window_end,
            })

    return violations



def validate_vehicle_shifts(simulation, vehicles):
    """Report vehicle schedules that finish after their shift ends."""

    vehicle_lookup = {
        row["vehicle_id"]: row
        for _, row in vehicles.iterrows()
    }

    violations = []

    for schedule in simulation.get("schedules", []):
        vehicle_id = schedule["vehicle_id"]
        vehicle = vehicle_lookup.get(vehicle_id)

        if vehicle is None:
            continue

        shift_end = float(vehicle.get("available_until", 1440))
        route_end = float(schedule["duration_minutes"])

        if route_end > shift_end:
            violations.append({
                "vehicle_id": vehicle_id,
                "route_end": route_end,
                "shift_end": shift_end,
                "status": "Late",
                "minutes_over_shift": route_end - shift_end,
            })

    return violations
