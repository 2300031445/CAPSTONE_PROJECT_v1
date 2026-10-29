
from pathlib import Path

import pandas as pd
import streamlit as st

from src.live_map import render_live_map as render_map_component
from src.data_generator import generate_scenario
from src.metrics import (
    calculate_metrics,
    calculate_remaining_distance_m,
)
from src.solver import solve_cvrp
from src.simulation import (
    build_simulation,
    merge_reoptimized_simulation,
    shift_schedule,
)

from src.disruptions import (
    create_disruption,
    cancel_customer,
    add_urgent_customer,
)
from src.reoptimization import reoptimize_remaining


st.set_page_config(
    page_title="Fleet Routing Simulator",
    page_icon="🚚",
    layout="wide",
)

st.title("Driver-Break Constrained Fleet Routing and Compliance Decision Platform")
st.caption("Interactive CPU-based routing and disruption simulator")


# ---------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------

def initialise_state():
    if "customers" not in st.session_state:
        depot, vehicles, customers = generate_scenario()
        st.session_state["depot"] = depot
        st.session_state["vehicles"] = vehicles
        st.session_state["customers"] = customers

    defaults = {
        "solution": None,
        "simulation": None,
        "sim_minute": 480.0,
        "sim_running": False,
        "events": [],
        "unavailable_vehicles": [],
        "revised_solution": None,
        "urgent_counter": 0,
        "urgent_customers": [],
        "baseline_distance_m": None,
        "reoptimization_runtime": None,
        "delay_minutes": 20,
        "baseline_remaining_distance_m": None,
        "disruption_mode": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_scenario(depot, vehicles, customers):
    st.session_state["depot"] = depot
    st.session_state["vehicles"] = vehicles
    st.session_state["customers"] = customers
    st.session_state["solution"] = None
    st.session_state["simulation"] = None
    st.session_state["sim_minute"] = 480.0
    st.session_state["sim_running"] = False
    st.session_state["events"] = []
    st.session_state["unavailable_vehicles"] = []
    st.session_state["revised_solution"] = None
    st.session_state["baseline_distance_m"] = None
    st.session_state["reoptimization_runtime"] = None
    st.session_state["urgent_counter"] = 0
    st.session_state["urgent_customers"] = []
    st.session_state["baseline_remaining_distance_m"] = None
    st.session_state["disruption_mode"] = False


# def shift_schedule(schedule, offset):
#     """Shift a schedule's timeline without changing its geometry."""
#     for leg in schedule["legs"]:
#         leg["depart"] += offset
#         leg["arrive"] += offset

#     for event in schedule["services"]:
#         event["arrival"] += offset
#         event["service_end"] += offset

#     schedule["duration_minutes"] += offset


# ---------------------------------------------------------------------
# Live eligibility checks
# ---------------------------------------------------------------------

def get_completed_customers(simulation, current_minute):
    """Return customer IDs whose service has finished."""
    if simulation is None:
        return set()

    return {
        customer_id
        for customer_id, event in simulation["service_events"].items()
        if current_minute >= event["service_end"]
    }


def customer_is_in_service(customer_id, simulation, current_minute):
    """Check whether service has started but not finished."""
    event = simulation["service_events"].get(customer_id)

    if event is None:
        return False

    return (
        event.get("service_start", event["arrival"]) <= current_minute
        < event["service_end"]
    )


def get_customer_options(
    customers,
    simulation,
    current_minute,
    disruption_type,
):
    """Return only customers eligible for the selected action."""
    if simulation is None:
        return []

    completed = get_completed_customers(simulation, current_minute)
    cancelled = {
        event["customer_id"]
        for event in st.session_state["events"]
        if event["type"] == "Customer cancellation"
        and event["status"].startswith("Applied")
        and event["customer_id"] is not None
    }

    already_urgent = set(st.session_state["urgent_customers"])
    service_events = simulation["service_events"]

    options = []

    for customer_id in customers["customer_id"].tolist():
        if customer_id not in service_events:
            continue

        if customer_id in completed or customer_id in cancelled:
            continue

        if customer_is_in_service(
            customer_id, simulation, current_minute
        ):
            continue

        if disruption_type == "Urgent delivery: existing order":
            if customer_id in already_urgent:
                continue

        options.append(customer_id)

    return options


def get_vehicle_options(
    vehicles,
    simulation,
    current_minute,
    unavailable_vehicles,
):
    """Return available vehicles that still have deliveries to make."""
    if simulation is None:
        return []

    completed = get_completed_customers(simulation, current_minute)
    unavailable = set(unavailable_vehicles)
    service_events = simulation["service_events"]

    vehicles_in_service = {
        event["vehicle_id"]
        for event in service_events.values()
        if event.get("service_start", event["arrival"]) <= current_minute < event["service_end"]
    }

    vehicles_with_remaining_work = {
        event["vehicle_id"]
        for customer_id, event in service_events.items()
        if customer_id not in completed
        and event["service_end"] > current_minute
    }

    return [
        vehicle_id
        for vehicle_id in vehicles["vehicle_id"].tolist()
        if vehicle_id not in unavailable
        # and vehicle_id not in vehicles_in_service
        and vehicle_id in vehicles_with_remaining_work
    ]


# ---------------------------------------------------------------------
# Re-optimisation
# ---------------------------------------------------------------------

def perform_reoptimization(
    disruption_type,
    selected_vehicle=None,
    selected_customer=None,
    delay_minutes=0,
):
    """Validate an incident, apply it, and calculate a revised plan."""
    depot = st.session_state["depot"]
    vehicles = st.session_state["vehicles"]
    customers = st.session_state["customers"]
    old_simulation = st.session_state["simulation"]
    current_minute = float(st.session_state["sim_minute"])

    # Every disruption is handled with the clock frozen.
    st.session_state["sim_running"] = False

    if old_simulation is None:
        st.error("Optimise routes before applying a disruption.")
        return False

    old_events = old_simulation["service_events"]
    unavailable = set(st.session_state["unavailable_vehicles"])

    completed = get_completed_customers(
        old_simulation, current_minute
    )

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

    cancelled_ids = {
        event["customer_id"]
        for event in st.session_state["events"]
        if event["type"] == "Customer cancellation"
        and event["status"].startswith("Applied")
        and event["customer_id"] is not None
    }

    # Save the baseline before modifying the plan.
    st.session_state["baseline_remaining_distance_m"] = (
        calculate_remaining_distance_m(
            old_simulation,
            current_minute,
        )
    )

    # Validate customer actions against the latest simulation state.
    if disruption_type in {
        "Customer cancellation",
        "Urgent delivery: existing order",
    }:
        if selected_customer is None:
            st.error("Select an eligible customer.")
            return False

        if selected_customer not in set(customers["customer_id"]):
            st.error("That customer is not in the current scenario.")
            return False

        if selected_customer in completed:
            st.error("That delivery has already been completed.")
            return False

        if selected_customer in cancelled_ids:
            st.error("That customer has already been cancelled.")
            return False

        if selected_customer not in old_events:
            st.error("That customer has no active scheduled delivery.")
            return False

        if customer_is_in_service(
            selected_customer, old_simulation, current_minute
        ):
            st.error(
                "That customer is currently being serviced and "
                "cannot be cancelled or reprioritised."
            )
            return False

        if (
            disruption_type == "Urgent delivery: existing order"
            and selected_customer
            in set(st.session_state["urgent_customers"])
        ):
            st.error("That customer has already been prioritised.")
            return False
        
    # Validate vehicle actions against the latest simulation state.
    if disruption_type in {"Vehicle delay", "Vehicle breakdown"}:
        if selected_vehicle is None:
            st.error("Select an eligible vehicle.")
            return False

        valid_vehicles = get_vehicle_options(
            vehicles,
            old_simulation,
            current_minute,
            unavailable,
        )

        if selected_vehicle not in valid_vehicles:
            st.error(
                "That vehicle is unavailable or has no remaining "
                "deliveries."
            )
            return False

    
    # Apply the incident.
    if disruption_type == "Customer cancellation":
        customers = cancel_customer(customers, selected_customer)
        st.session_state["customers"] = customers

        description = f"Customer {selected_customer} cancelled"
        customer_id = selected_customer

    elif disruption_type == "Urgent delivery: existing order":
        demand = int(
            customers.loc[
                customers["customer_id"] == selected_customer,
                "demand",
            ].iloc[0]
        )

        description = (
            f"Existing customer {selected_customer} prioritised "
            f"(demand {demand})"
        )
        customer_id = selected_customer

    elif disruption_type == "Urgent delivery: new order":
        next_number = st.session_state["urgent_counter"] + 1

        customers, urgent_customer = add_urgent_customer(
            customers=customers,
            depot=depot,
            next_number=next_number,
        )

        st.session_state["customers"] = customers
        st.session_state["urgent_counter"] = int(
            urgent_customer["customer_id"].split("_")[-1]
        )

        description = (
            f"New urgent order {urgent_customer['customer_id']} added "
            f"(demand {urgent_customer['demand']})"
        )
        customer_id = urgent_customer["customer_id"]

    elif disruption_type == "Vehicle breakdown":
        unavailable.add(selected_vehicle)
        st.session_state["unavailable_vehicles"] = list(unavailable)

        description = f"Vehicle {selected_vehicle} broke down"
        customer_id = None

    elif disruption_type == "Vehicle delay":
        description = (
            f"Vehicle {selected_vehicle} delayed by "
            f"{delay_minutes} simulated minutes"
        )
        customer_id = None

    else:
        st.error("Unknown disruption type.")
        return False


    event = create_disruption(
        disruption_type=disruption_type,
        description=description,
        minute=current_minute,
        vehicle_id=selected_vehicle,
        customer_id=customer_id,
    )
    event["status"] = "Applied"
    st.session_state["events"].append(event)

    vehicle_start_offsets = dict(in_service_remaining)

    if disruption_type == "Vehicle delay":
        vehicle_start_offsets[selected_vehicle] = (
            vehicle_start_offsets.get(selected_vehicle, 0.0)
            + float(delay_minutes)
        )

    # Re-optimise using the actual current vehicle positions.
    result = reoptimize_remaining(
        depot=depot,
        vehicles=vehicles,
        customers=customers,
        simulation=old_simulation,
        current_minute=current_minute,
        unavailable_vehicles=unavailable,
        urgent_customer_id=(
            customer_id
            if disruption_type in {
                "Urgent delivery: existing order",
                "Urgent delivery: new order",
            }
            else None
        ),
        time_limit_seconds=5,
        vehicle_start_offsets=vehicle_start_offsets,
    )

    revised = result["solution"]
    st.session_state["revised_solution"] = revised

    if revised["status"] != "Success":
        event["status"] = "Applied, but re-optimisation failed"
        st.error(
            "The disruption was recorded, but the remaining workload "
            f"could not be routed: {revised['status']}"
        )
        return False

    vehicle_start_times = {
        vehicle_id: state["current_time"]
        for vehicle_id, state in result["vehicle_states"].items()
        if state.get("available", True)
    }

    new_simulation = build_simulation(
        revised["routes"],
        customers,
        depot,
        start_time_minutes=current_minute,
        vehicle_start_times=vehicle_start_times,
    )

    new_simulation = merge_reoptimized_simulation(
        old_simulation=old_simulation,
        new_simulation=new_simulation,
        customers=customers,
        current_minute=current_minute,
        disruption_type=disruption_type,
        selected_vehicle=selected_vehicle,
        delay_minutes=delay_minutes,
        schedules_are_absolute=True,
    )

    # # Shift revised schedules to the current simulation time.
    # for schedule in new_simulation["schedules"]:
    #     shift_schedule(schedule, current_minute)

    #     vehicle_id = schedule["vehicle_id"]
    #     service_remaining = in_service_remaining.get(
    #         vehicle_id,
    #         0.0,
    #     )

    #     # Keep the vehicle occupied until its active service finishes.
    #     if service_remaining > 0:
    #         shift_schedule(schedule, service_remaining)

    #     # Apply any additional delay to the revised route.
    #     if (
    #         disruption_type == "Vehicle delay"
    #         and vehicle_id == selected_vehicle
    #     ):
    #         shift_schedule(schedule, delay_minutes)

    # # Keep completed delivery history from the previous simulation.
    # protected_customers = completed | in_service
    # current_customer_ids = set(customers["customer_id"])

    # merged_events = {
    #     customer_id: event_data
    #     for customer_id, event_data in old_events.items()
    #     if customer_id in protected_customers
    #     and customer_id in current_customer_ids
    # }

    # merged_events.update(new_simulation["service_events"])
    # new_simulation["service_events"] = merged_events

    # new_simulation["duration_minutes"] = max(
    #     [current_minute]
    #     + [
    #         schedule["duration_minutes"]
    #         for schedule in new_simulation["schedules"]
    #     ]
    #     + [
    #         event["service_end"]
    #         for event in new_simulation["service_events"].values()
    #     ]
    # )

    st.session_state["solution"] = revised
    st.session_state["simulation"] = new_simulation
    st.session_state["sim_minute"] = current_minute
    st.session_state["revised_solution"] = revised
    st.session_state["reoptimization_runtime"] = revised[
        "runtime_seconds"
    ]

    if disruption_type in {
        "Urgent delivery: existing order",
        "Urgent delivery: new order",
    }:
        st.session_state["urgent_customers"].append(customer_id)

    # Stay paused. Resuming requires an explicit user action.
    st.session_state["sim_running"] = False
    st.session_state["disruption_mode"] = True

    return True


# ---------------------------------------------------------------------
# Initialise and configure scenario
# ---------------------------------------------------------------------

initialise_state()

st.sidebar.header("Scenario Configuration")

num_vehicles = st.sidebar.slider(
    "Number of vehicles", 1, 20, 4
)
num_customers = st.sidebar.slider(
    "Number of customers", 5, 100, 20
)
seed = st.sidebar.number_input(
    "Random seed",
    min_value=0,
    max_value=999999,
    value=42,
    step=1,
)

if st.sidebar.button("Generate new scenario"):
    depot, vehicles, customers = generate_scenario(
        num_vehicles,
        num_customers,
        int(seed),
    )
    reset_scenario(depot, vehicles, customers)
    st.rerun()

depot = st.session_state["depot"]
vehicles = st.session_state["vehicles"]
customers = st.session_state["customers"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Vehicles", len(vehicles))
m2.metric("Customers", len(customers))
m3.metric("Total demand", int(customers["demand"].sum()))
m4.metric("Fleet capacity", int(vehicles["capacity"].sum()))

if customers["demand"].sum() > vehicles["capacity"].sum():
    st.warning("Aggregate demand exceeds fleet capacity.")


# ---------------------------------------------------------------------
# Initial route optimisation
# ---------------------------------------------------------------------

if st.button("Optimise initial routes", type="primary"):
    solution = solve_cvrp(depot, vehicles, customers)

    st.session_state["solution"] = solution
    st.session_state["revised_solution"] = None
    st.session_state["baseline_distance_m"] = (
        solution["total_distance_m"]
        if solution["status"] == "Success"
        else None
    )
    st.session_state["simulation"] = (
        build_simulation(solution["routes"], customers, depot)
        if solution["status"] == "Success"
        else None
    )
    st.session_state["sim_minute"] = 480.0
    st.session_state["sim_running"] = False
    st.session_state["events"] = []
    st.session_state["unavailable_vehicles"] = []
    st.session_state["urgent_customers"] = []
    st.session_state["disruption_mode"] = False
    st.session_state["baseline_remaining_distance_m"] = None

    st.rerun()

solution = st.session_state["solution"]
simulation = st.session_state["simulation"]


if solution and solution["status"] != "Success":
    st.error(f"Routing failed: {solution['status']}")


# ---------------------------------------------------------------------
# Operational dashboard
# ---------------------------------------------------------------------

if solution and solution["status"] == "Success" and simulation:
    st.subheader("Current Routing Plan")

    metrics = calculate_metrics(
        solution=solution,
        customers=customers,
        vehicles=vehicles,
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Distance",
        f"{metrics['total_distance_km']:.2f} km",
    )
    col2.metric(
        "Vehicles Used",
        f"{metrics['vehicles_used']} / "
        f"{metrics['vehicles_available']}",
    )
    col3.metric(
        "Customers Assigned",
        f"{metrics['assigned_customers']} / "
        f"{metrics['total_customers']}",
    )
    col4.metric(
        "Fleet Utilisation",
        f"{metrics['fleet_utilization_percent']:.1f}%",
    )

    col5, col6 = st.columns(2)

    col5.metric(
        "Assignment Rate",
        f"{metrics['assignment_rate_percent']:.1f}%",
    )
    col6.metric(
        "Solver Runtime",
        f"{metrics['solver_runtime_seconds']:.3f} seconds",
    )

    if metrics["unassigned_customers"] > 0:
        st.warning(
            f"{metrics['unassigned_customers']} customer(s) "
            "are not assigned to a vehicle."
        )

    # -------------------------------------------------------------
    # Simulation controls
    # -------------------------------------------------------------

    st.subheader("Simulation Controls")

    x1, x2, x3 = st.columns(3)

    with x1:
        if st.session_state["disruption_mode"]:
            st.button(
                "Paused for disruption",
                disabled=True,
                use_container_width=True,
            )
        else:
            if st.button(
                "Pause simulation"
                if st.session_state["sim_running"]
                else "Start simulation",
                use_container_width=True,
            ):
                st.session_state["sim_running"] = (
                    not st.session_state["sim_running"]
                )
                st.rerun()

    with x2:
        if st.button(
            "Reset clock",
            disabled=bool(st.session_state["events"])
            or st.session_state["disruption_mode"],
            use_container_width=True,
        ):
            st.session_state["sim_minute"] = 480.0
            st.session_state["sim_running"] = False
            st.rerun()

        if st.session_state["events"]:
            st.caption(
                "Generate a new scenario to reset after disruptions."
            )

    with x3:
        playback_speed = st.selectbox(
            "Playback speed",
            [1, 5, 10],
            index=1,
            format_func=lambda x: f"{x}x",
        )

    # -------------------------------------------------------------
    # Disruption workflow entry point
    # -------------------------------------------------------------

    st.subheader("Disruption Control Panel")

    if (
        not st.session_state["disruption_mode"]
        and st.button(
            "Configure disruption (pause simulation)",
            type="primary",
            use_container_width=True,
        )
    ):
        # Pause before displaying the incident-selection controls.
        st.session_state["sim_running"] = False
        st.session_state["disruption_mode"] = True
        st.rerun()

    if st.session_state["disruption_mode"]:
        st.info(
            f"Simulation paused at minute "
            f"{st.session_state['sim_minute']:.1f}. "
            "The clock will remain frozen until you resume."
        )

        disruption_type = st.selectbox(
            "Incident type",
            [
                "Vehicle delay",
                "Vehicle breakdown",
                "Urgent delivery: existing order",
                "Urgent delivery: new order",
                "Customer cancellation",
            ],
            key="active_disruption_type",
        )

        current_minute = float(st.session_state["sim_minute"])
        simulation = st.session_state["simulation"]

        selected_vehicle = None
        selected_customer = None
        delay_minutes = 20

        if disruption_type in {"Vehicle delay", "Vehicle breakdown"}:
            vehicle_options = get_vehicle_options(
                vehicles,
                simulation,
                current_minute,
                st.session_state["unavailable_vehicles"],
            )

            if vehicle_options:
                selected_vehicle = st.selectbox(
                    "Affected vehicle",
                    vehicle_options,
                    key="active_disruption_vehicle",
                )
            else:
                st.info(
                    "No available vehicles have remaining deliveries "
                    "that can be disrupted."
                )

        if disruption_type in {
            "Customer cancellation",
            "Urgent delivery: existing order",
        }:
            customer_options = get_customer_options(
                customers,
                simulation,
                current_minute,
                disruption_type,
            )

            if customer_options:
                label = (
                    "Customer to prioritise"
                    if disruption_type == "Urgent delivery: existing order"
                    else "Customer to cancel"
                )

                selected_customer = st.selectbox(
                    label,
                    customer_options,
                    key=f"eligible_customer_{disruption_type}",
                )
            else:
                st.info(
                    "No eligible customers are available for this action."
                )

        if disruption_type == "Vehicle delay":
            delay_minutes = st.slider(
                "Delay duration (simulated minutes)",
                5,
                120,
                20,
                step=5,
                key="active_delay_minutes",
            )

        can_apply = (
            selected_vehicle is not None
            if disruption_type in {"Vehicle delay", "Vehicle breakdown"}
            else selected_customer is not None
            if disruption_type in {
                "Customer cancellation",
                "Urgent delivery: existing order",
            }
            else disruption_type == "Urgent delivery: new order"
        )

        if st.button(
            "Apply disruption and re-optimise",
            type="primary",
            disabled=not can_apply,
            use_container_width=True,
        ):
            perform_reoptimization(
                disruption_type,
                selected_vehicle=selected_vehicle,
                selected_customer=selected_customer,
                delay_minutes=delay_minutes,
            )
            st.rerun()

        if st.button(
            "Resume simulation",
            use_container_width=True,
        ):
            st.session_state["disruption_mode"] = False
            st.session_state["sim_running"] = True
            st.rerun()

    # -------------------------------------------------------------
    # Re-optimisation comparison
    # -------------------------------------------------------------

    revised = st.session_state["revised_solution"]

    if revised and revised["status"] == "Success":
        st.subheader("Re-optimisation Comparison")

        baseline = st.session_state["baseline_remaining_distance_m"]
        revised_km = revised["total_distance_m"] / 1000

        p1, p2, p3 = st.columns(3)

        p1.metric(
            "Revised Remaining Distance",
            f"{revised_km:.2f} km",
        )

        runtime = st.session_state["reoptimization_runtime"]
        p2.metric(
            "Re-optimisation Runtime",
            f"{runtime:.3f} s" if runtime is not None else "N/A",
        )

        if baseline is not None:
            baseline_km = baseline / 1000
            delta_km = revised_km - baseline_km

            p3.metric(
                "Distance Change",
                f"{delta_km:+.2f} km",
                help=(
                    "Revised distance minus the distance remaining "
                    "in the previous plan at the incident time."
                ),
            )

            st.caption(
                f"Previous plan's remaining distance: "
                f"{baseline_km:.2f} km."
            )

    # -------------------------------------------------------------
    # Event log
    # -------------------------------------------------------------

    st.subheader("Event Log")

    if st.session_state["events"]:
        st.dataframe(
            pd.DataFrame(st.session_state["events"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No disruptions have been recorded yet.")

    # -------------------------------------------------------------
    # Live map and simulation clock
    # -------------------------------------------------------------

    st.subheader("Live Simulation")

    @st.fragment(run_every="1s")
    def render_live_map():
        sim = st.session_state["simulation"]

        if sim is None:
            st.info("Optimise routes to start the simulation.")
            return

        current = float(st.session_state["sim_minute"])

        # Never advance while configuring a disruption.
        if (
            st.session_state["sim_running"]
            and not st.session_state["disruption_mode"]
        ):
            current += 2 * playback_speed

            if current >= sim["duration_minutes"]:
                current = sim["duration_minutes"]
                st.session_state["sim_running"] = False

            st.session_state["sim_minute"] = current

        duration = float(sim["duration_minutes"])

        st.progress(
            min(
                1.0,
                max(0.0, current - 480.0) / (duration - 480.0),
            ) if duration > 480.0 else 1.0
        )

        st.write(f"**Simulated time:** {current:.1f} minutes")

        render_map_component(
            depot=st.session_state["depot"],
            customers=st.session_state["customers"],
            simulation=sim,
            solution=st.session_state["solution"],
            current_minute=current,
            height=550,
        )

        completed = get_completed_customers(sim, current)

        st.write(
            f"**Completed services:** {len(completed)}  |  "
            f"**Customers remaining in scenario:** "
            f"{len(st.session_state['customers']) - len(completed)}"
        )

        if st.session_state["disruption_mode"]:
            st.caption(
                "Clock frozen while the disruption is configured."
            )
        elif st.session_state["sim_running"]:
            st.caption("Simulation running.")
        else:
            st.caption("Simulation paused.")

    render_live_map()


# ---------------------------------------------------------------------
# Scenario data and export
# ---------------------------------------------------------------------

tab1, tab2 = st.tabs(["Customers", "Vehicles"])

with tab1:
    st.dataframe(
        st.session_state["customers"],
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    st.dataframe(
        st.session_state["vehicles"],
        use_container_width=True,
        hide_index=True,
    )

if st.button("Export scenario CSV files"):
    out = Path("data") / "simulated"
    out.mkdir(parents=True, exist_ok=True)

    st.session_state["customers"].to_csv(
        out / "customers.csv", index=False
    )
    st.session_state["vehicles"].to_csv(
        out / "vehicles.csv", index=False
    )
    pd.DataFrame([st.session_state["depot"]]).to_csv(
        out / "depot.csv", index=False
    )

    if st.session_state["events"]:
        pd.DataFrame(st.session_state["events"]).to_csv(
            out / "events.csv", index=False
        )

    st.success(f"Files saved to {out.resolve()}")

st.caption(
    "Synthetic coordinates and straight-line distances are used. "
    "This prototype models delivery service history, but not physical "
    "cargo transfer, road-network traffic, or driver regulations yet."
)
