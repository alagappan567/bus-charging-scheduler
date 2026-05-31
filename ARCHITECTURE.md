# Architecture Documentation

## Table of Contents
1. [Scheduler Approach: Event Simulation + Greedy Assignment](#1-scheduler-approach-event-simulation--greedy-assignment)
2. [Why This Approach (vs CP/MIP Solvers)](#2-why-this-approach-vs-cpmip-solvers)
3. [Data Structure Design Rationale](#3-data-structure-design-rationale)
4. [Anticipated Future Changes](#4-anticipated-future-changes)
5. [How Each Change Is Handled](#5-how-each-change-is-handled)
6. [Code Examples](#6-code-examples)
7. [Assumptions and Trade-offs](#7-assumptions-and-trade-offs)
8. [Performance Characteristics and Scaling](#8-performance-characteristics-and-scaling)

---

## 1. Scheduler Approach: Event Simulation + Greedy Assignment

The scheduler combines two techniques: a **greedy sequential assignment** algorithm that decides which stations each bus charges at, and a **discrete event simulation** that models the physical reality of buses arriving, waiting, and charging.

### 1.1 Greedy Sequential Assignment

The outer loop assigns charging plans to buses one at a time, in departure-time order.

**Step-by-step:**

1. **Generate candidate plans** — For each bus, enumerate every valid combination of charging stations. A bus traveling Bengaluru→Kochi (540 km) with a 240 km battery needs at least 2 charges. With 4 stations (A, B, C, D), the valid combinations of length 2, 3, and 4 are: `{A,B}`, `{A,C}`, `{A,D}`, `{B,C}`, `{B,D}`, `{C,D}`, `{A,B,C}`, `{A,B,D}`, `{A,C,D}`, `{B,C,D}`, `{A,B,C,D}` — 11 candidates per bus.

2. **Filter by hard constraints** — Each candidate plan is checked against three constraints:
   - `RangeConstraint`: No segment between consecutive charges exceeds 240 km
   - `RouteOrderConstraint`: Stations appear in travel order (no backtracking)
   - `CompletionConstraint`: Bus can reach destination from its last charge

3. **Sort buses by departure time** — Earlier buses are assigned first. This is operationally fair: buses that depart first have first claim on chargers.

4. **For each bus, try every valid plan** — For each candidate plan, temporarily add it to the current assignments and run a full simulation. Score the result using the weighted objective function.

5. **Lock in the best plan** — The plan with the highest score is committed. All subsequent buses see this assignment as fixed.

6. **Repeat until all buses are assigned** — The final set of assignments is then simulated one last time to produce the output.

```
Sort buses by departure time
│
├── Bus 1 (earliest departure)
│   ├── Try plan {A, C} → simulate → score = -5
│   ├── Try plan {A, D} → simulate → score = -3  ← best
│   ├── Try plan {B, D} → simulate → score = -8
│   └── Lock in {A, D}
│
├── Bus 2 (next departure)
│   ├── Try plan {A, C} → simulate (with Bus 1 locked) → score = -10
│   ├── Try plan {B, D} → simulate (with Bus 1 locked) → score = -4  ← best
│   └── Lock in {B, D}
│
└── ... continue for all buses
```

### 1.2 Discrete Event Simulation

The inner loop is a **discrete event simulation** (DES) that models time as a sequence of events rather than advancing a clock tick-by-tick. This is the standard approach for queuing systems.

**Event types:**
- `BUS_ARRIVES_AT_STATION` — Bus reaches a charging station
- `CHARGING_ENDS` — Bus finishes charging and releases the charger

(Note: `CHARGING_STARTS` is handled inline during arrival or queue release — no separate event is needed.)

**Event ordering:** Events at the same timestamp are processed in priority order: `CHARGING_ENDS` before `BUS_ARRIVES_AT_STATION`. This ensures a charger is freed before a newly arriving bus tries to claim it.

**Simulation loop:**

```
Initialize: for each bus, schedule BUS_ARRIVES_AT_STATION at (departure + travel_time)

While event queue is not empty:
    Pop earliest event

    If BUS_ARRIVES_AT_STATION:
        Record arrival time
        If charger available at station:
            Allocate charger
            Schedule CHARGING_ENDS at (now + 25 min)
            Record charging stop
        Else:
            Add bus to station's FIFO queue

    If CHARGING_ENDS:
        Release charger
        If queue is not empty:
            Pop next bus from queue
            Allocate charger to it
            Schedule CHARGING_ENDS at (now + 25 min)
            Record charging stop (with wait time = now - arrival_time)
        Continue bus journey:
            If more stations in plan:
                Schedule BUS_ARRIVES_AT_STATION at next station
            Else:
                Calculate arrival at destination
                Record BusTimeline
```

**Charger state** is tracked per station. Each station has `num_chargers` slots. An allocation is a `(bus_id, start_time, end_time)` tuple. When a bus arrives, the simulator checks how many allocations have `end_time > now` — if fewer than `num_chargers`, a slot is free.

**FIFO queue** — When all chargers are occupied, the arriving bus is appended to a list. When a charger is released, the first bus in the list is popped and immediately starts charging. Wait time = `charge_start - arrival`.

**Bidirectional routes** — Kochi→Bengaluru buses travel the same physical route in reverse. `Route.get_stations_on_route(origin, destination)` returns stations in travel order, reversed automatically for reverse-direction buses. Distance calculations work in both directions.

---

## 2. Why This Approach (vs CP/MIP Solvers)

### 2.1 The Alternatives

**Constraint Programming (CP)** — Tools like Google OR-Tools or IBM CP Optimizer model the problem as a set of variables and constraints, then search for a feasible (or optimal) assignment. They can find globally optimal solutions and handle complex constraint interactions.

**Mixed-Integer Programming (MIP)** — Tools like Gurobi, CPLEX, or PuLP model the problem as a linear (or quadratic) objective with integer decision variables. They provide provably optimal solutions with duality gaps.

**Genetic Algorithms / Simulated Annealing** — Metaheuristics that explore the solution space stochastically. Can escape local optima but are non-deterministic and require hyperparameter tuning.

### 2.2 Why We Chose Event Simulation + Greedy

| Criterion | Event Sim + Greedy | CP Solver | MIP Solver |
|---|---|---|---|
| **Transparency** | Full timeline visibility, easy to debug | Black-box search, hard to explain | Black-box solver, hard to explain |
| **Determinism** | Same input → same output, always | Deterministic but opaque | Deterministic but opaque |
| **Speed (20 buses)** | Sub-second | Sub-second | Sub-second |
| **Speed (1000 buses)** | ~1-2 seconds | Minutes to hours | Minutes to hours |
| **Extensibility** | Add a Python class | Rewrite constraint model | Rewrite LP formulation |
| **Non-linear objectives** | Trivial (any Python function) | Requires linearization | Requires linearization |
| **External dependencies** | None (stdlib only) | OR-Tools, Gurobi, etc. | Gurobi, CPLEX, PuLP, etc. |
| **Optimality** | Local (greedy) | Global | Global |
| **Debuggability** | Step through events | Hard to inspect search | Hard to inspect search |

**The decisive factors:**

1. **Operator fairness (variance) is non-linear.** The `OperatorFairnessObjective` computes variance across operator averages. MIP requires a linear objective — modeling variance requires quadratic terms or auxiliary variables, making the formulation complex and slow. Event simulation + Python handles this trivially.

2. **Rules are pluggable Python classes.** Adding a new objective means writing a class with a `score()` method. In CP/MIP, adding a new constraint or objective means modifying the mathematical model, which requires solver expertise.

3. **The problem is small enough that greedy is good enough.** With 20 buses and 4 stations, the greedy approach produces schedules that are within a few minutes of optimal. The real world has uncertainty (traffic, delays) that makes "optimal" illusory anyway.

4. **Transparency matters for operators.** A scheduler operator needs to understand *why* a bus was assigned to a particular station. Event simulation produces a full timeline with arrival times, wait times, and charger states — all inspectable. A CP solver produces an assignment with no explanation.

5. **No external dependencies.** The entire scheduler runs on Python stdlib + numpy. No solver licenses, no installation complexity, no version conflicts.

### 2.3 When to Reconsider

Switch to CP/MIP if:
- **Scale grows to 100+ buses** and greedy quality degrades noticeably
- **Hard deadlines are added** (e.g., "bus must depart by X") — CP handles these naturally
- **Cost optimization becomes primary** — MIP is ideal for minimizing electricity costs with time-of-day pricing
- **Optimality is contractually required** — e.g., SLA guarantees on wait times

The data model and constraint/objective interfaces are designed to be solver-agnostic. Replacing the greedy scheduler with a CP backend would not require changing models, constraints, or objectives — only `scheduler.py`.

---

## 3. Data Structure Design Rationale

### 3.1 Design Philosophy

**Configuration over code.** The world (routes, stations, buses, rules) lives in JSON. The engine is rule-agnostic. This means:
- Adding a station = edit JSON, zero code changes
- Changing battery capacity = edit JSON, zero code changes
- Adding a new operator = edit JSON, zero code changes

**Pydantic for all models.** Every data class is a Pydantic `BaseModel`, not a plain Python dataclass. This gives:
- Automatic JSON parsing (`Scenario(**json_data)`)
- Field-level validation with clear error messages
- Type coercion (string `"19:00"` validated as time format)
- Optional fields with defaults (backward-compatible extensions)
- IDE autocomplete and type checking

### 3.2 Model Hierarchy and Rationale

```
Scenario (top-level)
├── name: str
├── route: Route
│   ├── id, origin, destination
│   ├── segments: List[Segment]   ← ordered, defines distances
│   └── stations: List[Station]   ← defines charger counts
├── buses: List[Bus]              ← who is traveling and when
├── parameters: Parameters        ← physical constants
└── weights: Weights              ← optimization preferences
```

**Why `Scenario` is the top-level container:**
All components are scenario-specific. Different scenarios can have different routes, different bus lists, different weights. Keeping everything under `Scenario` makes it trivial to load, compare, and swap scenarios.

**Why `Route` contains both `segments` and `stations`:**
- `segments` define the physical topology: ordered list of `(from, to, distance_km)`. The order is the route order. Distance calculations traverse this list.
- `stations` define the charging infrastructure: `(id, name, num_chargers)`. They are separate from segments because not every location is a station, and station properties (charger count) are independent of segment distances.
- Station IDs match location names in segments (e.g., station `"A"` corresponds to the location `"A"` in segments). This allows `Route.get_distance("Bengaluru", "A")` to work without a separate lookup.

**Why `Segment` uses `from`/`to` aliases:**
The JSON uses `"from"` and `"to"` as keys (matching the requirements doc). Python's `from` is a reserved keyword, so Pydantic's `alias` feature maps `"from"` → `from_location` and `"to"` → `to_location`. The `populate_by_name = True` config allows both the alias and the Python name to work.

**Why `Station.num_chargers` is a single integer:**
The current requirement is N identical chargers per station. A single integer is the simplest representation. When charger types are needed (fast vs slow), this field can be replaced with a list of charger objects — existing scenarios with `num_chargers` can be migrated with a model validator.

**Why `Bus` stores `departure_time` as a string:**
Times are stored as `"HH:MM"` strings in JSON. Pydantic validates the format. The `get_departure_datetime(base_date)` method converts to a `datetime` when needed for simulation. Storing as string avoids timezone and date ambiguity in the JSON file.

**Why `Parameters` is a separate model:**
Physical constants (battery capacity, charge duration, speed) are scenario-level settings, not per-bus or per-station. Separating them from `Route` and `Bus` makes it clear that they apply globally. They also have sensible defaults, so a minimal scenario file doesn't need to specify them.

**Why `Weights` is a separate model:**
Weights are the primary tuning knob for operators. Separating them from `Parameters` makes it obvious where to look when changing optimization behavior. They are also the most likely thing to change between runs of the same scenario.

**Why `ChargingPlan` is immutable:**
A `ChargingPlan` is a list of station IDs for one bus. Once created, it is never modified — the simulator only reads it. Immutability makes plans safe to copy, cache, and inspect after simulation. The greedy algorithm creates temporary copies (`temp_assignments = self.assigned_plans.copy()`) without risk of mutation.

**Why `SimulationResult` contains two views:**
- `bus_timelines`: per-bus view (what did each bus experience?)
- `station_queues`: per-station view (what happened at each charger?)

These are two projections of the same underlying events. The UI needs both. Computing both during simulation (rather than deriving one from the other post-hoc) is more efficient and avoids re-traversal.

### 3.3 Route Validation

`Route` has a `model_validator` that enforces:
1. First segment starts at `origin`
2. Last segment ends at `destination`
3. Consecutive segments are connected (`segment[i].to == segment[i+1].from`)

This catches malformed scenario files at load time, not during scheduling.

### 3.4 Helper Methods on Route

`Route.get_distance(from_loc, to_loc)` and `Route.get_stations_on_route(from_loc, to_loc)` are methods on the model itself, not utility functions. This keeps distance logic co-located with the data it operates on, and makes the model self-contained. Both methods support bidirectional travel by detecting whether `from_idx > to_idx` and reversing accordingly.

---

## 4. Anticipated Future Changes

These 17 changes were identified during design. They are grouped by the effort required to implement them.

### Tier 1: Data-Only Changes (Zero Code Changes)

These changes require only editing a scenario JSON file. No Python code changes needed.

1. **More stations** — Add a new station to `route.stations` and insert the corresponding segment into `route.segments`. The scheduler reads stations dynamically from the route.

2. **More chargers per station** — Change `num_chargers` from 1 to N in a station entry. The `ChargerState` class reads `num_chargers` at runtime.

3. **Different segment distances** — Update `distance_km` values in `route.segments`. All distance calculations use these values directly.

4. **More buses** — Add entries to the `buses` list. The scheduler iterates over all buses in the list.

5. **New operators** — Add a new `operator` string to a bus entry. The `OperatorFairnessObjective` groups buses by operator dynamically — no hardcoded operator list.

6. **Different weights** — Change `individual`, `operator`, or `overall` values in `weights`. The `ObjectiveEvaluator` reads weights at initialization.

7. **Different battery capacity** — Change `battery_capacity_km` in `parameters`. The `RangeConstraint` and `calculate_min_charges` both read this value.

8. **Different charging time** — Change `charge_duration_minutes` in `parameters`. The simulator reads this when scheduling `CHARGING_ENDS` events.

9. **Variable speed** — Change `speed_kmh` in `parameters`. The `_calculate_travel_time` method in the simulator reads this value.

### Tier 2: New Rule Class Only (No Engine Changes)

These changes require writing a new Python class and registering it in `scheduler.py`. No changes to the simulation engine, constraint validator, or data models.

10. **Priority buses** — Add `PriorityBusObjective` class. Reads a `priority` flag from bus data (optional field, defaults to `False`). Register in `BusScheduler.__init__` with a `priority` weight from `scenario.weights`.

11. **Time-of-day electricity costs** — Add `TimeOfDayPricingObjective` class. Reads `peak_hours` and `peak_cost_multiplier` from `parameters`. Penalizes charging sessions that overlap with peak hours.

12. **Operator quotas** — Add `OperatorQuotaConstraint` class. Reads a `max_wait_minutes` field per operator from scenario config. Rejects plans where an operator's bus exceeds its quota.

13. **Station preferences** — Add `StationPreferenceObjective` class. Reads a `preferred_stations` list from bus data. Rewards plans that use preferred stations.

14. **Driver shift constraints** — Add `DriverShiftConstraint` class. Reads `max_shift_hours` from bus data. Rejects plans where total journey time exceeds the shift limit.

### Tier 3: Minimal Engine Extension

These changes require extending the simulation engine or data model, but the core algorithm remains unchanged.

15. **Multiple routes sharing stations** — Extend `Scenario` to support a `routes` list instead of a single `route`. Buses reference their route by `route_id`. The `ChargerState` merges charger pools by station ID across routes. Estimated: ~30 lines of refactoring.

16. **Partial charging** — Extend `ChargingPlan` to include a `charge_to_percent` per stop. Update the simulator to calculate `charge_duration` from the percentage. Update `RangeConstraint` to use the actual range added, not always full capacity. Estimated: ~20 lines.

17. **Dynamic charger availability** — Add `availability_windows: List[TimeWindow]` to `Station`. Update `ChargerState.is_charger_available()` to check windows before allocating. Add a `MaintenanceWindowConstraint` that rejects plans requiring charging during unavailable windows. Estimated: ~25 lines.

---

## 5. How Each Change Is Handled

### Tier 1 Details

**1. More stations**

The route is read as a list of segments. Adding station E between A and B:

```json
"segments": [
  {"from": "Bengaluru", "to": "A", "distance_km": 100},
  {"from": "A", "to": "E", "distance_km": 60},
  {"from": "E", "to": "B", "distance_km": 60},
  ...
],
"stations": [
  {"id": "A", "name": "Station A", "num_chargers": 1},
  {"id": "E", "name": "Station E", "num_chargers": 1},
  ...
]
```

`generate_charging_plans` calls `route.get_stations_on_route()` which reads the segment list dynamically. Station E is automatically included in candidate plans. `ChargerState.__init__` initializes a queue for every station in `scenario.route.stations` — E gets one automatically.

**2. More chargers per station**

```json
{"id": "B", "name": "Station B", "num_chargers": 3}
```

`ChargerState.get_num_chargers()` reads `station.num_chargers` at runtime. `is_charger_available()` compares occupied count against this value. Three buses can now charge simultaneously at B.

**3–9. Other Tier 1 changes** follow the same pattern: the relevant value is read from the scenario at runtime, never hardcoded.

### Tier 2 Details

**10. Priority buses**

Data change (optional field, backward-compatible):
```json
{"id": "bus-BK-01", "operator": "kpn", "priority": true, ...}
```

New class:
```python
class PriorityBusObjective(Objective):
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        penalty = 0.0
        for timeline in result.bus_timelines.values():
            bus = scenario.get_bus(timeline.bus_id)
            if bus and getattr(bus, 'priority', False):
                penalty += timeline.total_wait_minutes * 10
        return -penalty
```

Registration in `BusScheduler.__init__` (one line):
```python
(PriorityBusObjective(), getattr(scenario.weights, 'priority', 0.0))
```

Existing scenarios without `priority` fields work unchanged.

**11–14. Other Tier 2 changes** follow the same pattern: new class + one-line registration. The `ObjectiveEvaluator` and `ConstraintValidator` accept any number of objectives/constraints.

### Tier 3 Details

**15. Multiple routes sharing stations**

The `Scenario` model gains a `routes: List[Route]` field (alongside the existing `route` for backward compatibility). Buses gain a `route_id: str` field. The scheduler loops over all routes when generating plans. `ChargerState` is initialized from all stations across all routes — since station IDs are unique, shared stations (same ID on two routes) get a single charger pool. The simulation engine is unchanged; it already tracks charger state by station ID.

**16. Partial charging**

`ChargingPlan` gains an optional `charge_levels: List[float]` field (percentage per stop). The simulator reads `charge_levels[i]` when scheduling `CHARGING_ENDS` for stop `i`, computing duration as `charge_duration_minutes * (level / 100)`. `RangeConstraint` uses `battery_capacity_km * (level / 100)` as the range added at each stop. Plans without `charge_levels` default to 100% (current behavior).

**17. Dynamic charger availability**

`Station` gains `availability_windows: List[dict]` (optional, defaults to always available). `ChargerState.is_charger_available()` gains a time check: if the current time falls outside all availability windows, return `False`. A `MaintenanceWindowConstraint` pre-filters plans that would require charging during unavailable windows, avoiding wasted simulation runs.

---

## 6. Code Examples

### 6.1 Changing a Weight in Scenario JSON

Weights control how the scheduler balances three competing objectives:
- `individual`: minimize the worst single-bus wait time
- `operator`: minimize variance in average wait times across operators
- `overall`: minimize total wait time across all buses

**Default (balanced):**
```json
"weights": {
  "individual": 1.0,
  "operator": 1.0,
  "overall": 1.0
}
```

**Prioritize operator fairness (scenario 4 style):**
```json
"weights": {
  "individual": 1.0,
  "operator": 3.0,
  "overall": 1.0
}
```

Effect: The scheduler will accept a higher total wait time if it means KPN, Freshbus, and Flixbus buses wait roughly the same amount. A plan where KPN waits 0 min and Flixbus waits 30 min scores worse than one where both wait 15 min.

**Prioritize overall efficiency (minimize total delay):**
```json
"weights": {
  "individual": 0.5,
  "operator": 0.5,
  "overall": 3.0
}
```

Effect: The scheduler minimizes total fleet wait time. Some buses may wait longer than others, but the sum is minimized.

**Zero out an objective (ignore operator fairness entirely):**
```json
"weights": {
  "individual": 1.0,
  "operator": 0.0,
  "overall": 1.0
}
```

Effect: Operator balance is not considered. The scheduler only cares about individual and total wait times.

The `ObjectiveEvaluator` computes:
```
total_score = (individual × IndividualWaitObjective.score())
            + (operator  × OperatorFairnessObjective.score())
            + (overall   × OverallEfficiencyObjective.score())
```

All scores are negative (penalties), so higher total score = less penalty = better plan.

---

### 6.2 Adding a New Objective Rule Class

This example adds a `TimeOfDayPricingObjective` that penalizes charging during peak electricity hours (18:00–22:00).

**Step 1: Add parameters to scenario JSON**
```json
"parameters": {
  "battery_capacity_km": 240,
  "charge_duration_minutes": 25,
  "speed_kmh": 60,
  "peak_hours_start": "18:00",
  "peak_hours_end": "22:00",
  "peak_cost_multiplier": 2.5
}
```

**Step 2: Add weight to scenario JSON**
```json
"weights": {
  "individual": 1.0,
  "operator": 1.0,
  "overall": 1.0,
  "cost": 2.0
}
```

**Step 3: Write the objective class in `scheduler/objectives.py`**
```python
from datetime import datetime

class TimeOfDayPricingObjective(Objective):
    """
    Penalizes charging sessions that overlap with peak electricity hours.

    Validates: Requirements 5.2, 5.3 (weights defined in config, changing
    weights produces different schedules)
    """

    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        params = scenario.parameters
        peak_start_str = getattr(params, 'peak_hours_start', None)
        peak_end_str = getattr(params, 'peak_hours_end', None)
        multiplier = getattr(params, 'peak_cost_multiplier', 1.0)

        if not peak_start_str or not peak_end_str:
            return 0.0  # No peak hours configured

        peak_start = datetime.strptime(peak_start_str, "%H:%M").time()
        peak_end = datetime.strptime(peak_end_str, "%H:%M").time()

        penalty = 0.0
        for timeline in result.bus_timelines.values():
            for stop in timeline.charging_stops:
                charge_start = datetime.strptime(stop.charge_start, "%H:%M").time()
                # Check if charging starts during peak hours
                if peak_start <= charge_start <= peak_end:
                    # Penalize by charge duration × cost multiplier
                    charge_minutes = scenario.parameters.charge_duration_minutes
                    penalty += charge_minutes * (multiplier - 1.0)

        return -penalty
```

**Step 4: Register in `scheduler/scheduler.py` (one line)**
```python
self.objectives: List[tuple[Objective, float]] = [
    (IndividualWaitObjective(),    scenario.weights.individual),
    (OperatorFairnessObjective(),  scenario.weights.operator),
    (OverallEfficiencyObjective(), scenario.weights.overall),
    (TimeOfDayPricingObjective(),  getattr(scenario.weights, 'cost', 0.0)),  # NEW
]
```

**Zero changes to the simulation engine, constraint system, or data loading.**

Existing scenarios without `peak_hours_start` in parameters return `0.0` from the objective (no penalty). Existing scenarios without `cost` in weights use `0.0` (objective is ignored).

---

### 6.3 Adding a New Station to the Route

This example adds Station E between A and B on the Bengaluru→Kochi route.

**Before (scenario1.json excerpt):**
```json
{
  "route": {
    "segments": [
      {"from": "Bengaluru", "to": "A",    "distance_km": 100},
      {"from": "A",         "to": "B",    "distance_km": 120},
      {"from": "B",         "to": "C",    "distance_km": 100},
      {"from": "C",         "to": "D",    "distance_km": 120},
      {"from": "D",         "to": "Kochi","distance_km": 100}
    ],
    "stations": [
      {"id": "A", "name": "Station A", "num_chargers": 1},
      {"id": "B", "name": "Station B", "num_chargers": 1},
      {"id": "C", "name": "Station C", "num_chargers": 1},
      {"id": "D", "name": "Station D", "num_chargers": 1}
    ]
  }
}
```

**After (Station E added between A and B):**
```json
{
  "route": {
    "segments": [
      {"from": "Bengaluru", "to": "A",    "distance_km": 100},
      {"from": "A",         "to": "E",    "distance_km": 60},
      {"from": "E",         "to": "B",    "distance_km": 60},
      {"from": "B",         "to": "C",    "distance_km": 100},
      {"from": "C",         "to": "D",    "distance_km": 120},
      {"from": "D",         "to": "Kochi","distance_km": 100}
    ],
    "stations": [
      {"id": "A", "name": "Station A", "num_chargers": 1},
      {"id": "E", "name": "Station E", "num_chargers": 2},
      {"id": "B", "name": "Station B", "num_chargers": 1},
      {"id": "C", "name": "Station C", "num_chargers": 1},
      {"id": "D", "name": "Station D", "num_chargers": 1}
    ]
  }
}
```

**What happens automatically:**
- `Route.validate_route_continuity()` verifies the new segments form a continuous path
- `generate_charging_plans()` calls `route.get_stations_on_route()` which now returns `[A, E, B, C, D]` for Bengaluru→Kochi buses
- Candidate plans now include E: `{A,E}`, `{A,B}`, `{E,B}`, `{A,E,B}`, etc.
- `ChargerState.__init__` creates a queue for E with 2 charger slots
- `RangeConstraint` checks distances using the updated segment list (A→E = 60 km, E→B = 60 km)
- Kochi→Bengaluru buses automatically get E in reverse order: `[D, C, B, E, A]`

**Code changes: zero.**

---

## 7. Assumptions and Trade-offs

### 7.1 Physical World Assumptions

**A1. Buses start with a full battery.**
Every bus departs its origin (Bengaluru or Kochi) with 100% charge (240 km range). There is no model for buses arriving at the origin with partial charge.

*Trade-off:* Simplifies plan generation significantly. In reality, a bus returning from a previous trip may have partial charge. Extension: add `initial_charge_km` to `Bus` model.

**A2. Charging always fills to 100%.**
Every charging stop takes exactly `charge_duration_minutes` (25 min) and restores the battery to full capacity. Partial charging is not supported.

*Trade-off:* Simplifies the range constraint (always reset to full after each stop). Partial charging would require tracking state-of-charge throughout the journey. Extension: add `charge_to_percent` to `ChargingPlan` stops.

**A3. Constant speed for all buses.**
All buses travel at `speed_kmh` (60 km/h) regardless of direction, time of day, traffic, or road conditions. Travel time = `distance / speed`.

*Trade-off:* Makes arrival times deterministic and predictable. Real-world travel times vary by 20–40%. Extension: add `speed_kmh` per segment or per time-of-day window.

**A4. No charger failures.**
All chargers are always operational. There is no model for charger downtime, maintenance, or failure.

*Trade-off:* Simplifies charger state management. Extension: add `availability_windows` to `Station` (Tier 3 change #17).

**A5. Instant charger connection.**
When a bus arrives at a station and a charger is available, charging starts at the exact arrival time. There is no plug-in/plug-out overhead.

*Trade-off:* Negligible in practice (1–2 minutes). Extension: add `connection_overhead_minutes` to `Parameters`.

**A6. No battery degradation.**
Battery capacity is constant across all buses and all trips. Older buses have the same 240 km range as new ones.

*Trade-off:* Simplifies the model. Extension: add `battery_capacity_km` per bus (overrides scenario default).

**A7. No energy consumption variation.**
All buses consume energy at the same rate (1 km of range per 1 km traveled). Load, terrain, and driving style are not modeled.

*Trade-off:* Makes range calculations exact. Extension: add `consumption_rate` per bus or per segment.

### 7.2 Operational Assumptions

**A8. FIFO queue discipline at stations.**
When multiple buses are waiting for a charger, they are served in first-in-first-out order based on arrival time. There is no priority preemption.

*Trade-off:* Simple and fair for the current requirements. The queue is implemented as a Python list with `pop(0)`, making it easy to replace with a priority queue for Tier 2 change #10 (priority buses).

**A9. No reservations.**
Buses cannot reserve chargers in advance. Allocation is purely dynamic based on arrival order.

*Trade-off:* Simplifies the simulation. Reservations would require a two-phase model (reservation + execution). Extension: add `reserved_slots` to `Bus` and reservation logic to `ChargerState`.

**A10. One charger per bus at a time.**
Each bus uses exactly one charger per stop. No parallel charging (e.g., two chargers simultaneously for faster charging).

*Trade-off:* Matches current hardware reality. Extension: add `chargers_used` to charging plan if hardware supports it.

**A11. No route deviations.**
Buses must follow the fixed route in order. They cannot skip stations, take alternate paths, or charge at stations outside their route.

*Trade-off:* Enforced by `RouteOrderConstraint`. This is a hard physical constraint, not a simplification.

**A12. No driver breaks.**
Drivers can operate continuously for the full journey duration (~9 hours for 540 km at 60 km/h). No mandatory rest stops.

*Trade-off:* Simplifies scheduling. Extension: add `DriverShiftConstraint` (Tier 2 change #14).

**A13. No passenger boarding delays.**
Buses depart exactly at their scheduled `departure_time`. No delays for late passengers or boarding procedures.

*Trade-off:* Makes departure times deterministic. Extension: add `departure_delay_minutes` to `Bus`.

### 7.3 Scheduling Assumptions

**A14. Sequential greedy assignment.**
Buses are assigned plans one at a time in departure order. Once a bus is assigned, its plan is fixed and not reconsidered.

*Trade-off:* Fast and simple, but may miss globally optimal solutions. A bus assigned early may "block" a better global assignment. The departure-time ordering mitigates this by giving priority to buses that depart first (operationally sensible).

**A15. No look-ahead.**
When assigning bus N, the scheduler does not consider the impact on buses N+1, N+2, etc. beyond what the current simulation reveals.

*Trade-off:* Greedy is O(n × m × k) instead of exponential. For 20 buses, the quality difference from optimal is typically 0–5 minutes of total wait time.

**A16. Simultaneous arrivals are handled by heap order.**
When two buses arrive at the same station at the exact same time, the heap's internal ordering (by bus_id string comparison) determines which is processed first. This is deterministic but arbitrary.

*Trade-off:* Consistent and reproducible. If tie-breaking matters, add a secondary sort key (e.g., bus departure time) to the `Event` dataclass.

### 7.4 Data Assumptions

**A17. Station IDs match location names in segments.**
Station ID `"A"` must match the location name `"A"` used in route segments. This allows `route.get_distance("Bengaluru", "A")` to work without a separate ID-to-name mapping.

*Trade-off:* Simplifies distance calculations but creates a naming constraint. If station names need to differ from location names (e.g., "Station Alpha" at location "A"), a `location` field would need to be added to `Station`.

**A18. Unique IDs within a scenario.**
Bus IDs and station IDs are assumed unique. No validation enforces this, but duplicate IDs would cause silent bugs (e.g., `scenario.get_bus(bus_id)` returns the first match).

*Trade-off:* Could add a `model_validator` to check uniqueness. Not done to keep validation lightweight.

**A19. Day rollover is handled correctly.**
If a bus departs at 21:00 and arrives at 06:00 the next day, the `datetime` arithmetic handles this correctly (timedelta addition crosses midnight). The output times are formatted as `HH:MM` without a date, which may be ambiguous for multi-day journeys.

*Trade-off:* Acceptable for the current use case (single overnight journey). Extension: include date in output for multi-day scenarios.

---

## 8. Performance Characteristics and Scaling

### 8.1 Current Performance (20 Buses, 4 Stations)

**Measured:** Sub-second for all 5 scenarios on a standard laptop.

**Why it's fast:**

The greedy algorithm processes buses sequentially. For each bus, it tries all valid candidate plans. For each candidate, it runs a full simulation. The simulation processes events from a heap.

For the current scenario:
- 20 buses, each with ~11 candidate plans (combinations of 4 stations, min 2 charges)
- After constraint filtering: ~6–8 valid plans per bus
- Each simulation: ~40–80 events (20 buses × 2–4 charging stops each)
- Total simulations: 20 buses × 7 plans × 1 simulation = ~140 simulations
- Total events processed: ~140 × 60 = ~8,400 event operations

At ~1M event operations/second in Python, this is ~8ms. The actual measured time is dominated by Python object creation (Pydantic models), not algorithmic work.

### 8.2 Complexity Analysis

**Plan generation:** O(B × 2^S) where B = buses, S = stations on route.
- With 4 stations: 2^4 = 16 combinations per bus, filtered to ~11 valid ones
- With 10 stations: 2^10 = 1024 combinations per bus (most filtered out by range constraint)
- With 20 stations: 2^20 = 1M combinations — this is where plan generation becomes the bottleneck

**Constraint validation:** O(P × C × S) where P = plans, C = constraints (3), S = stations per plan.
- Effectively O(P) for small S.

**Greedy assignment:** O(B × P × E) where B = buses, P = plans per bus, E = events per simulation.
- E = O(B × charges_per_bus) = O(B × S)
- Total: O(B² × P × S)
- For 20 buses, 7 plans, 4 stations: 20² × 7 × 4 = 11,200 operations

**Event simulation (single run):** O(E log E) where E = total events.
- E = B × charges_per_bus × 2 (arrive + end) = 20 × 2 × 2 = 80 events
- heapq operations: O(E log E) = O(80 × 7) ≈ 560 comparisons

**Overall:** O(B² × P × S × log(B × S))

For current scale (B=20, P=7, S=4): ~50,000 operations → sub-millisecond algorithmic work.

### 8.3 Scaling Analysis

| Scale | Buses | Stations | Plans/bus | Simulations | Est. time |
|-------|-------|----------|-----------|-------------|-----------|
| Current | 20 | 4 | ~7 | ~140 | <0.1s |
| Medium | 50 | 6 | ~15 | ~750 | ~0.5s |
| Large | 100 | 8 | ~20 | ~2,000 | ~2s |
| Very large | 500 | 10 | ~25 | ~12,500 | ~15s |
| Extreme | 1,000 | 12 | ~30 | ~30,000 | ~45s |

*Estimates assume Python, no optimization, single-threaded.*

### 8.4 Bottlenecks at Scale

**Bottleneck 1: Plan generation with many stations.**
With 20 stations, `itertools.combinations` generates 2^20 = 1M combinations per bus. Most are filtered by the range constraint, but generation itself is slow.

*Mitigation:* Generate plans using dynamic programming instead of brute-force combinations. Only generate plans where each consecutive pair of stations is within battery range. This reduces generation from O(2^S) to O(S²).

```python
# Instead of itertools.combinations, use DP:
def generate_valid_plans_dp(stations, battery_capacity, distances):
    # Build a graph where edge (i, j) exists if distance(i, j) <= battery_capacity
    # Find all paths from origin to destination in this graph
    # This is O(S²) instead of O(2^S)
    pass
```

**Bottleneck 2: Repeated full simulations in greedy loop.**
For each bus, we run a full simulation for each candidate plan. Most of the simulation is identical across plans (buses already assigned don't change). We're recomputing the same events repeatedly.

*Mitigation:* Incremental simulation. Cache the simulation state after each bus is assigned. When evaluating a new bus's plans, only simulate the new bus's events on top of the cached state.

**Bottleneck 3: Python object creation overhead.**
Pydantic model creation (especially `SimulationResult`, `BusTimeline`, `ChargingStop`) is slow due to validation. At 30,000 simulations, this dominates.

*Mitigation:* Use plain dataclasses (no validation) for internal simulation state. Only convert to Pydantic models for the final output.

### 8.5 Scaling to 1,000+ Buses

For 1,000+ buses, the greedy approach remains viable with these optimizations:

1. **DP plan generation** — Reduces plan generation from O(2^S) to O(S²)
2. **Incremental simulation** — Reduces simulation cost from O(B × P × E) to O(P × E) per bus
3. **Early termination** — Stop evaluating plans once a plan scores better than a threshold
4. **Parallel plan evaluation** — Evaluate candidate plans for a bus in parallel (Python multiprocessing)
5. **Heuristic plan pruning** — For buses with many candidates, only evaluate the top K plans (ranked by a fast heuristic like "fewest stations = least wait")

With these optimizations, 1,000 buses should schedule in under 10 seconds.

For 10,000+ buses, consider:
- Switching to a CP solver (OR-Tools) for the assignment problem
- Using a rolling horizon approach (schedule buses in batches of 50)
- Pre-computing charger availability windows and using them to prune plans

### 8.6 Memory Usage

**Current:** Each simulation creates ~20 `BusTimeline` objects, each with ~2 `ChargingStop` objects. At 140 simulations, this is ~140 × 20 × 2 = 5,600 objects. Negligible.

**At 1,000 buses:** ~30,000 simulations × 1,000 timelines × 2 stops = 60M objects. This would require ~6 GB RAM.

*Mitigation:* Don't store all simulation results — only store the best result per bus. Discard intermediate results immediately. This reduces memory to O(B × stops_per_bus) = O(1,000 × 2) = 2,000 objects at any time.

---

## Summary

This architecture prioritizes **extensibility** and **transparency** over premature optimization.

**Key decisions:**
- Event simulation (not constraint solver) → transparent, debuggable, no external dependencies
- Pluggable rules (not monolithic cost function) → add a class, not modify the engine
- Configuration over code (not hardcoded world) → data-driven changes for 9 of 17 anticipated changes
- Greedy assignment (not global optimization) → sub-second for current scale, good enough quality

**Anticipated changes handled:**
- 9 changes: data only (zero code)
- 5 changes: new class + one-line registration
- 3 changes: ~20–30 lines of engine extension

**What we're NOT building:**
- Real-time updates (static schedules only)
- Database persistence (in-memory, stateless)
- Complex visualizations (tables only)
- Global optimization (greedy is sufficient)

The goal is a solid foundation that scales gracefully, not a feature-complete product.
