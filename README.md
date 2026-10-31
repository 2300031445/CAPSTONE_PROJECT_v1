# Fleet Routing Simulator

## 1. Project Overview

The **Fleet Routing Simulator** is a Python application for planning, optimizing, and simulating vehicle delivery routes. It models a depot, a fleet of vehicles, and customer deliveries, then uses a vehicle-routing solver to construct routes that respect operational constraints.

The application also simulates vehicle movement and delivery progress over time. It supports operational disruptions, dynamic route reoptimization, and operational performance metrics through an interactive Streamlit dashboard.

Development has focused on building a reliable routing and simulation workflow, with automated tests used to verify individual components and their integration.

### Main Goals

- Assign customer deliveries to available vehicles.
- Respect vehicle capacity limits and customer delivery time windows.
- Respect vehicle shift start and end times.
- Simulate travel, waiting, and delivery service over time.
- Represent vehicle positions and delivery progress.
- Support operational disruptions and dynamic reoptimization.
- Preserve completed and in-progress delivery history during replanning.
- Report routing and operational metrics.
- Validate planned and simulated schedules.

## 2. Technology Stack

- **Python 3.11** for application development.
- **Streamlit** for the interactive application interface.
- **Pandas** for scenario generation and tabular data handling.
- **OR-Tools** for vehicle-routing optimization.
- **Folium** and **streamlit-folium** for map visualization.
- **Pytest** for automated testing.

The project is developed in a Windows environment using a Python virtual environment.

## 3. Project Structure

```text
fleet-routing-simulator/
├── app.py
├── src/
│   ├── data_generator.py
│   ├── solver.py
│   ├── simulation.py
│   ├── disruptions.py
│   ├── reoptimization.py
│   ├── metrics.py
│   ├── live_map.py
│   └── validation.py
└── tests/
    ├── test_solver.py
    ├── test_simulation.py
    ├── test_disruptions.py
    ├── test_simulation_merge.py
    ├── test_reoptimization.py
    └── test_validation.py
```

This structure represents the main application modules and test files. Additional repository files, such as configuration files and environment definitions, may also be present.

## 4. Implemented Functionality

### 4.1 Scenario Generation and Route Optimization

`src/data_generator.py` generates reproducible synthetic depot, vehicle, and customer data.

`src/solver.py` uses Google OR-Tools to construct vehicle routes.

Implemented capabilities include:

- Haversine distance calculations between geographic coordinates.
- Customer assignment to available vehicles.
- Vehicle capacity constraints.
- Handling zero-vehicle scenarios.
- Detection of infeasible aggregate demand.
- Customer time-window constraints.
- Vehicle availability fields: `available_from` and `available_until`.
- Vehicle-specific state during reoptimization, including current position, remaining capacity, availability, and current time.
- Route information including stops, coordinates, distance, load, and planned stop times.
- Vehicle-specific starting locations during reoptimization.
- Urgent-customer visit-order constraints.
- Clear error handling when an urgent customer ID is not found.
- Protection against invalid solver time ranges when a vehicle's current start time is later than its shift end.

**Urgent delivery behavior:** The urgent customer is constrained to be the first customer stop on its assigned route. This prioritizes visit order but does not guarantee the earliest possible arrival across the entire fleet or automatically select the fastest vehicle.

**Current limitation:** All generated vehicles currently use the same shift, from 08:00 to 18:00. Individual vehicle shift schedules have not been implemented.

### 4.2 Route Simulation

`src/simulation.py` contains `build_simulation()` and related schedule-management helpers.

Implemented capabilities include:

- Building travel legs between route stops.
- Calculating travel duration from distance and average speed.
- Recording leg departure and arrival times.
- Modeling customer service start and end times.
- Waiting when a vehicle arrives before a customer's time window opens.
- Recording waiting time and assigned vehicles.
- Tracking schedule duration.
- Supporting vehicle-specific simulation start times.
- Shifting schedules along the timeline without changing route geometry.
- Interpolating vehicle positions along travel legs.
- Tracking customer delivery status, including unassigned, pending, in service, and delivered.
- Merging revised schedules with previous simulation data.
- Preserving relevant completed and in-progress delivery history during reoptimization.

Schedules contain a vehicle ID, travel `legs`, customer `services`, and `duration_minutes`.

Travel legs record `depart` and `arrive` times. Service events record `arrival`, `service_start`, and `service_end`.

### 4.3 Disruption Management and Dynamic Reoptimization

The application supports four main disruption categories:

1. Vehicle delay.
2. Vehicle breakdown.
3. Urgent delivery.
4. Customer cancellation.

