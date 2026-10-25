# Fleet Routing Simulator

## 1. Project Overview

The **Fleet Routing Simulator** is a Python application for planning and
simulating vehicle delivery routes. It models a depot, a fleet of
vehicles, and customer deliveries, then uses a vehicle-routing solver to
build routes that respect operational constraints.

The project is being developed incrementally, with automated tests used
to verify each change before moving on.

### Main goals

-   Assign customer deliveries to available vehicles.
-   Respect vehicle capacity limits.
-   Account for customer delivery time windows.
-   Respect vehicle shift start and end times.
-   Simulate travel and delivery service over time.
-   Represent vehicle positions and delivery progress during a
    simulation.
-   Support operational disruptions and reoptimization of the remaining
    deliveries.
-   Report routing and operational metrics.
-   Validate planned or simulated schedules and catch infeasible
    situations.

## 2. Technology Stack

The project currently uses:

-   **Python 3.11**
-   **Streamlit** for the application interface.
-   **Pandas** for scenario and tabular data.
-   **OR-Tools** for vehicle-routing optimization.
-   **Folium** and **streamlit-folium** for map-based visualization.
-   **Pytest** for automated tests.

The project is developed in a Windows environment using a virtual
environment.

## 3. Current Project Structure

The main files and modules known to be in use are:

``` text
fleet-routing-simulator/
├── app.py
├── src/
│   ├── data_generator.py
│   ├── solver.py
│   ├── simulation.py
│   ├── disruptions.py
│   ├── reoptimization.py
│   ├── metrics.py
│   └── validation.py
└── tests/
    ├── test_solver.py
    ├── test_simulation.py
    ├── test_disruptions.py
    ├── test_simulation_merge.py
    └── test_validation.py
```

This is a working summary of the files discussed so far, not a guarantee
that it lists every file in the repository.

## 4. Functionality Implemented So Far

### 4.1 Scenario and route optimization

The solver in `src/solver.py` uses OR-Tools to construct vehicle routes.

Current capabilities include:

-   Calculating geographic distance with a Haversine distance function.
-   Assigning customers to vehicles.
-   Enforcing vehicle capacity constraints.
-   Handling the case where no vehicles are available.
-   Reporting infeasibility when total delivery demand exceeds available
    fleet capacity.
-   Applying customer time-window constraints.
-   Applying vehicle shift boundaries through `available_from` and
    `available_until`.
-   Supporting vehicle-specific state during reoptimization, including
    current coordinates, remaining capacity, availability, and current
    time.
-   Returning route information such as stops, coordinates, distance,
    load, and planned stop times.
-   Supporting an urgent-customer constraint and visit-order logic.

The solver includes vehicle-specific start nodes when vehicle state is
provided, allowing a reoptimized route to begin from a vehicle's current
position instead of always starting from the depot.

### 4.2 Simulation

`src/simulation.py` contains `build_simulation()` and related schedule
helpers.

The simulation currently:

-   Builds travel legs between route stops.
-   Calculates travel duration from distance and average speed.
-   Records leg departure and arrival times.
-   Models customer service start and end times.
-   Makes vehicles wait when they arrive before a customer's time window
    opens.
-   Records waiting time and the vehicle assigned to each service event.
-   Tracks schedule duration.
-   Supports vehicle-specific simulation start times.
-   Can shift schedules along the timeline without changing their
    geometry.
-   Can interpolate a vehicle's position along a travel leg.
-   Can report a customer's status as unassigned, pending, being
    serviced, or delivered.

Simulation schedules contain a vehicle ID, a list of travel `legs`, a
list of customer `services`, and a `duration_minutes` value. Individual
legs use `depart` and `arrive`; service events use `arrival`,
`service_start`, and `service_end`.

### 4.3 Disruptions and reoptimization

The project includes disruption and reoptimization logic.

The current implementation and tests cover behavior such as:

-   Identifying completed deliveries based on service completion time.
-   Identifying deliveries currently in service.
-   Preserving completed delivery timestamps when merging a revised
    simulation.
-   Preserving in-progress deliveries.
-   Shifting revised schedules to the current simulation time.
-   Applying a vehicle delay to the selected vehicle rather than
    indiscriminately delaying every vehicle.
-   Avoiding duplicate application of time offsets.
-   Excluding cancelled customers from protected delivery history.
-   Accounting for service already in progress when calculating a
    vehicle's next available time.
-   Using a vehicle's current position and remaining capacity when
    solving the remaining routing problem.

The reoptimization flow is intended to preserve work already completed
or actively underway while replanning the remaining work.

### 4.4 Validation

`src/validation.py` currently provides two validators.

**`validate_time_windows(simulation, customers)`**

-   Reports deliveries that are early or late based on service start
    when that value is available.
-   Falls back to the recorded arrival time if no service start is
    present.
-   Reports customers with no service event as unscheduled.
-   Includes the number of minutes outside the window for early or late
    cases.
-   Treats the exact window boundaries as valid.
-   Currently checks the service start, not whether service finishes
    before the window closes.

**`validate_vehicle_shifts(simulation, vehicles)`**

-   Checks each simulated vehicle schedule's `duration_minutes` against
    that vehicle's `available_until` value.
