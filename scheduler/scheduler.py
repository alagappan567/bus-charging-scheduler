"""
Scheduler orchestrator for the Bus Charging Scheduler.

This module implements the main scheduling algorithm that coordinates
plan generation, constraint validation, simulation, and objective scoring
to produce optimal charging schedules for all buses.

Algorithm overview (greedy sequential assignment):

1. Generate all candidate charging plans for every bus.
2. Filter out plans that violate hard constraints.
3. Sort buses by departure time (earliest first).
4. For each bus in order:
   a. Try every valid candidate plan.
   b. Simulate the plan together with already-assigned buses.
   c. Score the simulation result using the weighted objectives.
   d. Lock in the highest-scoring plan.
5. Return the final simulation result.

The greedy approach is fast (O(buses × plans × simulation_cost)) and
produces good schedules.  It may not find the global optimum, but
earlier-departing buses get priority, which is operationally fair.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from scheduler.models import Scenario, Bus, ChargingPlan, SimulationResult
from scheduler.plan_generator import generate_charging_plans
from scheduler.constraints import (
    Constraint, ConstraintValidator,
    RangeConstraint, RouteOrderConstraint, CompletionConstraint,
)
from scheduler.objectives import (
    Objective, ObjectiveEvaluator,
    IndividualWaitObjective, OperatorFairnessObjective, OverallEfficiencyObjective,
)
from scheduler.simulator import EventSimulator


class BusScheduler:
    """Main scheduler orchestrator that coordinates all components.

    Implements a greedy sequential assignment algorithm: buses are
    processed in departure order, and for each bus the plan that
    maximises the weighted objective score (given the already-assigned
    buses) is selected and locked in.

    Attributes:
        scenario: The scenario being scheduled.
        constraints: List of hard :class:`Constraint` objects.
        constraint_validator: Validates plans against all constraints.
        objectives: List of ``(Objective, weight)`` pairs.
        objective_evaluator: Computes the weighted total score.
        assigned_plans: Plans locked in so far, keyed by ``bus_id``.
    """

    def __init__(self, scenario: Scenario) -> None:
        """Initialise the scheduler with a scenario.

        Registers all hard constraints and weighted soft objectives.

        Args:
            scenario: The scenario containing route, buses, parameters,
                and objective weights.
        """
        self.scenario = scenario

        # Hard constraints — all must pass for a plan to be considered
        self.constraints: List[Constraint] = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint(),
        ]
        self.constraint_validator = ConstraintValidator(self.constraints)

        # Soft objectives — weighted sum determines plan quality
        self.objectives: List[Tuple[Objective, float]] = [
            (IndividualWaitObjective(), scenario.weights.individual),
            (OperatorFairnessObjective(), scenario.weights.operator),
            (OverallEfficiencyObjective(), scenario.weights.overall),
        ]
        self.objective_evaluator = ObjectiveEvaluator(self.objectives)

        # Plans locked in during greedy assignment
        self.assigned_plans: Dict[str, ChargingPlan] = {}

    def schedule(self) -> SimulationResult:
        """Run the full scheduling pipeline and return the result.

        Orchestrates plan generation, constraint filtering, greedy
        assignment, and final simulation.

        Returns:
            :class:`SimulationResult` containing per-bus timelines and
            per-station charging queues.

        Raises:
            RuntimeError: If no valid plan can be found for any bus.
        """
        # Step 1: Generate candidate plans for every bus
        all_plans = self._generate_all_plans()

        # Step 2: Discard plans that violate hard constraints
        valid_plans = self._validate_plans(all_plans)

        # Step 3: Assign buses greedily in departure order
        self._greedy_assign(valid_plans)

        # Step 4: Run the final simulation with all locked-in assignments
        result = self._simulate_and_score(self.assigned_plans)

        return result

    def _generate_all_plans(self) -> Dict[str, List[ChargingPlan]]:
        """Generate all candidate charging plans for every bus.

        Calls :func:`generate_charging_plans` for each bus to produce
        every combination of stations that could satisfy the range
        requirement.  The constraint system performs the definitive
        validity check in the next step.

        Returns:
            Mapping of ``bus_id`` to list of candidate
            :class:`ChargingPlan` objects.
        """
        all_plans: Dict[str, List[ChargingPlan]] = {}

        for bus in self.scenario.buses:
            plans = generate_charging_plans(
                bus=bus,
                route=self.scenario.route,
                params=self.scenario.parameters,
            )
            all_plans[bus.id] = plans

        return all_plans

    def _validate_plans(
        self, all_plans: Dict[str, List[ChargingPlan]]
    ) -> Dict[str, List[ChargingPlan]]:
        """Filter out plans that violate any hard constraint.

        Args:
            all_plans: Mapping of ``bus_id`` to candidate plans.

        Returns:
            Mapping of ``bus_id`` to the subset of plans that pass all
            constraints.  A bus with no valid plans will have an empty
            list.
        """
        valid_plans: Dict[str, List[ChargingPlan]] = {}

        for bus_id, plans in all_plans.items():
            # Keep only plans that satisfy every registered constraint
            valid = [
                plan for plan in plans
                if self.constraint_validator.is_valid(plan, self.scenario)
            ]
            valid_plans[bus_id] = valid

        return valid_plans

    def _greedy_assign(
        self, valid_plans: Dict[str, List[ChargingPlan]]
    ) -> None:
        """Assign plans to buses sequentially in departure order.

        Processes buses from earliest to latest departure.  For each bus,
        evaluates all valid candidate plans in the context of already-
        assigned buses and locks in the best-scoring one.

        Greedy rationale: earlier-departing buses have priority because
        they arrive at stations first and their assignments constrain the
        options available to later buses.  Processing in departure order
        mirrors real-world fairness.

        Args:
            valid_plans: Mapping of ``bus_id`` to valid candidate plans.

        Raises:
            RuntimeError: If a bus has no valid plans (indicates a route
                or battery-capacity configuration problem).
        """
        # Sort buses by departure time so earlier buses are assigned first
        sorted_buses = sorted(
            self.scenario.buses,
            key=lambda b: b.get_departure_datetime(datetime.now()),
        )

        for bus in sorted_buses:
            candidates = valid_plans.get(bus.id, [])

            if not candidates:
                # No valid plans — likely a route/battery configuration issue
                raise RuntimeError(
                    f"No valid charging plans found for bus {bus.id}. "
                    f"This may indicate the route is too long for the battery capacity."
                )

            # Pick the best plan for this bus given current assignments
            best_plan = self._select_best_plan(bus, candidates)

            # Lock in the assignment before processing the next bus
            self.assigned_plans[bus.id] = best_plan

    def _select_best_plan(
        self, bus: Bus, candidates: List[ChargingPlan]
    ) -> ChargingPlan:
        """Select the highest-scoring plan for a single bus.

        For each candidate plan, runs a full simulation that includes
        all already-assigned buses plus this candidate, scores the
        result, and returns the plan with the best score.

        Args:
            bus: The bus to select a plan for.
            candidates: Non-empty list of valid candidate plans.

        Returns:
            The :class:`ChargingPlan` that produced the highest weighted
            objective score.  Falls back to the first candidate if all
            scores are equal to ``-inf`` (should not occur in practice).
        """
        best_plan: Optional[ChargingPlan] = None
        best_score: float = float('-inf')

        for plan in candidates:
            # Build a temporary assignment set that includes this candidate
            temp_assignments = self.assigned_plans.copy()
            temp_assignments[bus.id] = plan

            # Simulate and score this candidate in context
            result = self._simulate_and_score(temp_assignments)
            score = self.objective_evaluator.evaluate(result, self.scenario)

            # Track the plan with the highest score
            if score > best_score:
                best_score = score
                best_plan = plan

        if best_plan is None:
            # Fallback: return the first candidate (all scores were -inf)
            best_plan = candidates[0]

        return best_plan

    def _simulate_and_score(
        self, assignments: Dict[str, ChargingPlan]
    ) -> SimulationResult:
        """Run the event simulator with a given set of plan assignments.

        Creates a fresh :class:`EventSimulator` for each call so that
        simulation state does not leak between candidate evaluations.

        Args:
            assignments: Mapping of ``bus_id`` to :class:`ChargingPlan`
                for all buses that should participate in this simulation.

        Returns:
            :class:`SimulationResult` from the simulator.
        """
        # A new simulator instance ensures clean state for each evaluation
        simulator = EventSimulator(self.scenario)
        return simulator.simulate(assignments)
