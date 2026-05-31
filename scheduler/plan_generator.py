"""
Charging plan generation for the Bus Charging Scheduler.

This module generates all valid charging station combinations for buses,
ensuring they satisfy minimum charging requirements based on route distance
and battery capacity.
"""

import math
import itertools
from typing import List
from scheduler.models import Bus, Route, Parameters, ChargingPlan


def get_stations_on_route(bus: Bus, route: Route) -> List[str]:
    """
    Get list of station IDs available on the bus's route.
    
    Args:
        bus: The bus with origin and destination
        route: The route containing stations
        
    Returns:
        List of station IDs in route order between bus origin and destination
        
    Raises:
        ValueError: If bus origin or destination not found on route
    """
    return route.get_stations_on_route(bus.origin, bus.destination)


def calculate_min_charges(bus: Bus, route: Route, params: Parameters) -> int:
    """
    Calculate minimum number of charging stops needed for a bus to complete its journey.
    
    The minimum is based on total distance and battery capacity. A bus starts with
    a full battery, so it needs to charge when the remaining distance exceeds capacity.
    
    Args:
        bus: The bus with origin and destination
        route: The route with distance information
        params: Parameters including battery capacity
        
    Returns:
        Minimum number of charging stops required
        
    Raises:
        ValueError: If bus origin or destination not found on route
        
    Example:
        - Total distance: 540 km
        - Battery capacity: 240 km
        - Bus starts with full battery (240 km)
        - After 240 km, needs first charge (300 km remaining)
        - After charge, has 240 km (60 km remaining after traveling 240 km)
        - Needs second charge to cover last 60 km
        - Minimum charges: 2
    """
    total_distance = route.get_distance(bus.origin, bus.destination)
    battery_capacity = params.battery_capacity_km
    
    # Calculate how many charges are needed
    # Bus starts with full battery, so we need ceil(distance / capacity) - 1 charges
    # Example: 540 km / 240 km = 2.25 -> ceil = 3 segments -> 2 charges needed
    min_charges = math.ceil(total_distance / battery_capacity) - 1
    
    # Ensure at least 0 charges (for very short routes)
    return max(0, min_charges)


def generate_charging_plans(bus: Bus, route: Route, params: Parameters) -> List[ChargingPlan]:
    """
    Generate all valid charging station combinations for a bus.
    
    A charging plan is valid if:
    1. It includes at least the minimum number of charges needed
    2. Stations are in route order (handled by using combinations)
    3. The plan will be validated by constraints later for range safety
    
    This function generates candidate plans that will be filtered by the
    constraint system to ensure range and route order requirements.
    
    Args:
        bus: The bus to generate plans for
        route: The route with stations
        params: Parameters including battery capacity
        
    Returns:
        List of ChargingPlan objects, each representing a valid combination
        of charging stations
        
    Raises:
        ValueError: If bus origin or destination not found on route
        
    Example:
        For a route with stations [A, B, C, D] and min_charges=2:
        - Generates all combinations of length 2, 3, and 4
        - Returns: [A,B], [A,C], [A,D], [B,C], [B,D], [C,D],
                   [A,B,C], [A,B,D], [A,C,D], [B,C,D], [A,B,C,D]
    """
    # Get all stations on the bus's route
    stations_on_route = get_stations_on_route(bus, route)
    
    # If no stations on route, return empty list
    if not stations_on_route:
        return []
    
    # Calculate minimum charges needed
    min_charges = calculate_min_charges(bus, route, params)
    
    # If minimum charges exceeds available stations, return all stations as only option
    if min_charges > len(stations_on_route):
        # This plan will likely fail constraint validation, but we return it
        # so the constraint system can provide a proper error message
        return [ChargingPlan(bus_id=bus.id, stations=stations_on_route)]
    
    # Generate all combinations from min_charges to all stations
    # Ensure we generate at least 1 station per plan (ChargingPlan requires at least one)
    plans = []
    start_charges = max(1, min_charges)  # At least 1 station required
    for num_charges in range(start_charges, len(stations_on_route) + 1):
        # Generate all combinations of this length
        for combo in itertools.combinations(stations_on_route, num_charges):
            # Create a charging plan for this combination
            # Combinations maintain the order from the input list, so stations
            # will automatically be in route order
            plans.append(ChargingPlan(bus_id=bus.id, stations=list(combo)))
    
    return plans
