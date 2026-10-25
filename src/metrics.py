from collections import Counter

from src.solver import haversine_meters


def calculate_metrics(solution, customers, vehicles):
    """Calculate operational metrics for a CVRP solution."""

    routes = solution.get("routes", [])

    # customer_ids = set(customers["customer_id"].tolist())
    customer_ids = (
        set(customers["customer_id"].tolist())
        if not customers.empty
        else set()
    )
    total_customers = len(customer_ids)

    demand_by_customer = (
        customers.drop_duplicates("customer_id")
        .set_index("customer_id")["demand"]
        .to_dict()
        if not customers.empty
        else {}
    )

    total_demand = sum(
        int(demand_by_customer[customer_id])
        for customer_id in customer_ids
    )

    route_customer_ids = [
        customer_id
        for route in routes
        for customer_id in route.get("customer_stops", [])
    ]

    assignment_counts = Counter(route_customer_ids)
    assigned_customer_ids = set(route_customer_ids)

    valid_assigned_ids = assigned_customer_ids & customer_ids
    invalid_assignment_ids = assigned_customer_ids - customer_ids

    duplicate_assignments = sum(
        count - 1
        for count in assignment_counts.values()
        if count > 1
    )

    assigned_customers = len(valid_assigned_ids)

    assigned_demand = sum(
        int(demand_by_customer[customer_id])
        for customer_id in valid_assigned_ids
    )

    total_distance_m = sum(
        max(0.0, float(route.get("distance_m", 0)))
        for route in routes
    )

    used_vehicles = sum(
        1 for route in routes
        if route.get("customer_stops")
    )

    total_fleet_capacity = (
        sum(int(capacity) for capacity in vehicles["capacity"])
        if not vehicles.empty
        else 0
    )

    return {
        "status": solution.get("status", "Unknown"),
        "total_distance_km": total_distance_m / 1000,
        "vehicles_used": used_vehicles,
        "vehicles_available": len(vehicles),
        "total_customers": total_customers,
        "assigned_customers": assigned_customers,
        "unassigned_customers": total_customers - assigned_customers,
        "duplicate_customer_assignments": duplicate_assignments,
        "invalid_customer_assignments": len(invalid_assignment_ids),
        "assignment_rate_percent": (
            assigned_customers / total_customers * 100
            if total_customers
            else 100.0
        ),
        "total_demand": total_demand,
        "assigned_demand": assigned_demand,
        "fleet_capacity": total_fleet_capacity,
        "fleet_utilization_percent": (
            assigned_demand / total_fleet_capacity * 100
            if total_fleet_capacity > 0
            else 0.0
        ),
        "solver_runtime_seconds": max(
            0.0,
            float(solution.get("runtime_seconds", 0)),
        ),
    }


def calculate_remaining_distance_m(simulation, current_minute):
    """Estimate remaining travel distance across existing schedules."""

    current_minute = float(current_minute)
    remaining_distance_m = 0.0

    for schedule in simulation.get("schedules", []):
        for leg in schedule.get("legs", []):
            depart = float(leg["depart"])
            arrive = float(leg["arrive"])

            # Ignore completed legs and malformed negative-duration legs.
            if current_minute >= arrive or arrive < depart:
                continue

            distance_m = max(
                0.0,
                haversine_meters(
                    leg["from_lat"],
                    leg["from_lon"],
                    leg["to_lat"],
                    leg["to_lon"],
                ),
            )

            # Future legs count in full. Active legs count proportionally.
            if depart < current_minute < arrive:
                duration = arrive - depart
                fraction_remaining = (arrive - current_minute) / duration
                distance_m *= fraction_remaining

            remaining_distance_m += distance_m

    return remaining_distance_m
