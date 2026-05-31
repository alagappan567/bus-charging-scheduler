"""
Unit tests for data models.

Tests validation rules, helper methods, and model relationships.
"""

import pytest
from datetime import datetime
from scheduler.models import (
    Segment, Station, Route, Bus, Parameters, Weights,
    Scenario, ChargingPlan, ChargingStop, BusTimeline,
    SimulationResult, StationQueueEntry
)


class TestSegment:
    """Tests for Segment model."""
    
    def test_valid_segment(self):
        """Test creating a valid segment."""
        segment = Segment(**{
            "from": "A",
            "to": "B",
            "distance_km": 100.0
        })
        assert segment.from_location == "A"
        assert segment.to_location == "B"
        assert segment.distance_km == 100.0
    
    def test_negative_distance_raises_error(self):
        """Test that negative distance raises validation error."""
        with pytest.raises(ValueError):
            Segment(**{
                "from": "A",
                "to": "B",
                "distance_km": -10.0
            })
    
    def test_zero_distance_raises_error(self):
        """Test that zero distance raises validation error."""
        with pytest.raises(ValueError):
            Segment(**{
                "from": "A",
                "to": "B",
                "distance_km": 0.0
            })


class TestStation:
    """Tests for Station model."""
    
    def test_valid_station(self):
        """Test creating a valid station."""
        station = Station(
            id="A",
            name="Station A",
            num_chargers=2
        )
        assert station.id == "A"
        assert station.name == "Station A"
        assert station.num_chargers == 2
    
    def test_zero_chargers_raises_error(self):
        """Test that zero chargers raises validation error."""
        with pytest.raises(ValueError):
            Station(id="A", name="Station A", num_chargers=0)
    
    def test_negative_chargers_raises_error(self):
        """Test that negative chargers raises validation error."""
        with pytest.raises(ValueError):
            Station(id="A", name="Station A", num_chargers=-1)


class TestRoute:
    """Tests for Route model and helper methods."""
    
    def test_valid_route(self):
        """Test creating a valid route."""
        route = Route(
            id="test-route",
            origin="Start",
            destination="End",
            segments=[
                Segment(**{"from": "Start", "to": "Mid", "distance_km": 50}),
                Segment(**{"from": "Mid", "to": "End", "distance_km": 50})
            ],
            stations=[
                Station(id="mid", name="Mid", num_chargers=1)
            ]
        )
        assert route.id == "test-route"
        assert route.origin == "Start"
        assert route.destination == "End"
        assert len(route.segments) == 2
    
    def test_discontinuous_segments_raises_error(self):
        """Test that discontinuous segments raise validation error."""
        with pytest.raises(ValueError, match="Segment 0 ends at"):
            Route(
                id="test-route",
                origin="Start",
                destination="End",
                segments=[
                    Segment(**{"from": "Start", "to": "Mid1", "distance_km": 50}),
                    Segment(**{"from": "Mid2", "to": "End", "distance_km": 50})
                ],
                stations=[]
            )
    
    def test_get_distance(self):
        """Test get_distance helper method."""
        route = Route(
            id="test-route",
            origin="A",
            destination="D",
            segments=[
                Segment(**{"from": "A", "to": "B", "distance_km": 100}),
                Segment(**{"from": "B", "to": "C", "distance_km": 120}),
                Segment(**{"from": "C", "to": "D", "distance_km": 100})
            ],
            stations=[
                Station(id="b", name="B", num_chargers=1),
                Station(id="c", name="C", num_chargers=1)
            ]
        )
        
        # Test distance from A to C
        assert route.get_distance("A", "C") == 220.0
        
        # Test distance from B to D
        assert route.get_distance("B", "D") == 220.0
        
        # Test single segment
        assert route.get_distance("A", "B") == 100.0
    
    def test_get_stations_on_route(self):
        """Test get_stations_on_route helper method."""
        route = Route(
            id="test-route",
            origin="A",
            destination="D",
            segments=[
                Segment(**{"from": "A", "to": "B", "distance_km": 100}),
                Segment(**{"from": "B", "to": "C", "distance_km": 120}),
                Segment(**{"from": "C", "to": "D", "distance_km": 100})
            ],
            stations=[
                Station(id="B", name="Station B", num_chargers=1),
                Station(id="C", name="Station C", num_chargers=1)
            ]
        )
        
        # Test getting stations between A and D
        stations = route.get_stations_on_route("A", "D")
        assert stations == ["B", "C"]
        
        # Test getting stations between A and C
        stations = route.get_stations_on_route("A", "C")
        assert stations == ["B", "C"]


