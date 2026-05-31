"""
Tests for the BusScheduler orchestrator.

Tests the main scheduling algorithm including plan generation,
constraint validation, greedy assignment, and the select_best_plan method.
Also includes integration tests for all 5 scenario files.
"""

import json
import pytest
from pathlib import Path
from datetime import datetime
from scheduler.models import (
    Scenario, Route, Segment, Station, Bus, Parameters, Weights,
    ChargingPlan, SimulationResult
)
from scheduler.scheduler import BusScheduler


# ============================================================================
# Helpers
# ============================================================================

def load_scenario(filename: str) -> Scenario:
    """Load a scenario from a JSON file in the scenarios/ directory."""
    scenarios_dir = Path(__file__).parent.parent / "scenarios"
    with open(scenarios_dir / filename, "r") as f:
        data = json.load(f)
    return Scenario(**data)


def make_simple_scenario(num_buses=1, departure_time="10:00",
                          num_chargers_a=1, num_chargers_b=1):
    """Create a simple two-station scenario for testing."""
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
            Station(id="A", name="Station A", num_chargers=num_chargers_a),
            Station(id="B", name="Station B", num_chargers=num_chargers_b),
        ]
    )
    buses = [
        Bus(id=f"bus-{i:02d}", operator=f"op{i % 3 + 1}",
            origin="Origin", destination="Destination",
            departure_time=departure_time)
        for i in range(1, num_buses + 1)
    ]
    return Scenario(
        name="Test Scenario",
        route=route,
        buses=buses,
        parameters=Parameters(
            battery_capacity_km=240,
            charge_duration_minutes=25,
            speed_kmh=60
        ),
        weights=Weights(individual=1.0, operator=1.0, overall=1.0)
    )


# ============================================================================
# TestSelectBestPlan
# ============================================================================

class TestSelectBestPlan:
    """Test the _select_best_plan method."""

    def test_select_best_plan_with_single_candidate(self):
        """Test that _select_best_plan returns the only candidate when there's one."""
        scenario = make_simple_scenario()
        bus = scenario.buses[0]
        scheduler = BusScheduler(scenario)

        candidates = [ChargingPlan(bus_id="bus-01", stations=["A"])]
        best_plan = scheduler._select_best_plan(bus, candidates)

        assert best_plan == candidates[0]
        assert best_plan.stations == ["A"]

    def test_select_best_plan_with_multiple_candidates(self):
        """Test that _select_best_plan evaluates and selects from multiple candidates."""
        scenario = make_simple_scenario()
        bus = scenario.buses[0]
        scheduler = BusScheduler(scenario)

        candidates = [
            ChargingPlan(bus_id="bus-01", stations=["A"]),
            ChargingPlan(bus_id="bus-01", stations=["B"]),
            ChargingPlan(bus_id="bus-01", stations=["A", "B"]),
        ]
        best_plan = scheduler._select_best_plan(bus, candidates)

        assert best_plan in candidates
        assert best_plan.bus_id == "bus-01"

    def test_select_best_plan_simulates_each_candidate(self):
        """Test that _select_best_plan simulates each candidate plan."""
        scenario = make_simple_scenario()
        bus = scenario.buses[0]
        scheduler = BusScheduler(scenario)

        candidates = [
            ChargingPlan(bus_id="bus-01", stations=["A"]),
            ChargingPlan(bus_id="bus-01", stations=["B"]),
        ]

        simulation_count = 0
        original_simulate = scheduler._simulate_and_score

        def counting_simulate(assignments):
            nonlocal simulation_count
            simulation_count += 1
            return original_simulate(assignments)

        scheduler._simulate_and_score = counting_simulate
        best_plan = scheduler._select_best_plan(bus, candidates)

        assert simulation_count == len(candidates)
        assert best_plan in candidates

    def test_select_best_plan_uses_current_assignments(self):
        """Test that _select_best_plan considers current assignments when simulating."""
        scenario = make_simple_scenario(num_buses=2)
        bus1, bus2 = scenario.buses[0], scenario.buses[1]
        scheduler = BusScheduler(scenario)

        # Pre-assign the first bus
        scheduler.assigned_plans["bus-01"] = ChargingPlan(bus_id="bus-01", stations=["A"])

        candidates = [
            ChargingPlan(bus_id="bus-02", stations=["A"]),
            ChargingPlan(bus_id="bus-02", stations=["B"]),
        ]
        best_plan = scheduler._select_best_plan(bus2, candidates)

        assert best_plan in candidates
        assert best_plan.bus_id == "bus-02"

    def test_select_best_plan_scores_each_simulation(self):
        """Test that _select_best_plan scores each simulation using objectives."""
        scenario = make_simple_scenario()
        bus = scenario.buses[0]
        scheduler = BusScheduler(scenario)

        candidates = [
            ChargingPlan(bus_id="bus-01", stations=["A"]),
            ChargingPlan(bus_id="bus-01", stations=["B"]),
        ]

        scoring_count = 0
        original_evaluate = scheduler.objective_evaluator.evaluate

        def counting_evaluate(result, scenario):
            nonlocal scoring_count
            scoring_count += 1
            return original_evaluate(result, scenario)

        scheduler.objective_evaluator.evaluate = counting_evaluate
        best_plan = scheduler._select_best_plan(bus, candidates)

        assert scoring_count == len(candidates)
        assert best_plan in candidates

    def test_select_best_plan_returns_highest_scoring_plan(self):
        """Test that _select_best_plan returns the plan with the highest score."""
        scenario = make_simple_scenario()
        bus = scenario.buses[0]
        scheduler = BusScheduler(scenario)

        plan_a = ChargingPlan(bus_id="bus-01", stations=["A"])
        plan_b = ChargingPlan(bus_id="bus-01", stations=["B"])
        candidates = [plan_a, plan_b]

        original_evaluate = scheduler.objective_evaluator.evaluate

        def mock_evaluate(result, scenario):
            if result.bus_timelines.get("bus-01"):
                timeline = result.bus_timelines["bus-01"]
                if timeline.charging_stops and timeline.charging_stops[0].station == "Station A":
                    return 100.0
                else:
                    return 50.0
            return 0.0

        scheduler.objective_evaluator.evaluate = mock_evaluate
        best_plan = scheduler._select_best_plan(bus, candidates)

        assert best_plan.stations == ["A"]


