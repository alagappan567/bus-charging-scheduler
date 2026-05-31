# Architecture Documentation

## Table of Contents
1. [Scheduler Approach](#scheduler-approach)
2. [Data Structure Design](#data-structure-design)
3. [Anticipated Future Changes](#anticipated-future-changes)
4. [How to Change a Weight](#how-to-change-a-weight)
5. [How to Add a New Rule](#how-to-add-a-new-rule)
6. [Assumptions](#assumptions)

---

## Scheduler Approach

### Chosen Framework: Greedy Sequential Assignment

I chose a **greedy sequential assignment** algorithm for the bus charging scheduler. Here's why:

#### How It Works
1. **Generate candidate plans**: For each bus, generate all valid combinations of charging stations
2. **Validate constraints**: Filter out plans that violate hard constraints (range, route order, completion)
3. **Sort by departure time**: Process buses in chronological order
4. **Greedy selection**: For each bus, try all its valid plans, simulate each with current assignments, score using weighted objectives, and select the best
5. **Lock in assignment**: Once a bus is assigned, its plan is fixed and affects subsequent buses

#### Why This Approach?

**Pros:**
- **Fast**: O(n × m × k) where n=buses, m=plans per bus, k=simulation time. Runs in seconds for 20 buses
- **Deterministic**: Same input always produces same output
- **Transparent**: Easy to debug and explain to stakeholders
- **Fair**: Earlier buses (by departure time) get priority, which is operationally sensible
- **Good enough**: Produces reasonable schedules that respect all constraints

**Cons:**
- **Not globally optimal**: Greedy choices may lead to suboptimal overall solutions
- **Order-dependent**: Bus processing order affects results (mitigated by using departure time)
- **No backtracking**: Once a bus is assigned, we don't reconsider if later buses struggle

#### Alternatives Considered

**1. Constraint Programming (CP)**
- **Pros**: Can find globally optimal solutions, handles complex constraints elegantly
- **Cons**: Slow for large problems, requires specialized solver (OR-Tools, Gurobi), harder to debug
- **Why not chosen**: Overkill for this problem size, adds external dependency

**2. Genetic Algorithms (GA)**
- **Pros**: Can escape local optima, handles multi-objective optimization naturally
- **Cons**: Non-deterministic, slow convergence, many hyperparameters to tune
- **Why not chosen**: Unpredictable runtime, harder to explain to non-technical stakeholders

**3. Simulated Annealing (SA)**
- **Pros**: Can find near-optimal solutions, simple to implement
- **Cons**: Non-deterministic, requires careful temperature schedule tuning
- **Why not chosen**: Greedy is fast enough and more predictable

**4. Integer Linear Programming (ILP)**
- **Pros**: Provably optimal solutions, well-studied
- **Cons**: Requires linearizing objectives (hard for variance), slow for large instances
- **Why not chosen**: Operator fairness (variance) is non-linear

#### When to Reconsider

The greedy approach works well for:
- **Small to medium scale**: Up to ~50 buses, ~10 stations
- **Sparse contention**: Not all buses arrive at same station simultaneously
- **Balanced objectives**: No single objective dominates

Consider switching to CP or ILP if:
- **Scale increases**: 100+ buses, 20+ stations
- **Optimality matters**: Cost savings justify longer computation time
- **Complex constraints**: Time windows, driver shifts, maintenance schedules

---

## Data Structure Design

### Core Philosophy: Configuration Over Code

The data structure is designed so that **the world (routes, stations, buses) is defined in data, not code**. This means:
- Adding a station = editing JSON, not writing code
- Changing charger count = editing JSON, not writing code
- Adding a bus = editing JSON, not writing code

### Why Pydantic?

I chose **Pydantic** for all data models because:

1. **Validation**: Automatic type checking and constraint validation at runtime
2. **Parsing**: JSON → Python objects with one line (`Scenario(**data)`)
3. **Documentation**: Field descriptions serve as inline documentation
4. **IDE Support**: Full autocomplete and type hints
5. **Extensibility**: Easy to add optional fields without breaking existing code

### Model Hierarchy

```
Scenario (top-level)
├── Route
│   ├── Segments (list)
│   └── Stations (list)
├── Buses (list)
├── Parameters (battery, charge time, speed)
└── Weights (individual, operator, overall)
```

#### Key Design Decisions

**1. Separation of Concerns**
- **Route**: Describes the physical world (segments, stations)
- **Bus**: Describes a scheduled trip (operator, departure time)
- **Parameters**: Describes physical constants (battery, speed)
- **Weights**: Describes optimization preferences

This separation means:
- Changing the route doesn't affect bus definitions
- Changing weights doesn't require new scenarios
- Adding parameters doesn't break existing routes

**2. Station IDs as Location Names**
- Station IDs (A, B, C, D) are also location names in route segments
- This simplifies distance calculations and station lookups
- Trade-off: Station IDs must match segment location names exactly

**3. Bidirectional Route Support**
- Route is defined once (Bengaluru → Kochi)
- Buses can travel in either direction
- `get_stations_on_route()` returns stations in travel order (reversed for reverse-direction buses)
- `get_distance()` works in both directions

**4. Immutable Plans**
- Once a `ChargingPlan` is created, it's immutable
- Simulator doesn't modify plans, only executes them
- This makes debugging easier (plans can be inspected after simulation)

**5. Result Models**
- `SimulationResult` contains both bus timelines and station queues
- Two views of the same data: per-bus and per-station
- UI can display either view without recomputing

### Type Safety

Every model has:
- **Explicit types**: `str`, `int`, `float`, `List[...]`, `Dict[...]`
- **Validation**: `@field_validator` for custom rules
- **Defaults**: Sensible defaults for optional fields
- **Documentation**: Docstrings on every class and field

---

## Anticipated Future Changes

Here are 12 future changes I anticipated when designing the data structure, and how the design handles each **without code changes**:

### 1. Priority Buses
**Scenario**: Emergency vehicles or VIP buses need priority access to chargers.

**How to Handle**:
```json
// Add to Bus model (optional field)
{"id": "bus-BK-01", "operator": "kpn", "priority": true, ...}

// Add to Weights
"weights": {"individual": 1.0, "operator": 1.0, "overall": 1.0, "priority": 5.0}
```

**Code Change**: Add `PriorityBusObjective` class, register in scheduler. **No changes to data loading or simulation**.

### 2. Time-of-Day Electricity Costs
**Scenario**: Charging costs more during peak hours (6pm-10pm).

**How to Handle**:
```json
// Add to Parameters
"parameters": {
  "battery_capacity_km": 240,
  "charge_duration_minutes": 25,
  "speed_kmh": 60,
  "peak_hours": ["18:00", "22:00"],
  "peak_cost_multiplier": 2.0
}

// Add to Weights
"weights": {"individual": 1.0, "operator": 1.0, "overall": 1.0, "cost": 1.5}
```

**Code Change**: Add `ElectricityCostObjective` class. **No changes to route or bus definitions**.

### 3. Driver Shifts
**Scenario**: Drivers have shift limits (max 8 hours driving).

**How to Handle**:
```json
// Add to Bus model
{"id": "bus-BK-01", "operator": "kpn", "driver_shift_start": "19:00", "max_shift_hours": 8, ...}
```

**Code Change**: Add `DriverShiftConstraint` class. **No changes to route or simulation**.

### 4. Multiple Routes Sharing Stations
**Scenario**: Station B is shared by Bengaluru-Kochi and Bengaluru-Chennai routes.

**How to Handle**:
```json
// Define multiple routes
"routes": [
  {"id": "bengaluru-kochi", "origin": "Bengaluru", "destination": "Kochi", ...},
  {"id": "bengaluru-chennai", "origin": "Bengaluru", "destination": "Chennai", ...}
],

// Buses reference route by ID
{"id": "bus-BK-01", "route_id": "bengaluru-kochi", ...}
```

**Code Change**: Modify `Scenario` to support multiple routes. **Existing single-route scenarios still work**.

### 5. Different Charger Types
**Scenario**: Fast chargers (15 min) vs slow chargers (30 min).

**How to Handle**:
```json
// Add to Station model
{"id": "A", "name": "Station A", "chargers": [
  {"type": "fast", "count": 1, "duration_minutes": 15},
  {"type": "slow", "count": 2, "duration_minutes": 30}
]}
```

**Code Change**: Update `ChargerState` to track charger types. **Existing scenarios with `num_chargers` still work (default to one type)**.

### 6. Partial Charging
**Scenario**: Buses can charge to 80% in 15 min instead of 100% in 25 min.

**How to Handle**:
```json
// Add to Parameters
"parameters": {
  "battery_capacity_km": 240,
  "charge_options": [
    {"percent": 80, "duration_minutes": 15, "range_km": 192},
    {"percent": 100, "duration_minutes": 25, "range_km": 240}
  ],
  "speed_kmh": 60
}
```

**Code Change**: Update plan generator to consider partial charges. **Existing scenarios with fixed `charge_duration_minutes` still work**.

### 7. Dynamic Pricing
**Scenario**: Charger prices vary by demand (surge pricing).

**How to Handle**:
```json
// Add to Station model
{"id": "A", "name": "Station A", "num_chargers": 1, "pricing": {
  "base_price": 10.0,
  "surge_multiplier": 1.5,
  "surge_threshold_queue_length": 3
}}

// Add to Weights
"weights": {"individual": 1.0, "operator": 1.0, "overall": 1.0, "cost": 2.0}
```

**Code Change**: Add `DynamicPricingObjective` class. **No changes to core simulation**.

### 8. Maintenance Windows
**Scenario**: Station C is closed for maintenance 2pm-4pm.

**How to Handle**:
```json
// Add to Station model
{"id": "C", "name": "Station C", "num_chargers": 1, "maintenance_windows": [
  {"start": "14:00", "end": "16:00"}
]}
```

**Code Change**: Add `MaintenanceWindowConstraint` class. **No changes to route or bus definitions**.

### 9. Weather Delays
**Scenario**: Heavy rain reduces speed by 20%.

**How to Handle**:
```json
// Add to Parameters
"parameters": {
  "battery_capacity_km": 240,
  "charge_duration_minutes": 25,
  "speed_kmh": 60,
  "weather_conditions": {
    "type": "heavy_rain",
    "speed_multiplier": 0.8
  }
}
```

**Code Change**: Update travel time calculation in simulator. **No changes to route or bus definitions**.

### 10. Emergency Vehicles
**Scenario**: Ambulances can preempt regular buses at chargers.

**How to Handle**:
```json
// Add to Bus model
{"id": "ambulance-01", "operator": "emergency", "vehicle_type": "emergency", "can_preempt": true, ...}
```

**Code Change**: Update queue management in `ChargerState` to support preemption. **Existing buses without `can_preempt` default to false**.

### 11. Battery Degradation
**Scenario**: Older buses have reduced battery capacity (200 km instead of 240 km).

**How to Handle**:
```json
// Add to Bus model
{"id": "bus-BK-01", "operator": "kpn", "battery_capacity_km": 200, ...}
```

**Code Change**: Use bus-specific battery capacity in plan generator. **Existing buses without this field use scenario default**.

### 12. Multi-Charger Stations with Reservations
**Scenario**: Station B has 3 chargers, buses can reserve slots in advance.

**How to Handle**:
```json
// Add to Station model
{"id": "B", "name": "Station B", "num_chargers": 3, "allows_reservations": true}

// Add to Bus model
{"id": "bus-BK-01", "operator": "kpn", "reserved_slots": [
  {"station": "B", "time": "20:30"}
], ...}
```

**Code Change**: Add reservation logic to `ChargerState`. **Existing scenarios without reservations work as before**.

### Common Pattern

Notice the pattern:
1. **Add optional fields** to existing models (Bus, Station, Parameters)
2. **Add new objective or constraint** class
3. **Register in scheduler** (one line)
4. **Existing scenarios still work** (optional fields have defaults)

This is **configuration over code** in action.

---

## How to Change a Weight

Weights control how the scheduler balances competing objectives. Changing a weight is **trivial** — just edit the JSON file.

### Example: Prioritize Operator Fairness

**Before** (Scenario 1):
```json
{
  "name": "Scenario 1 - Even Spacing",
  "route": { ... },
  "buses": [ ... ],
  "parameters": { ... },
  "weights": {
    "individual": 1.0,
    "operator": 1.0,
    "overall": 1.0
  }
}
```

**After** (prioritize operator fairness 3x):
```json
{
  "name": "Scenario 1 - Even Spacing",
  "route": { ... },
  "buses": [ ... ],
  "parameters": { ... },
  "weights": {
    "individual": 1.0,
    "operator": 3.0,    // Changed from 1.0
    "overall": 1.0
  }
}
```

**Result**: The scheduler will now prioritize balancing wait times across operators (KPN, Freshbus, Flixbus) over minimizing individual bus wait times.

### Where Weights Are Used

Weights are used in `scheduler/scheduler.py`:

```python
# Initialize objective evaluator with weighted objectives
self.objectives: List[tuple[Objective, float]] = [
    (IndividualWaitObjective(), scenario.weights.individual),
    (OperatorFairnessObjective(), scenario.weights.operator),
    (OverallEfficiencyObjective(), scenario.weights.overall)
]
self.objective_evaluator = ObjectiveEvaluator(self.objectives)
```

The `ObjectiveEvaluator` computes:
```
total_score = (individual_weight × individual_score) + 
              (operator_weight × operator_score) + 
              (overall_weight × overall_score)
```

### Testing Different Weights

To see the effect of different weights:

1. **Create a copy** of a scenario with different weights:
   ```bash
   cp scenarios/scenario1.json scenarios/scenario1_operator_heavy.json
   ```

2. **Edit the weights** in the new file

3. **Run both** in the UI and compare results:
   - Look at operator statistics (avg wait, max wait per operator)
   - Look at individual bus wait times
   - Look at total wait time

**Expected Behavior**:
- Higher `individual` weight → Lower max wait for any single bus
- Higher `operator` weight → More balanced wait times across operators
- Higher `overall` weight → Lower total wait time (but may sacrifice fairness)

---

## How to Add a New Rule

Adding a new rule (constraint or objective) requires **minimal code changes** and **no changes to existing scenarios**.

### Example: Add a "Priority Bus" Objective

Let's say we want to give priority to certain buses (e.g., emergency vehicles, VIP routes).

#### Step 1: Add Data Field (Optional)

If the rule needs new data, add it to the scenario:

```json
// In scenarios/scenario1.json
{
  "buses": [
    {"id": "bus-BK-01", "operator": "kpn", "priority": true, ...},
    {"id": "bus-BK-02", "operator": "freshbus", ...}  // No priority field = default false
  ],
  "weights": {
    "individual": 1.0,
    "operator": 1.0,
    "overall": 1.0,
    "priority": 5.0  // New weight
  }
}
```

#### Step 2: Create Objective Class

Add a new file `scheduler/objectives.py` (or add to existing):

```python
class PriorityBusObjective(Objective):
    """
    Penalizes wait time for priority buses more heavily.
    
    This objective ensures priority buses (emergency vehicles, VIP routes)
    experience minimal wait times by applying a large penalty multiplier.
    
    Score: -sum(priority_bus_wait × 10)
    """
    
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """
        Compute score based on priority bus wait times.
        
        Args:
            result: The simulation result containing bus timelines
            scenario: The scenario context with bus priority information
            
        Returns:
            Negative of weighted wait time for priority buses
        """
        if not result.bus_timelines:
            return 0.0
        
        penalty = 0.0
        for timeline in result.bus_timelines.values():
            bus = scenario.get_bus(timeline.bus_id)
            if bus and getattr(bus, 'priority', False):  # Check if bus has priority
                # Apply 10x penalty for priority bus wait time
                penalty += timeline.total_wait_minutes * 10
        
        return -penalty  # Negative because we want to minimize
```

#### Step 3: Register in Scheduler

Modify `scheduler/scheduler.py`:

```python
class BusScheduler:
    def __init__(self, scenario: Scenario):
        # ... existing code ...
        
        # Initialize objective evaluator with weighted objectives
        self.objectives: List[tuple[Objective, float]] = [
            (IndividualWaitObjective(), scenario.weights.individual),
            (OperatorFairnessObjective(), scenario.weights.operator),
            (OverallEfficiencyObjective(), scenario.weights.overall),
            # Add new objective with weight from scenario (default 0.0 if not present)
            (PriorityBusObjective(), getattr(scenario.weights, 'priority', 0.0))
        ]
        self.objective_evaluator = ObjectiveEvaluator(self.objectives)
```

#### Step 4: Update Pydantic Models (Optional)

If you want type safety and validation, add the field to models:

```python
# In scheduler/models.py

class Bus(BaseModel):
    id: str
    operator: str
    origin: str
    destination: str
    departure_time: str
    priority: bool = Field(False, description="Whether this is a priority bus")  # New field

class Weights(BaseModel):
    individual: float = Field(1.0, ge=0)
    operator: float = Field(1.0, ge=0)
    overall: float = Field(1.0, ge=0)
    priority: float = Field(0.0, ge=0, description="Weight for priority bus objective")  # New field
```

#### Step 5: Test

Run the scheduler with the new rule:

```bash
streamlit run app.py
```

Select the scenario with priority buses and verify:
- Priority buses have lower wait times
- Non-priority buses may wait longer
- Changing the `priority` weight affects the trade-off

### Adding a Hard Constraint

For hard constraints (must be satisfied), the process is similar:

```python
# In scheduler/constraints.py

class DriverShiftConstraint(Constraint):
    """Ensures buses complete their journey within driver shift limits."""
    
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        bus = scenario.get_bus(plan.bus_id)
        if not bus or not hasattr(bus, 'max_shift_hours'):
            return True  # No shift limit = always valid
        
        # Calculate total journey time (travel + charging + waiting)
        # ... implementation ...
        
        return total_hours <= bus.max_shift_hours
    
    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        return f"Bus {plan.bus_id} exceeds driver shift limit"
```

Then register in `scheduler/scheduler.py`:

```python
self.constraints: List[Constraint] = [
    RangeConstraint(),
    RouteOrderConstraint(),
    CompletionConstraint(),
    DriverShiftConstraint()  # Add new constraint
]
```

### Key Principles

1. **Backward compatible**: Existing scenarios without new fields still work
2. **Optional fields**: Use `getattr()` or Pydantic defaults
3. **Single responsibility**: Each objective/constraint does one thing
4. **Pluggable**: Register in one place (scheduler `__init__`)

---

## Assumptions

Here are the key assumptions I made when designing this system:

### Physical World

1. **Buses start with full battery**: Every bus departs its origin (Bengaluru or Kochi) with 100% charge (240 km range)
2. **Charging always to full**: Partial charging is not supported; every charge takes exactly 25 minutes and fills the battery to 100%
3. **Constant speed**: All buses travel at 60 km/h with no variation for traffic, weather, or road conditions
4. **No charger failures**: Chargers are always operational; no maintenance downtime or breakdowns
5. **Instant charger connection**: No time required to plug in or unplug; charging starts immediately when a charger is available
6. **No battery degradation**: Battery capacity doesn't decrease over time or with usage

### Operational Rules

7. **FIFO queue discipline**: Buses are served in first-in-first-out order at each station; no priority or preemption
8. **No reservations**: Buses cannot reserve chargers in advance; allocation is dynamic based on arrival order
9. **One charger per bus**: Each bus uses exactly one charger; no parallel charging
10. **No route deviations**: Buses must follow the fixed route; cannot skip stations or take alternate paths
11. **Deterministic scheduling**: Same input always produces same output; no randomness or stochastic elements

### Scheduling Constraints

12. **Sequential assignment**: Buses are assigned plans in departure time order; no parallel or batch assignment
13. **No plan modification**: Once a bus is assigned a charging plan, it cannot be changed during simulation
14. **Greedy optimization**: The scheduler makes locally optimal choices without backtracking
15. **No look-ahead**: When assigning a bus, the scheduler doesn't consider future buses beyond simulation

### Data Assumptions

16. **Valid JSON**: Scenario files are well-formed JSON with all required fields
17. **Consistent units**: Distances in km, time in minutes, speed in km/h
18. **Unique IDs**: Bus IDs and station IDs are unique within a scenario
19. **Station IDs match locations**: Station IDs (A, B, C, D) are also location names in route segments
20. **Continuous route**: Route segments form a continuous path from origin to destination with no gaps

### Simplifications

21. **No driver breaks**: Drivers can drive continuously without rest stops
22. **No passenger boarding time**: Buses depart exactly at scheduled time; no delays for passengers
23. **No energy consumption variation**: All buses consume energy at the same rate regardless of load, terrain, or driving style
24. **No cost considerations**: Charging is free; no electricity costs or pricing optimization
25. **Single route**: All buses travel on the same Bengaluru-Kochi route; no alternate routes or branches

### Edge Cases

26. **Simultaneous arrivals**: When multiple buses arrive at the same station at the exact same time, they are processed in arbitrary order (heap order)
27. **Zero wait time**: If a charger is available when a bus arrives, wait time is 0 (no minimum wait)
28. **Day rollover**: If a bus journey extends past midnight, times are handled correctly (though not explicitly tested)

### Future Relaxations

These assumptions can be relaxed by:
- Adding optional fields to models (e.g., `battery_degradation_rate`)
- Adding new constraint or objective classes (e.g., `DriverBreakConstraint`)
- Extending the simulator (e.g., support for charger failures)

The data structure is designed to accommodate these extensions without breaking existing scenarios.

---

## Summary

This architecture prioritizes:
1. **Extensibility**: Easy to add new rules without rewriting core logic
2. **Transparency**: Clear separation between data, constraints, objectives, and simulation
3. **Maintainability**: Each component has a single responsibility
4. **Testability**: Components can be tested independently
5. **Usability**: Non-programmers can modify scenarios by editing JSON

The trade-off is that we don't achieve global optimality, but for this problem size and domain, the greedy approach is fast, predictable, and good enough.
