"""
Data models for the Bus Charging Scheduler.

This module defines all Pydantic models for scenario configuration,
simulation state, and results.
"""

from datetime import datetime, time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


# ============================================================================
# Route and Station Models
# ============================================================================

class Segment(BaseModel):
    """Represents a segment of the route between two locations."""
    from_location: str = Field(..., alias="from", description="Starting location name")
    to_location: str = Field(..., alias="to", description="Ending location name")
    distance_km: float = Field(..., gt=0, description="Distance in kilometers")

    class Config:
        populate_by_name = True

    @field_validator('distance_km')
    @classmethod
    def validate_distance(cls, v: float) -> float:
        if v <= 0:
            raise ValueError('Distance must be positive')
        return v


class Station(BaseModel):
    """Represents a charging station along the route."""
    id: str = Field(..., description="Unique station identifier")
    name: str = Field(..., description="Human-readable station name")
    num_chargers: int = Field(..., ge=1, description="Number of chargers at this station")

    @field_validator('num_chargers')
    @classmethod
    def validate_num_chargers(cls, v: int) -> int:
        if v < 1:
            raise ValueError('Number of chargers must be at least 1')
        return v


class Route(BaseModel):
    """Represents the complete route with segments and stations."""
    id: str = Field(..., description="Unique route identifier")
    origin: str = Field(..., description="Starting location")
    destination: str = Field(..., description="Ending location")
    segments: List[Segment] = Field(..., description="Ordered list of route segments")
    stations: List[Station] = Field(..., description="List of charging stations")

    @model_validator(mode='after')
    def validate_route_continuity(self) -> 'Route':
        """Ensure segments form a continuous path from origin to destination."""
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
        """
        Calculate distance between two locations on the route.
        Supports both forward (Bengaluru→Kochi) and reverse (Kochi→Bengaluru) directions.
        
        Args:
            from_loc: Starting location name
            to_loc: Ending location name
            
        Returns:
            Total distance in kilometers
            
        Raises:
            ValueError: If locations are not on route
        """
        # Build location order map
        locations = [self.origin]
        for segment in self.segments:
            locations.append(segment.to_location)
        
        # Find indices
        try:
            from_idx = locations.index(from_loc)
            to_idx = locations.index(to_loc)
        except ValueError as e:
            raise ValueError(f'Location not found on route: {e}')
        
        if from_idx == to_idx:
            return 0.0
        
        # Support both directions — always sum between the two indices
        lo, hi = min(from_idx, to_idx), max(from_idx, to_idx)
        total_distance = 0.0
        for i in range(lo, hi):
            total_distance += self.segments[i].distance_km
        
        return total_distance

    def get_stations_on_route(self, from_loc: str, to_loc: str) -> List[str]:
        """
        Get list of station IDs between two locations in travel order.
        Supports both forward (Bengaluru→Kochi) and reverse (Kochi→Bengaluru) directions.
        
        Args:
            from_loc: Starting location name
            to_loc: Ending location name
            
        Returns:
            List of station IDs in travel order (reversed for Kochi→Bengaluru buses)
        """
        # Build location order (always forward: Bengaluru → ... → Kochi)
        locations = [self.origin]
        for segment in self.segments:
            locations.append(segment.to_location)
        
        # Find indices
        try:
            from_idx = locations.index(from_loc)
            to_idx = locations.index(to_loc)
        except ValueError as e:
            raise ValueError(f'Location not found on route: {e}')
        
        station_ids = {station.id for station in self.stations}
        reverse = from_idx > to_idx
        lo, hi = min(from_idx, to_idx), max(from_idx, to_idx)
        
        # Collect stations in forward order between the two endpoints
        stations_in_order = []
        for i in range(lo + 1, hi + 1):
            loc = locations[i]
            if loc in station_ids:
                stations_in_order.append(loc)
        
        # For reverse-direction buses, return stations in reverse travel order
        if reverse:
            stations_in_order = list(reversed(stations_in_order))
        
        return stations_in_order


# ============================================================================
# Bus and Configuration Models
# ============================================================================

