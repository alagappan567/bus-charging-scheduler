"""
Constraint system for the Bus Charging Scheduler.

This module defines the constraint validation framework and implements
hard constraints that must be satisfied by all charging plans.
"""

from abc import ABC, abstractmethod
from typing import List
from scheduler.models import ChargingPlan, Scenario


class Constraint(ABC):
    """
    Abstract base class for all constraints.
    
    A constraint is a hard rule that must be satisfied by a charging plan.
    If a constraint is violated, the plan is invalid and cannot be used.
    """
    
    @abstractmethod
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """
        Check if a charging plan satisfies this constraint.
        
        Args:
            plan: The charging plan to validate
            scenario: The scenario context (route, buses, parameters)
            
        Returns:
            True if the plan satisfies the constraint, False otherwise
        """
        pass
    
    @abstractmethod
    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        """
        Get a human-readable message describing why the constraint was violated.
        
        Args:
            plan: The charging plan that violated the constraint
            scenario: The scenario context
            
        Returns:
            A descriptive error message
        """
        pass


class ConstraintValidator:
    """
    Validates charging plans against a set of constraints.
    
    This class runs all registered constraints and reports violations.
    """
    
    def __init__(self, constraints: List[Constraint]):
        """
        Initialize the validator with a list of constraints.
        
        Args:
            constraints: List of constraint objects to validate against
        """
        self.constraints = constraints
    
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """
        Check if a plan satisfies all constraints.
        
        Args:
            plan: The charging plan to validate
            scenario: The scenario context
            
        Returns:
            True if all constraints are satisfied, False otherwise
        """
        for constraint in self.constraints:
            if not constraint.is_valid(plan, scenario):
                return False
        return True
    
    def get_violations(self, plan: ChargingPlan, scenario: Scenario) -> List[str]:
        """
        Get a list of all constraint violations for a plan.
        
        Args:
            plan: The charging plan to validate
            scenario: The scenario context
            
        Returns:
            List of violation messages (empty if plan is valid)
        """
        violations = []
        for constraint in self.constraints:
            if not constraint.is_valid(plan, scenario):
                violations.append(constraint.get_violation_message(plan, scenario))
        return violations


class RangeConstraint(Constraint):
    """
    Ensures battery capacity is never exceeded between consecutive charges.
    
    This constraint verifies that:
    1. Distance from origin to first charging station ≤ battery capacity
    2. Distance between consecutive charging stations ≤ battery capacity
    3. Distance from last charging station to destination ≤ battery capacity
    """
    
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Check if the plan respects battery range limits."""
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return False
        
        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km
        
        # Station IDs in the plan are also location names in the route
        # (e.g., "A", "B", "C", "D" are both station IDs and location names)
        station_locations = plan.stations
        
        # Verify all station IDs exist
        valid_station_ids = {station.id for station in route.stations}
        if not all(sid in valid_station_ids for sid in station_locations):
            return False
        
        try:
            # Check distance from origin to first charging station
            first_station = station_locations[0]
            distance_to_first = route.get_distance(bus.origin, first_station)
            if distance_to_first > battery_capacity:
                return False
            
            # Check distance between consecutive charging stations
            for i in range(len(station_locations) - 1):
                distance = route.get_distance(station_locations[i], station_locations[i + 1])
                if distance > battery_capacity:
                    return False
            
            # Check distance from last charging station to destination
            last_station = station_locations[-1]
            distance_to_dest = route.get_distance(last_station, bus.destination)
            if distance_to_dest > battery_capacity:
                return False
            
            return True
        
        except ValueError:
            # get_distance raises ValueError if locations are invalid or out of order
            return False
    
    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        """Get a descriptive message about the range violation."""
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return f"Bus {plan.bus_id} not found in scenario"
        
        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km
        
        # Station IDs are also location names
        station_locations = plan.stations
        
        # Verify all station IDs exist
        valid_station_ids = {station.id for station in route.stations}
        invalid_ids = [sid for sid in station_locations if sid not in valid_station_ids]
        if invalid_ids:
            return f"Bus {plan.bus_id}: Invalid station IDs: {invalid_ids}"
        
        try:
            # Check which segment violates the constraint
            first_station = station_locations[0]
            distance_to_first = route.get_distance(bus.origin, first_station)
            if distance_to_first > battery_capacity:
                return (f"Bus {plan.bus_id}: Distance from {bus.origin} to {first_station} "
                       f"({distance_to_first:.1f} km) exceeds battery capacity ({battery_capacity:.1f} km)")
            
            for i in range(len(station_locations) - 1):
                distance = route.get_distance(station_locations[i], station_locations[i + 1])
                if distance > battery_capacity:
                    return (f"Bus {plan.bus_id}: Distance from {station_locations[i]} to {station_locations[i + 1]} "
                           f"({distance:.1f} km) exceeds battery capacity ({battery_capacity:.1f} km)")
            
            last_station = station_locations[-1]
            distance_to_dest = route.get_distance(last_station, bus.destination)
            if distance_to_dest > battery_capacity:
                return (f"Bus {plan.bus_id}: Distance from {last_station} to {bus.destination} "
                       f"({distance_to_dest:.1f} km) exceeds battery capacity ({battery_capacity:.1f} km)")
            
            return f"Bus {plan.bus_id}: Range constraint violated"
        
        except ValueError as e:
            return f"Bus {plan.bus_id}: {str(e)}"


class RouteOrderConstraint(Constraint):
    """
    Ensures charging stations are visited in route order (no backtracking).
    
    This constraint verifies that the stations in the charging plan appear
    in the same order as they appear on the route.
    """
    
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Check if stations are in route order."""
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return False
        
        route = scenario.route
        
        # Get all stations on the bus's route in travel order
        try:
            route_stations = route.get_stations_on_route(bus.origin, bus.destination)
        except ValueError:
            return False
        
        # Check that plan stations appear in the same order as route_stations
        plan_indices = []
        for station_id in plan.stations:
            if station_id not in route_stations:
                return False
            plan_indices.append(route_stations.index(station_id))
        
        # Indices must be strictly increasing (travel order)
        return plan_indices == sorted(plan_indices)
    
    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        """Get a descriptive message about the route order violation."""
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return f"Bus {plan.bus_id} not found in scenario"
        
        route = scenario.route
        
        try:
            route_stations = route.get_stations_on_route(bus.origin, bus.destination)
            
            plan_indices = []
            for station_id in plan.stations:
                if station_id not in route_stations:
                    return f"Bus {plan.bus_id}: Station {station_id} is not on the route"
                plan_indices.append(route_stations.index(station_id))
            
            if plan_indices != sorted(plan_indices):
                return (f"Bus {plan.bus_id}: Stations {plan.stations} are not in travel order. "
                       f"Expected order: {route_stations}")
            
            return f"Bus {plan.bus_id}: Route order constraint violated"
        
        except ValueError as e:
            return f"Bus {plan.bus_id}: {str(e)}"


