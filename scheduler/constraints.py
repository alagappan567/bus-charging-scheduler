"""
Constraint system for the Bus Charging Scheduler.

This module defines the constraint validation framework and implements
hard constraints that must be satisfied by all charging plans.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List
from scheduler.models import ChargingPlan, Scenario


class Constraint(ABC):
    """Abstract base class for all hard constraints.

    A constraint is a boolean rule that a charging plan must satisfy.
    If any constraint is violated the plan is considered invalid and
    will be discarded before simulation.

    Subclasses must implement :meth:`is_valid` and
    :meth:`get_violation_message`.
    """

    @abstractmethod
    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Check whether a charging plan satisfies this constraint.

        Args:
            plan: The charging plan to validate.
            scenario: The scenario context (route, buses, parameters).

        Returns:
            ``True`` if the plan satisfies the constraint, ``False``
            otherwise.
        """
        pass

    @abstractmethod
    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        """Return a human-readable description of why the constraint failed.

        This is only called when :meth:`is_valid` returns ``False``.

        Args:
            plan: The charging plan that violated the constraint.
            scenario: The scenario context.

        Returns:
            A descriptive error message suitable for logging or display.
        """
        pass


class ConstraintValidator:
    """Validates charging plans against a registered set of constraints.

    Runs every registered constraint in order and short-circuits on the
    first failure for :meth:`is_valid`, or collects all failures for
    :meth:`get_violations`.

    Attributes:
        constraints: The list of :class:`Constraint` objects to apply.
    """

    def __init__(self, constraints: List[Constraint]) -> None:
        """Initialise the validator with a list of constraints.

        Args:
            constraints: Ordered list of constraint objects to validate
                against.  Constraints are evaluated in list order.
        """
        self.constraints = constraints

    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Check whether a plan satisfies *all* registered constraints.

        Short-circuits on the first failure for efficiency.

        Args:
            plan: The charging plan to validate.
            scenario: The scenario context.

        Returns:
            ``True`` only if every constraint passes, ``False`` as soon
            as any constraint fails.
        """
        for constraint in self.constraints:
            if not constraint.is_valid(plan, scenario):
                return False
        return True

    def get_violations(self, plan: ChargingPlan, scenario: Scenario) -> List[str]:
        """Collect violation messages for every failed constraint.

        Unlike :meth:`is_valid`, this method does *not* short-circuit —
        it evaluates all constraints so that all violations are reported.

        Args:
            plan: The charging plan to validate.
            scenario: The scenario context.

        Returns:
            List of violation messages.  Empty list means the plan is
            fully valid.
        """
        violations = []
        for constraint in self.constraints:
            if not constraint.is_valid(plan, scenario):
                violations.append(constraint.get_violation_message(plan, scenario))
        return violations


class RangeConstraint(Constraint):
    """Ensures battery capacity is never exceeded between consecutive charges.

    Checks three conditions in order:

    1. Distance from the bus's **origin** to the **first** charging station
       does not exceed battery capacity.
    2. Distance between each pair of **consecutive** charging stations does
       not exceed battery capacity.
    3. Distance from the **last** charging station to the bus's
       **destination** does not exceed battery capacity.

    All three legs must be within range for the plan to be valid.
    """

    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Check whether the plan respects battery range limits.

        Args:
            plan: The charging plan to validate.
            scenario: The scenario context.

        Returns:
            ``True`` if every leg of the journey is within battery range.
        """
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return False

        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km

        # Station IDs double as location names in the route graph
        # (e.g. "A", "B", "C", "D" are both station IDs and segment endpoints)
        station_locations = plan.stations

        # Guard: all station IDs in the plan must exist in the route
        valid_station_ids = {station.id for station in route.stations}
        if not all(sid in valid_station_ids for sid in station_locations):
            return False

        try:
            # Leg 1: origin → first charging station
            first_station = station_locations[0]
            distance_to_first = route.get_distance(bus.origin, first_station)
            if distance_to_first > battery_capacity:
                return False

            # Leg 2: each consecutive pair of charging stations
            for i in range(len(station_locations) - 1):
                distance = route.get_distance(station_locations[i], station_locations[i + 1])
                if distance > battery_capacity:
                    return False

            # Leg 3: last charging station → destination
            last_station = station_locations[-1]
            distance_to_dest = route.get_distance(last_station, bus.destination)
            if distance_to_dest > battery_capacity:
                return False

            return True

        except ValueError:
            # get_distance raises ValueError for unknown or out-of-order locations
            return False

    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        """Return a descriptive message identifying which leg exceeds range.

        Args:
            plan: The charging plan that violated the constraint.
            scenario: The scenario context.

        Returns:
            A message naming the offending leg and the distances involved.
        """
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return f"Bus {plan.bus_id} not found in scenario"

        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km
        station_locations = plan.stations

        # Report any unknown station IDs before attempting distance lookups
        valid_station_ids = {station.id for station in route.stations}
        invalid_ids = [sid for sid in station_locations if sid not in valid_station_ids]
        if invalid_ids:
            return f"Bus {plan.bus_id}: Invalid station IDs: {invalid_ids}"

        try:
            # Identify the specific leg that violates the range constraint
            first_station = station_locations[0]
            distance_to_first = route.get_distance(bus.origin, first_station)
            if distance_to_first > battery_capacity:
                return (
                    f"Bus {plan.bus_id}: Distance from {bus.origin} to {first_station} "
                    f"({distance_to_first:.1f} km) exceeds battery capacity "
                    f"({battery_capacity:.1f} km)"
                )

            for i in range(len(station_locations) - 1):
                distance = route.get_distance(station_locations[i], station_locations[i + 1])
                if distance > battery_capacity:
                    return (
                        f"Bus {plan.bus_id}: Distance from {station_locations[i]} to "
                        f"{station_locations[i + 1]} ({distance:.1f} km) exceeds battery "
                        f"capacity ({battery_capacity:.1f} km)"
                    )

            last_station = station_locations[-1]
            distance_to_dest = route.get_distance(last_station, bus.destination)
            if distance_to_dest > battery_capacity:
                return (
                    f"Bus {plan.bus_id}: Distance from {last_station} to {bus.destination} "
                    f"({distance_to_dest:.1f} km) exceeds battery capacity "
                    f"({battery_capacity:.1f} km)"
                )

            return f"Bus {plan.bus_id}: Range constraint violated"

        except ValueError as e:
            return f"Bus {plan.bus_id}: {str(e)}"


