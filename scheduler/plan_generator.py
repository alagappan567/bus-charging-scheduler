"""
Charging plan generation for the Bus Charging Scheduler.

This module generates all valid charging station combinations for buses,
ensuring they satisfy minimum charging requirements based on route distance
and battery capacity.
"""

from __future__ import annotations

import math
import itertools
from typing import List
from scheduler.models import Bus, Route, Parameters, ChargingPlan


def get_stations_on_route(bus: Bus, route: Route) -> List[str]:
    """Return the station IDs available on the bus's route in travel order.

    Delegates to :meth:`Route.get_stations_on_route` using the bus's
    ``origin`` and ``destination`` as the endpoints.

    Args:
        bus: The bus whose route we are querying.
        route: The route object containing station and segment data.

    Returns:
        Ordered list of station IDs between the bus's origin and
        destination.  The order reflects the bus's actual travel
        direction (reversed for Kochi → Bengaluru buses).

    Raises:
        ValueError: If the bus's origin or destination is not found on
            the route.
    """
    return route.get_stations_on_route(bus.origin, bus.destination)


def calculate_min_charges(bus: Bus, route: Route, params: Parameters) -> int:
    """Calculate the minimum number of charging stops a bus needs.

    A bus starts with a full battery, so the number of charges required
    is determined by how many full-battery lengths fit into the total
    journey distance.

    Formula::

        min_charges = max(0, ceil(total_distance / battery_capacity) - 1)

    The ``- 1`` accounts for the initial full charge at departure.

    Args:
        bus: The bus with origin and destination.
        route: The route with distance information.
        params: Simulation parameters including battery capacity.

    Returns:
        Minimum number of charging stops required (≥ 0).

    Raises:
        ValueError: If the bus's origin or destination is not found on
            the route.

    Example:
        - Total distance: 540 km, battery capacity: 240 km
        - ``ceil(540 / 240) - 1 = ceil(2.25) - 1 = 3 - 1 = 2``
        - The bus needs at least **2** charging stops.
    """
    total_distance = route.get_distance(bus.origin, bus.destination)
    battery_capacity = params.battery_capacity_km

    # ceil(distance / capacity) gives the number of full-battery segments
    # needed; subtract 1 because the bus starts with a full battery
    min_charges = math.ceil(total_distance / battery_capacity) - 1

    # Clamp to 0 for very short routes that need no intermediate charging
    return max(0, min_charges)


def generate_charging_plans(bus: Bus, route: Route, params: Parameters) -> List[ChargingPlan]:
    """Generate all candidate charging station combinations for a bus.

    Produces every combination of stations (from the minimum required
    count up to all available stations) that could potentially satisfy
    the range constraint.  The constraint system performs the definitive
    range check; this function only ensures the *count* is sufficient.

    Because :func:`itertools.combinations` preserves the input order,
    all generated plans automatically have stations in the bus's travel
    order — satisfying the route-order constraint by construction.

    Args:
        bus: The bus to generate plans for.
        route: The route with station and distance data.
        params: Simulation parameters including battery capacity.

    Returns:
        List of :class:`ChargingPlan` objects.  Each plan is a distinct
        combination of charging stations.  Returns an empty list if
        there are no stations on the bus's route.

    Raises:
        ValueError: If the bus's origin or destination is not found on
            the route.

    Example:
        For stations ``[A, B, C, D]`` with ``min_charges = 2``::

            Plans of length 2: [A,B], [A,C], [A,D], [B,C], [B,D], [C,D]
            Plans of length 3: [A,B,C], [A,B,D], [A,C,D], [B,C,D]
            Plans of length 4: [A,B,C,D]
    """
    # Retrieve stations in the bus's actual travel order
    stations_on_route = get_stations_on_route(bus, route)

    # No stations means no plans can be generated
    if not stations_on_route:
        return []

    min_charges = calculate_min_charges(bus, route, params)

    # Edge case: if the minimum exceeds available stations, return the
    # only possible plan (all stations).  The constraint system will
    # report a proper error if this plan is still invalid.
    if min_charges > len(stations_on_route):
        return [ChargingPlan(bus_id=bus.id, stations=stations_on_route)]

    # ChargingPlan requires at least one station, so the lower bound is 1
    start_charges = max(1, min_charges)

    plans: List[ChargingPlan] = []
    for num_charges in range(start_charges, len(stations_on_route) + 1):
        # itertools.combinations yields tuples in the order of the input
        # list, so station order is preserved automatically — no need for
        # an explicit sort or route-order check here
        for combo in itertools.combinations(stations_on_route, num_charges):
            plans.append(ChargingPlan(bus_id=bus.id, stations=list(combo)))

    return plans
