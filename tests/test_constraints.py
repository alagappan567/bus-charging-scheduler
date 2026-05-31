"""
Unit tests for the constraint system.

Tests each constraint with valid and invalid charging plans to ensure
proper validation logic.
"""

import pytest
from scheduler.models import (
    Scenario, Route, Segment, Station, Bus, Parameters, Weights, ChargingPlan
)
from scheduler.constraints import (
    Constraint, ConstraintValidator,
    RangeConstraint, RouteOrderConstraint, CompletionConstraint
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def simple_route():
    """Create a simple linear route for testing."""
    return Route(
        id="test-route",
        origin="Origin",
        destination="Destination",
        segments=[
            Segment(**{"from": "Origin", "to": "A", "distance_km": 100}),
            Segment(**{"from": "A", "to": "B", "distance_km": 120}),
            Segment(**{"from": "B", "to": "C", "distance_km": 100}),
            Segment(**{"from": "C", "to": "Destination", "distance_km": 120}),
        ],
        stations=[
            Station(id="A", name="A", num_chargers=1),
            Station(id="B", name="B", num_chargers=1),
            Station(id="C", name="C", num_chargers=1),
        ]
    )


@pytest.fixture
def simple_bus():
    """Create a simple bus for testing."""
    return Bus(
        id="bus-01",
        operator="test-operator",
        origin="Origin",
        destination="Destination",
        departure_time="10:00"
    )


@pytest.fixture
def simple_scenario(simple_route, simple_bus):
    """Create a simple scenario for testing."""
    return Scenario(
        name="Test Scenario",
        route=simple_route,
        buses=[simple_bus],
        parameters=Parameters(
            battery_capacity_km=240,
            charge_duration_minutes=25,
            speed_kmh=60
        ),
        weights=Weights()
    )


# ============================================================================
# RangeConstraint Tests
# ============================================================================

class TestRangeConstraint:
    """Tests for RangeConstraint."""
    
    def test_valid_plan_within_range(self, simple_scenario):
        """Test that a valid plan with all segments within range passes."""
        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "C"])
        
        # Origin to A: 100 km (< 240)
        # A to C: 220 km (< 240)
        # C to Destination: 120 km (< 240)
        assert constraint.is_valid(plan, simple_scenario)
    
    def test_valid_plan_all_stations(self, simple_scenario):
        """Test that a plan using all stations is valid."""
        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        # All segments are within 240 km
        assert constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_exceeds_range_to_first_station(self, simple_scenario):
        """Test that a plan exceeding range to first station fails."""
        # Modify scenario to have first segment > battery capacity
        simple_scenario.route.segments[0].distance_km = 250
        
        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_exceeds_range_between_stations(self, simple_scenario):
        """Test that a plan exceeding range between stations fails."""
        constraint = RangeConstraint()
        # Skip station B, making A to C distance = 220 km
        # This is within range, so let's create a scenario where it exceeds
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "C"])
        
        # Modify the route to make A to C exceed battery capacity
        simple_scenario.route.segments[1].distance_km = 250
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_exceeds_range_to_destination(self, simple_scenario):
        """Test that a plan exceeding range to destination fails."""
        # Modify last segment to exceed battery capacity
        simple_scenario.route.segments[3].distance_km = 250
        
        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_with_invalid_station_id(self, simple_scenario):
        """Test that a plan with invalid station ID fails."""
        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "INVALID", "C"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_with_nonexistent_bus(self, simple_scenario):
        """Test that a plan for nonexistent bus fails."""
        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="nonexistent-bus", stations=["A", "B", "C"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_violation_message_contains_details(self, simple_scenario):
        """Test that violation message contains useful details."""
        simple_scenario.route.segments[0].distance_km = 250
        
        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
        assert "250" in message or "250.0" in message
        assert "240" in message or "240.0" in message


# ============================================================================
# RouteOrderConstraint Tests
# ============================================================================

class TestRouteOrderConstraint:
    """Tests for RouteOrderConstraint."""
    
    def test_valid_plan_in_order(self, simple_scenario):
        """Test that a plan with stations in route order passes."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        assert constraint.is_valid(plan, simple_scenario)
    
    def test_valid_plan_skipping_stations(self, simple_scenario):
        """Test that a plan skipping stations but maintaining order passes."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "C"])
        
        assert constraint.is_valid(plan, simple_scenario)
    
    def test_valid_plan_single_station(self, simple_scenario):
        """Test that a plan with single station passes."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["B"])
        
        assert constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_out_of_order(self, simple_scenario):
        """Test that a plan with stations out of order fails."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["B", "A", "C"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_reverse_order(self, simple_scenario):
        """Test that a plan with stations in reverse order fails."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["C", "B", "A"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_with_backtracking(self, simple_scenario):
        """Test that a plan with backtracking fails."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "C", "B"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_with_invalid_station(self, simple_scenario):
        """Test that a plan with invalid station ID fails."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "INVALID"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_with_nonexistent_bus(self, simple_scenario):
        """Test that a plan for nonexistent bus fails."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="nonexistent-bus", stations=["A", "B"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_violation_message_contains_details(self, simple_scenario):
        """Test that violation message contains useful details."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["C", "A"])
        
        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
        assert "order" in message.lower()


# ============================================================================
# CompletionConstraint Tests
# ============================================================================

class TestCompletionConstraint:
    """Tests for CompletionConstraint."""
    
    def test_valid_plan_can_reach_destination(self, simple_scenario):
        """Test that a valid plan that can reach destination passes."""
        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        assert constraint.is_valid(plan, simple_scenario)
    
    def test_valid_plan_with_minimal_stations(self, simple_scenario):
        """Test that a plan with minimal stations but valid completion passes."""
        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "C"])
        
        # C to Destination is 120 km, within battery capacity
        assert constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_empty_stations(self, simple_scenario):
        """Test that a plan with no stations fails validation at model level."""
        # Pydantic validation prevents creating empty plans
        with pytest.raises(Exception):  # ValidationError
            plan = ChargingPlan(bus_id="bus-01", stations=[])
    
    def test_invalid_plan_cannot_reach_destination(self, simple_scenario):
        """Test that a plan where bus cannot reach destination fails."""
        # Modify last segment to exceed battery capacity
        simple_scenario.route.segments[3].distance_km = 250
        
        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_with_invalid_station_id(self, simple_scenario):
        """Test that a plan with invalid station ID fails."""
        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "INVALID"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_with_station_not_on_route(self, simple_scenario):
        """Test that a plan with station not on route fails."""
        # Add a station that's not on the route
        simple_scenario.route.stations.append(
            Station(id="D", name="D", num_chargers=1)
        )
        
        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "D"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_invalid_plan_with_nonexistent_bus(self, simple_scenario):
        """Test that a plan for nonexistent bus fails."""
        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="nonexistent-bus", stations=["A", "B"])
        
        assert not constraint.is_valid(plan, simple_scenario)
    
    def test_violation_message_for_empty_plan(self, simple_scenario):
        """Test that empty plans are prevented by Pydantic validation."""
        # Pydantic validation prevents creating empty plans
        with pytest.raises(Exception):  # ValidationError
            plan = ChargingPlan(bus_id="bus-01", stations=[])
    
    def test_violation_message_for_unreachable_destination(self, simple_scenario):
        """Test violation message when destination is unreachable."""
        simple_scenario.route.segments[3].distance_km = 250
        
        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
        assert "destination" in message.lower()
        assert "250" in message or "250.0" in message


# ============================================================================
# ConstraintValidator Tests
# ============================================================================

class TestConstraintValidator:
    """Tests for ConstraintValidator."""
    
    def test_validator_with_all_valid_constraints(self, simple_scenario):
        """Test that validator passes when all constraints are satisfied."""
        constraints = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        validator = ConstraintValidator(constraints)
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        assert validator.is_valid(plan, simple_scenario)
    
    def test_validator_with_one_invalid_constraint(self, simple_scenario):
        """Test that validator fails when one constraint is violated."""
        constraints = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        validator = ConstraintValidator(constraints)
        
        # Create a plan with stations out of order
        plan = ChargingPlan(bus_id="bus-01", stations=["C", "A", "B"])
        
        assert not validator.is_valid(plan, simple_scenario)
    
    def test_validator_get_violations_empty_for_valid_plan(self, simple_scenario):
        """Test that get_violations returns empty list for valid plan."""
        constraints = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        validator = ConstraintValidator(constraints)
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        
        violations = validator.get_violations(plan, simple_scenario)
        assert len(violations) == 0
    
    def test_validator_get_violations_lists_all_violations(self, simple_scenario):
        """Test that get_violations lists all constraint violations."""
        # Modify scenario to violate multiple constraints
        simple_scenario.route.segments[3].distance_km = 250  # Violates range and completion
        
        constraints = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        validator = ConstraintValidator(constraints)
        
        # Plan with stations out of order (violates route order)
        plan = ChargingPlan(bus_id="bus-01", stations=["C", "A", "B"])
        
        violations = validator.get_violations(plan, simple_scenario)
        # Should have at least route order violation
        assert len(violations) > 0
        assert any("order" in v.lower() for v in violations)
    
    def test_validator_with_empty_constraints_list(self, simple_scenario):
        """Test that validator with no constraints always passes."""
        validator = ConstraintValidator([])
        plan = ChargingPlan(bus_id="bus-01", stations=["C", "A", "B"])
        
        # Even an invalid plan should pass with no constraints
        assert validator.is_valid(plan, simple_scenario)
    
    def test_validator_with_single_constraint(self, simple_scenario):
        """Test validator with a single constraint."""
        validator = ConstraintValidator([RouteOrderConstraint()])
        
        valid_plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        invalid_plan = ChargingPlan(bus_id="bus-01", stations=["C", "A"])
        
        assert validator.is_valid(valid_plan, simple_scenario)
        assert not validator.is_valid(invalid_plan, simple_scenario)


# ============================================================================
# Integration Tests
# ============================================================================

class TestConstraintIntegration:
    """Integration tests for the constraint system."""
    
    def test_realistic_scenario_with_valid_plan(self, simple_scenario):
        """Test a realistic scenario with a valid charging plan."""
        constraints = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        validator = ConstraintValidator(constraints)
        
        # Plan that charges at A and C (skipping B)
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "C"])
        
        assert validator.is_valid(plan, simple_scenario)
        assert len(validator.get_violations(plan, simple_scenario)) == 0
    
    def test_realistic_scenario_with_multiple_violations(self, simple_scenario):
        """Test a realistic scenario with multiple constraint violations."""
        # Modify scenario to create violations
        simple_scenario.route.segments[0].distance_km = 250  # Exceeds range
        
        constraints = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        validator = ConstraintValidator(constraints)
        
        # Plan with stations out of order
        plan = ChargingPlan(bus_id="bus-01", stations=["B", "A"])
        
        assert not validator.is_valid(plan, simple_scenario)
        violations = validator.get_violations(plan, simple_scenario)
        assert len(violations) >= 2  # At least range and route order violations
    
    def test_edge_case_single_station_plan(self, simple_scenario):
        """Test edge case with a single station in the plan."""
        constraints = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        validator = ConstraintValidator(constraints)
        
        # Single station plan
        plan = ChargingPlan(bus_id="bus-01", stations=["B"])
        
        # This should be valid if distances allow
        # Origin to B: 220 km (< 240)
        # B to Destination: 220 km (< 240)
        assert validator.is_valid(plan, simple_scenario)
    
    def test_edge_case_maximum_range_utilization(self, simple_scenario):
        """Test edge case where plan uses maximum battery range."""
        # Set up scenario where distances are exactly at battery capacity
        simple_scenario.parameters.battery_capacity_km = 220
        
        constraints = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        validator = ConstraintValidator(constraints)
        
        # Plan that uses exactly the battery capacity
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "C"])
        
        # A to C is 220 km, exactly at capacity
        assert validator.is_valid(plan, simple_scenario)


# ============================================================================
# Additional coverage tests for violation message paths
# ============================================================================

class TestRangeConstraintViolationMessages:
    """Tests for RangeConstraint violation message paths."""

    def test_violation_message_between_stations_exceeds_range(self, simple_scenario):
        """Test violation message when distance between stations exceeds range."""
        # Make A to B exceed battery capacity
        simple_scenario.route.segments[1].distance_km = 250
        simple_scenario.parameters.battery_capacity_km = 240

        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B"])

        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
        assert "250" in message or "250.0" in message

    def test_violation_message_last_station_to_destination(self, simple_scenario):
        """Test violation message when last station to destination exceeds range."""
        simple_scenario.route.segments[3].distance_km = 250

        constraint = RangeConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B"])

        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
        assert "Destination" in message

    def test_violation_message_no_violation_returns_generic(self, simple_scenario):
        """Test that get_violation_message returns generic message when no specific violation found."""
        constraint = RangeConstraint()
        # Plan that is actually valid — message should still return something
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message


class TestRouteOrderConstraintViolationMessages:
    """Tests for RouteOrderConstraint violation message paths."""

    def test_violation_message_station_not_on_route(self, simple_scenario):
        """Test violation message when station is not on the route."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "NOTASTATION"])

        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
        assert "NOTASTATION" in message

    def test_violation_message_out_of_order_stations(self, simple_scenario):
        """Test violation message for out-of-order stations."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["C", "A"])

        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
        assert "order" in message.lower()

    def test_violation_message_generic_fallback(self, simple_scenario):
        """Test that get_violation_message returns something for valid plan."""
        constraint = RouteOrderConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message


class TestCompletionConstraintViolationMessages:
    """Tests for CompletionConstraint violation message paths."""

    def test_violation_message_station_not_on_route(self, simple_scenario):
        """Test violation message when station is not on the bus's route."""
        # Add a station to the route that is not reachable from Origin to Destination
        # by adding it to stations list but not to segments
        simple_scenario.route.stations.append(
            Station(id="Z", name="Station Z", num_chargers=1)
        )

        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "Z"])

        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
        # The message should indicate some kind of route/location issue
        assert len(message) > 0

    def test_violation_message_generic_fallback(self, simple_scenario):
        """Test that get_violation_message returns something for valid plan."""
        constraint = CompletionConstraint()
        plan = ChargingPlan(bus_id="bus-01", stations=["A", "B", "C"])
        message = constraint.get_violation_message(plan, simple_scenario)
        assert "bus-01" in message