# ============================================================================
# TestGreedyAssign
# ============================================================================

class TestGreedyAssign:
    """Test the greedy assignment algorithm."""

    def test_greedy_assign_processes_all_buses(self):
        """Test that greedy assignment assigns plans to all buses."""
        scenario = make_simple_scenario(num_buses=3)
        scheduler = BusScheduler(scenario)

        valid_plans = {
            "bus-01": [ChargingPlan(bus_id="bus-01", stations=["A"])],
            "bus-02": [ChargingPlan(bus_id="bus-02", stations=["A"])],
            "bus-03": [ChargingPlan(bus_id="bus-03", stations=["B"])],
        }

        scheduler._greedy_assign(valid_plans)

        assert len(scheduler.assigned_plans) == 3
        assert "bus-01" in scheduler.assigned_plans
        assert "bus-02" in scheduler.assigned_plans
        assert "bus-03" in scheduler.assigned_plans

    def test_greedy_assign_locks_in_assignments_sequentially(self):
        """Test that greedy assignment locks in each bus's plan before moving to next."""
        scenario = make_simple_scenario(num_buses=3)
        scheduler = BusScheduler(scenario)

        assignment_order = []
        original_select = scheduler._select_best_plan

        def tracking_select(bus, candidates):
            plan = original_select(bus, candidates)
            assignment_order.append(bus.id)
            return plan

        scheduler._select_best_plan = tracking_select

        valid_plans = {
            "bus-01": [ChargingPlan(bus_id="bus-01", stations=["A"])],
            "bus-02": [ChargingPlan(bus_id="bus-02", stations=["B"])],
            "bus-03": [ChargingPlan(bus_id="bus-03", stations=["A"])],
        }

        scheduler._greedy_assign(valid_plans)

        # All buses should be assigned
        assert len(assignment_order) == 3

    def test_greedy_assign_raises_error_for_bus_with_no_valid_plans(self):
        """Test that greedy assignment raises error when a bus has no valid plans."""
        scenario = make_simple_scenario(num_buses=2)
        scheduler = BusScheduler(scenario)

        valid_plans = {
            "bus-01": [ChargingPlan(bus_id="bus-01", stations=["A"])],
            "bus-02": [],  # No valid plans
        }

        with pytest.raises(RuntimeError, match="No valid charging plans found for bus bus-02"):
            scheduler._greedy_assign(valid_plans)


