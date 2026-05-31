# Bus Charging Scheduler - Requirements

## Overview
Build a Python + Streamlit application that schedules electric bus charging along a fixed route, optimizing for tunable objectives while respecting hard constraints.

## Core Domain Model

### Physical World
- **Route**: Fixed sequence of locations (origin → stations → destination)
- **Station**: Location with N chargers (initially N=1, must scale to N>1)
- **Bus**: Vehicle with battery capacity, operator affiliation, scheduled departure
- **Charger**: Resource at a station (1 bus at a time, fixed charge duration)

### Key Insight
The world will change. Today: 1 route, 4 stations, 1 charger each, 3 operators. Tomorrow: multiple routes sharing stations, variable chargers per station, time-of-day pricing, driver shifts, priority buses.

**Design principle**: Configuration over code. The data structure must capture the world; the engine must be rule-agnostic.

---

## User Stories

### US-1: Load Scenario
**As a** scheduler operator  
**I want to** select a scenario from a dropdown  
**So that** I can see the charging plan for that specific departure schedule

**Acceptance Criteria:**
- 1.1 Dropdown shows all 5 scenarios by name
- 1.2 Selecting a scenario loads its configuration and displays input data
- 1.3 Input data shows: buses (ID, operator, direction, departure time), route structure, weights

### US-2: View Charging Plan Per Bus
**As a** scheduler operator  
**I want to** see each bus's complete timeline  
**So that** I can verify the plan is valid and understand delays

**Acceptance Criteria:**
- 2.1 For each bus, display: bus ID, operator, direction, departure time
- 2.2 For each charging stop: station name, arrival time, wait time (if any), charging start time, charging end time
- 2.3 Display final arrival time at destination
- 2.4 Timeline must respect 240km range constraint (never exceed range between charges)

### US-3: View Charging Queue Per Station
**As a** scheduler operator  
**I want to** see the order buses charged at each station  
**So that** I can understand contention and verify fairness

**Acceptance Criteria:**
- 3.1 For each station (A, B, C, D), show chronological list of buses that charged there
- 3.2 For each entry: bus ID, arrival time, charging start time, charging end time
- 3.3 Clearly show wait times when buses queue

### US-4: Respect Hard Constraints
**As a** system  
**I must** enforce physical and safety rules  
**So that** schedules are valid and safe

**Acceptance Criteria:**
- 4.1 Battery never exceeds 240km range between consecutive charges
- 4.2 Only one bus per charger at a time
- 4.3 Charging always takes exactly 25 minutes and fills to full
- 4.4 Buses visit stations in route order (no backtracking)
- 4.5 All buses must complete their journey

### US-5: Optimize Soft Objectives
**As a** scheduler operator  
**I want to** tune weights for individual, operator, and overall objectives  
**So that** I can balance competing priorities

**Acceptance Criteria:**
- 5.1 Three weights: `individual_weight`, `operator_weight`, `overall_weight`
- 5.2 Weights are defined in scenario configuration (not hardcoded)
- 5.3 Changing weights produces different (defensible) schedules
- 5.4 Individual: minimize max wait time for any single bus
- 5.5 Operator: balance wait times across operators' fleets
- 5.6 Overall: minimize total wait time across all buses

### US-6: Extensible Rule System
**As a** developer  
**I want to** add new rules without modifying the scheduler engine  
**So that** the system scales as requirements evolve

**Acceptance Criteria:**
- 6.1 Rules are defined as pluggable objects/classes
- 6.2 Adding a new rule = writing a new rule class + registering it
- 6.3 No changes to core scheduling logic when adding rules
- 6.4 Rules can be hard (constraints) or soft (objectives)

### US-7: Extensible Data Model
**As a** developer  
**I want to** change world parameters through data alone  
**So that** I don't rewrite code for every operational change

**Acceptance Criteria:**
- 7.1 Adding a station: update route configuration
- 7.2 Changing chargers per station: update station configuration
- 7.3 Adding a new operator: add to scenario bus list
- 7.4 Changing segment distances: update route configuration
- 7.5 Adding a new route: create new route configuration
- 7.6 Multiple routes sharing stations: reference same station IDs

---

## Anticipated Future Changes

### Tier 1: Data-only changes (zero code changes)
1. **More stations**: Add station to route segments list
2. **More chargers per station**: Change `num_chargers` from 1 to N
3. **Different segment distances**: Update distance values in route config
4. **More buses**: Add rows to scenario bus list
5. **New operators**: Add operator name to bus entry
6. **Different weights**: Change weight values in scenario config
7. **Different battery capacity**: Change `battery_capacity_km` in config
8. **Different charging time**: Change `charge_duration_minutes` in config
9. **Variable speed**: Add `speed_kmh` to config

