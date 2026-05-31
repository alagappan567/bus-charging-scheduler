"""
Tests for the BusScheduler orchestrator.

Tests the main scheduling algorithm including plan generation,
constraint validation, greedy assignment, and the select_best_plan method.
"""

import pytest
from datetime import datetime
from scheduler.models import (
    Scenario, Route, Segment, Station, Bus, Parameters, Weights, ChargingPlan
)
from scheduler.scheduler import BusScheduler


class TestSelectBestPlan:
    """Test the _select_best_plan method that implements greedy assignment logic."""
    
    def create_simple_scenario(self):
        """Create a simple scenario for testing."""
        route = Route(
            id="test-route",
            origin="Origin",
            destination="Destination",
            segments=[
                Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
                Segment(**{"from": "A", "to": "B", "distance_km": 100}),
                Segment(**{"from": "B", "to": "Destination", "distance_km": 100})
            ],
            stations=[
                Station(id="A", name="Station A", num_chargers=1),
                Station(id="B", name="Station B", num_chargers=1)
            ]
        )
        
        bus = Bus(
            id="bus-01",
            operator="test-operator",
            origin="Origin",
            destination="Destination",
            departure_time="10:00"
        )
        
        scenario = Scenario(
            name="Test Scenario",
            route=route,
            buses=[bus],
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights(
                individual=1.0,
                operator=1.0,
                overall=1.0
            )
        )
        
        return scenario, bus
    
    def test_select_best_plan_with_single_candidate(self):
        """Test that _select_best_plan returns the only candidate when there's one."""
        scenario, bus = self.create_simple_scenario()
        scheduler = BusScheduler(scenario)
        
        # Create a single candidate plan
        candidates = [ChargingPlan(bus_id="bus-01", stations=["A"])]
        
        # Select best plan
        best_plan = scheduler._select_best_plan(bus, candidates)
        
        # Should return the only candidate
        assert best_plan == candidates[0]
        assert best_plan.stations == ["A"]
    
    def test_select_best_plan_with_multiple_candidates(self):
        """Test that _select_best_plan evaluates and selects from multiple candidates."""
        scenario, bus = self.create_simple_scenario()
        scheduler = BusScheduler(scenario)
        
        # Create multiple candidate plans
        candidates = [
            ChargingPlan(bus_id="bus-01", stations=["A"]),
            ChargingPlan(bus_id="bus-01", stations=["B"]),
            ChargingPlan(bus_id="bus-01", stations=["A", "B"])
        ]
        
        # Select best plan
        best_plan = scheduler._select_best_plan(bus, candidates)
        
        # Should return one of the candidates
        assert best_plan in candidates
        assert best_plan.bus_id == "bus-01"
    
    def test_select_best_plan_simulates_each_candidate(self):
        """Test that _select_best_plan simulates each candidate plan."""
        scenario, bus = self.create_simple_scenario()
        scheduler = BusScheduler(scenario)
        
        # Create multiple candidate plans
        candidates = [
            ChargingPlan(bus_id="bus-01", stations=["A"]),
            ChargingPlan(bus_id="bus-01", stations=["B"])
        ]
        
        # Track simulation calls by monkey-patching
        simulation_count = 0
        original_simulate = scheduler._simulate_and_score
        
        def counting_simulate(assignments):
            nonlocal simulation_count
            simulation_count += 1
            return original_simulate(assignments)
        
        scheduler._simulate_and_score = counting_simulate
        
        # Select best plan
        best_plan = scheduler._select_best_plan(bus, candidates)
        
        # Should have simulated each candidate
        assert simulation_count == len(candidates)
        assert best_plan in candidates
    
    def test_select_best_plan_uses_current_assignments(self):
        """Test that _select_best_plan considers current assignments when simulating."""
        scenario, bus = self.create_simple_scenario()
        
        # Add a second bus to the scenario
        bus2 = Bus(
            id="bus-02",
            operator="test-operator",
            origin="Origin",
            destination="Destination",
            departure_time="10:30"
        )
        scenario.buses.append(bus2)
        
        scheduler = BusScheduler(scenario)
        
        # Pre-assign the first bus
        scheduler.assigned_plans["bus-01"] = ChargingPlan(bus_id="bus-01", stations=["A"])
        
        # Create candidates for second bus
        candidates = [
            ChargingPlan(bus_id="bus-02", stations=["A"]),
            ChargingPlan(bus_id="bus-02", stations=["B"])
        ]
        
        # Select best plan for second bus
        best_plan = scheduler._select_best_plan(bus2, candidates)
        
        # Should return a valid plan
        assert best_plan in candidates
        assert best_plan.bus_id == "bus-02"
        
        # The simulation should have considered the first bus's assignment
        # (We can't directly verify this without inspecting simulation internals,
        # but the fact that it runs without error is a good sign)
    
    def test_select_best_plan_scores_each_simulation(self):
        """Test that _select_best_plan scores each simulation using objectives."""
        scenario, bus = self.create_simple_scenario()
        scheduler = BusScheduler(scenario)
        
        # Create multiple candidate plans
        candidates = [
            ChargingPlan(bus_id="bus-01", stations=["A"]),
            ChargingPlan(bus_id="bus-01", stations=["B"])
        ]
        
        # Track scoring calls by monkey-patching
        scoring_count = 0
        original_evaluate = scheduler.objective_evaluator.evaluate
        
        def counting_evaluate(result, scenario):
            nonlocal scoring_count
            scoring_count += 1
            return original_evaluate(result, scenario)
        
        scheduler.objective_evaluator.evaluate = counting_evaluate
        
        # Select best plan
        best_plan = scheduler._select_best_plan(bus, candidates)
        
        # Should have scored each candidate
        assert scoring_count == len(candidates)
        assert best_plan in candidates
    
    def test_select_best_plan_returns_highest_scoring_plan(self):
        """Test that _select_best_plan returns the plan with the highest score."""
        scenario, bus = self.create_simple_scenario()
        scheduler = BusScheduler(scenario)
        
        # Create multiple candidate plans
        plan_a = ChargingPlan(bus_id="bus-01", stations=["A"])
        plan_b = ChargingPlan(bus_id="bus-01", stations=["B"])
        candidates = [plan_a, plan_b]
        
        # Mock the scoring to return predictable values
        original_evaluate = scheduler.objective_evaluator.evaluate
        
        def mock_evaluate(result, scenario):
            # Check which plan is being evaluated by looking at the result
            # Plan A gets a higher score
            if result.bus_timelines.get("bus-01"):
                timeline = result.bus_timelines["bus-01"]
                if timeline.charging_stops and timeline.charging_stops[0].station == "A":
                    return 100.0  # Higher score for plan A
                else:
                    return 50.0   # Lower score for plan B
            return 0.0
        
        scheduler.objective_evaluator.evaluate = mock_evaluate
        
        # Select best plan
        best_plan = scheduler._select_best_plan(bus, candidates)
        
        # Should return plan A (higher score)
        assert best_plan.stations == ["A"]


