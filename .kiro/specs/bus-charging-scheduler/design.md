# Bus Charging Scheduler - Design Document

## Architecture Overview

### Design Philosophy
**Configuration over Code**: The world (routes, stations, buses, rules) is data. The engine is rule-agnostic.

**Pluggable Rules**: Constraints and objectives are independent classes. Adding a rule = writing a class, not modifying the engine.

**Event-Driven Simulation**: Transparent, deterministic, debuggable. No black-box solvers.

### System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit UI                         │
│  (Scenario Picker, Input Display, Timeline Tables)     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                 Scheduler Orchestrator                  │
│  - Load scenario                                        │
│  - Generate candidate plans                             │
│  - Validate constraints                                 │
│  - Score with objectives                                │
│  - Select best plan                                     │
└────────┬────────────────────────────────┬───────────────┘
         │                                │
         ▼                                ▼
┌──────────────────────┐      ┌──────────────────────────┐
│  Constraint System   │      │   Objective System       │
│  (Hard Rules)        │      │   (Soft Rules)           │
│                      │      │                          │
│  - RangeConstraint   │      │  - IndividualWait        │
│  - RouteOrder        │      │  - OperatorFairness      │
│  - ChargerCapacity   │      │  - OverallEfficiency     │
└──────────────────────┘      └──────────────────────────┘
         │                                │
         └────────────┬───────────────────┘
                      ▼
         ┌─────────────────────────┐
         │   Event Simulator       │
         │  - Priority queue       │
         │  - Charger allocation   │
         │  - Timeline generation  │
         └─────────────────────────┘
```

---

## Data Model

### Core Entities

#### Scenario
Top-level configuration containing route, buses, parameters, weights.

```python
@dataclass
class Scenario:
    name: str
    route: Route
    buses: List[Bus]
    parameters: Parameters
    weights: Weights
```

#### Route
Defines the physical route structure: segments, stations, distances.

```python
@dataclass
class Route:
    id: str
    origin: str
    destination: str
    segments: List[Segment]  # Ordered list of segments
    stations: Dict[str, Station]  # Station ID -> Station object
    
@dataclass
class Segment:
    from_location: str
    to_location: str
    distance_km: float
    
@dataclass
class Station:
    id: str
    name: str
    num_chargers: int
    # Future: charger_type, pricing_schedule, availability_windows
```

**Design rationale:**
- Segments are ordered → route order is explicit
- Stations are dict → O(1) lookup by ID
- `num_chargers` is per-station → changing from 1 to N is one field
- Station ID is separate from name → multiple routes can reference same station

#### Bus
Represents a single bus with its schedule and operator.

```python
@dataclass
class Bus:
    id: str
    operator: str
    origin: str
    destination: str
    departure_time: datetime
    # Future: priority, vehicle_type, driver_shift
```

#### Parameters
Physical constants and simulation settings.

```python
@dataclass
class Parameters:
    battery_capacity_km: float = 240
    charge_duration_minutes: int = 25
    speed_kmh: float = 60
    # Future: partial_charge_allowed, charger_efficiency
```

#### Weights
Tunable coefficients for soft objectives.

```python
@dataclass
class Weights:
    individual: float = 1.0
    operator: float = 1.0
    overall: float = 1.0
    # Future: priority, time_of_day, station_preference
```

---

## Scheduler Algorithm

### High-Level Flow

```
1. Load Scenario
   ↓
2. For each bus:
   - Generate candidate charging plans
   - Filter invalid plans (constraints)
   ↓
3. Simulate all valid plans:
   - Run event simulation
   - Track charger allocation
   - Generate timelines
   ↓
4. Score each simulation:
   - Apply all objectives with weights
   - Compute total score
   ↓
5. Select best scoring plan
   ↓
6. Return: Bus timelines + Station queues
```

### Step 2: Charging Plan Generation

**Problem**: Given a bus's route, which stations should it charge at?

**Approach**: Generate all valid combinations that satisfy range constraint.

```python
def generate_charging_plans(bus: Bus, route: Route, params: Parameters) -> List[ChargingPlan]:
    """
    Generate all valid charging station combinations for a bus.
    
    A plan is valid if:
    - Distance between consecutive charges ≤ battery_capacity_km
    - Stations are in route order
    - Bus can reach destination after last charge
    """
    plans = []
    stations_on_route = get_stations_on_route(bus, route)
    
    # Minimum charges needed
    total_distance = get_total_distance(bus, route)
    min_charges = math.ceil(total_distance / params.battery_capacity_km) - 1
    
    # Generate combinations of length min_charges to len(stations_on_route)
    for num_charges in range(min_charges, len(stations_on_route) + 1):
        for combo in itertools.combinations(stations_on_route, num_charges):
            if is_valid_plan(combo, bus, route, params):
                plans.append(ChargingPlan(bus_id=bus.id, stations=list(combo)))
    
    return plans
