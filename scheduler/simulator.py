"""
Event-driven simulation system for the Bus Charging Scheduler.

This module implements a discrete event simulation to model bus arrivals,
charging sessions, and queue management at charging stations.

The simulation uses a min-heap priority queue ordered by event time.
When two events share the same timestamp, ``CHARGING_ENDS`` events are
processed before ``BUS_ARRIVES_AT_STATION`` events so that chargers are
released before newly-arriving buses attempt to claim them.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import heapq
from scheduler.models import (
    Scenario, Bus, ChargingPlan, BusTimeline, ChargingStop,
    SimulationResult, StationQueueEntry, Station,
)


# ============================================================================
# Event System
# ============================================================================

class EventType(Enum):
    """Types of discrete events processed by the simulator."""

    BUS_ARRIVES_AT_STATION = 1
    CHARGING_STARTS = 2
    CHARGING_ENDS = 3


@dataclass(order=True)
class Event:
    """A discrete event in the simulation timeline.

    Events are stored in a min-heap and compared first by ``time``, then
    by ``type_priority``.  The priority ordering ensures that at any
    given timestamp, ``CHARGING_ENDS`` events are processed before
    ``BUS_ARRIVES_AT_STATION`` events — this guarantees chargers are
    freed before new buses try to claim them.

    Attributes:
        time: Wall-clock time at which the event occurs.
        type_priority: Derived ordering key (lower = processed first).
        type: The kind of event (arrival, charge start, charge end).
        bus_id: Identifier of the bus involved.
        station_id: Identifier of the station involved.
    """

    # Fields used for heap comparison (must come first in dataclass order)
    time: datetime = field(compare=True)
    type_priority: int = field(init=False, compare=True)

    # Fields excluded from comparison
    type: EventType = field(compare=False)
    bus_id: str = field(compare=False)
    station_id: str = field(compare=False)

    def __post_init__(self) -> None:
        """Derive ``type_priority`` from the event type after construction.

        Lower priority numbers are processed first at the same timestamp.
        ``CHARGING_ENDS`` (priority 1) must precede ``BUS_ARRIVES_AT_STATION``
        (priority 3) so that released chargers are immediately available
        to newly-arriving buses.
        """
        priority_map = {
            EventType.CHARGING_ENDS: 1,       # Release charger first
            EventType.CHARGING_STARTS: 2,
            EventType.BUS_ARRIVES_AT_STATION: 3,  # Check availability last
        }
        self.type_priority = priority_map.get(self.type, 99)

    def __str__(self) -> str:
        """Return a human-readable representation for debugging.

        Returns:
            String in the form ``"EVENT_TYPE at HH:MM - Bus X at Station Y"``.
        """
        time_str = self.time.strftime("%H:%M")
        return f"{self.type.name} at {time_str} - Bus {self.bus_id} at Station {self.station_id}"


# ============================================================================
# Charger State Management
# ============================================================================

@dataclass
class ChargerAllocation:
    """Records a charger being occupied by a specific bus.

    Attributes:
        bus_id: The bus currently using the charger.
        start_time: When charging began.
        end_time: When charging will finish (charger is free at this moment).
    """

    bus_id: str
    start_time: datetime
    end_time: datetime


class ChargerState:
    """Manages charger allocation and FIFO queuing at all charging stations.

    Each station has a fixed number of chargers (``Station.num_chargers``).
    When all chargers are occupied, arriving buses are placed in a FIFO
    queue and served in arrival order once a charger becomes free.

    Attributes:
        scenario: The scenario containing station configurations.
        occupied_chargers: Maps ``station_id`` to the list of active
            :class:`ChargerAllocation` objects.
        waiting_queues: Maps ``station_id`` to the FIFO queue of
            ``(bus_id, arrival_time)`` tuples waiting for a charger.
    """

    def __init__(self, scenario: Scenario) -> None:
        """Initialise charger state for every station in the scenario.

        Args:
            scenario: The scenario whose stations will be tracked.
        """
        self.scenario = scenario

        # Active charger allocations per station
        self.occupied_chargers: Dict[str, List[ChargerAllocation]] = {}

        # FIFO waiting queues per station — buses are appended on arrival
        # and popped from the front (index 0) when a charger is released
        self.waiting_queues: Dict[str, List[Tuple[str, datetime]]] = {}

        # Initialise empty structures for every station
        for station in scenario.route.stations:
            self.occupied_chargers[station.id] = []
            self.waiting_queues[station.id] = []

    def get_num_chargers(self, station_id: str) -> int:
        """Return the total number of chargers at a station.

        Args:
            station_id: The station to query.

        Returns:
            Number of chargers configured for the station, or ``0`` if
            the station ID is not found.
        """
        for station in self.scenario.route.stations:
            if station.id == station_id:
                return station.num_chargers
        return 0

    def get_available_chargers(self, station_id: str, current_time: datetime) -> int:
        """Return the number of free chargers at a station at a given time.

        Expired allocations (whose ``end_time`` ≤ ``current_time``) are
        cleaned up before counting so the result is always accurate.

        Args:
            station_id: The station to check.
            current_time: The simulation time to evaluate availability at.

        Returns:
            Number of chargers not currently occupied (≥ 0).
        """
        # Remove allocations that have already ended
        self._cleanup_expired_allocations(station_id, current_time)

        total_chargers = self.get_num_chargers(station_id)
        occupied = len(self.occupied_chargers[station_id])
        return total_chargers - occupied

    def is_charger_available(self, station_id: str, current_time: datetime) -> bool:
        """Check whether at least one charger is free at a station.

        Args:
            station_id: The station to check.
            current_time: The simulation time to evaluate availability at.

        Returns:
            ``True`` if at least one charger is available.
        """
        return self.get_available_chargers(station_id, current_time) > 0

    def allocate_charger(
        self,
        station_id: str,
        bus_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Allocate a charger to a bus for a charging session.

        Cleans up expired allocations first, then checks availability.
        If a charger is free, records the allocation and returns ``True``.

        Args:
            station_id: The station where charging will occur.
            bus_id: The bus that will use the charger.
            start_time: When charging begins.
            end_time: When charging ends (charger released at this time).

        Returns:
            ``True`` if the allocation succeeded, ``False`` if no charger
            was available.
        """
        # Ensure stale allocations are removed before checking capacity
        self._cleanup_expired_allocations(station_id, start_time)

        if not self.is_charger_available(station_id, start_time):
            return False

        allocation = ChargerAllocation(
            bus_id=bus_id,
            start_time=start_time,
            end_time=end_time,
        )
        self.occupied_chargers[station_id].append(allocation)
        return True

    def release_charger(
        self, station_id: str, bus_id: str, current_time: datetime
    ) -> None:
        """Release the charger held by a specific bus.

        Removes the allocation record for ``bus_id`` at ``station_id``.
        The charger is immediately available for the next bus.

        Args:
            station_id: The station where charging occurred.
            bus_id: The bus that was using the charger.
            current_time: The time when charging ends (unused here but
                kept for interface consistency).
        """
        # Filter out the allocation belonging to this bus
        self.occupied_chargers[station_id] = [
            alloc for alloc in self.occupied_chargers[station_id]
            if alloc.bus_id != bus_id
        ]

    def add_to_queue(
        self, station_id: str, bus_id: str, arrival_time: datetime
    ) -> None:
        """Enqueue a bus that arrived when all chargers were occupied.

        Buses are appended to the end of the list, implementing FIFO
        discipline — first to arrive is first to be served.

        Args:
            station_id: The station where the bus is waiting.
            bus_id: The bus that is waiting.
            arrival_time: When the bus arrived (used for wait-time
                calculation later).
        """
        # Append to the tail of the FIFO queue
        self.waiting_queues[station_id].append((bus_id, arrival_time))

    def get_next_in_queue(
        self, station_id: str
    ) -> Optional[Tuple[str, datetime]]:
        """Dequeue and return the next bus waiting at a station (FIFO).

        Args:
            station_id: The station whose queue to check.

        Returns:
            ``(bus_id, arrival_time)`` tuple for the next bus, or
            ``None`` if the queue is empty.
        """
        if self.waiting_queues[station_id]:
            # Pop from the front (index 0) to honour FIFO order
            return self.waiting_queues[station_id].pop(0)
        return None

    def get_queue_length(self, station_id: str) -> int:
        """Return the number of buses currently waiting at a station.

        Args:
            station_id: The station to query.

        Returns:
            Number of buses in the waiting queue.
        """
        return len(self.waiting_queues[station_id])

    def _cleanup_expired_allocations(
        self, station_id: str, current_time: datetime
    ) -> None:
        """Remove charger allocations whose end time has passed.

        A charger is considered free at the *exact* moment its
        ``end_time`` is reached (``end_time <= current_time``).  This
        ensures that when a ``CHARGING_ENDS`` event fires, the charger
        is immediately available for the next bus.

        Args:
            station_id: The station whose allocations to clean up.
            current_time: The current simulation time.
        """
        # Keep only allocations that end strictly after the current time
        self.occupied_chargers[station_id] = [
            alloc for alloc in self.occupied_chargers[station_id]
            if alloc.end_time > current_time
        ]

    def get_earliest_free_time(self, station_id: str) -> datetime:
        """Return the earliest time a charger slot will become free.

        Useful for calculating how long a bus must wait when all chargers
        are occupied.  Finds the Nth earliest end-time (where N equals
        the station's charger count) — that is the moment a slot opens.

        Args:
            station_id: The station to query.

        Returns:
            The earliest ``datetime`` at which a charger will be free.
            Returns ``datetime.min`` if no allocations are active or if
            fewer allocations exist than charger slots.
        """
        num_chargers = self.get_num_chargers(station_id)
        if not self.occupied_chargers[station_id]:
            return datetime.min

        # Sort all active end-times and pick the Nth one (0-indexed)
        end_times = sorted(
            alloc.end_time for alloc in self.occupied_chargers[station_id]
        )
        if len(end_times) < num_chargers:
            # Fewer allocations than charger slots — a slot is already free
            return datetime.min
        return end_times[num_chargers - 1]