class TestBus:
    """Tests for Bus model."""
    
    def test_valid_bus(self):
        """Test creating a valid bus."""
        bus = Bus(
            id="bus-01",
            operator="kpn",
            origin="A",
            destination="B",
            departure_time="19:00"
        )
        assert bus.id == "bus-01"
        assert bus.operator == "kpn"
        assert bus.departure_time == "19:00"
    
    def test_invalid_time_format_raises_error(self):
        """Test that invalid time format raises validation error."""
        with pytest.raises(ValueError, match="HH:MM format"):
            Bus(
                id="bus-01",
                operator="kpn",
                origin="A",
                destination="B",
                departure_time="7pm"
            )
    
    def test_get_departure_datetime(self):
        """Test get_departure_datetime helper method."""
        bus = Bus(
            id="bus-01",
            operator="kpn",
            origin="A",
            destination="B",
            departure_time="19:00"
        )
        base_date = datetime(2024, 1, 1)
        dt = bus.get_departure_datetime(base_date)
        assert dt.hour == 19
        assert dt.minute == 0
        assert dt.date() == base_date.date()


class TestParameters:
    """Tests for Parameters model."""
    
    def test_default_parameters(self):
        """Test default parameter values."""
        params = Parameters()
        assert params.battery_capacity_km == 240.0
        assert params.charge_duration_minutes == 25
        assert params.speed_kmh == 60.0
    
    def test_custom_parameters(self):
        """Test custom parameter values."""
        params = Parameters(
            battery_capacity_km=300.0,
            charge_duration_minutes=30,
            speed_kmh=80.0
        )
        assert params.battery_capacity_km == 300.0
        assert params.charge_duration_minutes == 30
        assert params.speed_kmh == 80.0
    
    def test_negative_values_raise_error(self):
        """Test that negative values raise validation errors."""
        with pytest.raises(ValueError):
            Parameters(battery_capacity_km=-100.0)
        
        with pytest.raises(ValueError):
            Parameters(charge_duration_minutes=-10)
        
        with pytest.raises(ValueError):
            Parameters(speed_kmh=-60.0)


class TestWeights:
    """Tests for Weights model."""
    
    def test_default_weights(self):
        """Test default weight values."""
        weights = Weights()
        assert weights.individual == 1.0
        assert weights.operator == 1.0
        assert weights.overall == 1.0
    
    def test_custom_weights(self):
        """Test custom weight values."""
        weights = Weights(
            individual=2.0,
            operator=0.5,
            overall=1.5
        )
        assert weights.individual == 2.0
        assert weights.operator == 0.5
        assert weights.overall == 1.5
    
    def test_negative_weights_raise_error(self):
        """Test that negative weights raise validation errors."""
        with pytest.raises(ValueError):
            Weights(individual=-1.0)