```

**Example**: Bengaluru → Kochi (540 km), battery 240 km
- Must charge at least 2 times
- Valid plans: {A,B}, {A,C}, {A,D}, {B,C}, {B,D}, {C,D}, {A,B,C}, {A,B,D}, {A,C,D}, {B,C,D}, {A,B,C,D}

### Step 3: Event Simulation

**Core idea**: Simulate time progression using a priority queue of events.

```python
class EventType(Enum):
    BUS_ARRIVES_AT_STATION = 1
    CHARGING_STARTS = 2
    CHARGING_ENDS = 3

@dataclass
class Event:
    time: datetime
    type: EventType
    bus_id: str
    station_id: str
    
class EventSimulator:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.event_queue = PriorityQueue()
        self.charger_state = {}  # station_id -> List[available charger slots]
        self.bus_timelines = {}  # bus_id -> Timeline
        
    def simulate(self, charging_plans: Dict[str, ChargingPlan]) -> SimulationResult:
        # Initialize: schedule all bus departures
        for bus in self.scenario.buses:
            self._schedule_bus_journey(bus, charging_plans[bus.id])
        
        # Process events chronologically
        while not self.event_queue.empty():
            event = self.event_queue.get()
            self._handle_event(event)
        
        return SimulationResult(
            bus_timelines=self.bus_timelines,
            station_queues=self._build_station_queues()
        )
```

**Event handling**:
- `BUS_ARRIVES_AT_STATION`: Check charger availability
  - If available: schedule `CHARGING_STARTS` immediately
  - If busy: add bus to station queue
- `CHARGING_STARTS`: Occupy charger, schedule `CHARGING_ENDS` (+25 min)
- `CHARGING_ENDS`: Release charger, schedule next bus in queue (if any), continue bus journey

### Step 4: Scoring with Objectives

Each objective computes a score (higher = better). Total score is weighted sum.

```python
class Objective(ABC):
    @abstractmethod
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """Compute score for this objective. Higher is better."""
        pass

class IndividualWaitObjective(Objective):
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        # Penalize max wait time across all buses
        max_wait = max(timeline.total_wait_minutes for timeline in result.bus_timelines.values())
        return -max_wait  # Negative because we want to minimize

class OperatorFairnessObjective(Objective):
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        # Penalize variance in average wait time across operators
        operator_waits = defaultdict(list)
        for timeline in result.bus_timelines.values():
            bus = scenario.get_bus(timeline.bus_id)
            operator_waits[bus.operator].append(timeline.total_wait_minutes)
        
        avg_waits = [np.mean(waits) for waits in operator_waits.values()]
        variance = np.var(avg_waits)
        return -variance

class OverallEfficiencyObjective(Objective):
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        # Penalize total wait time
        total_wait = sum(timeline.total_wait_minutes for timeline in result.bus_timelines.values())
        return -total_wait
```

**Combining scores**:
```python
def compute_total_score(result: SimulationResult, scenario: Scenario) -> float:
    objectives = [
        (IndividualWaitObjective(), scenario.weights.individual),
        (OperatorFairnessObjective(), scenario.weights.operator),
        (OverallEfficiencyObjective(), scenario.weights.overall),
    ]
    
    total = 0.0
    for objective, weight in objectives:
        total += weight * objective.score(result, scenario)
    
    return total
```

---

## Constraint System

Constraints are boolean checks. A plan is valid only if all constraints pass.

```python
class Constraint(ABC):
    @abstractmethod
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        pass
    
    @abstractmethod
    def get_violation_message(self) -> str:
        pass

class RangeConstraint(Constraint):
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Ensure battery never exceeds capacity between charges."""
        bus = scenario.get_bus(plan.bus_id)
        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km
        
        # Check distance from origin to first charge
        first_station = plan.stations[0]
        distance_to_first = route.get_distance(bus.origin, first_station)
        if distance_to_first > battery_capacity:
            return False
        
        # Check distance between consecutive charges
        for i in range(len(plan.stations) - 1):
            distance = route.get_distance(plan.stations[i], plan.stations[i+1])
            if distance > battery_capacity:
                return False
        
        # Check distance from last charge to destination
        last_station = plan.stations[-1]
        distance_to_dest = route.get_distance(last_station, bus.destination)
        if distance_to_dest > battery_capacity:
            return False
        
        return True

class RouteOrderConstraint(Constraint):
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Ensure stations are visited in route order (no backtracking)."""
        bus = scenario.get_bus(plan.bus_id)
        route_stations = scenario.route.get_stations_on_route(bus.origin, bus.destination)
        
        # Check that plan stations appear in same order as route
        route_indices = [route_stations.index(s) for s in plan.stations]
        return route_indices == sorted(route_indices)
