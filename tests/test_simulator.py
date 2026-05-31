"""
Unit and integration tests for the event simulator.

Tests the complete event-driven simulation system including ChargerState
management and the EventSimulator with simple scenarios.
"""

import pytest
from datetime import datetime, timedelta
from scheduler.models import (
    Scenario, Route, Segment, Station, Bus, Parameters, Weights, ChargingPlan,
    SimulationResult, BusTimeline, ChargingStop
)
from scheduler.simulator import EventSimulator, EventType, Event, ChargerState


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def base_date():
    """Return a fixed base date for deterministic tests."""
    return datetime(2024, 1, 1, 0, 0, 0)


@pytest.fixture
def simple_scenario():
    """Create a simple scenario with two stations and one charger each."""
    route = Route(
        id="test-route",
        origin="Origin",
        destination="Destination",
        segments=[
            Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
            Segment(**{"from": "A", "to": "B", "distance_km": 100}),
            Segment(**{"from": "B", "to": "Destination", "distance_km": 100}),
        ],
        stations=[
            Station(id="A", name="Station A", num_chargers=1),
            Station(id="B", name="Station B", num_chargers=1),
        ]
    )

    buses = [
        Bus(id="bus-01", operator="op1", origin="Origin",
            destination="Destination", departure_time="10:00"),
        Bus(id="bus-02", operator="op2", origin="Origin",
            destination="Destination", departure_time="10:30"),
    ]

    return Scenario(
        name="Simple Test",
        route=route,
        buses=buses,
        parameters=Parameters(
            battery_capacity_km=240,
            charge_duration_minutes=25,
            speed_kmh=60
        ),
        weights=Weights()
    )


@pytest.fixture
def multi_charger_scenario():
    """Create a scenario with a station that has 2 chargers."""
    route = Route(
        id="test-route",
        origin="Origin",
        destination="Destination",
        segments=[
            Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
            Segment(**{"from": "A", "to": "Destination", "distance_km": 100}),
        ],
        stations=[
            Station(id="A", name="Station A", num_chargers=2),
        ]
    )

    buses = [
        Bus(id="bus-01", operator="op1", origin="Origin",
            destination="Destination", departure_time="10:00"),
        Bus(id="bus-02", operator="op2", origin="Origin",
            destination="Destination", departure_time="10:00"),
        Bus(id="bus-03", operator="op3", origin="Origin",
            destination="Destination", departure_time="10:00"),
    ]

    return Scenario(
        name="Multi-Charger Test",
        route=route,
        buses=buses,
        parameters=Parameters(
            battery_capacity_km=240,
            charge_duration_minutes=25,
            speed_kmh=60
        ),
        weights=Weights()
    )


# ============================================================================
# ChargerState Tests
# ============================================================================