class TestScenario:
    """Tests for Scenario model."""
    
    def test_valid_scenario(self):
        """Test creating a valid scenario."""
        route = Route(
            id="test-route",
            origin="A",
            destination="B",
            segments=[
                Segment(**{"from": "A", "to": "B", "distance_km": 100})
            ],
            stations=[]
        )
        
        bus = Bus(
            id="bus-01",
            operator="kpn",
            origin="A",
            destination="B",
            departure_time="19:00"
        )
        
        scenario = Scenario(
            name="Test Scenario",
            route=route,
            buses=[bus],
            parameters=Parameters(),
            weights=Weights()
        )
        
        assert scenario.name == "Test Scenario"
        assert len(scenario.buses) == 1
    
    def test_bus_with_invalid_origin_raises_error(self):
        """Test that bus with invalid origin raises validation error."""
        route = Route(
            id="test-route",
            origin="A",
            destination="B",
            segments=[
                Segment(**{"from": "A", "to": "B", "distance_km": 100})
            ],
            stations=[]
        )
        
        bus = Bus(
            id="bus-01",
            operator="kpn",
            origin="C",  # Invalid origin
            destination="B",
            departure_time="19:00"
        )
        
        with pytest.raises(ValueError, match="not on route"):
            Scenario(
                name="Test Scenario",
                route=route,
                buses=[bus]
            )
    
    def test_get_bus(self):
        """Test get_bus helper method."""
        route = Route(
            id="test-route",
            origin="A",
            destination="B",
            segments=[
                Segment(**{"from": "A", "to": "B", "distance_km": 100})
            ],
            stations=[]
        )
        
        bus1 = Bus(id="bus-01", operator="kpn", origin="A", destination="B", departure_time="19:00")
        bus2 = Bus(id="bus-02", operator="ksrtc", origin="A", destination="B", departure_time="20:00")
        
        scenario = Scenario(
            name="Test Scenario",
            route=route,
            buses=[bus1, bus2]
        )
        
        assert scenario.get_bus("bus-01") == bus1
        assert scenario.get_bus("bus-02") == bus2
        assert scenario.get_bus("bus-03") is None


class TestChargingPlan:
    """Tests for ChargingPlan model."""
    
    def test_valid_charging_plan(self):
        """Test creating a valid charging plan."""
        plan = ChargingPlan(
            bus_id="bus-01",
            stations=["A", "B", "C"]
        )
        assert plan.bus_id == "bus-01"
        assert len(plan.stations) == 3
    
    def test_empty_stations_raises_error(self):
        """Test that empty stations list raises validation error."""
        with pytest.raises(ValueError, match="at least one station"):
            ChargingPlan(bus_id="bus-01", stations=[])