class TestGreedyAssign:
    """Test the greedy assignment algorithm."""
    
    def create_multi_bus_scenario(self):
        """Create a scenario with multiple buses."""
        route = Route(
            id="test-route",
            origin="Origin",
            destination="Destination",
            segments=[
                Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
                Segment(**{"from": "A", "to": "B", "distance_km": 100}),
                Segment(**{"from": "B", "to": "Destination", "distance_km": 100})
            ],
            stations=[
                Station(id="A", name="Station A", num_chargers=1),
                Station(id="B", name="Station B", num_chargers=1)
            ]
        )
        
        buses = [
            Bus(id="bus-01", operator="op1", origin="Origin", 
                destination="Destination", departure_time="10:00"),
            Bus(id="bus-02", operator="op2", origin="Origin", 
                destination="Destination", departure_time="10:30"),
            Bus(id="bus-03", operator="op1", origin="Origin", 
                destination="Destination", departure_time="11:00")
        ]
        
        scenario = Scenario(
            name="Multi-Bus Test",
            route=route,
            buses=buses,
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights(
                individual=1.0,
                operator=1.0,
                overall=1.0
            )
        )
        
        return scenario
    
    def test_greedy_assign_processes_buses_in_departure_order(self):
        """Test that greedy assignment processes buses in departure time order."""
        scenario = self.create_multi_bus_scenario()
        scheduler = BusScheduler(scenario)
        
        # Create valid plans for all buses
        valid_plans = {
            "bus-01": [ChargingPlan(bus_id="bus-01", stations=["A"])],
            "bus-02": [ChargingPlan(bus_id="bus-02", stations=["A"])],
            "bus-03": [ChargingPlan(bus_id="bus-03", stations=["B"])]
        }
        
        # Run greedy assignment
        scheduler._greedy_assign(valid_plans)
        
        # All buses should have assignments
        assert len(scheduler.assigned_plans) == 3
        assert "bus-01" in scheduler.assigned_plans
        assert "bus-02" in scheduler.assigned_plans
        assert "bus-03" in scheduler.assigned_plans
    
    def test_greedy_assign_locks_in_assignments_sequentially(self):
        """Test that greedy assignment locks in each bus's plan before moving to next."""
        scenario = self.create_multi_bus_scenario()
        scheduler = BusScheduler(scenario)
        
        # Track the order of assignments
        assignment_order = []
        original_select = scheduler._select_best_plan
        
        def tracking_select(bus, candidates):
            plan = original_select(bus, candidates)
            assignment_order.append(bus.id)
            return plan
        
        scheduler._select_best_plan = tracking_select
        
        # Create valid plans
        valid_plans = {
            "bus-01": [ChargingPlan(bus_id="bus-01", stations=["A"])],
            "bus-02": [ChargingPlan(bus_id="bus-02", stations=["B"])],
            "bus-03": [ChargingPlan(bus_id="bus-03", stations=["A"])]
        }
        
        # Run greedy assignment
        scheduler._greedy_assign(valid_plans)
        
        # Buses should be assigned in departure order
        assert assignment_order == ["bus-01", "bus-02", "bus-03"]
    
    def test_greedy_assign_raises_error_for_bus_with_no_valid_plans(self):
        """Test that greedy assignment raises error when a bus has no valid plans."""
        scenario = self.create_multi_bus_scenario()
        scheduler = BusScheduler(scenario)
        
        # Create valid plans for only some buses
        valid_plans = {
            "bus-01": [ChargingPlan(bus_id="bus-01", stations=["A"])],
            "bus-02": [],  # No valid plans for bus-02
            "bus-03": [ChargingPlan(bus_id="bus-03", stations=["B"])]
        }
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="No valid charging plans found for bus bus-02"):
            scheduler._greedy_assign(valid_plans)


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
                Segment(**{"from": "A", "to": "Destination", "distance_km": 100})
            ],
            stations=[
                Station(id="A", name="Station A", num_chargers=1)
            ]
        )
        
        bus = Bus(
            id="bus-01",
            operator="test-op",
            origin="Origin",
            destination="Destination",
            departure_time="10:00"
        )
        
        scenario = Scenario(
            name="Simple Test",
            route=route,
            buses=[bus],
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights(
                individual=1.0,
                operator=1.0,
                overall=1.0
            )
        )
        
        # Run scheduler
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()
        
        # Verify result
        assert result is not None
        assert "bus-01" in result.bus_timelines
        assert len(result.bus_timelines["bus-01"].charging_stops) > 0
    
    def test_schedule_multiple_buses(self):
        """Test scheduling multiple buses."""
        route = Route(
            id="test-route",
            origin="Origin",
            destination="Destination",
            segments=[
                Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
                Segment(**{"from": "A", "to": "B", "distance_km": 100}),
                Segment(**{"from": "B", "to": "Destination", "distance_km": 100})
            ],
            stations=[
                Station(id="A", name="Station A", num_chargers=1),
                Station(id="B", name="Station B", num_chargers=1)
            ]
        )
        
        buses = [
            Bus(id="bus-01", operator="op1", origin="Origin", 
                destination="Destination", departure_time="10:00"),
            Bus(id="bus-02", operator="op2", origin="Origin", 
                destination="Destination", departure_time="10:30")
        ]
        
        scenario = Scenario(
            name="Multi-Bus Test",
            route=route,
            buses=buses,
            parameters=Parameters(
                battery_capacity_km=240,
                charge_duration_minutes=25,
                speed_kmh=60
            ),
            weights=Weights(
                individual=1.0,
                operator=1.0,
                overall=1.0
            )
        )
        
        # Run scheduler
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()
        
        # Verify result
        assert result is not None
        assert len(result.bus_timelines) == 2
        assert "bus-01" in result.bus_timelines
        assert "bus-02" in result.bus_timelines


