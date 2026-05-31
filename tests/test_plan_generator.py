"""
Unit tests for the charging plan generator.

Tests plan generation logic including station selection, minimum charge
calculation, and combination generation.
"""

import pytest
from scheduler.models import (
    Route, Segment, Station, Bus, Parameters, ChargingPlan
)
from scheduler.plan_generator import (
    get_stations_on_route,
    calculate_min_charges,
    generate_charging_plans
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
def long_route():
    """Create a longer route requiring multiple charges."""
    return Route(
        id="long-route",
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
            Station(id="A", name="A", num_chargers=1),
            Station(id="B", name="B", num_chargers=1),
            Station(id="C", name="C", num_chargers=1),
            Station(id="D", name="D", num_chargers=1),
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
def long_route_bus():
    """Create a bus for the long route."""
    return Bus(
        id="bus-BK-01",
        operator="kpn",
        origin="Bengaluru",
        destination="Kochi",
        departure_time="19:00"
    )


@pytest.fixture
def standard_params():
    """Create standard parameters."""
    return Parameters(
        battery_capacity_km=240,
        charge_duration_minutes=25,
        speed_kmh=60
    )


# ============================================================================
# get_stations_on_route Tests
# ============================================================================

class TestGetStationsOnRoute:
    """Tests for get_stations_on_route helper function."""
    
    def test_get_all_stations_on_route(self, simple_bus, simple_route):
        """Test getting all stations between origin and destination."""
        stations = get_stations_on_route(simple_bus, simple_route)
        
        assert stations == ["A", "B", "C"]
    
    def test_get_stations_on_long_route(self, long_route_bus, long_route):
        """Test getting stations on a longer route."""
        stations = get_stations_on_route(long_route_bus, long_route)
        
        assert stations == ["A", "B", "C", "D"]
    
    def test_stations_in_correct_order(self, simple_bus, simple_route):
        """Test that stations are returned in route order."""
        stations = get_stations_on_route(simple_bus, simple_route)
        
        # Verify order matches route segments
        assert stations[0] == "A"
        assert stations[1] == "B"
        assert stations[2] == "C"
    
    def test_partial_route_bus(self, simple_route):
        """Test bus that only travels part of the route."""
        # Bus from Origin to B (not full route)
        partial_bus = Bus(
            id="bus-02",
            operator="test-operator",
            origin="Origin",
            destination="B",
            departure_time="10:00"
        )
        
        stations = get_stations_on_route(partial_bus, simple_route)
        
        # Should only include stations up to B
        assert stations == ["A", "B"]
    
    def test_bus_starting_mid_route(self, simple_route):
        """Test bus that starts at a station (not origin)."""
        mid_route_bus = Bus(
            id="bus-03",
            operator="test-operator",
            origin="A",
            destination="Destination",
            departure_time="10:00"
        )
        
        stations = get_stations_on_route(mid_route_bus, simple_route)
        
        # Should include stations from A onwards (B and C)
        assert stations == ["B", "C"]
    
    def test_invalid_origin_raises_error(self, simple_route):
        """Test that invalid origin raises ValueError."""
        invalid_bus = Bus(
            id="bus-04",
            operator="test-operator",
            origin="InvalidOrigin",
            destination="Destination",
            departure_time="10:00"
        )
        
        with pytest.raises(ValueError):
            get_stations_on_route(invalid_bus, simple_route)
    
    def test_invalid_destination_raises_error(self, simple_route):
        """Test that invalid destination raises ValueError."""
        invalid_bus = Bus(
            id="bus-05",
            operator="test-operator",
            origin="Origin",
            destination="InvalidDestination",
            departure_time="10:00"
        )
        
        with pytest.raises(ValueError):
            get_stations_on_route(invalid_bus, simple_route)


# ============================================================================
# calculate_min_charges Tests
# ============================================================================

class TestCalculateMinCharges:
    """Tests for calculate_min_charges helper function."""
    
    def test_short_route_no_charges_needed(self, simple_route):
        """Test route shorter than battery capacity needs no charges."""
        # Create a very short route
        short_bus = Bus(
            id="bus-short",
            operator="test-operator",
            origin="Origin",
            destination="A",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=240)
        min_charges = calculate_min_charges(short_bus, simple_route, params)
        
        # 100 km < 240 km, no charges needed
        assert min_charges == 0
    
    def test_route_needs_one_charge(self, simple_route):
        """Test route that needs exactly one charge."""
        # Origin to Destination is 440 km
        # With 240 km battery: needs 1 charge
        params = Parameters(battery_capacity_km=240)
        bus = Bus(
            id="bus-01",
            operator="test-operator",
            origin="Origin",
            destination="Destination",
            departure_time="10:00"
        )
        
        min_charges = calculate_min_charges(bus, simple_route, params)
        
        # 440 km / 240 km = 1.83 -> ceil = 2 segments -> 1 charge
        assert min_charges == 1
    
    def test_long_route_needs_multiple_charges(self, long_route_bus, long_route):
        """Test long route that needs multiple charges."""
        # Bengaluru to Kochi is 540 km
        # With 240 km battery: needs 2 charges
        params = Parameters(battery_capacity_km=240)
        
        min_charges = calculate_min_charges(long_route_bus, long_route, params)
        
        # 540 km / 240 km = 2.25 -> ceil = 3 segments -> 2 charges
        assert min_charges == 2
    
    def test_exact_battery_capacity_multiple(self, simple_route):
        """Test route that is exact multiple of battery capacity."""
        # Create route of exactly 480 km (2 * 240)
        bus = Bus(
            id="bus-exact",
            operator="test-operator",
            origin="Origin",
            destination="B",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=220)
        # Origin to B is 220 km, exactly one battery capacity
        
        min_charges = calculate_min_charges(bus, simple_route, params)
        
        # 220 km / 220 km = 1.0 -> ceil = 1 segment -> 0 charges
        assert min_charges == 0
    
    def test_just_over_battery_capacity(self, simple_route):
        """Test route just over battery capacity."""
        bus = Bus(
            id="bus-over",
            operator="test-operator",
            origin="Origin",
            destination="B",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=200)
        # Origin to B is 220 km, just over 200 km
        
        min_charges = calculate_min_charges(bus, simple_route, params)
        
        # 220 km / 200 km = 1.1 -> ceil = 2 segments -> 1 charge
        assert min_charges == 1
    
    def test_very_long_route(self, long_route):
        """Test very long route with small battery."""
        bus = Bus(
            id="bus-long",
            operator="test-operator",
            origin="Bengaluru",
            destination="Kochi",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=150)
        # 540 km / 150 km = 3.6 -> ceil = 4 segments -> 3 charges
        
        min_charges = calculate_min_charges(bus, long_route, params)
        
        assert min_charges == 3
    
    def test_min_charges_never_negative(self, simple_route):
        """Test that minimum charges is never negative."""
        short_bus = Bus(
            id="bus-short",
            operator="test-operator",
            origin="Origin",
            destination="A",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=500)
        min_charges = calculate_min_charges(short_bus, simple_route, params)
        
        assert min_charges >= 0


# ============================================================================
# generate_charging_plans Tests
# ============================================================================

class TestGenerateChargingPlans:
    """Tests for generate_charging_plans function."""
    
    def test_generate_plans_for_simple_route(self, simple_bus, simple_route, standard_params):
        """Test generating plans for a simple route."""
        plans = generate_charging_plans(simple_bus, simple_route, standard_params)
        
        # Should generate multiple plans
        assert len(plans) > 0
        
        # All plans should be ChargingPlan objects
        assert all(isinstance(plan, ChargingPlan) for plan in plans)
        
        # All plans should have correct bus_id
        assert all(plan.bus_id == "bus-01" for plan in plans)
    
    def test_plans_include_minimum_charges(self, simple_bus, simple_route, standard_params):
        """Test that all plans include at least minimum charges."""
        min_charges = calculate_min_charges(simple_bus, simple_route, standard_params)
        plans = generate_charging_plans(simple_bus, simple_route, standard_params)
        
        # All plans should have at least min_charges stations
        assert all(len(plan.stations) >= min_charges for plan in plans)
    
    def test_plans_for_long_route(self, long_route_bus, long_route, standard_params):
        """Test generating plans for a long route requiring multiple charges."""
        plans = generate_charging_plans(long_route_bus, long_route, standard_params)
        
        # Should generate multiple plans
        assert len(plans) > 0
        
        # Minimum charges for 540 km with 240 km battery is 2
        min_charges = calculate_min_charges(long_route_bus, long_route, standard_params)
        assert min_charges == 2
        
        # All plans should have at least 2 stations
        assert all(len(plan.stations) >= 2 for plan in plans)
    
    def test_plans_include_all_combinations(self, long_route_bus, long_route, standard_params):
        """Test that plans include all valid combinations."""
        plans = generate_charging_plans(long_route_bus, long_route, standard_params)
        
        # For 4 stations with min 2 charges:
        # - 2 stations: C(4,2) = 6 combinations
        # - 3 stations: C(4,3) = 4 combinations
        # - 4 stations: C(4,4) = 1 combination
        # Total: 11 plans
        assert len(plans) == 11
    
    def test_plans_maintain_route_order(self, long_route_bus, long_route, standard_params):
        """Test that stations in plans maintain route order."""
        plans = generate_charging_plans(long_route_bus, long_route, standard_params)
        
        # Get all stations in route order
        all_stations = get_stations_on_route(long_route_bus, long_route)
        
        # Check each plan maintains order
        for plan in plans:
            indices = [all_stations.index(station) for station in plan.stations]
            assert indices == sorted(indices), f"Plan {plan.stations} not in route order"
    
    def test_specific_combinations_present(self, long_route_bus, long_route, standard_params):
        """Test that specific expected combinations are present."""
        plans = generate_charging_plans(long_route_bus, long_route, standard_params)
        
        # Convert plans to sets of stations for easier checking
        plan_sets = [set(plan.stations) for plan in plans]
        
        # Check some expected combinations
        assert {"A", "B"} in plan_sets
        assert {"A", "C"} in plan_sets
        assert {"A", "D"} in plan_sets
        assert {"B", "C"} in plan_sets
        assert {"B", "D"} in plan_sets
        assert {"C", "D"} in plan_sets
        assert {"A", "B", "C"} in plan_sets
        assert {"A", "B", "D"} in plan_sets
        assert {"A", "C", "D"} in plan_sets
        assert {"B", "C", "D"} in plan_sets
        assert {"A", "B", "C", "D"} in plan_sets
    
    def test_no_duplicate_plans(self, long_route_bus, long_route, standard_params):
        """Test that no duplicate plans are generated."""
        plans = generate_charging_plans(long_route_bus, long_route, standard_params)
        
        # Convert to tuples for comparison
        plan_tuples = [tuple(plan.stations) for plan in plans]
        
        # Check no duplicates
        assert len(plan_tuples) == len(set(plan_tuples))
    
    def test_short_route_generates_minimal_plans(self, simple_route):
        """Test that short route generates appropriate plans."""
        short_bus = Bus(
            id="bus-short",
            operator="test-operator",
            origin="Origin",
            destination="A",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=240)
        plans = generate_charging_plans(short_bus, simple_route, params)
        
        # For a route that doesn't need charging (100 km < 240 km),
        # min_charges = 0, so should generate plans with 1 station
        # (range starts from max(0, min_charges) which is 0, but we need at least 1)
        # Since there's only 1 station (A) on this partial route, we get 1 plan
        assert len(plans) == 1
        assert plans[0].stations == ["A"]
    
    def test_route_with_insufficient_stations(self, simple_route):
        """Test route where minimum charges exceeds available stations."""
        # Create scenario where battery is very small
        bus = Bus(
            id="bus-small-battery",
            operator="test-operator",
            origin="Origin",
            destination="Destination",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=100)
        # 440 km / 100 km = 4.4 -> ceil = 5 segments -> 4 charges needed
        # But only 3 stations available
        
        plans = generate_charging_plans(bus, simple_route, params)
        
        # Should return a plan with all available stations
        # This plan will fail constraint validation, but generator returns it
        assert len(plans) >= 1
        assert any(len(plan.stations) == 3 for plan in plans)
    
    def test_empty_route_returns_empty_list(self, simple_route):
        """Test that route with no stations returns empty list."""
        # Create a route with no stations
        empty_route = Route(
            id="empty-route",
            origin="Start",
            destination="End",
            segments=[
                Segment(**{"from": "Start", "to": "End", "distance_km": 100})
            ],
            stations=[]
        )
        
        bus = Bus(
            id="bus-empty",
            operator="test-operator",
            origin="Start",
            destination="End",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=240)
        plans = generate_charging_plans(bus, empty_route, params)
        
        # No stations available, should return empty list
        assert len(plans) == 0
    
    def test_plans_have_correct_bus_id(self, long_route_bus, long_route, standard_params):
        """Test that all generated plans have correct bus_id."""
        plans = generate_charging_plans(long_route_bus, long_route, standard_params)
        
        assert all(plan.bus_id == "bus-BK-01" for plan in plans)
    
    def test_plans_with_different_battery_capacities(self, long_route_bus, long_route):
        """Test that different battery capacities generate different plan counts."""
        # Large battery (fewer charges needed)
        large_battery_params = Parameters(battery_capacity_km=300)
        large_battery_plans = generate_charging_plans(long_route_bus, long_route, large_battery_params)
        
        # Small battery (more charges needed)
        small_battery_params = Parameters(battery_capacity_km=150)
        small_battery_plans = generate_charging_plans(long_route_bus, long_route, small_battery_params)
        
        # Small battery should require more minimum charges
        # and thus generate fewer valid combinations (higher minimum)
        min_large = calculate_min_charges(long_route_bus, long_route, large_battery_params)
        min_small = calculate_min_charges(long_route_bus, long_route, small_battery_params)
        
        assert min_small > min_large
        # Fewer combinations when minimum is higher
        assert len(small_battery_plans) < len(large_battery_plans)


# ============================================================================
# Integration Tests
# ============================================================================

class TestPlanGeneratorIntegration:
    """Integration tests for the plan generator."""
    
    def test_realistic_scenario_bengaluru_kochi(self, long_route_bus, long_route, standard_params):
        """Test realistic Bengaluru to Kochi scenario."""
        # This is the main scenario from the requirements
        plans = generate_charging_plans(long_route_bus, long_route, standard_params)
        
        # Verify we get expected number of plans
        assert len(plans) == 11
        
        # Verify minimum charges
        min_charges = calculate_min_charges(long_route_bus, long_route, standard_params)
        assert min_charges == 2
        
        # Verify all plans have at least 2 stations
        assert all(len(plan.stations) >= 2 for plan in plans)
        
        # Verify specific useful plans exist
        plan_sets = [set(plan.stations) for plan in plans]
        assert {"A", "C"} in plan_sets  # Skip B
        assert {"B", "D"} in plan_sets  # Skip A and C
        assert {"A", "B", "C", "D"} in plan_sets  # Use all stations
    
    def test_edge_case_exact_capacity_boundary(self):
        """Test edge case where distance exactly matches battery capacity."""
        route = Route(
            id="exact-route",
            origin="Start",
            destination="End",
            segments=[
                Segment(**{"from": "Start", "to": "Mid", "distance_km": 240}),
                Segment(**{"from": "Mid", "to": "End", "distance_km": 240}),
            ],
            stations=[
                Station(id="Mid", name="Mid", num_chargers=1),
            ]
        )
        
        bus = Bus(
            id="bus-exact",
            operator="test-operator",
            origin="Start",
            destination="End",
            departure_time="10:00"
        )
        
        params = Parameters(battery_capacity_km=240)
        plans = generate_charging_plans(bus, route, params)
        
        # Should generate plan with the middle station
        assert len(plans) >= 1
        assert any(plan.stations == ["Mid"] for plan in plans)
    
    def test_multiple_buses_same_route(self, long_route, standard_params):
        """Test generating plans for multiple buses on same route."""
        bus1 = Bus(
            id="bus-01",
            operator="kpn",
            origin="Bengaluru",
            destination="Kochi",
            departure_time="19:00"
        )
        
        bus2 = Bus(
            id="bus-02",
            operator="ksrtc",
            origin="Bengaluru",
            destination="Kochi",
            departure_time="20:00"
        )
        
        plans1 = generate_charging_plans(bus1, long_route, standard_params)
        plans2 = generate_charging_plans(bus2, long_route, standard_params)
        
        # Both should generate same number of plans
        assert len(plans1) == len(plans2)
        
        # But with different bus IDs
        assert all(plan.bus_id == "bus-01" for plan in plans1)
        assert all(plan.bus_id == "bus-02" for plan in plans2)
        
        # Station combinations should be the same
        stations1 = [set(plan.stations) for plan in plans1]
        stations2 = [set(plan.stations) for plan in plans2]
        assert sorted([sorted(s) for s in stations1]) == sorted([sorted(s) for s in stations2])