```

---

## Extensibility Examples

### Example 1: Add a New Station

**Change required**: Update scenario JSON only.

```json
{
  "route": {
    "segments": [
      {"from": "Bengaluru", "to": "A", "distance_km": 100},
      {"from": "A", "to": "E", "distance_km": 60},  // NEW
      {"from": "E", "to": "B", "distance_km": 60},  // UPDATED
      {"from": "B", "to": "C", "distance_km": 100},
      ...
    ],
    "stations": [
      {"id": "A", "name": "Station A", "num_chargers": 1},
      {"id": "E", "name": "Station E", "num_chargers": 1},  // NEW
      ...
    ]
  }
}
```

**Code changes**: Zero. Scheduler reads segments and stations dynamically.

### Example 2: Change Chargers Per Station

**Change required**: Update station config.

```json
{"id": "B", "name": "Station B", "num_chargers": 3}  // Changed from 1 to 3
```

**Code changes**: Zero. Event simulator allocates chargers based on `num_chargers`.

### Example 3: Add Priority Bus Rule

**Step 1**: Add priority field to bus data.
```json
{"id": "bus-BK-01", "operator": "kpn", "priority": true, ...}
```

**Step 2**: Create objective class.
```python
class PriorityBusObjective(Objective):
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        penalty = 0
        for timeline in result.bus_timelines.values():
            bus = scenario.get_bus(timeline.bus_id)
            if bus.priority and timeline.total_wait_minutes > 0:
                penalty += timeline.total_wait_minutes * 10
        return -penalty
```

**Step 3**: Register in weights.
```json
"weights": {"individual": 1.0, "operator": 1.0, "overall": 1.0, "priority": 5.0}
```

**Step 4**: Add to objective list in scheduler.
```python
objectives = [
    (IndividualWaitObjective(), scenario.weights.individual),
    (OperatorFairnessObjective(), scenario.weights.operator),
    (OverallEfficiencyObjective(), scenario.weights.overall),
    (PriorityBusObjective(), scenario.weights.get('priority', 0.0)),  // NEW
]
```

**Engine changes**: One line to register the objective. Core logic untouched.

### Example 4: Multiple Routes Sharing Stations

**Data model change**: Scenarios can have multiple routes.

```json
{
  "routes": [
    {
      "id": "bengaluru-kochi",
      "segments": [...],
      "stations": [...]
    },
    {
      "id": "chennai-kochi",
      "segments": [...],
      "stations": [
        {"id": "C", ...},  // Shared with bengaluru-kochi
        {"id": "D", ...}   // Shared with bengaluru-kochi
      ]
    }
  ],
  "buses": [
    {"id": "bus-BK-01", "route_id": "bengaluru-kochi", ...},
    {"id": "bus-CK-01", "route_id": "chennai-kochi", ...}
  ]
}
```

**Code changes**: 
- Scheduler loops over all routes
- Event simulator merges charger state across routes (same station ID = same chargers)
- ~20 lines of refactoring, zero algorithm changes

---

## File Structure

```
bus-charging-scheduler/
├── app.py                      # Streamlit UI entry point
├── requirements.txt            # Dependencies
├── README.md                   # How to run, change weights, add rules
├── ARCHITECTURE.md             # Design decisions, extensibility
├── scheduler/
│   ├── __init__.py
│   ├── models.py               # Data classes (Scenario, Bus, Route, etc.)
│   ├── scheduler.py            # Main orchestrator
│   ├── simulator.py            # Event-driven simulation
│   ├── constraints.py          # Constraint classes
│   ├── objectives.py           # Objective classes
│   └── utils.py                # Helper functions
├── scenarios/
│   ├── scenario1.json
│   ├── scenario2.json
│   ├── scenario3.json
│   ├── scenario4.json
│   └── scenario5.json
└── tests/
    ├── test_constraints.py
    ├── test_objectives.py
    └── test_simulator.py