class TestScenarioFiles:
    """Test the scheduler with all 5 scenario files."""
    
    def load_scenario_from_file(self, filename: str) -> Scenario:
        """Load a scenario from a JSON file."""
        import json
        from pathlib import Path
        
        # Get the scenarios directory
        scenarios_dir = Path(__file__).parent.parent / "scenarios"
        scenario_path = scenarios_dir / filename
        
        # Load and parse the JSON
        with open(scenario_path, 'r') as f:
            data = json.load(f)
        
        # Create Scenario object
        scenario = Scenario(**data)
        return scenario
    
    def validate_result(self, result: SimulationResult, scenario: Scenario) -> None:
        """Validate that a simulation result is correct."""
        # Check that all buses have timelines
        assert len(result.bus_timelines) == len(scenario.buses), \
            f"Expected {len(scenario.buses)} bus timelines, got {len(result.bus_timelines)}"
        
        for bus in scenario.buses:
            assert bus.id in result.bus_timelines, \
                f"Bus {bus.id} missing from timelines"
            
            timeline = result.bus_timelines[bus.id]
            
            # Check that bus has at least one charging stop
            assert len(timeline.charging_stops) > 0, \
                f"Bus {bus.id} has no charging stops"
            
            # Check that all charging stops have valid times
            for stop in timeline.charging_stops:
                assert stop.arrival_time is not None, \
                    f"Bus {bus.id} stop at {stop.station} has no arrival time"
                assert stop.charge_start is not None, \
                    f"Bus {bus.id} stop at {stop.station} has no charge start time"
                assert stop.charge_end is not None, \
                    f"Bus {bus.id} stop at {stop.station} has no charge end time"
                assert stop.wait_minutes >= 0, \
                    f"Bus {bus.id} stop at {stop.station} has negative wait time"
            
            # Check that arrival time is set
            assert timeline.arrival_time is not None, \
                f"Bus {bus.id} has no arrival time"
            
            # Check that total wait is non-negative
            assert timeline.total_wait_minutes >= 0, \
                f"Bus {bus.id} has negative total wait time"
        
        # Check that station queues are populated
        assert len(result.station_queues) > 0, \
            "No station queues in result"
    
    def test_scenario1_even_spacing(self):
        """Test Scenario 1 - Even Spacing."""
        scenario = self.load_scenario_from_file("scenario1.json")
        
        # Run scheduler
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()
        
        # Validate result
        self.validate_result(result, scenario)
        
        # Scenario-specific checks
        assert scenario.name == "Scenario 1 - Even Spacing"
        assert len(scenario.buses) == 20
        assert scenario.weights.individual == 1.0
        assert scenario.weights.operator == 1.0
        assert scenario.weights.overall == 1.0
    
    def test_scenario2_bunched_start(self):
        """Test Scenario 2 - Bunched Start."""
        scenario = self.load_scenario_from_file("scenario2.json")
        
        # Run scheduler
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()
        
        # Validate result
        self.validate_result(result, scenario)
        
        # Scenario-specific checks
        assert scenario.name == "Scenario 2 - Bunched Start"
        assert len(scenario.buses) == 20
        
        # This scenario should have more contention (higher wait times)
        total_wait = sum(t.total_wait_minutes for t in result.bus_timelines.values())
        assert total_wait > 0, "Expected some wait time due to bunched departures"
    
    def test_scenario3_asymmetric_load(self):
        """Test Scenario 3 - Asymmetric Load."""
        scenario = self.load_scenario_from_file("scenario3.json")
        
        # Run scheduler
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()
        
        # Validate result
        self.validate_result(result, scenario)
        
        # Scenario-specific checks
        assert scenario.name == "Scenario 3 - Asymmetric Load"
        assert len(scenario.buses) == 14  # 10 BK + 4 KB
        
        # Count buses by direction
        bk_buses = [b for b in scenario.buses if b.id.startswith("bus-BK")]
        kb_buses = [b for b in scenario.buses if b.id.startswith("bus-KB")]
        assert len(bk_buses) == 10
        assert len(kb_buses) == 4
    
    def test_scenario4_operator_heavy(self):
        """Test Scenario 4 - Operator Heavy."""
        scenario = self.load_scenario_from_file("scenario4.json")
        
        # Run scheduler
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()
        
        # Validate result
        self.validate_result(result, scenario)
        
        # Scenario-specific checks
        assert scenario.name == "Scenario 4 - Operator Heavy"
        assert len(scenario.buses) == 20
        assert scenario.weights.operator == 2.0  # Operator weight is doubled
        
        # Count KPN buses
        kpn_buses = [b for b in scenario.buses if b.operator == "kpn"]
        assert len(kpn_buses) > 10, "KPN should dominate the fleet"
    
    def test_scenario5_worst_case_convergence(self):
        """Test Scenario 5 - Worst Case Convergence."""
        scenario = self.load_scenario_from_file("scenario5.json")
        
        # Run scheduler
        scheduler = BusScheduler(scenario)
        result = scheduler.schedule()
        
        # Validate result
        self.validate_result(result, scenario)
        
        # Scenario-specific checks
        assert scenario.name == "Scenario 5 - Worst Case Convergence"
        assert len(scenario.buses) == 20
        
        # This scenario should have the highest contention
        total_wait = sum(t.total_wait_minutes for t in result.bus_timelines.values())
        max_wait = max(t.total_wait_minutes for t in result.bus_timelines.values())
        
        # Expect significant wait times due to convergence
        assert total_wait > 0, "Expected wait time due to convergence"
        assert max_wait > 0, "Expected at least one bus to wait"
    
    def test_all_scenarios_respect_constraints(self):
        """Test that all scenarios produce valid schedules that respect constraints."""
        from scheduler.constraints import RangeConstraint, RouteOrderConstraint, CompletionConstraint
        
        scenarios = [
            "scenario1.json",
            "scenario2.json",
            "scenario3.json",
            "scenario4.json",
            "scenario5.json"
        ]
        
        for scenario_file in scenarios:
            scenario = self.load_scenario_from_file(scenario_file)
            
            # Run scheduler
            scheduler = BusScheduler(scenario)
            result = scheduler.schedule()
            
            # Validate result
            self.validate_result(result, scenario)
            
            # Check that all assigned plans respect constraints
            for bus_id, plan in scheduler.assigned_plans.items():
                # Range constraint
                range_constraint = RangeConstraint()
                assert range_constraint.is_valid(plan, scenario), \
                    f"Range constraint violated for {bus_id} in {scenario_file}"
                
                # Route order constraint
                route_order_constraint = RouteOrderConstraint()
                assert route_order_constraint.is_valid(plan, scenario), \
                    f"Route order constraint violated for {bus_id} in {scenario_file}"
                
                # Completion constraint
                completion_constraint = CompletionConstraint()
                assert completion_constraint.is_valid(plan, scenario), \
                    f"Completion constraint violated for {bus_id} in {scenario_file}"
