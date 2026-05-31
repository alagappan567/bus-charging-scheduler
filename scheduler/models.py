"""
Data models for the Bus Charging Scheduler.

This module defines all Pydantic models for scenario configuration,
simulation state, and results.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


# ============================================================================
# Route and Station Models
# ============================================================================

class Segment(BaseModel):
    """Represents a segment of the route between two locations.

    A segment is a directed edge in the route graph, connecting two
    consecutive locations with a known distance.

    Attributes:
        from_location: Name of the starting location.
        to_location: Name of the ending location.
        distance_km: Distance of this segment in kilometres (must be > 0).
    """

    from_location: str = Field(..., alias="from", description="Starting location name")
    to_location: str = Field(..., alias="to", description="Ending location name")
    distance_km: float = Field(..., gt=0, description="Distance in kilometers")

    model_config = {"populate_by_name": True}

    @field_validator('distance_km')
    @classmethod
    def validate_distance(cls, v: float) -> float:
        """Ensure distance is strictly positive.

        Args:
            v: The distance value to validate.

        Returns:
            The validated distance value.

        Raises:
            ValueError: If distance is not positive.
        """
        if v <= 0:
            raise ValueError('Distance must be positive')
        return v


class Station(BaseModel):
    """Represents a charging station along the route.

    Stations are the physical locations where buses can charge.  Each
    station has one or more chargers; the number of chargers controls
    how many buses can charge simultaneously.

    Attributes:
        id: Unique station identifier (also used as the location name in
            route segments, e.g. ``"A"``, ``"B"``).
        name: Human-readable display name (e.g. ``"Station A"``).
        num_chargers: Number of chargers available at this station (≥ 1).
    """

    id: str = Field(..., description="Unique station identifier")
    name: str = Field(..., description="Human-readable station name")
    num_chargers: int = Field(..., ge=1, description="Number of chargers at this station")

    @field_validator('num_chargers')
    @classmethod
    def validate_num_chargers(cls, v: int) -> int:
        """Ensure at least one charger is present.

        Args:
            v: The number of chargers to validate.

        Returns:
            The validated charger count.

        Raises:
            ValueError: If the count is less than 1.
        """
        if v < 1:
            raise ValueError('Number of chargers must be at least 1')
        return v


class Route(BaseModel):
    """Represents the complete route with segments and stations.

    A route is an ordered sequence of segments that forms a continuous
    path from ``origin`` to ``destination``.  Stations are a subset of
    the locations on that path where buses can charge.

    The route supports both forward (origin → destination) and reverse
    (destination → origin) travel, which is needed for bidirectional
    bus services.

    Attributes:
        id: Unique route identifier.
        origin: Name of the starting location.
        destination: Name of the ending location.
        segments: Ordered list of segments forming the route.
        stations: List of charging stations on the route.
    """

    id: str = Field(..., description="Unique route identifier")
    origin: str = Field(..., description="Starting location")
    destination: str = Field(..., description="Ending location")
    segments: List[Segment] = Field(..., description="Ordered list of route segments")
    stations: List[Station] = Field(..., description="List of charging stations")

    @model_validator(mode='after')
    def validate_route_continuity(self) -> Route:
        """Ensure segments form a continuous path from origin to destination.

        Checks that:
        - The first segment starts at ``origin``.
        - The last segment ends at ``destination``.
        - Each segment's ``to_location`` matches the next segment's
          ``from_location`` (no gaps or jumps).

        Returns:
            The validated Route instance.

        Raises:
            ValueError: If the route is discontinuous or endpoints mismatch.
        """
        if not self.segments:
            raise ValueError('Route must have at least one segment')

        # Check first segment starts at origin
        if self.segments[0].from_location != self.origin:
            raise ValueError(f'First segment must start at origin {self.origin}')

        # Check last segment ends at destination
        if self.segments[-1].to_location != self.destination:
            raise ValueError(f'Last segment must end at destination {self.destination}')

        # Check continuity between segments
        for i in range(len(self.segments) - 1):
            if self.segments[i].to_location != self.segments[i + 1].from_location:
                raise ValueError(
                    f'Segment {i} ends at {self.segments[i].to_location} but '
                    f'segment {i+1} starts at {self.segments[i + 1].from_location}'
                )

        return self

    def get_distance(self, from_loc: str, to_loc: str) -> float:
        """Calculate the distance between two locations on the route.

        Supports both forward (Bengaluru → Kochi) and reverse
        (Kochi → Bengaluru) directions by summing the segment distances
        between the two location indices regardless of order.

        Args:
            from_loc: Name of the starting location.
            to_loc: Name of the ending location.

        Returns:
            Total distance in kilometres.  Returns ``0.0`` if both
            locations are the same.

        Raises:
            ValueError: If either location is not found on the route.
        """
        # Build an ordered list of all locations along the route
        # (origin, then each segment's destination in order)
        locations = [self.origin]
        for segment in self.segments:
            locations.append(segment.to_location)

        # Resolve both locations to their positional indices
        try:
            from_idx = locations.index(from_loc)
            to_idx = locations.index(to_loc)
        except ValueError as e:
            raise ValueError(f'Location not found on route: {e}')

        if from_idx == to_idx:
            return 0.0

        # Sum segment distances between the two indices regardless of direction.
        # Using min/max means this works for both forward and reverse travel.
        lo, hi = min(from_idx, to_idx), max(from_idx, to_idx)
        total_distance = 0.0
        for i in range(lo, hi):
            total_distance += self.segments[i].distance_km

        return total_distance

    def get_stations_on_route(self, from_loc: str, to_loc: str) -> List[str]:
        """Get station IDs between two locations in travel order.

        Supports both forward (Bengaluru → Kochi) and reverse
        (Kochi → Bengaluru) directions.  For reverse-direction buses the
        returned list is reversed so that it always reflects the actual
        travel order of that bus.

        Args:
            from_loc: Name of the starting location.
            to_loc: Name of the ending location.

        Returns:
            List of station IDs in the order the bus will encounter them.
            Empty list if there are no stations between the two locations.

        Raises:
            ValueError: If either location is not found on the route.
        """
        # Build the canonical forward-direction location list
        locations = [self.origin]
        for segment in self.segments:
            locations.append(segment.to_location)

        # Resolve both endpoints to indices
        try:
            from_idx = locations.index(from_loc)
            to_idx = locations.index(to_loc)
        except ValueError as e:
            raise ValueError(f'Location not found on route: {e}')

        # Station IDs form a set for O(1) membership checks
        station_ids = {station.id for station in self.stations}

        # Determine travel direction so we can reverse the result if needed
        reverse = from_idx > to_idx
        lo, hi = min(from_idx, to_idx), max(from_idx, to_idx)

        # Collect stations that lie strictly between the two endpoints
        # (index lo is the departure point, so we start from lo+1)
        stations_in_order: List[str] = []
        for i in range(lo + 1, hi + 1):
            loc = locations[i]
            if loc in station_ids:
                stations_in_order.append(loc)

        # Reverse for buses travelling in the opposite direction so the
        # caller always receives stations in the bus's actual travel order
        if reverse:
            stations_in_order = list(reversed(stations_in_order))

        return stations_in_order


# ============================================================================
# Bus and Configuration Models
# ============================================================================

class Bus(BaseModel):
    """Represents a bus with its schedule and operator affiliation.

    Attributes:
        id: Unique bus identifier (e.g. ``"bus-BK-01"``).
        operator: Operator name (e.g. ``"kpn"``, ``"ksrtc"``).
        origin: Name of the bus's starting location.
        destination: Name of the bus's ending location.
        departure_time: Scheduled departure time in ``HH:MM`` format.
    """

    id: str = Field(..., description="Unique bus identifier")
    operator: str = Field(..., description="Operator name (e.g., 'kpn', 'ksrtc')")
    origin: str = Field(..., description="Starting location")
    destination: str = Field(..., description="Ending location")
    departure_time: str = Field(..., description="Departure time in HH:MM format")

    @field_validator('departure_time')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate that departure_time is in ``HH:MM`` format.

        Args:
            v: The time string to validate.

        Returns:
            The validated time string.

        Raises:
            ValueError: If the string is not a valid ``HH:MM`` time.
        """
        try:
            time.fromisoformat(v)
        except ValueError:
            raise ValueError('departure_time must be in HH:MM format (e.g., "19:00")')
        return v

    def get_departure_datetime(self, base_date: datetime) -> datetime:
        """Convert the departure time string to a full ``datetime`` object.

        Args:
            base_date: The calendar date to combine with the departure time.

        Returns:
            A ``datetime`` representing the exact departure moment.
        """
        t = time.fromisoformat(self.departure_time)
        return datetime.combine(base_date.date(), t)


