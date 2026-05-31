"""
Event-driven simulation system for the Bus Charging Scheduler.

This module implements a discrete event simulation to model bus arrivals,
charging sessions, and queue management at charging stations.
"""

from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import heapq
from scheduler.models import (
    Scenario, Bus, ChargingPlan, BusTimeline, ChargingStop,
    SimulationResult, StationQueueEntry
)


# ============================================================================
# Event System
# ============================================================================

class EventType(Enum):
    """Types of events in the simulation."""
    BUS_ARRIVES_AT_STATION = 1
    CHARGING_STARTS = 2
    CHARGING_ENDS = 3


@dataclass(order=True)
class Event:
    """
    Represents a discrete event in the simulation.
    
    Events are ordered by time first, then by type priority.
    CHARGING_ENDS events are processed before BUS_ARRIVES_AT_STATION events
    at the same time to ensure chargers are released before new buses try to use them.
    """
    time: datetime = field(compare=True)
    type_priority: int = field(init=False, compare=True)
    type: EventType = field(compare=False)
    bus_id: str = field(compare=False)
    station_id: str = field(compare=False)
    
    def __post_init__(self):
        """Set type priority for proper event ordering."""
        # Lower priority number = processed first
        priority_map = {
            EventType.CHARGING_ENDS: 1,  # Process first
            EventType.CHARGING_STARTS: 2,
            EventType.BUS_ARRIVES_AT_STATION: 3  # Process last
        }
        self.type_priority = priority_map.get(self.type, 99)
    
    def __str__(self) -> str:
        """String representation for debugging."""
        time_str = self.time.strftime("%H:%M")
        return f"{self.type.name} at {time_str} - Bus {self.bus_id} at Station {self.station_id}"


# ============================================================================
# Charger State Management
# ============================================================================

@dataclass
class ChargerAllocation:
    """Represents a charger being used by a bus."""
    bus_id: str
    start_time: datetime
    end_time: datetime


class ChargerState:
    """
    Manages charger allocation and queuing at charging stations.
    
    Each station has a fixed number of chargers. When all chargers are occupied,
    arriving buses are queued in FIFO order.
    """
    
    def __init__(self, scenario: Scenario):
        """
        Initialize charger state for all stations.
        
        Args:
            scenario: The scenario containing station configurations
        """
        self.scenario = scenario
        
        # Map station_id -> list of ChargerAllocation (occupied chargers)
        self.occupied_chargers: Dict[str, List[ChargerAllocation]] = {}
        
        # Map station_id -> queue of (bus_id, arrival_time) waiting for chargers
        self.waiting_queues: Dict[str, List[tuple[str, datetime]]] = {}
        
        # Initialize for each station
        for station in scenario.route.stations:
            self.occupied_chargers[station.id] = []
            self.waiting_queues[station.id] = []
    
    def get_num_chargers(self, station_id: str) -> int:
        """Get the total number of chargers at a station."""
        for station in self.scenario.route.stations:
            if station.id == station_id:
                return station.num_chargers
        return 0
    
    def get_available_chargers(self, station_id: str, current_time: datetime) -> int:
        """
        Get the number of available chargers at a station at a given time.
        
        Args:
            station_id: The station to check
            current_time: The time to check availability
            
        Returns:
            Number of available chargers (0 if all occupied)
        """
        # Clean up expired allocations
        self._cleanup_expired_allocations(station_id, current_time)
        
        total_chargers = self.get_num_chargers(station_id)
        occupied = len(self.occupied_chargers[station_id])
        return total_chargers - occupied
    
    def is_charger_available(self, station_id: str, current_time: datetime) -> bool:
        """
        Check if a charger is available at a station.
        
        Args:
            station_id: The station to check
            current_time: The time to check availability
            
        Returns:
            True if at least one charger is available
        """
        return self.get_available_chargers(station_id, current_time) > 0
    
    def allocate_charger(self, station_id: str, bus_id: str, start_time: datetime, 
                        end_time: datetime) -> bool:
        """
        Allocate a charger to a bus.
        
        Args:
            station_id: The station where charging occurs
            bus_id: The bus that will use the charger
            start_time: When charging starts
            end_time: When charging ends
            
        Returns:
            True if allocation successful, False if no chargers available
        """
        # Clean up expired allocations first
        self._cleanup_expired_allocations(station_id, start_time)
        
        # Check if charger is available
        if not self.is_charger_available(station_id, start_time):
            return False
        
        # Allocate the charger
        allocation = ChargerAllocation(
            bus_id=bus_id,
            start_time=start_time,
            end_time=end_time
        )
        self.occupied_chargers[station_id].append(allocation)
        return True
    
    def release_charger(self, station_id: str, bus_id: str, current_time: datetime) -> None:
        """
        Release a charger when a bus finishes charging.
        
        Args:
            station_id: The station where charging occurred
            bus_id: The bus that was using the charger
            current_time: The time when charging ends
        """
        # Remove the allocation for this bus
        self.occupied_chargers[station_id] = [
            alloc for alloc in self.occupied_chargers[station_id]
            if alloc.bus_id != bus_id
        ]
    
    def add_to_queue(self, station_id: str, bus_id: str, arrival_time: datetime) -> None:
        """
        Add a bus to the waiting queue at a station.
        
        Args:
            station_id: The station where the bus is waiting
            bus_id: The bus that is waiting
            arrival_time: When the bus arrived at the station
        """
        self.waiting_queues[station_id].append((bus_id, arrival_time))
    
    def get_next_in_queue(self, station_id: str) -> Optional[tuple[str, datetime]]:
        """
        Get the next bus in the waiting queue (FIFO).
        
        Args:
            station_id: The station to check
            
        Returns:
            Tuple of (bus_id, arrival_time) or None if queue is empty
        """
        if self.waiting_queues[station_id]:
            return self.waiting_queues[station_id].pop(0)
        return None
    
    def get_queue_length(self, station_id: str) -> int:
        """Get the number of buses waiting at a station."""
        return len(self.waiting_queues[station_id])
    
    def _cleanup_expired_allocations(self, station_id: str, current_time: datetime) -> None:
        """
        Remove allocations that have expired (end_time <= current_time).
        A charger is free at exactly the moment its end_time is reached.
        
        Args:
            station_id: The station to clean up
            current_time: The current simulation time
        """
        self.occupied_chargers[station_id] = [
            alloc for alloc in self.occupied_chargers[station_id]
            if alloc.end_time > current_time  # Keep allocations that end AFTER current_time
        ]
        """
        Get the earliest time a charger will be free at a station.
        
        Args:
            station_id: The station to check
            
        Returns:
            Earliest datetime when a charger is available
        """
        num_chargers = self.get_num_chargers(station_id)
        if not self.occupied_chargers[station_id]:
            from datetime import datetime
            return datetime.min
        
        # Sort allocations by end time and return the Nth earliest
        # (where N = num_chargers), meaning when a slot opens up
        end_times = sorted(alloc.end_time for alloc in self.occupied_chargers[station_id])
        if len(end_times) < num_chargers:
            from datetime import datetime
            return datetime.min
        return end_times[num_chargers - 1]