### Tier 2: New rule class only (no engine changes)
10. **Priority buses**: Add `PriorityBusRule` class that scores buses by priority flag
11. **Time-of-day electricity costs**: Add `TimeOfDayPricingRule` that penalizes charging during peak hours
12. **Operator quotas**: Add `OperatorQuotaRule` that enforces max wait per operator
13. **Station preferences**: Add `StationPreferenceRule` that prefers certain stations
14. **Driver shift constraints**: Add `DriverShiftRule` that respects shift boundaries

### Tier 3: Minimal engine extension (new constraint type)
15. **Multiple routes sharing stations**: Extend scheduler to handle multiple route objects
16. **Partial charging**: Extend charging model to support non-full charges
17. **Dynamic charger availability**: Add time-based charger availability windows

---

## Data Structure Design

### Scenario File Format (JSON)
```json
{
  "name": "Scenario 1 - Even Spacing",
  "route": {
    "id": "bengaluru-kochi",
    "origin": "Bengaluru",
    "destination": "Kochi",
    "segments": [
      {"from": "Bengaluru", "to": "A", "distance_km": 100},
      {"from": "A", "to": "B", "distance_km": 120},
      {"from": "B", "to": "C", "distance_km": 100},
      {"from": "C", "to": "D", "distance_km": 120},
      {"from": "D", "to": "Kochi", "distance_km": 100}
    ],
    "stations": [
      {"id": "A", "name": "Station A", "num_chargers": 1},
      {"id": "B", "name": "Station B", "num_chargers": 1},
      {"id": "C", "name": "Station C", "num_chargers": 1},
      {"id": "D", "name": "Station D", "num_chargers": 1}
    ]
  },
  "buses": [
    {
      "id": "bus-BK-01",
      "operator": "kpn",
      "origin": "Bengaluru",
      "destination": "Kochi",
      "departure_time": "19:00"
    }
  ],
  "parameters": {
    "battery_capacity_km": 240,
    "charge_duration_minutes": 25,
    "speed_kmh": 60
  },
  "weights": {
    "individual": 1.0,
    "operator": 1.0,
    "overall": 1.0
  }
}
```

**Why this structure:**
- Route is self-contained: segments + stations. Adding a station = adding to both lists.
- Stations have `num_chargers` — changing from 1 to N is one field change.
- Buses reference origin/destination by name — works for multiple routes.
- Parameters are explicit — no magic numbers in code.
- Weights are top-level — one obvious place.

### Output Data Structure
```json
{
  "bus_timelines": [
    {
      "bus_id": "bus-BK-01",
      "operator": "kpn",
      "direction": "Bengaluru→Kochi",
      "departure_time": "19:00",
      "charging_stops": [
        {
          "station": "A",
          "arrival_time": "20:40",
          "wait_minutes": 0,
          "charge_start": "20:40",
          "charge_end": "21:05"
        },
        {
          "station": "C",
          "arrival_time": "23:05",
          "wait_minutes": 5,
          "charge_start": "23:10",
          "charge_end": "23:35"
        }
      ],
      "arrival_time": "01:15",
      "total_wait_minutes": 5
    }
  ],
  "station_queues": {
    "A": [
      {
        "bus_id": "bus-BK-01",
        "arrival_time": "20:40",
        "charge_start": "20:40",
        "charge_end": "21:05"
      }
    ]
  }
}
```

---

## Scheduler Architecture

### Approach: Event-Driven Simulation with Pluggable Cost Functions

**Why this approach:**
- **Scalable**: Handles any number of buses, stations, chargers
- **Extensible**: New rules = new cost function classes
- **Testable**: Deterministic, reproducible
- **Transparent**: Full timeline visibility

### Core Components

#### 1. Scheduler Engine (rule-agnostic)
- Input: Scenario configuration
- Output: Bus timelines + station queues
- Algorithm:
  1. For each bus, determine candidate charging plans (which stations to use)
  2. Filter plans that violate hard constraints (range, route order)
  3. Simulate each valid plan using event queue
  4. Score each plan using pluggable cost functions
  5. Select plan with best score

#### 2. Constraint System (hard rules)
```python
class Constraint(ABC):
    @abstractmethod
    def is_valid(self, plan: ChargingPlan, context: Context) -> bool:
        pass

class RangeConstraint(Constraint):
    # Ensures battery never exceeds capacity between charges
    pass

class RouteOrderConstraint(Constraint):
    # Ensures stations visited in route order
    pass
```

#### 3. Objective System (soft rules)
```python
class Objective(ABC):
    @abstractmethod
    def score(self, schedule: Schedule, context: Context) -> float:
        pass

class IndividualWaitObjective(Objective):
    # Penalizes max wait time for any single bus
    pass

class OperatorFairnessObjective(Objective):
    # Penalizes variance in wait times across operators
    pass

class OverallEfficiencyObjective(Objective):
    # Penalizes total wait time
    pass
```

#### 4. Event Simulator
- Priority queue of events: bus arrives at station, charging starts, charging ends
- Charger allocation: FIFO queue per station (can be replaced with priority queue)
- Deterministic: same input → same output