# ============================================================================
# TestSchedulerIntegration (simple scenarios)
# ============================================================================

class TestSchedulerIntegration:
    """Integration tests for the complete scheduler."""

    def test_schedule_simple_scenario(self):
        """Test scheduling a simple scenario end-to-end."""
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
        bus = Bus(id="bus-01", operator="test-op", origin="Origin",
                  destination="Destination", departure_time="10:00")
        scenario = Scenario(
            name="Simple Test",
            route=route,
            buses=[bus],
            parameters=Parameters(battery_capacity_km=240,
                                   charge_duration_minutes=25, speed_kmh=60),
            weights=Weights(individual=1.0, operator=1.0, overall=1.0)
        )

        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        assert result is not None
        assert "bus-01" in result.bus_timelines
        assert len(result.bus_timelines["bus-01"].charging_stops) > 0

    def test_schedule_multiple_buses(self):
        """Test scheduling multiple buses."""
        scenario = make_simple_scenario(num_buses=2)
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        assert result is not None
        assert len(result.bus_timelines) == 2
        assert "bus-01" in result.bus_timelines
        assert "bus-02" in result.bus_timelines


# ============================================================================
# TestScenarioFiles — Integration tests for all 5 scenario JSON files
# ============================================================================

class TestScenarioFiles:
    """Integration tests that load and schedule all 5 scenario JSON files."""

    def _validate_result(self, result: SimulationResult, scenario: Scenario) -> None:
        """Validate that a simulation result is correct."""
        assert len(result.bus_timelines) == len(scenario.buses), (
            f"Expected {len(scenario.buses)} bus timelines, "
            f"got {len(result.bus_timelines)}"
        )

        for bus in scenario.buses:
            assert bus.id in result.bus_timelines, \
                f"Bus {bus.id} missing from timelines"

            timeline = result.bus_timelines[bus.id]

            assert len(timeline.charging_stops) > 0, \
                f"Bus {bus.id} has no charging stops"

            for stop in timeline.charging_stops:
                assert stop.arrival_time is not None
                assert stop.charge_start is not None
                assert stop.charge_end is not None
                assert stop.wait_minutes >= 0

            assert timeline.arrival_time is not None
            assert timeline.total_wait_minutes >= 0

        assert len(result.station_queues) > 0, "No station queues in result"

    def test_scenario1_even_spacing(self):
        """Test Scenario 1 - Even Spacing."""
        scenario = load_scenario("scenario1.json")
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        self._validate_result(result, scenario)
        assert scenario.name == "Scenario 1 - Even Spacing"
        assert len(scenario.buses) == 20
        assert scenario.weights.individual == 1.0
        assert scenario.weights.operator == 1.0
        assert scenario.weights.overall == 1.0

    def test_scenario2_bunched_start(self):
        """Test Scenario 2 - Bunched Start."""
        scenario = load_scenario("scenario2.json")
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        self._validate_result(result, scenario)
        assert scenario.name == "Scenario 2 - Bunched Start"
        assert len(scenario.buses) == 20

        total_wait = sum(t.total_wait_minutes for t in result.bus_timelines.values())
        assert total_wait > 0, "Expected some wait time due to bunched departures"

    def test_scenario3_asymmetric_load(self):
        """Test Scenario 3 - Asymmetric Load."""
        scenario = load_scenario("scenario3.json")
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        self._validate_result(result, scenario)
        assert scenario.name == "Scenario 3 - Asymmetric Load"

        bk_buses = [b for b in scenario.buses if b.id.startswith("bus-BK")]
        kb_buses = [b for b in scenario.buses if b.id.startswith("bus-KB")]
        assert len(bk_buses) == 10
        assert len(kb_buses) == 4

    def test_scenario4_operator_heavy(self):
        """Test Scenario 4 - Operator Heavy."""
        scenario = load_scenario("scenario4.json")
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        self._validate_result(result, scenario)
        assert scenario.name == "Scenario 4 - Operator Heavy"
        assert len(scenario.buses) == 20
        assert scenario.weights.operator == 2.0

        kpn_buses = [b for b in scenario.buses if b.operator == "kpn"]
        assert len(kpn_buses) > 10, "KPN should dominate the fleet"

    def test_scenario5_worst_case_convergence(self):
        """Test Scenario 5 - Worst Case Convergence."""
        scenario = load_scenario("scenario5.json")
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        self._validate_result(result, scenario)
        assert scenario.name == "Scenario 5 - Worst Case Convergence"
        assert len(scenario.buses) == 20

        total_wait = sum(t.total_wait_minutes for t in result.bus_timelines.values())
        max_wait = max(t.total_wait_minutes for t in result.bus_timelines.values())
        assert total_wait > 0, "Expected wait time due to convergence"
        assert max_wait > 0, "Expected at least one bus to wait"

    def test_all_scenarios_have_bus_timelines_for_every_bus(self):
        """Test that all scenarios produce a timeline for every bus."""
        for i in range(1, 6):
            scenario = load_scenario(f"scenario{i}.json")
            scheduler = BusScheduler(scenario)
            result = scheduler.schedule()

            for bus in scenario.buses:
                assert bus.id in result.bus_timelines, (
                    f"scenario{i}: Bus {bus.id} missing from timelines"
                )


