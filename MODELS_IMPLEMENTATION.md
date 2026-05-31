# Pydantic Models Implementation Summary

This document summarizes the implementation of all Pydantic models for the Bus Charging Scheduler.

## Implemented Models

### 1. Route and Station Models

#### Segment
- Represents a segment of the route between two locations
- **Fields**: `from_location`, `to_location`, `distance_km`
- **Validation**: Distance must be positive (> 0)

#### Station
- Represents a charging station along the route
- **Fields**: `id`, `name`, `num_chargers`
- **Validation**: Number of chargers must be at least 1

#### Route
- Represents the complete route with segments and stations
- **Fields**: `id`, `origin`, `destination`, `segments`, `stations`
- **Validation**:
  - Must have at least one segment
  - First segment must start at origin
  - Last segment must end at destination
  - Segments must be continuous (no gaps)
- **Helper Methods**:
  - `get_distance(from_loc, to_loc)`: Calculate distance between two locations
  - `get_stations_on_route(from_loc, to_loc)`: Get stations between two locations in route order

### 2. Bus and Configuration Models

#### Bus
- Represents a bus with its schedule and operator
- **Fields**: `id`, `operator`, `origin`, `destination`, `departure_time`
- **Validation**: Departure time must be in HH:MM format
- **Helper Methods**:
  - `get_departure_datetime(base_date)`: Convert time string to datetime

#### Parameters
- Physical constants and simulation settings
- **Fields**: `battery_capacity_km`, `charge_duration_minutes`, `speed_kmh`
- **Defaults**: 240 km, 25 minutes, 60 km/h
- **Validation**: All values must be positive

#### Weights
- Tunable coefficients for soft objectives
- **Fields**: `individual`, `operator`, `overall`
- **Defaults**: All 1.0
- **Validation**: All weights must be non-negative

### 3. Scenario Model (Top-Level)

#### Scenario
- Top-level configuration containing route, buses, parameters, and weights
- **Fields**: `name`, `route`, `buses`, `parameters`, `weights`
- **Validation**: All buses must have valid origin/destination on the route
- **Helper Methods**:
  - `get_bus(bus_id)`: Get bus by ID

### 4. Charging Plan and Timeline Models

#### ChargingPlan
- Represents a planned sequence of charging stations for a bus
- **Fields**: `bus_id`, `stations`
- **Validation**: Must include at least one station

#### ChargingStop
- Represents a single charging stop in a bus's timeline
- **Fields**: `station`, `arrival_time`, `wait_minutes`, `charge_start`, `charge_end`
- **Validation**: Wait time cannot be negative

#### BusTimeline
- Complete timeline for a single bus including all charging stops
- **Fields**: `bus_id`, `operator`, `direction`, `departure_time`, `charging_stops`, `arrival_time`, `total_wait_minutes`
- **Validation**: Total wait time cannot be negative

### 5. Simulation Result Model

#### StationQueueEntry
- Represents a single bus's charging session at a station
- **Fields**: `bus_id`, `arrival_time`, `charge_start`, `charge_end`

#### SimulationResult
- Complete result of a scheduling simulation
- **Fields**: `bus_timelines` (dict), `station_queues` (dict)
- **Helper Methods**:
  - `get_timeline(bus_id)`: Get timeline for a specific bus
  - `get_station_queue(station_id)`: Get queue for a specific station

## Key Features

### Comprehensive Validation
All models include appropriate validation rules:
- Positive values for distances, capacities, speeds
- Non-negative values for wait times and weights
- Format validation for time strings (HH:MM)
- Structural validation for routes (continuity, origin/destination)
- Cross-model validation (buses must be on route)

### Helper Methods
Utility methods are provided for common operations:
- Distance calculations between locations
- Station lookups on routes
- Time conversions
- Data retrieval by ID

### Type Safety
- All fields have explicit type hints
- Pydantic provides runtime type checking
- Optional fields are properly typed with `Optional[T]`

### Extensibility
The models are designed to support future enhancements:
- Station model can be extended with `charger_type`, `pricing_schedule`, `availability_windows`
- Bus model can be extended with `priority`, `vehicle_type`, `driver_shift`
- Weights model can be extended with additional objective weights
- Parameters model can be extended with `partial_charge_allowed`, `charger_efficiency`

## Testing

A comprehensive test suite (`tests/test_models.py`) has been created covering:
- Valid model creation
- Validation error cases
- Helper method functionality
- Edge cases and boundary conditions

## Usage Example

```python
from scheduler.models import Scenario, Route, Segment, Station, Bus, Parameters, Weights

# Create a simple scenario
route = Route(
    id="bengaluru-kochi",
    origin="Bengaluru",
    destination="Kochi",
    segments=[
        Segment(**{"from": "Bengaluru", "to": "Station A", "distance_km": 100}),
        Segment(**{"from": "Station A", "to": "Kochi", "distance_km": 100})
    ],
    stations=[
        Station(id="A", name="Station A", num_chargers=1)
    ]
)

bus = Bus(
    id="bus-01",
    operator="kpn",
    origin="Bengaluru",
    destination="Kochi",
    departure_time="19:00"
)

scenario = Scenario(
    name="Simple Scenario",
    route=route,
    buses=[bus],
    parameters=Parameters(),
    weights=Weights()
)

# Use helper methods
distance = route.get_distance("Bengaluru", "Kochi")  # 200.0
stations = route.get_stations_on_route("Bengaluru", "Kochi")  # ["A"]
```

## Files Created

1. **scheduler/models.py** - All Pydantic model definitions (380+ lines)
2. **tests/test_models.py** - Comprehensive test suite (350+ lines)
3. **MODELS_IMPLEMENTATION.md** - This documentation file

## Status

✅ All models implemented
✅ All validation rules added
✅ All helper methods implemented
✅ Test suite created
✅ Documentation complete

The models are ready to be used by the scheduler, simulator, and UI components.