class TestSimulationResult:
    """Tests for SimulationResult model."""
    
    def test_empty_simulation_result(self):
        """Test creating an empty simulation result."""
        result = SimulationResult()
        assert len(result.bus_timelines) == 0
        assert len(result.station_queues) == 0
    
    def test_get_timeline(self):
        """Test get_timeline helper method."""
        timeline = BusTimeline(
            bus_id="bus-01",
            operator="kpn",
            direction="A→B",
            departure_time="19:00",
            arrival_time="21:00",
            total_wait_minutes=0
        )
        
        result = SimulationResult(
            bus_timelines={"bus-01": timeline}
        )
        
        assert result.get_timeline("bus-01") == timeline
        assert result.get_timeline("bus-02") is None
    
    def test_get_station_queue(self):
        """Test get_station_queue helper method."""
        entry = StationQueueEntry(
            bus_id="bus-01",
            arrival_time="20:00",
            charge_start="20:00",
            charge_end="20:25"
        )
        
        result = SimulationResult(
            station_queues={"A": [entry]}
        )
        
        assert result.get_station_queue("A") == [entry]
        assert result.get_station_queue("B") == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestScenarioFiles:
    """Tests for scenario JSON files."""
    
    def test_all_scenarios_load_correctly(self):
        """Test that all 5 scenario files load and validate correctly with Pydantic."""
        import json
        from pathlib import Path
        
        scenarios_dir = Path("scenarios")
        scenario_files = [
            "scenario1.json",
            "scenario2.json",
            "scenario3.json",
            "scenario4.json",
            "scenario5.json"
        ]
        
        loaded_scenarios = []
        
        for scenario_file in scenario_files:
            scenario_path = scenarios_dir / scenario_file
            
            # Verify file exists
            assert scenario_path.exists(), f"{scenario_file} not found"
            
            # Load JSON
            with open(scenario_path, 'r') as f:
                data = json.load(f)
            
            # Validate with Pydantic - this will raise ValidationError if invalid
            scenario = Scenario(**data)
            
            # Verify basic structure
            assert scenario.name, f"{scenario_file}: Scenario must have a name"
            assert scenario.route, f"{scenario_file}: Scenario must have a route"
            assert scenario.buses, f"{scenario_file}: Scenario must have buses"
            assert len(scenario.buses) > 0, f"{scenario_file}: Scenario must have at least one bus"
            
            # Verify route structure
            assert scenario.route.id, f"{scenario_file}: Route must have an ID"
            assert scenario.route.origin, f"{scenario_file}: Route must have an origin"
            assert scenario.route.destination, f"{scenario_file}: Route must have a destination"
            assert len(scenario.route.segments) > 0, f"{scenario_file}: Route must have segments"
            assert len(scenario.route.stations) > 0, f"{scenario_file}: Route must have stations"
            
            # Verify route continuity (already validated by Pydantic, but double-check)
            assert scenario.route.segments[0].from_location == scenario.route.origin
            assert scenario.route.segments[-1].to_location == scenario.route.destination
            
            # Verify all buses have valid origins and destinations on the route
            valid_locations = {scenario.route.origin, scenario.route.destination}
            for segment in scenario.route.segments:
                valid_locations.add(segment.to_location)
            
            for bus in scenario.buses:
                assert bus.origin in valid_locations, \
                    f"{scenario_file}: Bus {bus.id} origin {bus.origin} not on route"
                assert bus.destination in valid_locations, \
                    f"{scenario_file}: Bus {bus.id} destination {bus.destination} not on route"
                assert bus.operator, f"{scenario_file}: Bus {bus.id} must have an operator"
                assert bus.departure_time, f"{scenario_file}: Bus {bus.id} must have a departure time"
            
            # Verify parameters are valid
            assert scenario.parameters.battery_capacity_km > 0
            assert scenario.parameters.charge_duration_minutes > 0
            assert scenario.parameters.speed_kmh > 0
            
            # Verify weights are non-negative
            assert scenario.weights.individual >= 0
            assert scenario.weights.operator >= 0
            assert scenario.weights.overall >= 0
            
            # Verify all stations have at least one charger
            for station in scenario.route.stations:
                assert station.num_chargers >= 1, \
                    f"{scenario_file}: Station {station.id} must have at least one charger"
            
            # Calculate total distance
            total_distance = scenario.route.get_distance(
                scenario.route.origin,
                scenario.route.destination
            )
            assert total_distance > 0, f"{scenario_file}: Total route distance must be positive"
            
            loaded_scenarios.append({
                'file': scenario_file,
                'name': scenario.name,
                'buses': len(scenario.buses),
                'stations': len(scenario.route.stations),
                'distance_km': total_distance
            })
            
            print(f"✓ {scenario_file}: {scenario.name}")
            print(f"  - {len(scenario.buses)} buses")
            print(f"  - {len(scenario.route.stations)} stations")
            print(f"  - {total_distance} km total distance")
        
        # Verify we loaded all 5 scenarios
        assert len(loaded_scenarios) == 5, f"Expected 5 scenarios, loaded {len(loaded_scenarios)}"
        
        print(f"\n✓ All {len(loaded_scenarios)} scenarios loaded and validated successfully!")
    
    def test_scenario1_specific_validation(self):
        """Test specific validation for scenario1.json."""
        import json
        from pathlib import Path
        
        scenario_path = Path("scenarios/scenario1.json")
        with open(scenario_path, 'r') as f:
            data = json.load(f)
        
        scenario = Scenario(**data)
        
        # Scenario 1 specific checks
        assert scenario.name == "Scenario 1 - Even Spacing"
        assert scenario.route.id == "bengaluru-kochi"
        assert scenario.route.origin == "Bengaluru"
        assert scenario.route.destination == "Kochi"
        
        # Verify exact route structure for scenario 1
        assert len(scenario.route.segments) == 5
        assert len(scenario.route.stations) == 4
        
        # Verify total distance is 540 km
        total_distance = scenario.route.get_distance(
            scenario.route.origin,
            scenario.route.destination
        )
        assert total_distance == 540.0, f"Expected 540 km, got {total_distance} km"
        
        # Verify default parameters
        assert scenario.parameters.battery_capacity_km == 240
        assert scenario.parameters.charge_duration_minutes == 25
        assert scenario.parameters.speed_kmh == 60
        
        # Verify default weights
        assert scenario.weights.individual == 1.0
        assert scenario.weights.operator == 1.0
        assert scenario.weights.overall == 1.0