### Adding a New Rule (Example)

**Scenario**: Add priority bus rule (emergency buses skip queue)

**Step 1**: Add priority flag to bus data
```json
{"id": "bus-BK-01", "operator": "kpn", "priority": true, ...}
```

**Step 2**: Create rule class
```python
class PriorityBusObjective(Objective):
    def score(self, schedule: Schedule, context: Context) -> float:
        # Penalize schedules where priority buses wait
        penalty = 0
        for bus in schedule.buses:
            if bus.priority and bus.total_wait > 0:
                penalty += bus.total_wait * 10  # Heavy penalty
        return -penalty
```

**Step 3**: Register rule in config
```json
"weights": {
  "individual": 1.0,
  "operator": 1.0,
  "overall": 1.0,
  "priority": 5.0
}
```

**Zero changes to scheduler engine.**

---

## Technical Stack

- **Python 3.10+**: Type hints, dataclasses
- **Streamlit**: UI (zero frontend code)
- **Pydantic**: Data validation for scenario files
- **No database**: In-memory state
- **No external APIs**: Self-contained

---

## Non-Functional Requirements

### Performance
- Schedule 20 buses in < 5 seconds
- UI loads in < 2 seconds

### Code Quality
- Type hints on all functions
- Docstrings on public APIs
- Unit tests for constraints and objectives
- Integration test for each scenario

### Documentation
- README.md: How to run, how to change weights, how to add rules
- ARCHITECTURE.md: Design decisions, anticipated changes, examples
- Inline comments for non-obvious logic

---

## Out of Scope (Explicitly Not Building)

- Real-time updates (static schedules only)
- User authentication
- Database persistence
- Maps / visualizations beyond tables
- Mobile responsiveness
- Multi-route scheduling (single route only for now, but data model supports it)

---

## Success Criteria

### Must Have
- ✅ All 5 scenarios load and produce valid schedules
- ✅ Hard constraints always respected (range, charger capacity)
- ✅ Changing weights produces different schedules
- ✅ UI shows per-bus timeline and per-station queue
- ✅ Adding a station requires only data changes
- ✅ Adding a rule requires only new class + registration

### Should Have
- ✅ Schedules are defensible (not obviously suboptimal)
- ✅ Code is readable and well-structured
- ✅ Documentation is clear and honest

### Nice to Have
- Unit tests for core logic
- Validation errors for invalid scenarios
- Export schedule to CSV

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scheduler produces invalid plans | High | Comprehensive constraint validation + tests |
| Performance degrades with scale | Medium | Profile early, optimize hot paths |
| Data model doesn't handle future changes | High | Design for extensibility from day 1 |
| Streamlit hosting issues | Medium | Test deployment early, have local fallback |

---

## Timeline (3-4 days)

### Day 1: Foundation
- Data model design + validation (Pydantic schemas)
- Scenario files for all 5 scenarios
- Basic constraint system

### Day 2: Scheduler Core
- Event simulator
- Charging plan generation
- Constraint validation
- Basic greedy scheduler

### Day 3: Objectives + Optimization
- Pluggable objective system
- Implement 3 core objectives
- Tune scoring functions
- Test all scenarios

### Day 4: UI + Documentation
- Streamlit UI (scenario picker, tables)
- README.md + ARCHITECTURE.md
- Deploy to Streamlit Cloud
- Final testing

---

## Open Questions / Assumptions

### Assumptions Made
1. **Speed is constant**: 60 km/h for all buses (configurable)
2. **Charging is atomic**: Bus occupies charger for full 25 min, no interruptions
3. **FIFO at stations**: When multiple buses arrive simultaneously, first-come-first-served (can be overridden by objectives)
4. **No charger failures**: All chargers always available
5. **No traffic**: Travel time = distance / speed (deterministic)
6. **Buses always choose optimal plan**: No suboptimal human decisions

### Design Decisions to Defend
1. **Why event simulation vs constraint solver (CP/MIP)?**
   - Event sim is transparent, debuggable, and fast enough for this scale
   - CP/MIP is overkill for 20 buses and harder to extend with custom rules
   - If scale grows to 1000s of buses, reconsider

2. **Why JSON for scenarios vs YAML/TOML?**
   - JSON has native Python support, Pydantic validation
   - Structured enough for nested data
   - Easy to generate programmatically

3. **Why greedy scheduler vs optimal search?**
   - Greedy with good heuristics is fast and "good enough"
   - Optimal search (branch-and-bound) is exponential in buses
   - Real world has uncertainty anyway — optimal is illusory

4. **Why pluggable objectives vs single cost function?**
   - Separation of concerns: each objective is independently testable
   - Easy to add/remove objectives without touching others
   - Weights are explicit and tunable

---

## Next Steps

1. Review this requirements doc
2. Create design.md with detailed architecture
3. Create tasks.md with implementation checklist
4. Begin implementation