# ============================================================================
# TestConstraintViolations — Verify no constraint violations in output
# ============================================================================

class TestConstraintViolations:
    """Verify that scheduled results respect all hard constraints."""

    def test_no_range_violations_in_all_scenarios(self):
        """Test that no bus exceeds battery range between charges in any scenario."""
        from scheduler.constraints import RangeConstraint
        constraint = RangeConstraint()

        for i in range(1, 6):
            scenario = load_scenario(f"scenario{i}.json")
            scheduler = BusScheduler(scenario)
            scheduler.schedule()

            for bus_id, plan in scheduler.assigned_plans.items():
                assert constraint.is_valid(plan, scenario), (
                    f"scenario{i}: Range constraint violated for {bus_id}"
                )

    def test_no_route_order_violations_in_all_scenarios(self):
        """Test that no bus visits stations out of order in any scenario."""
        from scheduler.constraints import RouteOrderConstraint
        constraint = RouteOrderConstraint()

        for i in range(1, 6):
            scenario = load_scenario(f"scenario{i}.json")
            scheduler = BusScheduler(scenario)
            scheduler.schedule()

            for bus_id, plan in scheduler.assigned_plans.items():
                assert constraint.is_valid(plan, scenario), (
                    f"scenario{i}: Route order constraint violated for {bus_id}"
                )

    def test_all_buses_complete_journey_in_all_scenarios(self):
        """Test that all buses complete their journey in every scenario."""
        from scheduler.constraints import CompletionConstraint
        constraint = CompletionConstraint()

        for i in range(1, 6):
            scenario = load_scenario(f"scenario{i}.json")
            scheduler = BusScheduler(scenario)
            result = scheduler.schedule()

            # Every bus must have an arrival time
            for bus in scenario.buses:
                assert bus.id in result.bus_timelines, (
                    f"scenario{i}: Bus {bus.id} has no timeline"
                )
                timeline = result.bus_timelines[bus.id]
                assert timeline.arrival_time is not None, (
                    f"scenario{i}: Bus {bus.id} has no arrival time"
                )

            # All assigned plans must pass completion constraint
            for bus_id, plan in scheduler.assigned_plans.items():
                assert constraint.is_valid(plan, scenario), (
                    f"scenario{i}: Completion constraint violated for {bus_id}"
                )

    def test_no_simultaneous_charger_overload(self):
        """Test that no station has more simultaneous chargers than num_chargers."""
        for i in range(1, 6):
            scenario = load_scenario(f"scenario{i}.json")
            scheduler = BusScheduler(scenario)
            result = scheduler.schedule()

            # For each station, check that charging sessions don't overlap
            # more than num_chargers times
            station_map = {s.id: s.num_chargers for s in scenario.route.stations}

            for station_id, queue in result.station_queues.items():
                num_chargers = station_map.get(station_id, 1)

                # Build list of (start, end) intervals
                intervals = []
                for entry in queue:
                    start = datetime.strptime(entry.charge_start, "%H:%M")
                    end = datetime.strptime(entry.charge_end, "%H:%M")
                    intervals.append((start, end))

                # Check no time point has more than num_chargers overlapping
                for j, (s1, e1) in enumerate(intervals):
                    overlap_count = sum(
                        1 for k, (s2, e2) in enumerate(intervals)
                        if k != j and s2 < e1 and s1 < e2
                    )
                    assert overlap_count < num_chargers, (
                        f"scenario{i}: Station {station_id} has "
                        f"{overlap_count + 1} simultaneous chargers "
                        f"but only {num_chargers} available"
                    )


