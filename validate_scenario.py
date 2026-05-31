#!/usr/bin/env python3
"""Quick validation script for scenario files."""

import json
from scheduler.models import Scenario

def validate_scenario(filepath: str):
    """Load and validate a scenario file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    scenario = Scenario(**data)
    
    print(f"✓ Scenario loaded successfully: {scenario.name}")
    print(f"  - Buses: {len(scenario.buses)}")
    print(f"  - Stations: {len(scenario.route.stations)}")
    print(f"  - Total route distance: {scenario.route.get_distance(scenario.route.origin, scenario.route.destination)} km")
    print(f"  - Battery capacity: {scenario.parameters.battery_capacity_km} km")
    print(f"  - Charge duration: {scenario.parameters.charge_duration_minutes} minutes")
    print(f"  - Speed: {scenario.parameters.speed_kmh} km/h")
    
    # List buses
    print(f"\n  Buses:")
    for bus in scenario.buses:
        print(f"    - {bus.id} ({bus.operator}) departs at {bus.departure_time}")
    
    # List stations
    print(f"\n  Stations:")
    for station in scenario.route.stations:
        print(f"    - {station.name} ({station.id}): {station.num_chargers} charger(s)")
    
    return scenario

if __name__ == "__main__":
    validate_scenario("scenarios/scenario1.json")