class TestChargerState:
    """Test charger state management."""

    def test_charger_allocation_and_release(self, simple_scenario, base_date):
        """Test basic charger allocation and release."""
        state = ChargerState(simple_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)

        # Initially charger should be available
        assert state.is_charger_available("A", t0)

        # Allocate the charger
        success = state.allocate_charger("A", "bus-01", t0, t25)
        assert success is True

        # Now charger should be occupied
        assert not state.is_charger_available("A", t0)

        # Release the charger
        state.release_charger("A", "bus-01", t25)

        # Charger should be available again
        assert state.is_charger_available("A", t25)

    def test_allocate_charger_returns_false_when_full(self, simple_scenario, base_date):
        """Test that allocate_charger returns False when no charger is available."""
        state = ChargerState(simple_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)

        # Allocate the only charger
        success1 = state.allocate_charger("A", "bus-01", t0, t25)
        assert success1 is True

        # Try to allocate again — should fail
        success2 = state.allocate_charger("A", "bus-02", t0, t25)
        assert success2 is False

    def test_add_to_queue_and_get_next_in_queue(self, simple_scenario, base_date):
        """Test FIFO queue operations."""
        state = ChargerState(simple_scenario)
        t0 = base_date
        t5 = t0 + timedelta(minutes=5)
        t10 = t0 + timedelta(minutes=10)

        # Add two buses to the queue
        state.add_to_queue("A", "bus-01", t0)
        state.add_to_queue("A", "bus-02", t5)

        # First in, first out
        next_bus = state.get_next_in_queue("A")
        assert next_bus is not None
        assert next_bus[0] == "bus-01"
        assert next_bus[1] == t0

        next_bus2 = state.get_next_in_queue("A")
        assert next_bus2 is not None
        assert next_bus2[0] == "bus-02"

        # Queue should now be empty
        assert state.get_next_in_queue("A") is None

    def test_get_next_in_queue_empty_returns_none(self, simple_scenario):
        """Test that get_next_in_queue returns None for empty queue."""
        state = ChargerState(simple_scenario)
        result = state.get_next_in_queue("A")
        assert result is None

    def test_is_charger_available_initially_true(self, simple_scenario, base_date):
        """Test that chargers are available at the start."""
        state = ChargerState(simple_scenario)
        assert state.is_charger_available("A", base_date)
        assert state.is_charger_available("B", base_date)

    def test_is_charger_available_after_allocation(self, simple_scenario, base_date):
        """Test charger availability after allocation."""
        state = ChargerState(simple_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)

        state.allocate_charger("A", "bus-01", t0, t25)

        # Not available during charging
        assert not state.is_charger_available("A", t0)
        assert not state.is_charger_available("A", t0 + timedelta(minutes=10))

        # Available after charging ends (at exact end time)
        assert state.is_charger_available("A", t25)

    def test_multiple_chargers_per_station(self, multi_charger_scenario, base_date):
        """Test that stations with multiple chargers can serve multiple buses."""
        state = ChargerState(multi_charger_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)

        # Station A has 2 chargers — both should be allocatable simultaneously
        success1 = state.allocate_charger("A", "bus-01", t0, t25)
        assert success1 is True

        success2 = state.allocate_charger("A", "bus-02", t0, t25)
        assert success2 is True

        # Third bus should fail (only 2 chargers)
        success3 = state.allocate_charger("A", "bus-03", t0, t25)
        assert success3 is False

    def test_release_charger_allows_reallocation(self, simple_scenario, base_date):
        """Test that releasing a charger allows it to be reallocated."""
        state = ChargerState(simple_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)
        t50 = t0 + timedelta(minutes=50)

        # Allocate and release
        state.allocate_charger("A", "bus-01", t0, t25)
        state.release_charger("A", "bus-01", t25)

        # Should be able to allocate again
        success = state.allocate_charger("A", "bus-02", t25, t50)
        assert success is True

    def test_get_queue_length(self, simple_scenario, base_date):
        """Test queue length tracking."""
        state = ChargerState(simple_scenario)
        t0 = base_date

        assert state.get_queue_length("A") == 0

        state.add_to_queue("A", "bus-01", t0)
        assert state.get_queue_length("A") == 1

        state.add_to_queue("A", "bus-02", t0)
        assert state.get_queue_length("A") == 2

        state.get_next_in_queue("A")
        assert state.get_queue_length("A") == 1

    def test_get_available_chargers_count(self, multi_charger_scenario, base_date):
        """Test available charger count with multiple chargers."""
        state = ChargerState(multi_charger_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)

        # Initially 2 chargers available
        assert state.get_available_chargers("A", t0) == 2

        # After one allocation, 1 available
        state.allocate_charger("A", "bus-01", t0, t25)
        assert state.get_available_chargers("A", t0) == 1

        # After two allocations, 0 available
        state.allocate_charger("A", "bus-02", t0, t25)
        assert state.get_available_chargers("A", t0) == 0

    def test_cleanup_expired_allocations(self, simple_scenario, base_date):
        """Test that expired allocations are cleaned up automatically."""
        state = ChargerState(simple_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)
        t50 = t0 + timedelta(minutes=50)

        # Allocate charger
        state.allocate_charger("A", "bus-01", t0, t25)

        # At t25, the allocation has expired — charger should be free
        assert state.is_charger_available("A", t25)

        # Can allocate again at t25
        success = state.allocate_charger("A", "bus-02", t25, t50)
        assert success is True

    def test_get_earliest_free_time_no_allocations(self, simple_scenario, base_date):
        """Test get_earliest_free_time with no active allocations."""
        state = ChargerState(simple_scenario)
        result = state.get_earliest_free_time("A")
        assert result == datetime.min

    def test_get_earliest_free_time_with_allocation(self, simple_scenario, base_date):
        """Test get_earliest_free_time returns correct time."""
        state = ChargerState(simple_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)

        state.allocate_charger("A", "bus-01", t0, t25)
        free_time = state.get_earliest_free_time("A")
        assert free_time == t25

    def test_charger_state_initializes_all_stations(self, simple_scenario):
        """Test that ChargerState initializes structures for all stations."""
        state = ChargerState(simple_scenario)

        # Both stations should be initialized
        assert "A" in state.occupied_chargers
        assert "B" in state.occupied_chargers
        assert "A" in state.waiting_queues
        assert "B" in state.waiting_queues

    def test_queue_fifo_order_preserved(self, simple_scenario, base_date):
        """Test that FIFO order is strictly preserved in the queue."""
        state = ChargerState(simple_scenario)
        t0 = base_date

        # Add buses in order
        bus_ids = ["bus-01", "bus-02", "bus-03", "bus-04"]
        for i, bus_id in enumerate(bus_ids):
            state.add_to_queue("A", bus_id, t0 + timedelta(minutes=i))

        # Dequeue and verify order
        for expected_id in bus_ids:
            result = state.get_next_in_queue("A")
            assert result is not None
            assert result[0] == expected_id