# ============================================================================
# Event Simulator
# ============================================================================

class EventSimulator:
    """Discrete event simulator for bus charging scheduling.

    Processes events chronologically using a min-heap priority queue.
    Manages bus movements, charger allocation, and FIFO queue discipline
    at each station.

    The simulation lifecycle:

    1. :meth:`simulate` schedules the first arrival event for every bus.
    2. The main loop pops the earliest event and dispatches it.
    3. Each handler may push new events (e.g. a charge-end event after a
       charge-start, or an arrival event at the next station after a
       charge-end).
    4. When the queue is empty all buses have completed their journeys.

    Attributes:
        scenario: The scenario being simulated.
        base_date: Calendar date used to anchor ``HH:MM`` departure times.
        event_queue: Min-heap of :class:`Event` objects.
        charger_state: Tracks charger occupancy and waiting queues.
        bus_timelines: Completed :class:`BusTimeline` objects keyed by
            ``bus_id``.
        charging_stops: Temporary per-bus list of stops built during
            simulation.
        station_sessions: Per-station list of :class:`StationQueueEntry`
            objects for the station-queue view.
        bus_plan_index: Tracks which station in the plan each bus is
            currently heading to.
        bus_arrival_times: Maps ``(bus_id, station_id)`` to the arrival
            ``datetime`` for wait-time calculation.
        bus_plans: The charging plans being simulated.
    """

    def __init__(
        self,
        scenario: Scenario,
        base_date: Optional[datetime] = None,
    ) -> None:
        """Initialise the event simulator.

        Args:
            scenario: The scenario to simulate.
            base_date: Base calendar date for the simulation.  Defaults
                to today at midnight if not provided.
        """
        self.scenario = scenario
        self.base_date = base_date or datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Min-heap of Event objects; heapq uses the dataclass ordering
        self.event_queue: List[Event] = []

        # Manages charger occupancy and FIFO waiting queues
        self.charger_state = ChargerState(scenario)

        # Completed timelines, populated as buses finish their journeys
        self.bus_timelines: Dict[str, BusTimeline] = {}

        # Charging stops accumulated per bus during the simulation
        self.charging_stops: Dict[str, List[ChargingStop]] = {}

        # Chronological charging sessions per station (for the queue view)
        self.station_sessions: Dict[str, List[StationQueueEntry]] = {}

        # Index into each bus's station list — which stop comes next
        self.bus_plan_index: Dict[str, int] = {}

        # Arrival time at each (bus, station) pair for wait-time calculation
        self.bus_arrival_times: Dict[Tuple[str, str], datetime] = {}

        # Charging plans indexed by bus_id
        self.bus_plans: Dict[str, ChargingPlan] = {}

        # Pre-populate station session lists so every station appears in output
        for station in scenario.route.stations:
            self.station_sessions[station.id] = []

    def simulate(
        self, charging_plans: Dict[str, ChargingPlan]
    ) -> SimulationResult:
        """Run the complete simulation for all buses.

        Schedules the first arrival event for every bus that has a plan,
        then processes events in chronological order until the queue is
        empty.

        Args:
            charging_plans: Mapping of ``bus_id`` to :class:`ChargingPlan`.

        Returns:
            :class:`SimulationResult` containing per-bus timelines and
            per-station charging queues.
        """
        self.bus_plans = charging_plans

        # Seed the event queue with each bus's first station arrival
        for bus in self.scenario.buses:
            if bus.id in charging_plans:
                self._schedule_bus_journey(bus, charging_plans[bus.id])

        # Main simulation loop — process events in time order
        while self.event_queue:
            event = heapq.heappop(self.event_queue)
            self._handle_event(event)

        return self._build_result()

    def _schedule_bus_journey(self, bus: Bus, plan: ChargingPlan) -> None:
        """Schedule the first arrival event for a bus.

        Calculates the travel time from the bus's origin to its first
        charging station and pushes a ``BUS_ARRIVES_AT_STATION`` event.

        Args:
            bus: The bus to schedule.
            plan: The charging plan specifying which stations to visit.
        """
        # Initialise per-bus tracking structures
        self.bus_plan_index[bus.id] = 0
        self.charging_stops[bus.id] = []

        departure_time = bus.get_departure_datetime(self.base_date)

        if plan.stations:
            first_station_id = plan.stations[0]
            first_station = self._get_station_by_id(first_station_id)

            if first_station:
                # Station IDs are also location names in the route graph
                distance = self.scenario.route.get_distance(
                    bus.origin, first_station_id
                )
                travel_time = self._calculate_travel_time(distance)
                arrival_time = departure_time + travel_time

                event = Event(
                    time=arrival_time,
                    type=EventType.BUS_ARRIVES_AT_STATION,
                    bus_id=bus.id,
                    station_id=first_station_id,
                )
                heapq.heappush(self.event_queue, event)

    def _handle_event(self, event: Event) -> None:
        """Dispatch an event to its specific handler.

        Args:
            event: The event to process.
        """
        if event.type == EventType.BUS_ARRIVES_AT_STATION:
            self._handle_arrival(event)
        elif event.type == EventType.CHARGING_STARTS:
            self._handle_charge_start(event)
        elif event.type == EventType.CHARGING_ENDS:
            self._handle_charge_end(event)

    def _handle_arrival(self, event: Event) -> None:
        """Handle a bus arriving at a charging station.

        Records the arrival time, then either starts charging immediately
        (if a charger is free) or enqueues the bus to wait (FIFO).

        Args:
            event: The ``BUS_ARRIVES_AT_STATION`` event.
        """
        bus_id = event.bus_id
        station_id = event.station_id
        arrival_time = event.time

        # Store arrival time so we can compute wait duration later
        self.bus_arrival_times[(bus_id, station_id)] = arrival_time

        if self.charger_state.is_charger_available(station_id, arrival_time):
            # Charger is free — start charging without any wait
            self._start_charging(bus_id, station_id, arrival_time)
        else:
            # All chargers occupied — join the FIFO waiting queue
            self.charger_state.add_to_queue(station_id, bus_id, arrival_time)

    def _start_charging(
        self,
        bus_id: str,
        station_id: str,
        charge_start_time: datetime,
    ) -> None:
        """Begin a charging session for a bus.

        Allocates a charger, schedules the ``CHARGING_ENDS`` event, and
        records the :class:`ChargingStop` and :class:`StationQueueEntry`
        for output.

        Args:
            bus_id: The bus that will charge.
            station_id: The station where charging occurs.
            charge_start_time: The moment charging begins.

        Raises:
            RuntimeError: If charger allocation fails unexpectedly (this
                indicates a logic error in the simulator).
        """
        charge_duration = timedelta(
            minutes=self.scenario.parameters.charge_duration_minutes
        )
        charge_end_time = charge_start_time + charge_duration

        # Claim a charger slot for the duration of the session
        success = self.charger_state.allocate_charger(
            station_id, bus_id, charge_start_time, charge_end_time
        )
        if not success:
            # Should never happen if arrival/queue logic is correct
            raise RuntimeError(
                f"Failed to allocate charger for bus {bus_id} at station {station_id}"
            )

        # Schedule the event that will release the charger and continue the journey
        charge_end_event = Event(
            time=charge_end_time,
            type=EventType.CHARGING_ENDS,
            bus_id=bus_id,
            station_id=station_id,
        )
        heapq.heappush(self.event_queue, charge_end_event)

        # Compute wait time: difference between charge start and arrival
        station = self._get_station_by_id(station_id)
        arrival_time = self.bus_arrival_times.get(
            (bus_id, station_id), charge_start_time
        )
        wait_minutes = int(
            (charge_start_time - arrival_time).total_seconds() / 60
        )

        # Record the stop in the bus's timeline
        charging_stop = ChargingStop(
            station=station.name if station else station_id,
            arrival_time=arrival_time.strftime("%H:%M"),
            wait_minutes=wait_minutes,
            charge_start=charge_start_time.strftime("%H:%M"),
            charge_end=charge_end_time.strftime("%H:%M"),
        )
        self.charging_stops[bus_id].append(charging_stop)

        # Record the session in the station's chronological queue
        session = StationQueueEntry(
            bus_id=bus_id,
            arrival_time=arrival_time.strftime("%H:%M"),
            charge_start=charge_start_time.strftime("%H:%M"),
            charge_end=charge_end_time.strftime("%H:%M"),
        )
        self.station_sessions[station_id].append(session)

    def _handle_charge_start(self, event: Event) -> None:
        """Handle a ``CHARGING_STARTS`` event.

        This event type is reserved for future use.  In the current
        implementation charging begins directly inside
        :meth:`_start_charging` (called from :meth:`_handle_arrival` or
        :meth:`_handle_charge_end`), so this handler should never be
        invoked.

        Args:
            event: The charge-start event.

        Raises:
            RuntimeError: Always — this event type is not in active use.
        """
        raise RuntimeError("CHARGING_STARTS event should not be used")

    def _handle_charge_end(self, event: Event) -> None:
        """Handle a charging session ending.

        Releases the charger, immediately starts the next queued bus (if
        any), and continues the current bus's journey to its next station
        or destination.

        Args:
            event: The ``CHARGING_ENDS`` event.
        """
        bus_id = event.bus_id
        station_id = event.station_id
        charge_end_time = event.time

        # Free the charger so it is available for the next bus
        self.charger_state.release_charger(station_id, bus_id, charge_end_time)

        # Serve the next waiting bus immediately (FIFO discipline)
        next_bus = self.charger_state.get_next_in_queue(station_id)
        if next_bus:
            next_bus_id, _arrival_time = next_bus
            # The next bus starts charging at the exact moment this one finishes
            self._start_charging(next_bus_id, station_id, charge_end_time)

        # Continue this bus's journey to the next station or destination
        self._continue_bus_journey(bus_id, station_id, charge_end_time)

    def _continue_bus_journey(
        self,
        bus_id: str,
        current_station_id: str,
        current_time: datetime,
    ) -> None:
        """Advance a bus to its next destination after finishing charging.

        If the bus has more stations in its plan, schedules an arrival
        event at the next one.  Otherwise, calculates the final arrival
        time at the destination and records the completed
        :class:`BusTimeline`.

        Args:
            bus_id: The bus to advance.
            current_station_id: The station where the bus just finished
                charging.
            current_time: The time when charging ended.
        """
        bus = self.scenario.get_bus(bus_id)
        if not bus:
            return

        plan = self.bus_plans.get(bus_id)
        if not plan:
            return

        current_index = self.bus_plan_index.get(bus_id, 0)

        if current_index + 1 < len(plan.stations):
            # There is another charging station to visit
            next_station_id = plan.stations[current_index + 1]
            next_station = self._get_station_by_id(next_station_id)
            current_station = self._get_station_by_id(current_station_id)

            if next_station and current_station:
                # Station IDs are also location names in the route graph
                distance = self.scenario.route.get_distance(
                    current_station_id, next_station_id
                )
                travel_time = self._calculate_travel_time(distance)
                arrival_time = current_time + travel_time

                # Advance the plan pointer before pushing the event
                self.bus_plan_index[bus_id] = current_index + 1

                event = Event(
                    time=arrival_time,
                    type=EventType.BUS_ARRIVES_AT_STATION,
                    bus_id=bus_id,
                    station_id=next_station_id,
                )
                heapq.heappush(self.event_queue, event)
        else:
            # No more charging stations — travel directly to destination
            current_station = self._get_station_by_id(current_station_id)
            if not current_station:
                return

            distance_to_dest = self.scenario.route.get_distance(
                current_station_id, bus.destination
            )
            travel_time = self._calculate_travel_time(distance_to_dest)
            arrival_at_dest = current_time + travel_time

            # Aggregate total wait across all stops for this bus
            total_wait = sum(
                stop.wait_minutes for stop in self.charging_stops[bus_id]
            )

            timeline = BusTimeline(
                bus_id=bus.id,
                operator=bus.operator,
                direction=f"{bus.origin}→{bus.destination}",
                departure_time=bus.departure_time,
                charging_stops=self.charging_stops[bus_id],
                arrival_time=arrival_at_dest.strftime("%H:%M"),
                total_wait_minutes=total_wait,
            )
            self.bus_timelines[bus_id] = timeline

    def _calculate_travel_time(self, distance_km: float) -> timedelta:
        """Convert a distance to a travel-time duration.

        Uses the constant speed from the scenario parameters.

        Args:
            distance_km: Distance to travel in kilometres.

        Returns:
            Travel time as a :class:`timedelta`.
        """
        speed_kmh = self.scenario.parameters.speed_kmh
        # time = distance / speed (hours), converted to a timedelta
        hours = distance_km / speed_kmh
        return timedelta(hours=hours)

    def _get_station_by_id(self, station_id: str) -> Optional[Station]:
        """Look up a :class:`Station` object by its identifier.

        Args:
            station_id: The station identifier to search for.

        Returns:
            The matching :class:`Station`, or ``None`` if not found.
        """
        for station in self.scenario.route.stations:
            if station.id == station_id:
                return station
        return None

    def _build_result(self) -> SimulationResult:
        """Assemble the final :class:`SimulationResult` from accumulated state.

        Returns:
            A :class:`SimulationResult` containing all bus timelines and
            station charging queues.
        """
        return SimulationResult(
            bus_timelines=self.bus_timelines,
            station_queues=self.station_sessions,
        )
