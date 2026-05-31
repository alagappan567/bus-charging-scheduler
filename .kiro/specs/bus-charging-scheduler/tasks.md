# Bus Charging Scheduler - Implementation Tasks

## Phase 1: Foundation & Data Model

### 1.1 Project Setup
- [x] Create project structure (scheduler/, scenarios/, tests/)
- [x] Create requirements.txt with dependencies (streamlit, pydantic, numpy)
- [x] Create .gitignore (venv/, __pycache__/, .streamlit/)
- [x] Initialize README.md with basic setup instructions

### 1.2 Data Models
- [x] Define Pydantic models in scheduler/models.py:
  - [x] Segment, Station, Route
  - [x] Bus, Parameters, Weights
  - [x] Scenario (top-level)
  - [x] ChargingPlan, ChargingStop, BusTimeline
  - [x] SimulationResult
- [x] Add validation rules (e.g., distance > 0, num_chargers >= 1)
- [x] Add helper methods (Route.get_distance, Route.get_stations_on_route)

### 1.3 Scenario Files
- [x] Create scenarios/scenario1.json (Even spacing)
- [x] Create scenarios/scenario2.json (Bunched start)
- [x] Create scenarios/scenario3.json (Asymmetric load)
- [x] Create scenarios/scenario4.json (Operator-heavy)
- [x] Create scenarios/scenario5.json (Worst case convergence)
- [x] Test loading all scenarios with Pydantic validation

---

## Phase 2: Constraint System

### 2.1 Constraint Base Classes
- [x] Create scheduler/constraints.py
- [x] Define Constraint abstract base class with is_valid() method
- [x] Define ConstraintValidator class to run all constraints

### 2.2 Implement Core Constraints
- [x] RangeConstraint: Verify battery capacity never exceeded
- [x] RouteOrderConstraint: Verify stations in route order
- [x] CompletionConstraint: Verify bus can reach destination
- [x] Write unit tests for each constraint (valid/invalid cases)

---

## Phase 3: Charging Plan Generation

### 3.1 Plan Generator
- [x] Create scheduler/plan_generator.py
- [x] Implement get_stations_on_route(bus, route) helper
- [x] Implement calculate_min_charges(bus, route, params) helper
- [x] Implement generate_charging_plans(bus, route, params):
  - [x] Generate all combinations of stations
  - [x] Filter by minimum charges needed
  - [x] Return list of ChargingPlan objects
- [x] Write unit tests with known routes

---

## Phase 4: Event Simulator

### 4.1 Event System
- [x] Create scheduler/simulator.py
- [x] Define EventType enum (ARRIVE, CHARGE_START, CHARGE_END)
- [x] Define Event dataclass with time, type, bus_id, station_id
- [x] Implement event priority queue (heapq)

### 4.2 Charger State Management
- [x] Implement ChargerState class:
  - [x] Track available/occupied chargers per station
  - [x] Track queue of waiting buses per station
  - [x] allocate_charger(station_id, bus_id, time)
  - [x] release_charger(station_id, bus_id, time)

### 4.3 Event Simulator Core
- [x] Implement EventSimulator class:
  - [x] __init__: Initialize event queue, charger state, timelines
  - [x] simulate(charging_plans): Main simulation loop
  - [x] _schedule_bus_journey(bus, plan): Schedule initial departure
  - [x] _handle_event(event): Dispatch to specific handlers
  - [x] _handle_arrival(event): Check charger, queue or start charging
  - [x] _handle_charge_start(event): Occupy charger, schedule end
  - [x] _handle_charge_end(event): Release charger, continue journey
  - [x] _build_station_queues(): Aggregate station view
- [x] Write integration test: simulate simple 2-bus scenario

---

## Phase 5: Objective System

### 5.1 Objective Base Classes
- [x] Create scheduler/objectives.py
- [x] Define Objective abstract base class with score() method
- [x] Define ObjectiveEvaluator class to compute weighted sum

### 5.2 Implement Core Objectives
- [x] IndividualWaitObjective: Penalize max wait time
- [x] OperatorFairnessObjective: Penalize variance across operators
- [x] OverallEfficiencyObjective: Penalize total wait time
- [x] Write unit tests for each objective with known scenarios

---

## Phase 6: Scheduler Orchestrator

### 6.1 Main Scheduler
- [x] Create scheduler/scheduler.py
- [x] Implement BusScheduler class:
  - [x] __init__(scenario): Load scenario, initialize components
  - [x] schedule(): Main entry point
  - [x] _generate_all_plans(): Generate plans for all buses
  - [x] _validate_plans(plans): Filter invalid plans
  - [x] _greedy_assign(): Assign buses sequentially
  - [x] _simulate_and_score(assignments): Run simulation + scoring
  - [x] _select_best_plan(bus, candidates): Pick best for one bus
- [x] Write integration test: schedule scenario 1

### 6.2 Greedy Assignment Algorithm
- [x] Sort buses by departure time
- [x] For each bus:
  - [x] Get candidate plans
  - [x] For each plan, simulate with current assignments
  - [x] Score each simulation
  - [x] Pick best, lock in assignment
- [x] Test with scenarios 1-5

---

## Phase 7: Streamlit UI

### 7.1 Basic UI Structure
- [x] Create app.py
- [x] Add title and description
- [x] Add scenario dropdown (load from scenarios/ directory)
- [x] Load selected scenario and display name

### 7.2 Input Display
- [x] Display scenario parameters (battery, charge time, speed)
- [x] Display weights (individual, operator, overall)
- [x] Display route structure (segments, stations)
- [x] Display bus list (ID, operator, direction, departure)