class Parameters(BaseModel):
    """Physical constants and simulation settings.

    These values are read from the scenario JSON and control the physics
    of the simulation.  All values can be changed via configuration
    without touching any code.

    Attributes:
        battery_capacity_km: Maximum range on a full charge in kilometres.
        charge_duration_minutes: Time required for a full charge in minutes.
        speed_kmh: Constant bus speed used for travel-time calculations.
    """

    battery_capacity_km: float = Field(240.0, gt=0, description="Battery capacity in kilometers")
    charge_duration_minutes: int = Field(25, gt=0, description="Time to fully charge in minutes")
    speed_kmh: float = Field(60.0, gt=0, description="Average bus speed in km/h")

    @field_validator('battery_capacity_km', 'speed_kmh')
    @classmethod
    def validate_positive_float(cls, v: float) -> float:
        """Ensure float parameters are strictly positive.

        Args:
            v: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If the value is not positive.
        """
        if v <= 0:
            raise ValueError('Value must be positive')
        return v

    @field_validator('charge_duration_minutes')
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """Ensure integer parameters are strictly positive.

        Args:
            v: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If the value is not positive.
        """
        if v <= 0:
            raise ValueError('Value must be positive')
        return v


class Weights(BaseModel):
    """Tunable coefficients for soft objectives.

    Each weight scales the contribution of its corresponding objective
    to the total score.  Setting a weight to ``0.0`` effectively disables
    that objective.  Weights must be non-negative.

    Attributes:
        individual: Weight for the individual wait-time objective.
        operator: Weight for the operator-fairness objective.
        overall: Weight for the overall-efficiency objective.
    """

    individual: float = Field(1.0, ge=0, description="Weight for individual wait time objective")
    operator: float = Field(1.0, ge=0, description="Weight for operator fairness objective")
    overall: float = Field(1.0, ge=0, description="Weight for overall efficiency objective")

    @field_validator('individual', 'operator', 'overall')
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        """Ensure weights are non-negative.

        Args:
            v: The weight value to validate.

        Returns:
            The validated weight.

        Raises:
            ValueError: If the weight is negative.
        """
        if v < 0:
            raise ValueError('Weight must be non-negative')
        return v