```

---

## Technology Choices

### Python 3.10+
- Type hints for clarity
- Dataclasses for clean data modeling
- Standard library (heapq, itertools, datetime)

### Pydantic
- JSON schema validation
- Automatic parsing and type coercion
- Clear error messages for invalid scenarios

### Streamlit
- Zero frontend code
- Rapid prototyping
- Free hosting on Streamlit Cloud

### No Database
- In-memory state
- Scenarios loaded from JSON files
- Stateless app (reload = fresh state)

---

## Performance Considerations

### Current Scale
- 20 buses, 4 stations, 1 charger each
- ~10 candidate plans per bus → 10^20 combinations
- **Optimization**: Greedy per-bus assignment (not global optimization)

### Greedy Approach
Instead of trying all combinations, assign buses sequentially:
1. Sort buses by departure time
2. For each bus, try all its candidate plans
3. Simulate each plan given current assignments
4. Pick best scoring plan for this bus
5. Lock in assignment, move to next bus

**Complexity**: O(buses × plans_per_bus × simulation_cost)
- 20 buses × 10 plans × O(events) ≈ 200 simulations
- Each simulation: O(buses × charges_per_bus) events ≈ O(20 × 2) = 40 events
- Total: ~8000 event operations → sub-second

### Scaling to 1000 buses
- Greedy approach still O(buses × plans × events)
- 1000 × 10 × 2000 = 20M operations → ~1-2 seconds
- If too slow: add heuristics (prune bad plans early, cache simulation results)

---

## Testing Strategy

### Unit Tests
- **Constraints**: Test each constraint with valid/invalid plans
- **Objectives**: Test scoring logic with known scenarios
- **Route utilities**: Distance calculations, station ordering

### Integration Tests
- **Each scenario**: Load, schedule, verify output
- **Constraint violations**: Ensure no invalid schedules produced
- **Weight sensitivity**: Change weights, verify different results

### Manual Testing
- **UI flow**: Load each scenario, inspect tables
- **Edge cases**: Single bus, all buses same time, asymmetric routes

---

## Deployment

### Streamlit Community Cloud
1. Push code to GitHub (public repo)
2. Connect repo to Streamlit Cloud
3. Streamlit reads `requirements.txt` and installs dependencies
4. App auto-deploys on push

### Local Development
```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Open Design Questions

### 1. Greedy vs Optimal
**Decision**: Use greedy sequential assignment.
**Rationale**: Fast, transparent, good enough for this scale. Optimal search is exponential.
**Trade-off**: May miss global optimum, but real-world has uncertainty anyway.

### 2. FIFO vs Priority Queue at Stations
**Decision**: Start with FIFO, make it pluggable.
**Rationale**: FIFO is simple and fair. Priority queue can be added as a rule.
**Implementation**: `ChargerAllocator` interface with `FIFOAllocator` and `PriorityAllocator` implementations.

### 3. Partial Charging
**Decision**: Not supported initially (always charge to full).
**Rationale**: Simplifies model. Can be added later as a parameter.
**Extension path**: Add `charge_to_percent` field in charging plan.

### 4. Dynamic Charger Availability
**Decision**: Not supported initially (chargers always available).
**Rationale**: No requirement for it yet.
**Extension path**: Add `availability_windows` to Station, check in event simulator.

---

## Correctness Properties

### Hard Properties (Must Always Hold)
1. **Range Safety**: No bus ever exceeds battery capacity between charges
2. **Charger Capacity**: No more than `num_chargers` buses charging simultaneously at any station
3. **Route Order**: Buses visit stations in route order (no backtracking)
4. **Completion**: All buses reach their destination

### Soft Properties (Optimize For)
5. **Individual Fairness**: No single bus waits excessively
6. **Operator Fairness**: Operators' fleets have balanced wait times
7. **Overall Efficiency**: Total wait time is minimized

### Validation
- After scheduling, run validation pass to check properties 1-4
- If any violation, raise error (scheduler bug)
- Properties 5-7 are measured but not enforced

---

## Future Enhancements (Post-Submission)

### Near-term (1-2 weeks)
- Export schedule to CSV
- Validation error messages in UI
- Unit test coverage >80%

### Medium-term (1-2 months)
- Multiple routes sharing stations
- Time-of-day electricity pricing
- Driver shift constraints
- Partial charging support

### Long-term (3-6 months)
- Real-time rescheduling (handle delays)
- Machine learning for demand prediction
- Integration with fleet management system
- Mobile app for drivers

---

## Summary

This design prioritizes **extensibility** and **transparency** over premature optimization.

**Key decisions:**
- Event simulation (not constraint solver) → transparent, debuggable
- Pluggable rules (not monolithic cost function) → easy to extend
- Configuration over code (not hardcoded world) → data-driven changes
- Greedy assignment (not global optimization) → fast, good enough

**Anticipated changes handled:**
- More stations/chargers: data only
- New operators: data only
- New rules: new class + registration
- Multiple routes: minor refactoring (~20 lines)

**What we're NOT building:**
- Real-time updates
- Database persistence
- Complex visualizations
- Mobile app

The goal is a solid foundation that scales gracefully, not a feature-complete product.