### 7.3 Output Display - Per Bus
- [x] Create per-bus timeline table:
  - [x] Columns: Bus ID, Operator, Direction, Departure
  - [x] Expandable section per bus showing charging stops
  - [x] For each stop: Station, Arrival, Wait, Charge Start, Charge End
  - [x] Show final arrival time and total wait
- [x] Add filtering/sorting options (by operator, by wait time)

### 7.4 Output Display - Per Station
- [x] Create per-station queue table:
  - [x] Tabs or sections for each station (A, B, C, D)
  - [x] For each station: chronological list of buses
  - [x] Columns: Bus ID, Arrival, Charge Start, Charge End, Wait
- [x] Highlight buses with wait > 0

### 7.5 UI Polish
- [x] Add loading spinner during scheduling
- [x] Add error handling for invalid scenarios
- [x] Add "Run Scheduler" button (vs auto-run on selection)
- [x] Format times consistently (HH:MM)
- [x] Add summary stats (total wait, max wait, avg wait per operator)

---

## Phase 8: Documentation

### 8.1 README.md
- [x] How to run locally (pip install, streamlit run)
- [x] How to change a weight (edit scenario JSON, example)
- [ ] How to add a new rule (write class, register, example)
- [ ] Project structure overview
- [ ] Dependencies and requirements

### 8.2 ARCHITECTURE.md
- [ ] Explain scheduler approach (event simulation + greedy)
- [ ] Justify why this approach (vs CP/MIP solver)
- [ ] Data structure design rationale
- [ ] List of anticipated changes (15+ items from requirements)
- [ ] For each change, explain how design handles it
- [ ] Code examples: changing weight, adding rule, adding station
- [ ] Assumptions made and trade-offs
- [ ] Performance characteristics and scaling

### 8.3 Code Documentation
- [ ] Add docstrings to all public classes and methods
- [ ] Add inline comments for non-obvious logic
- [ ] Add type hints to all function signatures

---

## Phase 9: Testing & Validation

### 9.1 Unit Tests
- [ ] Test all constraints with valid/invalid inputs
- [ ] Test all objectives with known scenarios
- [ ] Test plan generation with various routes
- [ ] Test charger allocation logic
- [ ] Achieve >70% code coverage

### 9.2 Integration Tests
- [ ] Test full scheduling for each scenario
- [ ] Verify no constraint violations in output
- [ ] Verify weight changes produce different schedules
- [ ] Test edge cases (single bus, all buses same time)

### 9.3 Manual Validation
- [ ] Run all 5 scenarios in UI
- [ ] Verify timelines make sense (no negative waits, valid times)
- [ ] Verify station queues are chronological
- [ ] Check that scenario 4 (operator weight=2.0) shows operator fairness
- [ ] Verify scenario 5 (worst case) handles congestion

---

## Phase 10: Deployment

### 10.1 Prepare for Deployment
- [ ] Ensure requirements.txt is complete
- [ ] Test fresh install in clean environment
- [ ] Verify all scenarios load without errors
- [ ] Check app runs on default Streamlit port

### 10.2 Deploy to Streamlit Cloud
- [ ] Create public GitHub repository
- [ ] Push all code and scenarios
- [ ] Connect repo to Streamlit Community Cloud
- [ ] Configure app settings (main file: app.py)
- [ ] Test deployed app with all scenarios
- [ ] Verify hosted URL is accessible

### 10.3 Final Checks
- [ ] Test hosted app on different browsers
- [ ] Verify all 5 scenarios work on hosted version
- [ ] Check that tables render correctly
- [ ] Ensure no errors in Streamlit Cloud logs

---

## Phase 11: Submission

### 11.1 Repository Cleanup
- [ ] Remove any debug code or commented-out sections
- [ ] Ensure .gitignore is correct (no venv, __pycache__)
- [ ] Verify README and ARCHITECTURE are complete
- [ ] Add LICENSE file (MIT or similar)

### 11.2 Submit
- [ ] Fill out submission form with:
  - [ ] Hosted Streamlit URL
  - [ ] GitHub repo URL
  - [ ] Scheduler approach description
  - [ ] Brief notes about build
- [ ] Double-check both URLs are public and accessible
- [ ] Test URLs in incognito mode

---

## Optional Enhancements (If Time Permits)

### Nice-to-Have Features
- [ ] Add CSV export for schedules
- [ ] Add validation error messages in UI
- [ ] Add visualization: Gantt chart of charger usage
- [ ] Add "Compare Scenarios" view (side-by-side)
- [ ] Add weight sliders in UI (vs editing JSON)

### Code Quality
- [ ] Increase test coverage to >80%
- [ ] Add type checking with mypy
- [ ] Add linting with ruff or pylint
- [ ] Add pre-commit hooks

---

## Task Execution Notes

**Priority**: Complete phases 1-10 before any optional enhancements.

**Testing strategy**: Test incrementally after each phase. Don't wait until the end.

**Time allocation** (3-4 days):
- Day 1: Phases 1-3 (foundation, constraints, plan generation)
- Day 2: Phases 4-6 (simulator, objectives, scheduler)
- Day 3: Phases 7-9 (UI, documentation, testing)
- Day 4: Phase 10-11 (deployment, submission) + buffer for fixes

**Risk mitigation**:
- If simulator is complex, simplify to FIFO-only first
- If greedy assignment is slow, start with random assignment
- If UI is taking too long, use simple st.write() instead of fancy tables
- Always have a working version to submit, even if not perfect