Urgent delivery can apply to an existing customer or a newly generated customer.

Implemented behavior includes:

- Identifying completed deliveries and in-progress service.
- Preventing completed or currently serviced customers from being selected for cancellation or reprioritization.
- Preventing repeated cancellation or repeated urgent prioritization of the same customer.
- Adding new urgent customers to the scenario.
- Excluding unavailable vehicles from reoptimization.
- Using current vehicle positions and remaining capacity during reoptimization.
- Accounting for active service when calculating vehicle availability.
- Applying delays to the selected vehicle.
- Preserving completed delivery timestamps and in-progress service during schedule merging.
- Removing cancelled customers from the remaining optimization workload.
- Pausing the simulation clock while configuring and applying disruptions.
- Recording disruption events and their outcomes.
- Comparing revised remaining distance with the previous plan's remaining distance.

The reoptimization process focuses on the remaining delivery workload while preserving relevant work already completed or actively underway.

### 4.4 Operational Metrics and Streamlit Dashboard

`src/metrics.py` provides routing metrics and remaining-distance calculations.

The Streamlit interface displays:

- Total route distance.
- Number of vehicles used.
- Customer assignment counts.
- Customer assignment rate.
- Fleet utilization.
- Solver runtime.
- Revised remaining distance.
- Reoptimization runtime.
- Distance change relative to the previous plan's remaining distance.

The dashboard also includes:

- Scenario generation and configuration.
- Customer and vehicle data tables.
- Initial route optimization.
- Route visualization.
- Simulation playback controls.
- Live vehicle positions.
- Disruption controls.
- Reoptimization results.
- Event logging.
- Operational metrics.

### 4.5 Schedule Validation

`src/validation.py` provides validation helpers for customer time windows and vehicle shifts.

**`validate_time_windows(simulation, customers)`**

- Reports early and late deliveries using service start time when available.
- Falls back to arrival time when service start is missing.
- Reports customers without service events as unscheduled.
- Includes the number of minutes outside the delivery window.
- Treats exact time-window boundaries as valid.
- Checks service start time rather than requiring service completion before the window closes.

**`validate_vehicle_shifts(simulation, vehicles)`**

- Checks schedule `duration_minutes` against each vehicle's `available_until`.
- Reports route end, shift end, and minutes over shift.
- Defaults to 1440 when `available_until` is absent.
- Skips schedules whose vehicle IDs are not present in the vehicle data.

These validators provide operational checks for simulated schedules. Their results should be interpreted according to the time semantics used by the simulation.

## 5. Solver Safeguards and Edge-Case Handling

The solver includes safeguards for invalid and infeasible routing scenarios.

### Vehicle Shift Expiry

Before applying an OR-Tools time range, the solver checks whether a vehicle's selected start time is later than its shift end.

When `start_time > end_time`, it returns an infeasible result with no routes, zero total distance, and a diagnostic status instead of passing an invalid time range to OR-Tools.

### Urgent Customer Handling

The solver identifies the requested urgent customer and constrains it to be the first customer stop on its assigned route.

An unknown urgent customer ID produces a clear error result.

### Reoptimization State

Reoptimization accounts for:

- Completed deliveries.
- Customers currently being serviced.
- Current vehicle positions.
- Remaining vehicle capacity.
- Vehicle availability.
- Remaining customer demand.
- Vehicle-specific timing offsets.

Schedule merging protects completed and in-progress service history from being overwritten by revised delivery events.

## 6. Automated Testing

The project includes a Pytest suite covering the main solver, simulation, disruption, reoptimization, schedule-merging, and validation components.

Test coverage includes:

- Customer assignment.
- Vehicle capacity constraints.
- Infeasible demand.
- Zero-vehicle scenarios.
- Customer time windows.
- Vehicle shift boundaries.
- Vehicle state and current-time constraints.
- Urgent-customer first-stop behavior.
- Unknown urgent-customer handling.
- Simulation travel and service events.
- Delivery completion tracking.
- Disruption handling.
- Customer cancellation.
- Reoptimization using current vehicle positions and remaining capacity.
- Exclusion of unavailable vehicles.
- Active-service handling.
- Schedule merging.
- Preservation of completed and in-progress delivery history.
- Time-window and vehicle-shift validation.
- Expired vehicle shifts and invalid solver time ranges.

The full automated test suite has passed, and the application has also been manually checked through its Streamlit interface.

### Running the Tests

Run the full test suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Run an individual test module:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_solver.py -v
```

Run disruption and reoptimization tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_disruptions.py tests/test_reoptimization.py -v
```