-   Reports the route end, shift end, and minutes over the shift.
-   Uses `1440` as the default shift end when `available_until` is
    absent.
-   Skips schedules whose vehicle ID is not present in the vehicle data.

### 4.5 Automated tests

Automated tests are a central part of the development workflow. The test
suite has covered:

-   Customer assignment and vehicle capacity.
-   Infeasible demand and zero-vehicle scenarios.
-   Customer time windows and vehicle shift boundaries.
-   Vehicle state and current-time constraints.
-   Simulation travel and service events.
-   Disruption handling.
-   Merging revised schedules while preserving completed and in-progress
    service.
-   Time-window and vehicle-shift validation.
-   Handling an already-expired vehicle shift without allowing OR-Tools
    to crash.

The latest reported test run passed after adding a guard in
`solve_cvrp()` for a vehicle whose current time is later than its shift
end. The exact current total test count may change as development
continues.

## 5. Recent Solver Safeguard

The solver now checks whether a vehicle's selected start time is later
than its shift end before applying the OR-Tools time range.

When `start_time > end_time`, it returns an infeasible result with no
routes, zero total distance, and a diagnostic status instead of passing
an invalid range to OR-Tools and raising an exception.

A regression test covers this case. Another test verifies that a route
that cannot fit within a very short shift is rejected.

## 6. Known Gaps and Items to Review

The following are known follow-up areas, not claims that the project is
broken in every scenario.

1.  **Solver/simulation timing consistency:** The solver uses
    integer-minute travel times, while the simulation calculates travel
    durations as floating-point values. Planned and simulated timestamps
    may therefore differ slightly.
2.  **Time-window enforcement in simulation:** The simulation waits
    until `window_start`, but it does not itself prevent service from
    starting after `window_end`. The validator can report late service
    starts.
3.  **Vehicle shift validation:** The validator checks shift end but
    does not currently validate `available_from`.
4.  **Shift validation semantics:** Confirm that `duration_minutes` is
    consistently treated as an absolute simulated end time wherever it
    is compared with `available_until`.
5.  **Reoptimization edge cases:** Continue checking vehicle position,
    active service, remaining capacity, delays, cancellations, and time
    offsets together, since these interact.
6.  **Application integration:** Ensure the Streamlit interface presents
    solver infeasibility, validation warnings, disruptions, revised
    routes, and metrics clearly.
7.  **Route quality and scalability:** Distance minimization,
    travel-time realism, and behavior with larger scenarios may need
    additional evaluation.

## 7. Planned Development Roadmap

The following is a proposed roadmap. Priorities may change as tests and
application behavior reveal issues.

### Phase 1: Strengthen correctness

-   Align solver and simulation time calculations.
-   Add tests for edge cases involving customer windows and vehicle
    shifts.
-   Validate vehicle shift start times as well as shift end times.
-   Review infeasibility messages and return consistent result
    structures.
-   Verify route stop timestamps against simulation service events.

### Phase 2: Improve disruption handling

-   Test combinations of delays, breakdowns, urgent deliveries, and
    cancellations.
-   Verify that completed deliveries remain unchanged after
    reoptimization.
-   Verify that in-progress service is not duplicated or interrupted
    incorrectly.
-   Ensure a delay affects only the intended vehicle.
-   Check that remaining capacity and vehicle availability are accurate
    after a disruption.

### Phase 3: Improve operational metrics

-   Review total distance, total demand, vehicle utilization, customer
    assignment, and route completion metrics.
-   Add explicit counts and summaries for late, early, and unscheduled
    deliveries.
-   Make sure metrics distinguish solver output from simulation
    outcomes.

### Phase 4: Improve the Streamlit interface

-   Review scenario generation and route display.
-   Present simulation progress and vehicle status clearly.
-   Make disruption controls easy to use.
-   Show validation warnings and infeasibility explanations.
-   Display original and reoptimized plans in a way that makes their
    differences clear.

### Phase 5: Broader testing and documentation

-   Add integration tests for complete workflows.
-   Test multiple vehicles, different shift times, varying customer
    windows, and more complex disruptions.
-   Document setup, execution, test commands, and expected application
    behavior.
-   Revisit this document after significant feature changes.

## 8. Development Workflow

Run commands from the repository root with the virtual environment
activated.

To run the full test suite in PowerShell:

``` powershell
$env:PYTHONPATH = "."
pytest -v
```

To run one test module, for example:

``` powershell
$env:PYTHONPATH = "."
pytest tests/test_solver.py -v
```

Recommended workflow for each change:

1.  Inspect the current implementation and tests.
2.  Identify the smallest missing behavior.
3.  Add or update a focused test.
4.  Implement the change.
5.  Run the focused tests.
6.  Run the full test suite.
7.  Update this document when the implemented functionality or roadmap
    changes.

## 9. Current Status Summary

The project has a working foundation for vehicle-routing optimization,
time-window and shift constraints, route simulation, disruption-aware
reoptimization, operational validation, and automated testing.

Development is currently focused on tightening correctness at the
boundaries between the solver, simulator, and validation layer before
expanding functionality further.

This document is intended to evolve with the project. Update the
implementation and roadmap sections as features are added, changed, or
completed.