class Bus(BaseModel):
    """Represents a bus with its schedule and operator."""
    id: str = Field(..., description="Unique bus identifier")
    operator: str = Field(..., description="Operator name (e.g., 'kpn', 'ksrtc')")
    origin: str = Field(..., description="Starting location")
    destination: str = Field(..., description="Ending location")
    departure_time: str = Field(..., description="Departure time in HH:MM format")

    @field_validator('departure_time')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time is in HH:MM format."""
        try:
            time.fromisoformat(v)
        except ValueError:
            raise ValueError('departure_time must be in HH:MM format (e.g., "19:00")')
        return v

    def get_departure_datetime(self, base_date: datetime) -> datetime:
        """
        Convert departure time string to datetime.
        
        Args:
            base_date: Base date to use for the departure
            
        Returns:
            Full datetime object
        """
        t = time.fromisoformat(self.departure_time)
        return datetime.combine(base_date.date(), t)


class Parameters(BaseModel):
    """Physical constants and simulation settings."""
    battery_capacity_km: float = Field(240.0, gt=0, description="Battery capacity in kilometers")
    charge_duration_minutes: int = Field(25, gt=0, description="Time to fully charge in minutes")
    speed_kmh: float = Field(60.0, gt=0, description="Average bus speed in km/h")

    @field_validator('battery_capacity_km', 'speed_kmh')
    @classmethod
    def validate_positive_float(cls, v: float) -> float:
        if v <= 0:
            raise ValueError('Value must be positive')
        return v

    @field_validator('charge_duration_minutes')
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('Value must be positive')
        return v


class Weights(BaseModel):
    """Tunable coefficients for soft objectives."""
    individual: float = Field(1.0, ge=0, description="Weight for individual wait time objective")
    operator: float = Field(1.0, ge=0, description="Weight for operator fairness objective")
    overall: float = Field(1.0, ge=0, description="Weight for overall efficiency objective")

    @field_validator('individual', 'operator', 'overall')
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError('Weight must be non-negative')
        return v


# ============================================================================
# Scenario Model (Top-Level)
# ============================================================================

class Scenario(BaseModel):
    """Top-level scenario configuration containing route, buses, parameters, and weights."""
    name: str = Field(..., description="Scenario name")
    route: Route = Field(..., description="Route configuration")
    buses: List[Bus] = Field(..., description="List of buses to schedule")
    parameters: Parameters = Field(default_factory=Parameters, description="Simulation parameters")
    weights: Weights = Field(default_factory=Weights, description="Objective weights")

    @model_validator(mode='after')
    def validate_buses_on_route(self) -> 'Scenario':
        """Ensure all buses have valid origin/destination on the route."""
        # Build set of valid locations
        valid_locations = {self.route.origin, self.route.destination}
        for segment in self.route.segments:
            valid_locations.add(segment.from_location)
            valid_locations.add(segment.to_location)
        
        # Check each bus
        for bus in self.buses:
            if bus.origin not in valid_locations:
                raise ValueError(f'Bus {bus.id} origin {bus.origin} not on route')
            if bus.destination not in valid_locations:
                raise ValueError(f'Bus {bus.id} destination {bus.destination} not on route')
        
        return self

    def get_bus(self, bus_id: str) -> Optional[Bus]:
        """Get bus by ID."""
        for bus in self.buses:
            if bus.id == bus_id:
                return bus
        return None


# ============================================================================
# Charging Plan and Timeline Models
# ============================================================================

class ChargingPlan(BaseModel):
    """Represents a planned sequence of charging stations for a bus."""
    bus_id: str = Field(..., description="Bus identifier")
    stations: List[str] = Field(..., description="Ordered list of station IDs to charge at")

    @field_validator('stations')
    @classmethod
    def validate_stations_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError('Charging plan must include at least one station')
        return v


class ChargingStop(BaseModel):
    """Represents a single charging stop in a bus's timeline."""
    station: str = Field(..., description="Station name")
    arrival_time: str = Field(..., description="Time bus arrives at station (HH:MM)")
    wait_minutes: int = Field(..., ge=0, description="Minutes waited before charging")
    charge_start: str = Field(..., description="Time charging starts (HH:MM)")
    charge_end: str = Field(..., description="Time charging ends (HH:MM)")

    @field_validator('wait_minutes')
    @classmethod
    def validate_wait_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError('Wait time cannot be negative')
        return v


class BusTimeline(BaseModel):
    """Complete timeline for a single bus including all charging stops."""
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
        if v < 0:
            raise ValueError('Total wait time cannot be negative')
        return v


# ============================================================================
# Simulation Result Model
# ============================================================================

class StationQueueEntry(BaseModel):
    """Represents a single bus's charging session at a station."""
    bus_id: str = Field(..., description="Bus identifier")
    arrival_time: str = Field(..., description="Time bus arrived (HH:MM)")
    charge_start: str = Field(..., description="Time charging started (HH:MM)")
    charge_end: str = Field(..., description="Time charging ended (HH:MM)")


class SimulationResult(BaseModel):
    """Complete result of a scheduling simulation."""
    bus_timelines: Dict[str, BusTimeline] = Field(
        default_factory=dict,
        description="Map of bus_id to timeline"
    )
    station_queues: Dict[str, List[StationQueueEntry]] = Field(
        default_factory=dict,
        description="Map of station_id to chronological queue"
    )

    def get_timeline(self, bus_id: str) -> Optional[BusTimeline]:
        """Get timeline for a specific bus."""
        return self.bus_timelines.get(bus_id)

    def get_station_queue(self, station_id: str) -> List[StationQueueEntry]:
        """Get queue for a specific station."""
        return self.station_queues.get(station_id, [])
