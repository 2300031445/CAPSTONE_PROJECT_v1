
import math
import time

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def haversine_meters(lat1, lon1, lat2, lon2):
    """Approximate straight-line distance in meters."""
    radius = 6_371_000

    lat1, lon1, lat2, lon2 = map(
        math.radians, [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return int(
        radius * 2 * math.atan2(
            math.sqrt(a), math.sqrt(1 - a)
        )
    )


def solve_cvrp(
    depot,
    vehicles,
    customers,
    time_limit_seconds=5,
    vehicle_states=None,
    urgent_customer_id=None,
    average_speed_kmh=35,
):
    """
    Solve a capacitated vehicle routing problem.

    vehicle_states is optional. When provided, each state can contain:
      vehicle_id, latitude, longitude, available, remaining_capacity

    Every route ends at the depot. Unavailable vehicles receive no work.
    """

    started = time.perf_counter()

    vehicle_ids = vehicles["vehicle_id"].tolist()
    capacities = vehicles["capacity"].astype(int).tolist()

    # Node 0 is always the depot.
    locations = [{
        "id": depot["depot_id"],
        "latitude": float(depot["latitude"]),
        "longitude": float(depot["longitude"]),
        "demand": 0,
    }]

    for _, customer in customers.iterrows():
        locations.append({
            "id": customer["customer_id"],
            "latitude": float(customer["latitude"]),
            "longitude": float(customer["longitude"]),
            "demand": int(customer["demand"]),
        })

    customer_count = len(customers)
    vehicle_count = len(vehicles)

    if vehicle_count == 0:
        return {
            "status": "No vehicles",
            "routes": [],
            "total_distance_m": 0,
            "runtime_seconds": time.perf_counter() - started,
        }

    if vehicle_states is None:
        vehicle_states = {}

    # Allow a separate starting location for each vehicle.
    starts = []
    vehicle_capacities = []
    unavailable_ids = set()

    for i, vehicle_id in enumerate(vehicle_ids):
        state = vehicle_states.get(vehicle_id)

        if state is None:
            starts.append(0)
            vehicle_capacities.append(capacities[i])
            continue

        if not state.get("available", True):
            unavailable_ids.add(vehicle_id)
            vehicle_capacities.append(0)
        else:
            vehicle_capacities.append(
                max(
                    0,
                    int(state.get("remaining_capacity", capacities[i])),
                )
            )

        # Add a unique start node for this vehicle.
        starts.append(len(locations))
        locations.append({
            "id": f"START_{vehicle_id}",
            "latitude": float(state["latitude"]),
            "longitude": float(state["longitude"]),
            "demand": 0,
        })

    ends = [0] * vehicle_count

    total_demand = sum(
        int(value) for value in customers["demand"]
    )

    available_capacity = sum(
        vehicle_capacities[i]
        for i in range(vehicle_count)
        if vehicle_ids[i] not in unavailable_ids
    )

    if total_demand > available_capacity:
        return {
            "status": "Infeasible: remaining fleet capacity is insufficient",
            "routes": [],
            "total_distance_m": 0,
            "runtime_seconds": time.perf_counter() - started,
        }

    num_locations = len(locations)

    distance_matrix = [
        [
            haversine_meters(
                locations[i]["latitude"],
                locations[i]["longitude"],
                locations[j]["latitude"],
                locations[j]["longitude"],
            )
            for j in range(num_locations)
        ]
        for i in range(num_locations)
    ]

    manager = pywrapcp.RoutingIndexManager(
        num_locations, vehicle_count, starts, ends
    )
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        source = manager.IndexToNode(from_index)
        target = manager.IndexToNode(to_index)
        return distance_matrix[source][target]

    distance_index = routing.RegisterTransitCallback(
        distance_callback
    )
    routing.SetArcCostEvaluatorOfAllVehicles(distance_index)

    def demand_callback(from_index):
        node = manager.IndexToNode(from_index)
        return locations[node]["demand"]

    demand_index = routing.RegisterUnaryTransitCallback(
        demand_callback
    )

    routing.AddDimensionWithVehicleCapacity(
        demand_index,
        0,
        vehicle_capacities,
        True,
        "Capacity",
    )


    # Enforce delivery windows and vehicle shift boundaries.
    customer_lookup = {
        row["customer_id"]: row
        for _, row in customers.iterrows()
    }

    vehicle_lookup = {
        row["vehicle_id"]: row
        for _, row in vehicles.iterrows()
    }

    def time_callback(from_index, to_index):
        source = manager.IndexToNode(from_index)
        target = manager.IndexToNode(to_index)

        distance_m = distance_matrix[source][target]

        travel_minutes = math.ceil(
            distance_m / 1000 / average_speed_kmh * 60
        )

        source_id = locations[source]["id"]
        service_minutes = 0

        if source_id in customer_lookup:
            service_minutes = int(
                customer_lookup[source_id]["service_minutes"]
            )

        return service_minutes + travel_minutes

    time_index = routing.RegisterTransitCallback(time_callback)

    routing.AddDimension(
        time_index,
        1440,  # Maximum permitted slack at each transition.
        1440,  # Maximum cumulative time value.
        False,
        "Time",
    )

    time_dimension = routing.GetDimensionOrDie("Time")

    # Constrain customer arrival times to their delivery windows.
    for node in range(1, customer_count + 1):
        customer_id = locations[node]["id"]
        customer = customer_lookup[customer_id]

        window_start = int(customer.get("window_start", 0))
        window_end = int(customer.get("window_end", 1440))

        time_dimension.CumulVar(
            manager.NodeToIndex(node)
        ).SetRange(window_start, window_end)

    # Constrain vehicle start and return times.
    for vehicle_index, vehicle_id in enumerate(vehicle_ids):
        vehicle = vehicle_lookup[vehicle_id]
        state = vehicle_states.get(vehicle_id)

        if state is not None:
            start_time = int(
                state.get(
                    "current_time",
                    vehicle.get("available_from", 0),
                )
            )
        else:
            start_time = int(
                vehicle.get("available_from", 0)
            )

        end_time = int(
            vehicle.get("available_until", 1440)
        )


        if start_time > end_time:
            return {
                "status": (
                    "Infeasible: vehicle current time "
                    "is after shift end"
                ),
                "routes": [],
                "total_distance_m": 0,
                "runtime_seconds": time.perf_counter() - started,
            }

        time_dimension.CumulVar(
            routing.Start(vehicle_index)
        ).SetRange(start_time, start_time)

        time_dimension.CumulVar(
            routing.End(vehicle_index)
        ).SetRange(start_time, end_time)


    # Count customer visits along each route.
    def visit_order_callback(from_index):
        node = manager.IndexToNode(from_index)
        return 1 if 1 <= node <= customer_count else 0

    visit_order_index = routing.RegisterUnaryTransitCallback(
        visit_order_callback
    )

    routing.AddDimension(
        visit_order_index,
        0,
        customer_count,
        True,
        "VisitOrder",
    )


    # Strongly prioritise the urgent customer as the first stop.
    # Ensure the urgent customer is the first customer on its route.
    if urgent_customer_id is not None:
        urgent_node = next(
            (
                node
                for node in range(1, customer_count + 1)
                if locations[node]["id"] == urgent_customer_id
            ),
            None,
        )

        if urgent_node is None:
            return {
                "status": (
                    f"Urgent customer {urgent_customer_id} "
                    "was not found"
                ),
                "routes": [],
                "total_distance_m": 0,
                "runtime_seconds": time.perf_counter() - started,
            }

        urgent_index = manager.NodeToIndex(urgent_node)
        solver = routing.solver()

        for vehicle_index in range(vehicle_count):
            start_index = routing.Start(vehicle_index)

            # Boolean variable: is this vehicle assigned the urgent customer?
            assigned_to_vehicle = solver.IsEqualCstVar(
                routing.VehicleVar(urgent_index),
                vehicle_index,
            )

            # Boolean variable: is the urgent customer this vehicle's first stop?
            urgent_is_first = solver.IsEqualCstVar(
                routing.NextVar(start_index),
                urgent_index,
            )

            # If assigned to this vehicle, the urgent customer must be first.
            solver.Add(assigned_to_vehicle <= urgent_is_first)


    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search.time_limit.FromSeconds(max(1, int(time_limit_seconds)))

    solution = routing.SolveWithParameters(search)
    runtime = time.perf_counter() - started

    if solution is None:
        return {
            "status": "No feasible solution found",
            "routes": [],
            "total_distance_m": 0,
            "runtime_seconds": runtime,
        }

    routes = []
    total_distance = 0

    for vehicle_index, vehicle_id in enumerate(vehicle_ids):
        index = routing.Start(vehicle_index)
        start_node = manager.IndexToNode(index)

        path_nodes = [start_node]
        path_indices = [index]
        route_distance = 0
        route_load = 0

        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))

            route_distance += routing.GetArcCostForVehicle(
                index, next_index, vehicle_index
            )

            index = next_index
            node = manager.IndexToNode(index)

            path_nodes.append(node)
            path_indices.append(index)

            if node != 0:
                route_load += locations[node]["demand"]

        # Do not display unused vehicles as active routes.
        if len(path_nodes) <= 2:
            continue


        stop_times = []

        for node, route_index in zip(path_nodes, path_indices):
            stop_id = locations[node]["id"]

            time_minute = solution.Value(
                time_dimension.CumulVar(route_index)
            )

            stop_time = {
                "stop_id": stop_id,
                "time_minute": time_minute,
            }

            if stop_id in customer_lookup:
                service_minutes = int(
                    customer_lookup[stop_id]["service_minutes"]
                )

                stop_time["service_start"] = time_minute
                stop_time["service_end"] = (
                    time_minute + service_minutes
                )

            stop_times.append(stop_time)


        routes.append({
            "vehicle_id": vehicle_id,
            "stops": [locations[node]["id"] for node in path_nodes],
            "customer_stops": [
                locations[node]["id"]
                for node in path_nodes
                if 1 <= node <= customer_count
            ],
            "coordinates": [
                (
                    locations[node]["latitude"],
                    locations[node]["longitude"],
                )
                for node in path_nodes
            ],
            "start_location": {
                "latitude": locations[start_node]["latitude"],
                "longitude": locations[start_node]["longitude"],
            },
            "stop_times": stop_times,
            "distance_m": route_distance,
            "load": route_load,
            "capacity": vehicle_capacities[vehicle_index],
        })

        total_distance += route_distance

    return {
        "status": "Success",
        "routes": routes,
        "total_distance_m": total_distance,
        "runtime_seconds": runtime,
    }