# ============================================================================
# Scenario Model (Top-Level)
# ============================================================================

class Scenario(BaseModel):
    """Top-level scenario configuration.

    A scenario bundles everything needed to run a scheduling simulation:
    the physical route, the fleet of buses, simulation parameters, and
    the objective weights.

    Attributes:
        name: Human-readable scenario name (e.g. ``"Scenario 1 - Even Spacing"``).
        route: Route configuration including segments and stations.
        buses: List of buses to schedule.
        parameters: Physical simulation parameters.
        weights: Objective weights for scoring.
    """

    name: str = Field(..., description="Scenario name")
    route: Route = Field(..., description="Route configuration")
    buses: List[Bus] = Field(..., description="List of buses to schedule")
    parameters: Parameters = Field(default_factory=Parameters, description="Simulation parameters")
    weights: Weights = Field(default_factory=Weights, description="Objective weights")

    @model_validator(mode='after')
    def validate_buses_on_route(self) -> Scenario:
        """Ensure every bus has a valid origin and destination on the route.

        Builds the set of all named locations from the route segments and
        checks that each bus's ``origin`` and ``destination`` are members.

        Returns:
            The validated Scenario instance.

        Raises:
            ValueError: If any bus references a location not on the route.
        """
        # Collect every named location that appears in the route definition
        valid_locations = {self.route.origin, self.route.destination}
        for segment in self.route.segments:
            valid_locations.add(segment.from_location)
            valid_locations.add(segment.to_location)

        # Validate each bus against the collected location set
        for bus in self.buses:
            if bus.origin not in valid_locations:
                raise ValueError(f'Bus {bus.id} origin {bus.origin} not on route')
            if bus.destination not in valid_locations:
                raise ValueError(f'Bus {bus.id} destination {bus.destination} not on route')

        return self

    def get_bus(self, bus_id: str) -> Optional[Bus]:
        """Look up a bus by its unique identifier.

        Args:
            bus_id: The bus identifier to search for.

        Returns:
            The matching ``Bus`` object, or ``None`` if not found.
        """
        for bus in self.buses:
            if bus.id == bus_id:
                return bus
        return None


# ============================================================================
# Charging Plan and Timeline Models
# ============================================================================

class ChargingPlan(BaseModel):
    """Represents a planned sequence of charging stations for a bus.

    A charging plan is a candidate assignment produced by the plan
    generator and later validated by the constraint system.  It records
    which stations a bus will charge at, in travel order.

    Attributes:
        bus_id: Identifier of the bus this plan belongs to.
        stations: Ordered list of station IDs the bus will charge at.
    """

    bus_id: str = Field(..., description="Bus identifier")
    stations: List[str] = Field(..., description="Ordered list of station IDs to charge at")

    @field_validator('stations')
    @classmethod
    def validate_stations_not_empty(cls, v: List[str]) -> List[str]:
        """Ensure the plan contains at least one charging station.

        Args:
            v: The list of station IDs to validate.

        Returns:
            The validated list.

        Raises:
            ValueError: If the list is empty.
        """
        if not v:
            raise ValueError('Charging plan must include at least one station')
        return v