# ============================================================================
# Event Simulator
# ============================================================================

class EventSimulator:
    """
    Discrete event simulator for bus charging scheduling.
    
    This simulator processes events chronologically using a priority queue,
    managing bus movements, charger allocation, and queue management.
    """
    
    def __init__(self, scenario: Scenario, base_date: Optional[datetime] = None):
        """
        Initialize the event simulator.
        
        Args:
            scenario: The scenario to simulate
            base_date: Base date for simulation (defaults to today)
        """
        self.scenario = scenario
        self.base_date = base_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Event queue (min-heap by time)
        self.event_queue: List[Event] = []
        
        # Charger state manager
        self.charger_state = ChargerState(scenario)
        
        # Bus timelines being built
        self.bus_timelines: Dict[str, BusTimeline] = {}
        
        # Track charging stops for each bus (temporary storage during simulation)
        self.charging_stops: Dict[str, List[ChargingStop]] = {}
        
        # Track all charging sessions for station queue view
        self.station_sessions: Dict[str, List[StationQueueEntry]] = {}
        
        # Track bus current position in their charging plan
        self.bus_plan_index: Dict[str, int] = {}
        
        # Track bus arrival times at stations (for wait time calculation)
        self.bus_arrival_times: Dict[tuple[str, str], datetime] = {}
        
        # Store charging plans for each bus
        self.bus_plans: Dict[str, ChargingPlan] = {}
        
        # Initialize station sessions
        for station in scenario.route.stations:
            self.station_sessions[station.id] = []
    
    def simulate(self, charging_plans: Dict[str, ChargingPlan]) -> SimulationResult:
        """
        Run the complete simulation for all buses.
        
        Args:
            charging_plans: Map of bus_id to ChargingPlan
            
        Returns:
            SimulationResult containing timelines and station queues
        """
        # Store charging plans
        self.bus_plans = charging_plans
        
        # Initialize: schedule all bus journeys
        for bus in self.scenario.buses:
            if bus.id in charging_plans:
                self._schedule_bus_journey(bus, charging_plans[bus.id])
        
        # Process events chronologically
        while self.event_queue:
            event = heapq.heappop(self.event_queue)
            self._handle_event(event)
        
        # Build final result
        return self._build_result()
    
    def _schedule_bus_journey(self, bus: Bus, plan: ChargingPlan) -> None:
        """
        Schedule the initial departure and first charging stop for a bus.
        
        Args:
            bus: The bus to schedule
            plan: The charging plan for this bus
        """
        # Initialize tracking
        self.bus_plan_index[bus.id] = 0
        self.charging_stops[bus.id] = []
        
        # Get departure time
        departure_time = bus.get_departure_datetime(self.base_date)
        
        # Calculate arrival at first charging station
        if plan.stations:
            first_station_id = plan.stations[0]
            first_station = self._get_station_by_id(first_station_id)
            
            if first_station:
                # Calculate travel time to first station
                # Station ID is also the location name in the route
                distance = self.scenario.route.get_distance(bus.origin, first_station_id)
                travel_time = self._calculate_travel_time(distance)
                arrival_time = departure_time + travel_time
                
                # Schedule arrival event
                event = Event(
                    time=arrival_time,
                    type=EventType.BUS_ARRIVES_AT_STATION,
                    bus_id=bus.id,
                    station_id=first_station_id
                )
                heapq.heappush(self.event_queue, event)
    
    def _handle_event(self, event: Event) -> None:
        """
        Dispatch event to appropriate handler.
        
        Args:
            event: The event to handle
        """
        if event.type == EventType.BUS_ARRIVES_AT_STATION:
            self._handle_arrival(event)
        elif event.type == EventType.CHARGING_STARTS:
            self._handle_charge_start(event)
        elif event.type == EventType.CHARGING_ENDS:
            self._handle_charge_end(event)
    
    def _handle_arrival(self, event: Event) -> None:
        """
        Handle a bus arriving at a charging station.
        
        If a charger is available, start charging immediately.
        Otherwise, add the bus to the waiting queue.
        
        Args:
            event: The arrival event
        """
        bus_id = event.bus_id
        station_id = event.station_id
        arrival_time = event.time
        
        # Record arrival time for wait calculation
        self.bus_arrival_times[(bus_id, station_id)] = arrival_time
        
        # Check if a charger is available
        if self.charger_state.is_charger_available(station_id, arrival_time):
            # Start charging immediately
            self._start_charging(bus_id, station_id, arrival_time)
        else:
            # Add to waiting queue
            self.charger_state.add_to_queue(station_id, bus_id, arrival_time)
    
    def _start_charging(self, bus_id: str, station_id: str, charge_start_time: datetime) -> None:
        """
        Start charging for a bus.
        
        Allocate a charger, schedule the charging end event, and record the charging stop.
        
        Args:
            bus_id: The bus that will charge
            station_id: The station where charging occurs
            charge_start_time: When charging starts
        """
        # Calculate charge end time
        charge_duration = timedelta(minutes=self.scenario.parameters.charge_duration_minutes)
        charge_end_time = charge_start_time + charge_duration
        
        # Allocate charger
        success = self.charger_state.allocate_charger(
            station_id, bus_id, charge_start_time, charge_end_time
        )
        
        if not success:
            # This shouldn't happen if logic is correct
            raise RuntimeError(f"Failed to allocate charger for bus {bus_id} at station {station_id}")
        
        # Schedule charge end event
        charge_end_event = Event(
            time=charge_end_time,
            type=EventType.CHARGING_ENDS,
            bus_id=bus_id,
            station_id=station_id
        )
        heapq.heappush(self.event_queue, charge_end_event)
        
        # Record charging stop
        station = self._get_station_by_id(station_id)
        arrival_time = self.bus_arrival_times.get((bus_id, station_id), charge_start_time)
        wait_minutes = int((charge_start_time - arrival_time).total_seconds() / 60)
        
        charging_stop = ChargingStop(
            station=station.name if station else station_id,
            arrival_time=arrival_time.strftime("%H:%M"),
            wait_minutes=wait_minutes,
            charge_start=charge_start_time.strftime("%H:%M"),
            charge_end=charge_end_time.strftime("%H:%M")
        )
        self.charging_stops[bus_id].append(charging_stop)
        
        # Record station session
        session = StationQueueEntry(
            bus_id=bus_id,
            arrival_time=arrival_time.strftime("%H:%M"),
            charge_start=charge_start_time.strftime("%H:%M"),
            charge_end=charge_end_time.strftime("%H:%M")
        )
        self.station_sessions[station_id].append(session)
    
    def _handle_charge_start(self, event: Event) -> None:
        """
        Handle charging starting for a bus.
        
        This event type is no longer used - charging starts immediately
        when a charger becomes available (either on arrival or when a
        previous bus finishes charging).
        
        Args:
            event: The charge start event
        """
        # This should not be called anymore
        raise RuntimeError("CHARGING_STARTS event should not be used")
    
    def _handle_charge_end(self, event: Event) -> None:
        """
        Handle charging ending for a bus.
        
        Release the charger, check if any buses are waiting, and continue
        the bus's journey to the next station or destination.
        
        Args:
            event: The charge end event
        """
        bus_id = event.bus_id
        station_id = event.station_id
        charge_end_time = event.time
        
        # Release charger
        self.charger_state.release_charger(station_id, bus_id, charge_end_time)
        
        # Check if any buses are waiting and start charging the next one
        next_bus = self.charger_state.get_next_in_queue(station_id)
        if next_bus:
            next_bus_id, arrival_time = next_bus
            # Start charging immediately for the next bus
            self._start_charging(next_bus_id, station_id, charge_end_time)
        
        # Continue this bus's journey
        self._continue_bus_journey(bus_id, station_id, charge_end_time)
    
    def _continue_bus_journey(self, bus_id: str, current_station_id: str, 
                             current_time: datetime) -> None:
        """
        Continue a bus's journey to the next station or destination.
        
        Args:
            bus_id: The bus to continue
            current_station_id: The station where the bus just finished charging
            current_time: The time when charging ended
        """
        bus = self.scenario.get_bus(bus_id)
        if not bus:
            return
        
        # Get the bus's charging plan
        plan = self.bus_plans.get(bus_id)
        if not plan:
            return
        
        # Get current index in the plan
        current_index = self.bus_plan_index.get(bus_id, 0)
        
        # Check if there are more stations in the plan
        if current_index + 1 < len(plan.stations):
            # There's another charging station to visit
            next_station_id = plan.stations[current_index + 1]
            next_station = self._get_station_by_id(next_station_id)
            current_station = self._get_station_by_id(current_station_id)
            
            if next_station and current_station:
                # Calculate travel time to next station
                # Station IDs are also location names in the route
                distance = self.scenario.route.get_distance(current_station_id, next_station_id)
                travel_time = self._calculate_travel_time(distance)
                arrival_time = current_time + travel_time
                
                # Update plan index
                self.bus_plan_index[bus_id] = current_index + 1
                
                # Schedule arrival at next station
                event = Event(
                    time=arrival_time,
                    type=EventType.BUS_ARRIVES_AT_STATION,
                    bus_id=bus_id,
                    station_id=next_station_id
                )
                heapq.heappush(self.event_queue, event)
        else:
            # No more charging stations - go to destination
            current_station = self._get_station_by_id(current_station_id)
            if not current_station:
                return
            
            # Calculate travel to destination
            # Station ID is also the location name in the route
            distance_to_dest = self.scenario.route.get_distance(current_station_id, bus.destination)
            travel_time = self._calculate_travel_time(distance_to_dest)
            arrival_at_dest = current_time + travel_time
            
            # Create timeline for this bus
            total_wait = sum(stop.wait_minutes for stop in self.charging_stops[bus_id])
            
            timeline = BusTimeline(
                bus_id=bus.id,
                operator=bus.operator,
                direction=f"{bus.origin}→{bus.destination}",
                departure_time=bus.departure_time,
                charging_stops=self.charging_stops[bus_id],
                arrival_time=arrival_at_dest.strftime("%H:%M"),
                total_wait_minutes=total_wait
            )
            self.bus_timelines[bus_id] = timeline
    
    def _calculate_travel_time(self, distance_km: float) -> timedelta:
        """
        Calculate travel time based on distance and speed.
        
        Args:
            distance_km: Distance to travel in kilometers
            
        Returns:
            Travel time as timedelta
        """
        speed_kmh = self.scenario.parameters.speed_kmh
        hours = distance_km / speed_kmh
        return timedelta(hours=hours)
    
    def _get_station_by_id(self, station_id: str) -> Optional[object]:
        """Get station object by ID."""
        for station in self.scenario.route.stations:
            if station.id == station_id:
                return station
        return None
    
    def _build_result(self) -> SimulationResult:
        """
        Build the final simulation result.
        
        Returns:
            SimulationResult with timelines and station queues
        """
        return SimulationResult(
            bus_timelines=self.bus_timelines,
            station_queues=self.station_sessions
        )