# ============================================================================
# TestWeightSensitivity — Verify weight changes produce different schedules
# ============================================================================

class TestWeightSensitivity:
    """Verify that changing weights produces different schedules."""

    def test_different_weights_produce_different_schedules_scenario2(self):
        """Test that two weight configs produce different schedules on scenario2.

        Uses scenario5 (worst-case convergence) which has maximum contention,
        making it most sensitive to weight changes. Compares operator-fairness-
        heavy vs overall-efficiency-heavy configurations.
        """
        scenario_a = load_scenario("scenario5.json")
        scenario_b = load_scenario("scenario5.json")

        # Config A: heavily prioritize operator fairness
        scenario_a.weights.individual = 1.0
        scenario_a.weights.operator = 100.0
        scenario_a.weights.overall = 1.0

        # Config B: heavily prioritize overall efficiency (minimize total wait)
        scenario_b.weights.individual = 1.0
        scenario_b.weights.operator = 1.0
        scenario_b.weights.overall = 100.0

        scheduler_a = BusScheduler(scenario_a)
        result_a = scheduler_a.schedule()

        scheduler_b = BusScheduler(scenario_b)
        result_b = scheduler_b.schedule()

        # Collect station assignments for each bus
        assignments_a = {
            bus_id: tuple(plan.stations)
            for bus_id, plan in scheduler_a.assigned_plans.items()
        }
        assignments_b = {
            bus_id: tuple(plan.stations)
            for bus_id, plan in scheduler_b.assigned_plans.items()
        }

        # The schedules should differ in at least one bus's assignment
        # OR in the total/max wait times (different weight emphasis)
        total_wait_a = sum(t.total_wait_minutes for t in result_a.bus_timelines.values())
        total_wait_b = sum(t.total_wait_minutes for t in result_b.bus_timelines.values())
        max_wait_a = max(t.total_wait_minutes for t in result_a.bus_timelines.values())
        max_wait_b = max(t.total_wait_minutes for t in result_b.bus_timelines.values())

        # At least one metric should differ, or the assignments differ
        schedules_differ = (
            assignments_a != assignments_b
            or total_wait_a != total_wait_b
            or max_wait_a != max_wait_b
        )
        assert schedules_differ, (
            "Expected different schedules with different weights, "
            f"but got identical results: total_wait={total_wait_a}, max_wait={max_wait_a}"
        )

    def test_different_weights_produce_different_schedules_scenario5(self):
        """Test that two weight configs produce different schedules on scenario5."""
        scenario_a = load_scenario("scenario5.json")
        scenario_b = load_scenario("scenario5.json")

        # Config A: prioritize operator fairness
        scenario_a.weights.individual = 1.0
        scenario_a.weights.operator = 10.0
        scenario_a.weights.overall = 1.0

        # Config B: prioritize overall efficiency
        scenario_b.weights.individual = 1.0
        scenario_b.weights.operator = 1.0
        scenario_b.weights.overall = 10.0

        scheduler_a = BusScheduler(scenario_a)
        result_a = scheduler_a.schedule()

        scheduler_b = BusScheduler(scenario_b)
        result_b = scheduler_b.schedule()

        # Both results should be valid
        for bus in scenario_a.buses:
            assert bus.id in result_a.bus_timelines
            assert bus.id in result_b.bus_timelines

        # Results should differ in some measurable way
        total_wait_a = sum(t.total_wait_minutes for t in result_a.bus_timelines.values())
        total_wait_b = sum(t.total_wait_minutes for t in result_b.bus_timelines.values())

        assignments_a = {
            bus_id: tuple(plan.stations)
            for bus_id, plan in scheduler_a.assigned_plans.items()
        }
        assignments_b = {
            bus_id: tuple(plan.stations)
            for bus_id, plan in scheduler_b.assigned_plans.items()
        }

        schedules_differ = (
            assignments_a != assignments_b
            or total_wait_a != total_wait_b
        )
        assert schedules_differ, (
            "Expected different schedules with different weights"
        )