class CompletionConstraint(Constraint):
    """
    Ensures the bus can complete its journey and reach the destination.
    
    This constraint verifies that:
    1. The charging plan includes at least one station
    2. The bus can reach its destination from the last charging station
    3. All stations in the plan are valid and on the route
    """
    
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Check if the bus can complete its journey with this plan."""
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return False
        
        # Plan must have at least one charging station
        if not plan.stations:
            return False
        
        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km
        
        # Station IDs are also location names
        station_locations = plan.stations
        
        # Verify all station IDs exist
        valid_station_ids = {station.id for station in route.stations}
        if not all(sid in valid_station_ids for sid in station_locations):
            return False
        
        try:
            # Verify the bus can reach destination from last charging station
            last_station = station_locations[-1]
            distance_to_dest = route.get_distance(last_station, bus.destination)
            
            # Must be able to reach destination within battery capacity
            if distance_to_dest > battery_capacity:
                return False
            
            # Verify all stations are on the route between origin and destination
            route_stations = route.get_stations_on_route(bus.origin, bus.destination)
            for station_id in plan.stations:
                if station_id not in route_stations:
                    return False
            
            return True
        
        except ValueError:
            # get_distance or get_stations_on_route raised ValueError
            return False
    
    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        """Get a descriptive message about the completion violation."""
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return f"Bus {plan.bus_id} not found in scenario"
        
        if not plan.stations:
            return f"Bus {plan.bus_id}: Charging plan is empty"
        
        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km
        
        # Station IDs are also location names
        station_locations = plan.stations
        
        # Verify all station IDs exist
        valid_station_ids = {station.id for station in route.stations}
        invalid_ids = [sid for sid in station_locations if sid not in valid_station_ids]
        if invalid_ids:
            return f"Bus {plan.bus_id}: Invalid station IDs: {invalid_ids}"
        
        try:
            last_station = station_locations[-1]
            distance_to_dest = route.get_distance(last_station, bus.destination)
            
            if distance_to_dest > battery_capacity:
                return (f"Bus {plan.bus_id}: Cannot reach destination {bus.destination} from "
                       f"last charging station {last_station}. Distance ({distance_to_dest:.1f} km) "
                       f"exceeds battery capacity ({battery_capacity:.1f} km)")
            
            route_stations = route.get_stations_on_route(bus.origin, bus.destination)
            for station_id in plan.stations:
                if station_id not in route_stations:
                    return f"Bus {plan.bus_id}: Station {station_id} is not on the route"
            
            return f"Bus {plan.bus_id}: Completion constraint violated"
        
        except ValueError as e:
            return f"Bus {plan.bus_id}: {str(e)}"
