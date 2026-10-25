
from src.solver import solve_cvrp
from src.simulation import vehicle_position


def reoptimize_remaining(
    depot,
    vehicles,
    customers,
    simulation,
    current_minute,
    unavailable_vehicles=None,
    urgent_customer_id=None,
    time_limit_seconds=5,
    vehicle_start_offsets=None,
):
    """Re-optimise deliveries that have not started service yet."""

    unavailable_vehicles = set(unavailable_vehicles or [])
    current_minute = float(current_minute)
    vehicle_start_offsets = vehicle_start_offsets or {}

    service_events = simulation["service_events"]

    # Identify completed and in-progress deliveries.
    completed = {
        customer_id
        for customer_id, event in service_events.items()
        if current_minute >= event["service_end"]
    }

    in_service = {
        customer_id
        for customer_id, event in service_events.items()
        if event.get("service_start", event["arrival"]) <= current_minute < event["service_end"]
    }

    # Only customers whose service has not started are reassigned.
    protected_customers = completed | in_service

    remaining_customers = customers[
        ~customers["customer_id"].isin(protected_customers)
    ].copy()

    # Calculate load already delivered by each vehicle.
    customer_demands = dict(
        zip(customers["customer_id"], customers["demand"])
    )

    delivered_load = {}

    for customer_id, event in service_events.items():
        # Count cargo already delivered or currently being delivered.
        if current_minute >= event.get("service_start", event["arrival"]):
            vehicle_id = event["vehicle_id"]
            demand = int(customer_demands.get(customer_id, 0))
            delivered_load[vehicle_id] = (
                delivered_load.get(vehicle_id, 0) + demand
            )

    vehicle_states = {}

    for schedule in simulation["schedules"]:
        vehicle_id = schedule["vehicle_id"]

        vehicle_row = vehicles.loc[
            vehicles["vehicle_id"] == vehicle_id,
            "capacity",
        ]

        if vehicle_row.empty:
            continue

        original_capacity = int(vehicle_row.iloc[0])

        if vehicle_id in unavailable_vehicles:
            vehicle_states[vehicle_id] = {
                "latitude": float(depot["latitude"]),
                "longitude": float(depot["longitude"]),
                "available": False,
                "remaining_capacity": 0,
                "current_time": current_minute,
            }
            continue

        latitude, longitude = vehicle_position(
            schedule,
            current_minute,
            depot,
        )

        remaining_capacity = max(
            0,
            original_capacity - delivered_load.get(vehicle_id, 0),
        )


        active_service_end = max(
            (
                float(event["service_end"])
                for customer_id, event in service_events.items()
                if event["vehicle_id"] == vehicle_id
                and customer_id in in_service
            ),
            default=current_minute,
        )

        vehicle_states[vehicle_id] = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "available": True,
            "remaining_capacity": remaining_capacity,
            "current_time": max(
                current_minute,
                active_service_end,
            )
            + float(vehicle_start_offsets.get(vehicle_id, 0.0)),
        }


    # Solve only the work that remains eligible for reassignment.
    result = solve_cvrp(
        depot=depot,
        vehicles=vehicles,
        customers=remaining_customers,
        time_limit_seconds=time_limit_seconds,
        vehicle_states=vehicle_states,
        urgent_customer_id=urgent_customer_id,
    )

    return {
        "solution": result,
        "remaining_customers": remaining_customers,
        "completed_customers": completed,
        "in_service_customers": in_service,
        "vehicle_states": vehicle_states,
        "reoptimization_minute": current_minute,
    }
