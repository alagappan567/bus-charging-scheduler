"""
Unit tests for the objective system.

Tests each objective with known scenarios to ensure proper scoring logic.
"""

import pytest
import numpy as np
from scheduler.models import (
    Scenario, Route, Segment, Station, Bus, Parameters, Weights,
    SimulationResult, BusTimeline, ChargingStop, StationQueueEntry
)
from scheduler.objectives import (
    Objective, ObjectiveEvaluator,
    IndividualWaitObjective, OperatorFairnessObjective, OverallEfficiencyObjective
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def simple_scenario():
    """Create a simple scenario for testing."""
    route = Route(
        id="test-route",
        origin="Origin",
        destination="Destination",
        segments=[
            Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
            Segment(**{"from": "A", "to": "B", "distance_km": 120}),
            Segment(**{"from": "B", "to": "Destination", "distance_km": 100}),
        ],
        stations=[
            Station(id="A", name="A", num_chargers=1),
            Station(id="B", name="B", num_chargers=1),
        ]
    )
    
    buses = [
        Bus(id="bus-01", operator="kpn", origin="Origin", destination="Destination", departure_time="10:00"),
        Bus(id="bus-02", operator="ksrtc", origin="Origin", destination="Destination", departure_time="10:30"),
        Bus(id="bus-03", operator="kpn", origin="Origin", destination="Destination", departure_time="11:00"),
    ]
    
    return Scenario(
        name="Test Scenario",
        route=route,
        buses=buses,
        parameters=Parameters(battery_capacity_km=240, charge_duration_minutes=25, speed_kmh=60),
        weights=Weights(individual=1.0, operator=1.0, overall=1.0)
    )


@pytest.fixture
def result_no_wait():
    """Create a simulation result with no wait times."""
    return SimulationResult(
        bus_timelines={
            "bus-01": BusTimeline(
                bus_id="bus-01",
                operator="kpn",
                direction="Origin→Destination",
                departure_time="10:00",
                charging_stops=[
                    ChargingStop(station="A", arrival_time="11:40", wait_minutes=0, 
                               charge_start="11:40", charge_end="12:05")
                ],
                arrival_time="13:45",
                total_wait_minutes=0
            ),
            "bus-02": BusTimeline(
                bus_id="bus-02",
                operator="ksrtc",
                direction="Origin→Destination",
                departure_time="10:30",
                charging_stops=[
                    ChargingStop(station="A", arrival_time="12:10", wait_minutes=0,
                               charge_start="12:10", charge_end="12:35")
                ],
                arrival_time="14:15",
                total_wait_minutes=0
            ),
        },
        station_queues={}
    )



@pytest.fixture
def result_with_wait():
    """Create a simulation result with varying wait times."""
    return SimulationResult(
        bus_timelines={
            "bus-01": BusTimeline(
                bus_id="bus-01",
                operator="kpn",
                direction="Origin→Destination",
                departure_time="10:00",
                charging_stops=[
                    ChargingStop(station="A", arrival_time="11:40", wait_minutes=5,
                               charge_start="11:45", charge_end="12:10")
                ],
                arrival_time="13:50",
                total_wait_minutes=5
            ),
            "bus-02": BusTimeline(
                bus_id="bus-02",
                operator="ksrtc",
                direction="Origin→Destination",
                departure_time="10:30",
                charging_stops=[
                    ChargingStop(station="A", arrival_time="12:10", wait_minutes=10,
                               charge_start="12:20", charge_end="12:45")
                ],
                arrival_time="14:25",
                total_wait_minutes=10
            ),
            "bus-03": BusTimeline(
                bus_id="bus-03",
                operator="kpn",
                direction="Origin→Destination",
                departure_time="11:00",
                charging_stops=[
                    ChargingStop(station="A", arrival_time="12:40", wait_minutes=15,
                               charge_start="12:55", charge_end="13:20")
                ],
                arrival_time="15:00",
                total_wait_minutes=15
            ),
        },
        station_queues={}
    )



@pytest.fixture
def result_operator_balanced():
    """Create a simulation result with balanced wait times across operators."""
    return SimulationResult(
        bus_timelines={
            "bus-01": BusTimeline(
                bus_id="bus-01",
                operator="kpn",
                direction="Origin→Destination",
                departure_time="10:00",
                charging_stops=[],
                arrival_time="13:40",
                total_wait_minutes=10
            ),
            "bus-02": BusTimeline(
                bus_id="bus-02",
                operator="ksrtc",
                direction="Origin→Destination",
                departure_time="10:30",
                charging_stops=[],
                arrival_time="14:10",
                total_wait_minutes=10
            ),
            "bus-03": BusTimeline(
                bus_id="bus-03",
                operator="kpn",
                direction="Origin→Destination",
                departure_time="11:00",
                charging_stops=[],
                arrival_time="14:40",
                total_wait_minutes=10
            ),
        },
        station_queues={}
    )


@pytest.fixture
def result_operator_unbalanced():
    """Create a simulation result with unbalanced wait times across operators."""
    return SimulationResult(
        bus_timelines={
            "bus-01": BusTimeline(
                bus_id="bus-01",
                operator="kpn",
                direction="Origin→Destination",
                departure_time="10:00",
                charging_stops=[],
                arrival_time="13:40",
                total_wait_minutes=5
            ),
            "bus-02": BusTimeline(
                bus_id="bus-02",
                operator="ksrtc",
                direction="Origin→Destination",
                departure_time="10:30",
                charging_stops=[],
                arrival_time="14:10",
                total_wait_minutes=20
            ),
            "bus-03": BusTimeline(
                bus_id="bus-03",
                operator="kpn",
                direction="Origin→Destination",
                departure_time="11:00",
                charging_stops=[],
                arrival_time="14:40",
                total_wait_minutes=5
            ),
        },
        station_queues={}
    )



# ============================================================================
# IndividualWaitObjective Tests
# ============================================================================

class TestIndividualWaitObjective:
    """Tests for IndividualWaitObjective."""
    
    def test_score_no_wait(self, simple_scenario, result_no_wait):
        """Test that score is 0 when no buses wait."""
        objective = IndividualWaitObjective()
        score = objective.score(result_no_wait, simple_scenario)
        assert score == 0.0
    
    def test_score_with_wait(self, simple_scenario, result_with_wait):
        """Test that score equals negative of max wait time."""
        objective = IndividualWaitObjective()
        score = objective.score(result_with_wait, simple_scenario)
        # Max wait is 15 minutes (bus-03)
        assert score == -15.0
    
    def test_score_penalizes_max_not_average(self, simple_scenario, result_with_wait):
        """Test that objective penalizes max wait, not average."""
        objective = IndividualWaitObjective()
        score = objective.score(result_with_wait, simple_scenario)
        # Average wait is (5 + 10 + 15) / 3 = 10, but score should be -15 (max)
        assert score == -15.0
        assert score != -10.0
    
    def test_score_empty_result(self, simple_scenario):
        """Test that score is 0 for empty result."""
        objective = IndividualWaitObjective()
        empty_result = SimulationResult(bus_timelines={}, station_queues={})
        score = objective.score(empty_result, simple_scenario)
        assert score == 0.0
    
    def test_score_single_bus(self, simple_scenario):
        """Test score with single bus."""
        objective = IndividualWaitObjective()
        result = SimulationResult(
            bus_timelines={
                "bus-01": BusTimeline(
                    bus_id="bus-01",
                    operator="kpn",
                    direction="Origin→Destination",
                    departure_time="10:00",
                    charging_stops=[],
                    arrival_time="13:40",
                    total_wait_minutes=25
                ),
            },
            station_queues={}
        )
        score = objective.score(result, simple_scenario)
        assert score == -25.0



# ============================================================================
# OperatorFairnessObjective Tests
# ============================================================================

class TestOperatorFairnessObjective:
    """Tests for OperatorFairnessObjective."""
    
    def test_score_balanced_operators(self, simple_scenario, result_operator_balanced):
        """Test that score is 0 when all operators have same average wait."""
        objective = OperatorFairnessObjective()
        score = objective.score(result_operator_balanced, simple_scenario)
        # kpn average: (10 + 10) / 2 = 10
        # ksrtc average: 10
        # Variance: 0
        assert score == 0.0
    
    def test_score_unbalanced_operators(self, simple_scenario, result_operator_unbalanced):
        """Test that score penalizes variance in operator averages."""
        objective = OperatorFairnessObjective()
        score = objective.score(result_operator_unbalanced, simple_scenario)
        # kpn average: (5 + 5) / 2 = 5
        # ksrtc average: 20
        # Variance: ((5-12.5)^2 + (20-12.5)^2) / 2 = (56.25 + 56.25) / 2 = 56.25
        expected_variance = np.var([5.0, 20.0])
        assert score == pytest.approx(-expected_variance)
    
    def test_score_single_operator(self, simple_scenario):
        """Test that score is 0 when only one operator exists."""
        objective = OperatorFairnessObjective()
        result = SimulationResult(
            bus_timelines={
                "bus-01": BusTimeline(
                    bus_id="bus-01",
                    operator="kpn",
                    direction="Origin→Destination",
                    departure_time="10:00",
                    charging_stops=[],
                    arrival_time="13:40",
                    total_wait_minutes=10
                ),
                "bus-03": BusTimeline(
                    bus_id="bus-03",
                    operator="kpn",
                    direction="Origin→Destination",
                    departure_time="11:00",
                    charging_stops=[],
                    arrival_time="14:40",
                    total_wait_minutes=20
                ),
            },
            station_queues={}
        )
        score = objective.score(result, simple_scenario)
        # Only one operator, so variance is 0
        assert score == 0.0

    
    def test_score_empty_result(self, simple_scenario):
        """Test that score is 0 for empty result."""
        objective = OperatorFairnessObjective()
        empty_result = SimulationResult(bus_timelines={}, station_queues={})
        score = objective.score(empty_result, simple_scenario)
        assert score == 0.0
    
    def test_score_three_operators(self):
        """Test score with three different operators."""
        # Create a fresh scenario with three operators
        route = Route(
            id="test-route",
            origin="Origin",
            destination="Destination",
            segments=[
                Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
                Segment(**{"from": "A", "to": "Destination", "distance_km": 100}),
            ],
            stations=[
                Station(id="A", name="A", num_chargers=1),
            ]
        )
        
        buses = [
            Bus(id="bus-01", operator="kpn", origin="Origin", destination="Destination", departure_time="10:00"),
            Bus(id="bus-02", operator="ksrtc", origin="Origin", destination="Destination", departure_time="10:30"),
            Bus(id="bus-03", operator="private", origin="Origin", destination="Destination", departure_time="11:00"),
        ]
        
        scenario = Scenario(
            name="Three Operator Scenario",
            route=route,
            buses=buses,
            parameters=Parameters(),
            weights=Weights()
        )
        
        objective = OperatorFairnessObjective()
        result = SimulationResult(
            bus_timelines={
                "bus-01": BusTimeline(
                    bus_id="bus-01",
                    operator="kpn",
                    direction="Origin→Destination",
                    departure_time="10:00",
                    charging_stops=[],
                    arrival_time="13:40",
                    total_wait_minutes=10
                ),
                "bus-02": BusTimeline(
                    bus_id="bus-02",
                    operator="ksrtc",
                    direction="Origin→Destination",
                    departure_time="10:30",
                    charging_stops=[],
                    arrival_time="14:10",
                    total_wait_minutes=20
                ),
                "bus-03": BusTimeline(
                    bus_id="bus-03",
                    operator="private",
                    direction="Origin→Destination",
                    departure_time="11:00",
                    charging_stops=[],
                    arrival_time="14:40",
                    total_wait_minutes=30
                ),
            },
            station_queues={}
        )
        
        score = objective.score(result, scenario)
        # Averages: kpn=10, ksrtc=20, private=30
        expected_variance = np.var([10.0, 20.0, 30.0])
        assert score == pytest.approx(-expected_variance)



# ============================================================================
# OverallEfficiencyObjective Tests
# ============================================================================

class TestOverallEfficiencyObjective:
    """Tests for OverallEfficiencyObjective."""
    
    def test_score_no_wait(self, simple_scenario, result_no_wait):
        """Test that score is 0 when no buses wait."""
        objective = OverallEfficiencyObjective()
        score = objective.score(result_no_wait, simple_scenario)
        assert score == 0.0
    
    def test_score_with_wait(self, simple_scenario, result_with_wait):
        """Test that score equals negative of total wait time."""
        objective = OverallEfficiencyObjective()
        score = objective.score(result_with_wait, simple_scenario)
        # Total wait: 5 + 10 + 15 = 30
        assert score == -30.0
    
    def test_score_sums_all_buses(self, simple_scenario, result_with_wait):
        """Test that objective sums wait times across all buses."""
        objective = OverallEfficiencyObjective()
        score = objective.score(result_with_wait, simple_scenario)
        # Verify it's the sum, not max or average
        assert score == -30.0  # Sum of 5, 10, 15
        assert score != -15.0  # Not max
        assert score != -10.0  # Not average
    
    def test_score_empty_result(self, simple_scenario):
        """Test that score is 0 for empty result."""
        objective = OverallEfficiencyObjective()
        empty_result = SimulationResult(bus_timelines={}, station_queues={})
        score = objective.score(empty_result, simple_scenario)
        assert score == 0.0
    
    def test_score_single_bus(self, simple_scenario):
        """Test score with single bus."""
        objective = OverallEfficiencyObjective()
        result = SimulationResult(
            bus_timelines={
                "bus-01": BusTimeline(
                    bus_id="bus-01",
                    operator="kpn",
                    direction="Origin→Destination",
                    departure_time="10:00",
                    charging_stops=[],
                    arrival_time="13:40",
                    total_wait_minutes=25
                ),
            },
            station_queues={}
        )
        score = objective.score(result, simple_scenario)
        assert score == -25.0



# ============================================================================
# ObjectiveEvaluator Tests
# ============================================================================

class TestObjectiveEvaluator:
    """Tests for ObjectiveEvaluator."""
    
    def test_evaluate_single_objective(self, simple_scenario, result_with_wait):
        """Test evaluation with a single objective."""
        objectives = [(IndividualWaitObjective(), 1.0)]
        evaluator = ObjectiveEvaluator(objectives)
        
        score = evaluator.evaluate(result_with_wait, simple_scenario)
        # Max wait is 15, so score should be -15
        assert score == -15.0
    
    def test_evaluate_multiple_objectives_equal_weights(self, simple_scenario, result_with_wait):
        """Test evaluation with multiple objectives and equal weights."""
        objectives = [
            (IndividualWaitObjective(), 1.0),
            (OverallEfficiencyObjective(), 1.0),
        ]
        evaluator = ObjectiveEvaluator(objectives)
        
        score = evaluator.evaluate(result_with_wait, simple_scenario)
        # Individual: -15, Overall: -30, Total: -45
        assert score == -45.0
    
    def test_evaluate_multiple_objectives_different_weights(self, simple_scenario, result_with_wait):
        """Test evaluation with different weights."""
        objectives = [
            (IndividualWaitObjective(), 2.0),
            (OverallEfficiencyObjective(), 1.0),
        ]
        evaluator = ObjectiveEvaluator(objectives)
        
        score = evaluator.evaluate(result_with_wait, simple_scenario)
        # Individual: -15 * 2 = -30, Overall: -30 * 1 = -30, Total: -60
        assert score == -60.0
    
    def test_evaluate_with_zero_weight(self, simple_scenario, result_with_wait):
        """Test that zero weight excludes an objective."""
        objectives = [
            (IndividualWaitObjective(), 1.0),
            (OverallEfficiencyObjective(), 0.0),
        ]
        evaluator = ObjectiveEvaluator(objectives)
        
        score = evaluator.evaluate(result_with_wait, simple_scenario)
        # Only individual objective counts: -15
        assert score == -15.0
    
    def test_evaluate_all_three_objectives(self, simple_scenario, result_with_wait):
        """Test evaluation with all three core objectives."""
        objectives = [
            (IndividualWaitObjective(), 1.0),
            (OperatorFairnessObjective(), 1.0),
            (OverallEfficiencyObjective(), 1.0),
        ]
        evaluator = ObjectiveEvaluator(objectives)
        
        score = evaluator.evaluate(result_with_wait, simple_scenario)
        # Individual: -15
        # Operator: -variance of [10, 10] (kpn avg: (5+15)/2=10, ksrtc: 10) = 0
        # Overall: -30
        # Total: -45
        assert score == pytest.approx(-45.0)

    
    def test_evaluate_detailed(self, simple_scenario, result_with_wait):
        """Test detailed evaluation returns breakdown of scores."""
        objectives = [
            (IndividualWaitObjective(), 2.0),
            (OverallEfficiencyObjective(), 1.0),
        ]
        evaluator = ObjectiveEvaluator(objectives)
        
        detailed = evaluator.evaluate_detailed(result_with_wait, simple_scenario)
        
        # Check structure
        assert 'IndividualWaitObjective' in detailed
        assert 'OverallEfficiencyObjective' in detailed
        assert 'total' in detailed
        
        # Check individual objective details
        individual_details = detailed['IndividualWaitObjective']
        assert individual_details['raw_score'] == -15.0
        assert individual_details['weight'] == 2.0
        assert individual_details['weighted_score'] == -30.0
        
        # Check overall objective details
        overall_details = detailed['OverallEfficiencyObjective']
        assert overall_details['raw_score'] == -30.0
        assert overall_details['weight'] == 1.0
        assert overall_details['weighted_score'] == -30.0
        
        # Check total
        assert detailed['total'] == -60.0
    
    def test_evaluate_empty_objectives_list(self, simple_scenario, result_with_wait):
        """Test that evaluator with no objectives returns 0."""
        evaluator = ObjectiveEvaluator([])
        score = evaluator.evaluate(result_with_wait, simple_scenario)
        assert score == 0.0


# ============================================================================
# Integration Tests
# ============================================================================

class TestObjectiveIntegration:
    """Integration tests for the objective system."""
    
    def test_objectives_prefer_no_wait_over_wait(self, simple_scenario, result_no_wait, result_with_wait):
        """Test that all objectives prefer no wait over wait."""
        objectives = [
            (IndividualWaitObjective(), 1.0),
            (OperatorFairnessObjective(), 1.0),
            (OverallEfficiencyObjective(), 1.0),
        ]
        evaluator = ObjectiveEvaluator(objectives)
        
        score_no_wait = evaluator.evaluate(result_no_wait, simple_scenario)
        score_with_wait = evaluator.evaluate(result_with_wait, simple_scenario)
        
        # No wait should have higher (better) score
        assert score_no_wait > score_with_wait

    
    def test_operator_fairness_prefers_balanced(self, simple_scenario, 
                                                 result_operator_balanced, 
                                                 result_operator_unbalanced):
        """Test that operator fairness objective prefers balanced wait times."""
        objective = OperatorFairnessObjective()
        
        score_balanced = objective.score(result_operator_balanced, simple_scenario)
        score_unbalanced = objective.score(result_operator_unbalanced, simple_scenario)
        
        # Balanced should have higher (better) score
        assert score_balanced > score_unbalanced
    
    def test_weight_changes_affect_total_score(self, simple_scenario, result_with_wait):
        """Test that changing weights changes the total score."""
        # High individual weight
        evaluator1 = ObjectiveEvaluator([
            (IndividualWaitObjective(), 10.0),
            (OverallEfficiencyObjective(), 1.0),
        ])
        
        # High overall weight
        evaluator2 = ObjectiveEvaluator([
            (IndividualWaitObjective(), 1.0),
            (OverallEfficiencyObjective(), 10.0),
        ])
        
        score1 = evaluator1.evaluate(result_with_wait, simple_scenario)
        score2 = evaluator2.evaluate(result_with_wait, simple_scenario)
        
        # Scores should be different
        assert score1 != score2
        
        # Score1: -15*10 + -30*1 = -180
        # Score2: -15*1 + -30*10 = -315
        assert score1 == -180.0
        assert score2 == -315.0
    
    def test_realistic_scenario_scoring(self, simple_scenario):
        """Test scoring with a realistic scenario."""
        # Create a result with mixed wait times
        result = SimulationResult(
            bus_timelines={
                "bus-01": BusTimeline(
                    bus_id="bus-01",
                    operator="kpn",
                    direction="Origin→Destination",
                    departure_time="10:00",
                    charging_stops=[
                        ChargingStop(station="A", arrival_time="11:40", wait_minutes=0,
                                   charge_start="11:40", charge_end="12:05")
                    ],
                    arrival_time="13:45",
                    total_wait_minutes=0
                ),
                "bus-02": BusTimeline(
                    bus_id="bus-02",
                    operator="ksrtc",
                    direction="Origin→Destination",
                    departure_time="10:30",
                    charging_stops=[
                        ChargingStop(station="A", arrival_time="12:10", wait_minutes=5,
                                   charge_start="12:15", charge_end="12:40")
                    ],
                    arrival_time="14:20",
                    total_wait_minutes=5
                ),
                "bus-03": BusTimeline(
                    bus_id="bus-03",
                    operator="kpn",
                    direction="Origin→Destination",
                    departure_time="11:00",
                    charging_stops=[
                        ChargingStop(station="A", arrival_time="12:40", wait_minutes=10,
                                   charge_start="12:50", charge_end="13:15")
                    ],
                    arrival_time="14:55",
                    total_wait_minutes=10
                ),
            },
            station_queues={}
        )
        
        # Use realistic weights from scenario
        objectives = [
            (IndividualWaitObjective(), simple_scenario.weights.individual),
            (OperatorFairnessObjective(), simple_scenario.weights.operator),
            (OverallEfficiencyObjective(), simple_scenario.weights.overall),
        ]
        evaluator = ObjectiveEvaluator(objectives)
        
        score = evaluator.evaluate(result, simple_scenario)
        detailed = evaluator.evaluate_detailed(result, simple_scenario)
        
        # Verify score is negative (penalties)
        assert score < 0
        
        # Verify detailed breakdown is available
        assert 'IndividualWaitObjective' in detailed
        assert 'OperatorFairnessObjective' in detailed
        assert 'OverallEfficiencyObjective' in detailed
        assert detailed['total'] == score