class ChargingStop(BaseModel):
    """Represents a single charging stop in a bus's timeline.

    Captures the full timing information for one visit to a charging
    station, including any time spent waiting for a charger to become
    available.

    Attributes:
        station: Human-readable station name.
        arrival_time: Time the bus arrived at the station (``HH:MM``).
        wait_minutes: Minutes spent waiting before a charger was free.
        charge_start: Time charging began (``HH:MM``).
        charge_end: Time charging finished (``HH:MM``).
    """

    station: str = Field(..., description="Station name")
    arrival_time: str = Field(..., description="Time bus arrives at station (HH:MM)")
    wait_minutes: int = Field(..., ge=0, description="Minutes waited before charging")
    charge_start: str = Field(..., description="Time charging starts (HH:MM)")
    charge_end: str = Field(..., description="Time charging ends (HH:MM)")

    @field_validator('wait_minutes')
    @classmethod
    def validate_wait_non_negative(cls, v: int) -> int:
        """Ensure wait time is non-negative.

        Args:
            v: The wait time in minutes.

        Returns:
            The validated wait time.

        Raises:
            ValueError: If the wait time is negative.
        """
        if v < 0:
            raise ValueError('Wait time cannot be negative')
        return v


class BusTimeline(BaseModel):
    """Complete timeline for a single bus including all charging stops.

    This is the primary output model for a bus.  It records the full
    journey from departure through each charging stop to final arrival.

    Attributes:
        bus_id: Unique bus identifier.
        operator: Operator name.
        direction: Human-readable route direction (e.g. ``"Bengaluru→Kochi"``).
        departure_time: Scheduled departure time (``HH:MM``).
        charging_stops: Ordered list of charging stops made during the journey.
        arrival_time: Final arrival time at the destination (``HH:MM``).
        total_wait_minutes: Sum of all wait times across all charging stops.
    """

    bus_id: str = Field(..., description="Bus identifier")
    operator: str = Field(..., description="Operator name")
    direction: str = Field(..., description="Route direction (e.g., 'Bengaluru→Kochi')")
    departure_time: str = Field(..., description="Departure time (HH:MM)")
    charging_stops: List[ChargingStop] = Field(default_factory=list, description="List of charging stops")
    arrival_time: str = Field(..., description="Final arrival time at destination (HH:MM)")
    total_wait_minutes: int = Field(..., ge=0, description="Total wait time across all stops")

    @field_validator('total_wait_minutes')
    @classmethod
    def validate_total_wait(cls, v: int) -> int:
        """Ensure total wait time is non-negative.

        Args:
            v: The total wait time in minutes.

        Returns:
            The validated total wait time.

        Raises:
            ValueError: If the total wait time is negative.
        """
        if v < 0:
            raise ValueError('Total wait time cannot be negative')
        return v


# ============================================================================
# Simulation Result Model
# ============================================================================

class StationQueueEntry(BaseModel):
    """Represents a single bus's charging session at a station.

    Used to build the per-station chronological queue view shown in the UI.

    Attributes:
        bus_id: Identifier of the bus that charged.
        arrival_time: Time the bus arrived at the station (``HH:MM``).
        charge_start: Time charging began (``HH:MM``).
        charge_end: Time charging finished (``HH:MM``).
    """

    bus_id: str = Field(..., description="Bus identifier")
    arrival_time: str = Field(..., description="Time bus arrived (HH:MM)")
    charge_start: str = Field(..., description="Time charging started (HH:MM)")
    charge_end: str = Field(..., description="Time charging ended (HH:MM)")


class SimulationResult(BaseModel):
    """Complete result of a scheduling simulation.

    Aggregates all per-bus timelines and per-station queue views produced
    by a single run of the event simulator.

    Attributes:
        bus_timelines: Mapping of ``bus_id`` to its complete ``BusTimeline``.
        station_queues: Mapping of ``station_id`` to the chronological list
            of charging sessions at that station.
    """

    bus_timelines: Dict[str, BusTimeline] = Field(
        default_factory=dict,
        description="Map of bus_id to timeline"
    )
    station_queues: Dict[str, List[StationQueueEntry]] = Field(
        default_factory=dict,
        description="Map of station_id to chronological queue"
    )

    def get_timeline(self, bus_id: str) -> Optional[BusTimeline]:
        """Retrieve the timeline for a specific bus.

        Args:
            bus_id: The bus identifier to look up.

        Returns:
            The ``BusTimeline`` for the bus, or ``None`` if not found.
        """
        return self.bus_timelines.get(bus_id)

    def get_station_queue(self, station_id: str) -> List[StationQueueEntry]:
        """Retrieve the charging queue for a specific station.

        Args:
            station_id: The station identifier to look up.

        Returns:
            Chronological list of ``StationQueueEntry`` objects, or an
            empty list if the station has no recorded sessions.
        """
        return self.station_queues.get(station_id, [])