class RouteOrderConstraint(Constraint):
    """Ensures charging stations are visited in route order (no backtracking).

    Obtains the canonical travel-order list of stations for the bus's
    route and verifies that the plan's station sequence is a
    strictly-increasing subsequence of that list.

    A bus travelling Kochi → Bengaluru must visit stations in the
    reverse geographic order (D, C, B, A), which
    :meth:`Route.get_stations_on_route` already returns in the correct
    travel order for that direction.
    """

    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Check whether stations are visited in the bus's travel order.

        Args:
            plan: The charging plan to validate.
            scenario: The scenario context.

        Returns:
            ``True`` if the plan's stations appear in the same order as
            the route's station sequence for this bus.
        """
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return False

        route = scenario.route

        # Retrieve stations in the bus's actual travel order
        try:
            route_stations = route.get_stations_on_route(bus.origin, bus.destination)
        except ValueError:
            return False

        # Map each plan station to its position in the travel-order list
        plan_indices: List[int] = []
        for station_id in plan.stations:
            if station_id not in route_stations:
                return False
            plan_indices.append(route_stations.index(station_id))

        # Indices must be strictly increasing — no revisiting or backtracking
        return plan_indices == sorted(plan_indices)

    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        """Return a message describing the out-of-order stations.

        Args:
            plan: The charging plan that violated the constraint.
            scenario: The scenario context.

        Returns:
            A message showing the plan's station order vs. the expected
            travel order.
        """
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return f"Bus {plan.bus_id} not found in scenario"

        route = scenario.route

        try:
            route_stations = route.get_stations_on_route(bus.origin, bus.destination)

            plan_indices: List[int] = []
            for station_id in plan.stations:
                if station_id not in route_stations:
                    return f"Bus {plan.bus_id}: Station {station_id} is not on the route"
                plan_indices.append(route_stations.index(station_id))

            if plan_indices != sorted(plan_indices):
                return (
                    f"Bus {plan.bus_id}: Stations {plan.stations} are not in travel order. "
                    f"Expected order: {route_stations}"
                )

            return f"Bus {plan.bus_id}: Route order constraint violated"

        except ValueError as e:
            return f"Bus {plan.bus_id}: {str(e)}"


class CompletionConstraint(Constraint):
    """Ensures the bus can complete its journey and reach the destination.

    Verifies three conditions:

    1. The charging plan is non-empty (at least one stop).
    2. All station IDs in the plan are valid and lie on the bus's route.
    3. The bus can reach its destination from the last charging station
       within battery capacity.
    """

    def is_valid(self, plan: ChargingPlan, scenario: Scenario) -> bool:
        """Check whether the bus can complete its journey with this plan.

        Args:
            plan: The charging plan to validate.
            scenario: The scenario context.

        Returns:
            ``True`` if the bus can reach its destination after the last
            charging stop.
        """
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return False

        # An empty plan can never complete the journey
        if not plan.stations:
            return False

        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km
        station_locations = plan.stations

        # Guard: all station IDs must be known
        valid_station_ids = {station.id for station in route.stations}
        if not all(sid in valid_station_ids for sid in station_locations):
            return False

        try:
            # Check that the final leg (last station → destination) is within range
            last_station = station_locations[-1]
            distance_to_dest = route.get_distance(last_station, bus.destination)
            if distance_to_dest > battery_capacity:
                return False

            # All stations must lie on the bus's actual route segment
            route_stations = route.get_stations_on_route(bus.origin, bus.destination)
            for station_id in plan.stations:
                if station_id not in route_stations:
                    return False

            return True

        except ValueError:
            # get_distance or get_stations_on_route raised ValueError
            return False

    def get_violation_message(self, plan: ChargingPlan, scenario: Scenario) -> str:
        """Return a message describing why the journey cannot be completed.

        Args:
            plan: The charging plan that violated the constraint.
            scenario: The scenario context.

        Returns:
            A message identifying the specific completion failure.
        """
        bus = scenario.get_bus(plan.bus_id)
        if not bus:
            return f"Bus {plan.bus_id} not found in scenario"

        if not plan.stations:
            return f"Bus {plan.bus_id}: Charging plan is empty"

        route = scenario.route
        battery_capacity = scenario.parameters.battery_capacity_km
        station_locations = plan.stations

        # Report unknown station IDs first
        valid_station_ids = {station.id for station in route.stations}
        invalid_ids = [sid for sid in station_locations if sid not in valid_station_ids]
        if invalid_ids:
            return f"Bus {plan.bus_id}: Invalid station IDs: {invalid_ids}"

        try:
            last_station = station_locations[-1]
            distance_to_dest = route.get_distance(last_station, bus.destination)

            if distance_to_dest > battery_capacity:
                return (
                    f"Bus {plan.bus_id}: Cannot reach destination {bus.destination} from "
                    f"last charging station {last_station}. Distance ({distance_to_dest:.1f} km) "
                    f"exceeds battery capacity ({battery_capacity:.1f} km)"
                )

            route_stations = route.get_stations_on_route(bus.origin, bus.destination)
            for station_id in plan.stations:
                if station_id not in route_stations:
                    return f"Bus {plan.bus_id}: Station {station_id} is not on the route"

            return f"Bus {plan.bus_id}: Completion constraint violated"

        except ValueError as e:
            return f"Bus {plan.bus_id}: {str(e)}"