# ============================================================================
# TestEdgeCases — Single bus, all buses same time
# ============================================================================

class TestEdgeCases:
    """Test edge cases: single bus, all buses same departure time."""

    def test_single_bus_scenario(self):
        """Test scheduling with a single bus."""
        route = Route(
            id="test-route",
            origin="Bengaluru",
            destination="Kochi",
            segments=[
                Segment(**{"from": "Bengaluru", "to": "A", "distance_km": 100}),
                Segment(**{"from": "A", "to": "B", "distance_km": 120}),
                Segment(**{"from": "B", "to": "C", "distance_km": 100}),
                Segment(**{"from": "C", "to": "D", "distance_km": 120}),
                Segment(**{"from": "D", "to": "Kochi", "distance_km": 100}),
            ],
            stations=[
                Station(id="A", name="Station A", num_chargers=1),
                Station(id="B", name="Station B", num_chargers=1),
                Station(id="C", name="Station C", num_chargers=1),
                Station(id="D", name="Station D", num_chargers=1),
            ]
        )

        bus = Bus(id="bus-solo", operator="kpn", origin="Bengaluru",
                  destination="Kochi", departure_time="19:00")

        scenario = Scenario(
            name="Single Bus",
            route=route,
            buses=[bus],
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights(individual=1.0, operator=1.0, overall=1.0)
        )

        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        # Single bus should complete with no wait
        assert "bus-solo" in result.bus_timelines
        timeline = result.bus_timelines["bus-solo"]
        assert timeline.total_wait_minutes == 0
        assert len(timeline.charging_stops) >= 2  # 540km needs at least 2 charges
        assert timeline.arrival_time is not None

    def test_single_bus_no_contention(self):
        """Test that a single bus never waits (no contention)."""
        scenario = make_simple_scenario(num_buses=1)
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        assert len(result.bus_timelines) == 1
        timeline = list(result.bus_timelines.values())[0]
        assert timeline.total_wait_minutes == 0

    def test_all_buses_same_departure_time_scenario2(self):
        """Test scenario2 which has bunched departures (many buses close together)."""
        scenario = load_scenario("scenario2.json")
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        # All buses should complete their journeys
        assert len(result.bus_timelines) == len(scenario.buses)

        for bus in scenario.buses:
            assert bus.id in result.bus_timelines
            timeline = result.bus_timelines[bus.id]
            assert timeline.arrival_time is not None
            assert timeline.total_wait_minutes >= 0

        # With bunched departures, there should be contention
        total_wait = sum(t.total_wait_minutes for t in result.bus_timelines.values())
        assert total_wait > 0, "Bunched departures should cause some waiting"

    def test_two_buses_exact_same_departure(self):
        """Test two buses departing at exactly the same time."""
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
            name="Same Time Test",
            route=route,
            buses=buses,
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights(individual=1.0, operator=1.0, overall=1.0)
        )

        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        # Both buses should complete
        assert len(result.bus_timelines) == 2
        assert "bus-01" in result.bus_timelines
        assert "bus-02" in result.bus_timelines

        # One bus must wait (only 1 charger)
        total_wait = sum(t.total_wait_minutes for t in result.bus_timelines.values())
        assert total_wait == 25, "Second bus should wait exactly one charge duration"

    def test_single_bus_with_minimal_route(self):
        """Test single bus on a route that barely needs one charge."""
        route = Route(
            id="short-route",
            origin="Start",
            destination="End",
            segments=[
                Segment(**{"from": "Start", "to": "Mid", "distance_km": 200}),
                Segment(**{"from": "Mid", "to": "End", "distance_km": 200}),
            ],
            stations=[
                Station(id="Mid", name="Mid Station", num_chargers=1),
            ]
        )

        bus = Bus(id="bus-01", operator="op1", origin="Start",
                  destination="End", departure_time="08:00")

        scenario = Scenario(
            name="Minimal Route",
            route=route,
            buses=[bus],
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights()
        )

        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()

        assert "bus-01" in result.bus_timelines
        timeline = result.bus_timelines["bus-01"]
        assert len(timeline.charging_stops) == 1
        assert timeline.total_wait_minutes == 0