## 7. Running the Application

### Step 1: Create and Activate a Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies

Install the project dependencies using the repository's dependency file, if present.

For example:

```powershell
pip install -r requirements.txt
```

### Step 3: Start the Streamlit Application

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

The application opens in a browser and provides access to scenario generation, route optimization, simulation, disruption management, and operational metrics.

## 8. Current Limitations

The current implementation provides a working routing and simulation prototype. The following limitations remain:

1. **Identical vehicle shifts:** All generated vehicles currently use the same 08:00-18:00 shift.
2. **No driver-break modeling:** Planned driver breaks, accumulated driving-time constraints, and break-aware reoptimization have not been implemented.
3. **Urgent delivery optimization:** Urgent-customer logic prioritizes the first stop on its assigned route but does not guarantee the earliest fleet-wide arrival.
4. **Time-window simulation:** The simulation waits when a vehicle arrives early, but it does not itself prevent service from starting after the customer's window closes. The validator can report late starts.
5. **Time precision:** The solver uses integer-minute travel times, while simulation durations use floating-point values. Small timing differences may occur.
6. **Shift validation:** Shift validation focuses on `available_until`; shift-start validation and consistent absolute-time semantics remain areas for future improvement.
7. **Failed reoptimization:** A disruption can be recorded as applied before reoptimization has successfully completed. The application distinguishes failed reoptimization in its event status, but this behavior remains a possible area for stronger transactional state handling.
8. **Scalability and route quality:** Larger scenarios and more realistic travel-time models require further evaluation.

The simulator is intended as an operational routing prototype, not a legally certified fleet or driver-hours compliance system.

## 9. Future Development Roadmap

The current implementation is complete for its defined scope. Future development can extend the simulator in the following areas.

### Phase 1: Vehicle-Specific Shifts

- Generate individual `available_from` and `available_until` values for each vehicle.
- Use varied but controlled shift start times and durations.
- Keep scenario generation reproducible by seed.
- Ensure the solver respects each vehicle's individual shift.
- Maintain consistent shift semantics across simulation, validation, live maps, and reoptimization.
- Test vehicles whose shifts have ended and routes that cannot finish within the remaining shift.

### Phase 2: Driver-Break Constraints

- Define operating assumptions and the applicable jurisdiction before implementing legal-compliance claims.
- Introduce driver-break data, including break duration and rules for when a break is due.
- Distinguish driving time, service time, waiting time, break time, and total elapsed shift time.
- Represent breaks explicitly in simulation schedules and the live timeline.
- Prevent driving and customer service while a driver is on a break.
- Preserve accumulated driving and work state during reoptimization.
- Test breaks alongside time windows, shifts, delays, breakdowns, urgent deliveries, and cancellations.
- Add metrics and validation reports for break violations and infeasible schedules.

The initial implementation should use a controlled planned-break model. Solver-selected break placement can be considered later.

Until jurisdiction-specific rules have been implemented and validated, the system should be described as a break-constrained routing prototype rather than a legally certified compliance system.

### Phase 3: Further Optimization and Evaluation

- Evaluate route quality across larger scenarios.
- Explore more realistic travel-time estimates.
- Review optimization performance as fleet and customer counts increase.
- Compare routing outcomes across different scenario configurations.

### Phase 4: Further Interface and Reporting Improvements

- Improve visualization of original and revised routes.
- Expand operational reporting.
- Improve presentation of validation warnings and reoptimization failures.
- Add workflow-level integration tests as new functionality is introduced.

## 10. Development Workflow

The recommended development workflow is:

1. Inspect the existing implementation and tests.
2. Identify the smallest missing behavior.
3. Add or update a focused test.
4. Implement the required change.
5. Run focused tests.
6. Run the full test suite.
7. Verify application behavior.
8. Update this documentation when functionality or project scope changes.

Run all commands from the repository root using PowerShell.

## 11. Project Status

The Fleet Routing Simulator currently provides a working foundation for:

- Vehicle-routing optimization using OR-Tools.
- Customer assignment and capacity management.
- Customer time-window and vehicle-shift constraints.
- Route simulation and live vehicle visualization.
- Disruption-aware dynamic reoptimization.
- Urgent delivery and cancellation handling.
- Preservation of completed and in-progress delivery history.
- Operational metrics and schedule validation.
- An interactive Streamlit dashboard.
- Automated testing of core functionality.

The automated test suite has passed, and the application has passed manual interface checks.

**Current status: Core implementation complete.**

Varied vehicle shifts and driver-break constraints remain future development work and are not part of the current implementation.