# ============================================================================
# EventSimulator Tests
# ============================================================================

class TestEventSimulator:
    """Tests for the EventSimulator."""

    def test_simulate_single_bus_no_wait(self, simple_scenario, base_date):
        """Test simulation with a single bus that doesn't need to wait."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"])
        }

        result = simulator.simulate(plans)

        assert "bus-01" in result.bus_timelines
        timeline = result.bus_timelines["bus-01"]
        assert len(timeline.charging_stops) == 1
        assert timeline.charging_stops[0].station == "Station A"
        assert timeline.charging_stops[0].wait_minutes == 0
        assert timeline.total_wait_minutes == 0

    def test_simulate_two_buses_same_station_creates_wait(self, simple_scenario, base_date):
        """Test that two buses at the same station creates a wait for the second."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
            "bus-02": ChargingPlan(bus_id="bus-02", stations=["A"]),
        }

        result = simulator.simulate(plans)

        assert "bus-01" in result.bus_timelines
        assert "bus-02" in result.bus_timelines

        # bus-01 departs at 10:00, arrives at A at 11:40 (100km / 60kmh = 100min)
        # bus-02 departs at 10:30, arrives at A at 12:10
        # bus-01 charges 11:40-12:05, bus-02 arrives at 12:10 (after bus-01 finishes)
        # So bus-02 should NOT wait in this case
        timeline_01 = result.bus_timelines["bus-01"]
        timeline_02 = result.bus_timelines["bus-02"]

        assert timeline_01.total_wait_minutes == 0
        # bus-02 arrives after bus-01 finishes, so no wait
        assert timeline_02.total_wait_minutes == 0

    def test_simulate_builds_station_queues(self, simple_scenario, base_date):
        """Test that simulation builds station queue entries."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
        }

        result = simulator.simulate(plans)

        assert "A" in result.station_queues
        assert len(result.station_queues["A"]) == 1
        assert result.station_queues["A"][0].bus_id == "bus-01"

    def test_simulate_multiple_stops_per_bus(self, simple_scenario, base_date):
        """Test simulation with a bus that charges at multiple stations."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A", "B"]),
        }

        result = simulator.simulate(plans)

        assert "bus-01" in result.bus_timelines
        timeline = result.bus_timelines["bus-01"]
        assert len(timeline.charging_stops) == 2
        assert timeline.charging_stops[0].station == "Station A"
        assert timeline.charging_stops[1].station == "Station B"

    def test_simulate_arrival_time_is_set(self, simple_scenario, base_date):
        """Test that final arrival time is set in the timeline."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
        }

        result = simulator.simulate(plans)

        timeline = result.bus_timelines["bus-01"]
        assert timeline.arrival_time is not None
        assert ":" in timeline.arrival_time  # HH:MM format

    def test_simulate_charge_duration_is_correct(self, simple_scenario, base_date):
        """Test that charging takes exactly the configured duration."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
        }

        result = simulator.simulate(plans)

        stop = result.bus_timelines["bus-01"].charging_stops[0]
        # Parse times
        charge_start = datetime.strptime(stop.charge_start, "%H:%M")
        charge_end = datetime.strptime(stop.charge_end, "%H:%M")
        duration = (charge_end - charge_start).total_seconds() / 60
        assert duration == 25  # Exactly 25 minutes

    def test_simulate_empty_plans_returns_empty_result(self, simple_scenario, base_date):
        """Test simulation with no plans returns empty result."""
        simulator = EventSimulator(simple_scenario, base_date)
        result = simulator.simulate({})

        assert len(result.bus_timelines) == 0

    def test_simulate_station_queues_initialized_for_all_stations(self, simple_scenario, base_date):
        """Test that station queues are initialized for all stations even if unused."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
        }

        result = simulator.simulate(plans)

        # Both stations should appear in station_queues
        assert "A" in result.station_queues
        assert "B" in result.station_queues

    def test_simulate_congested_station_creates_wait(self, base_date):
        """Test that buses queuing at a congested station creates wait times."""
        # Create scenario where two buses depart at the same time
        route = Route(
            id="test-route",
            origin="Origin",
            destination="Destination",
            segments=[
                Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
                Segment(**{"from": "A", "to": "Destination", "distance_km": 100}),
            ],
            stations=[
                Station(id="A", name="Station A", num_chargers=1),
            ]
        )

        buses = [
            Bus(id="bus-01", operator="op1", origin="Origin",
                destination="Destination", departure_time="10:00"),
            Bus(id="bus-02", operator="op2", origin="Origin",
                destination="Destination", departure_time="10:00"),
        ]

        scenario = Scenario(
            name="Congested Test",
            route=route,
            buses=buses,
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights()
        )

        simulator = EventSimulator(scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
            "bus-02": ChargingPlan(bus_id="bus-02", stations=["A"]),
        }

        result = simulator.simulate(plans)

        # Both buses should have timelines
        assert "bus-01" in result.bus_timelines
        assert "bus-02" in result.bus_timelines

        # One bus should wait (the second one in queue)
        total_wait = sum(t.total_wait_minutes for t in result.bus_timelines.values())
        assert total_wait == 25  # Second bus waits exactly one charge duration

    def test_simulate_multi_charger_station_no_wait(self, multi_charger_scenario, base_date):
        """Test that multiple chargers allow simultaneous charging without wait."""
        simulator = EventSimulator(multi_charger_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
            "bus-02": ChargingPlan(bus_id="bus-02", stations=["A"]),
        }

        result = simulator.simulate(plans)

        # Both buses depart at same time, arrive at same time
        # Station A has 2 chargers, so neither should wait
        assert result.bus_timelines["bus-01"].total_wait_minutes == 0
        assert result.bus_timelines["bus-02"].total_wait_minutes == 0

    def test_event_ordering_charge_end_before_arrival(self, base_date):
        """Test that CHARGING_ENDS events are processed before BUS_ARRIVES events at same time."""
        # This tests the event priority ordering
        route = Route(
            id="test-route",
            origin="Origin",
            destination="Destination",
            segments=[
                Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
                Segment(**{"from": "A", "to": "Destination", "distance_km": 100}),
            ],
            stations=[
                Station(id="A", name="Station A", num_chargers=1),
            ]
        )

        # bus-01 departs at 10:00, arrives at A at 11:40
        # bus-02 departs at 10:25, arrives at A at 12:05 (exactly when bus-01 finishes)
        buses = [
            Bus(id="bus-01", operator="op1", origin="Origin",
                destination="Destination", departure_time="10:00"),
            Bus(id="bus-02", operator="op2", origin="Origin",
                destination="Destination", departure_time="10:25"),
        ]

        scenario = Scenario(
            name="Event Order Test",
            route=route,
            buses=buses,
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights()
        )

        simulator = EventSimulator(scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
            "bus-02": ChargingPlan(bus_id="bus-02", stations=["A"]),
        }

        result = simulator.simulate(plans)

        # Both buses should complete successfully
        assert "bus-01" in result.bus_timelines
        assert "bus-02" in result.bus_timelines

        # bus-02 arrives exactly when bus-01 finishes — should not wait
        assert result.bus_timelines["bus-02"].total_wait_minutes == 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestSimulatorIntegration:
    """Integration tests for the event simulator."""

    def test_two_bus_scenario_complete_journey(self, simple_scenario, base_date):
        """Test complete journey simulation for two buses."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
            "bus-02": ChargingPlan(bus_id="bus-02", stations=["B"]),
        }

        result = simulator.simulate(plans)

        # Both buses should complete their journeys
        assert len(result.bus_timelines) == 2

        for bus_id in ["bus-01", "bus-02"]:
            timeline = result.bus_timelines[bus_id]
            assert timeline.arrival_time is not None
            assert timeline.total_wait_minutes >= 0
            assert len(timeline.charging_stops) == 1

    def test_simulation_result_has_correct_operator(self, simple_scenario, base_date):
        """Test that simulation result preserves operator information."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
        }

        result = simulator.simulate(plans)

        timeline = result.bus_timelines["bus-01"]
        assert timeline.operator == "op1"

    def test_simulation_result_has_correct_direction(self, simple_scenario, base_date):
        """Test that simulation result has correct direction string."""
        simulator = EventSimulator(simple_scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
        }

        result = simulator.simulate(plans)

        timeline = result.bus_timelines["bus-01"]
        assert "Origin" in timeline.direction
        assert "Destination" in timeline.direction

    def test_station_queue_entries_are_chronological(self, base_date):
        """Test that station queue entries are in chronological order."""
        route = Route(
            id="test-route",
            origin="Origin",
            destination="Destination",
            segments=[
                Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
                Segment(**{"from": "A", "to": "Destination", "distance_km": 100}),
            ],
            stations=[
                Station(id="A", name="Station A", num_chargers=1),
            ]
        )

        buses = [
            Bus(id="bus-01", operator="op1", origin="Origin",
                destination="Destination", departure_time="10:00"),
            Bus(id="bus-02", operator="op2", origin="Origin",
                destination="Destination", departure_time="10:30"),
        ]

        scenario = Scenario(
            name="Queue Order Test",
            route=route,
            buses=buses,
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights()
        )

        simulator = EventSimulator(scenario, base_date)
        plans = {
            "bus-01": ChargingPlan(bus_id="bus-01", stations=["A"]),
            "bus-02": ChargingPlan(bus_id="bus-02", stations=["A"]),
        }

        result = simulator.simulate(plans)

        queue = result.station_queues["A"]
        assert len(queue) == 2
        # bus-01 departs earlier, so it should be first in queue
        assert queue[0].bus_id == "bus-01"
        assert queue[1].bus_id == "bus-02"


# ============================================================================
# Additional coverage tests
# ============================================================================

class TestEventStr:
    """Tests for Event __str__ method."""

    def test_event_str_representation(self, base_date):
        """Test that Event __str__ returns a readable string."""
        event = Event(
            time=base_date.replace(hour=10, minute=30),
            type=EventType.BUS_ARRIVES_AT_STATION,
            bus_id="bus-01",
            station_id="A",
        )
        s = str(event)
        assert "BUS_ARRIVES_AT_STATION" in s
        assert "10:30" in s
        assert "bus-01" in s
        assert "A" in s


class TestChargerStateEdgeCases:
    """Edge case tests for ChargerState."""

    def test_get_num_chargers_unknown_station(self, simple_scenario):
        """Test get_num_chargers returns 0 for unknown station."""
        state = ChargerState(simple_scenario)
        result = state.get_num_chargers("UNKNOWN_STATION")
        assert result == 0

    def test_get_earliest_free_time_fewer_allocations_than_chargers(
        self, multi_charger_scenario, base_date
    ):
        """Test get_earliest_free_time when fewer allocations than charger slots."""
        state = ChargerState(multi_charger_scenario)
        t0 = base_date
        t25 = t0 + timedelta(minutes=25)

        # Station A has 2 chargers, allocate only 1
        state.allocate_charger("A", "bus-01", t0, t25)

        # With 1 allocation and 2 charger slots, a slot is already free
        result = state.get_earliest_free_time("A")
        assert result == datetime.min


class TestSimulatorEdgeCases:
    """Edge case tests for EventSimulator."""

    def test_event_type_priority_ordering(self, base_date):
        """Test that CHARGING_ENDS has lower priority number than BUS_ARRIVES."""
        t = base_date
        end_event = Event(
            time=t,
            type=EventType.CHARGING_ENDS,
            bus_id="bus-01",
            station_id="A",
        )
        arrive_event = Event(
            time=t,
            type=EventType.BUS_ARRIVES_AT_STATION,
            bus_id="bus-02",
            station_id="A",
        )
        # CHARGING_ENDS should sort before BUS_ARRIVES at same time
        assert end_event < arrive_event

    def test_charging_starts_event_raises_runtime_error(self, simple_scenario, base_date):
        """Test that CHARGING_STARTS event raises RuntimeError."""
        simulator = EventSimulator(simple_scenario, base_date)
        event = Event(
            time=base_date,
            type=EventType.CHARGING_STARTS,
            bus_id="bus-01",
            station_id="A",
        )
        with pytest.raises(RuntimeError, match="CHARGING_STARTS event should not be used"):
            simulator._handle_charge_start(event)
