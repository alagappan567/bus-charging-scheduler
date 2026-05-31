"""
Objective system for the Bus Charging Scheduler.

This module defines the objective evaluation framework and implements
soft objectives that are optimised through weighted scoring.

Each objective returns a score where **higher is better**.  Because all
three built-in objectives are minimisation problems (we want to reduce
wait times), they return *negative* values so that a lower wait maps to
a higher (less-negative) score.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple
from collections import defaultdict
import numpy as np
from scheduler.models import SimulationResult, Scenario


class Objective(ABC):
    """Abstract base class for all soft objectives.

    An objective scores a completed simulation result.  Higher scores
    are better.  Objectives are combined via a weighted sum to produce
    a single total score for a candidate charging plan.

    Subclasses must implement :meth:`score`.
    """

    @abstractmethod
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """Compute a score for this objective.

        Args:
            result: The simulation result to score.
            scenario: The scenario context (route, buses, parameters,
                weights).

        Returns:
            A score value where higher is better.  Typically a negative
            number representing a penalty (minimisation objective).
        """
        pass


class ObjectiveEvaluator:
    """Evaluates simulation results using multiple weighted objectives.

    Combines a list of ``(objective, weight)`` pairs into a single
    scalar score by computing the weighted sum of individual objective
    scores.

    Attributes:
        objectives: List of ``(Objective, weight)`` tuples.
    """

    def __init__(self, objectives: List[Tuple[Objective, float]]) -> None:
        """Initialise the evaluator with objectives and their weights.

        Args:
            objectives: List of ``(objective, weight)`` tuples where
                *objective* is an :class:`Objective` instance and
                *weight* is a non-negative float coefficient.
        """
        self.objectives = objectives

    def evaluate(self, result: SimulationResult, scenario: Scenario) -> float:
        """Compute the total weighted score for a simulation result.

        Iterates over all registered objectives, multiplies each raw
        score by its weight, and sums the results.

        Args:
            result: The simulation result to evaluate.
            scenario: The scenario context.

        Returns:
            Total weighted score (higher is better).
        """
        total_score = 0.0
        for objective, weight in self.objectives:
            objective_score = objective.score(result, scenario)
            # Each term is weight × raw_score; negative raw scores mean
            # a higher weight amplifies the penalty for bad behaviour
            total_score += weight * objective_score
        return total_score

    def evaluate_detailed(
        self, result: SimulationResult, scenario: Scenario
    ) -> Dict[str, object]:
        """Compute per-objective scores alongside the total.

        Useful for debugging and UI display — shows how much each
        objective contributes to the final score.

        Args:
            result: The simulation result to evaluate.
            scenario: The scenario context.

        Returns:
            Dictionary mapping objective class names to a nested dict
            with keys ``raw_score``, ``weight``, and ``weighted_score``,
            plus a ``"total"`` key with the summed weighted score.
        """
        scores: Dict[str, object] = {}
        for objective, weight in self.objectives:
            objective_name = objective.__class__.__name__
            objective_score = objective.score(result, scenario)
            weighted_score = weight * objective_score
            scores[objective_name] = {
                'raw_score': objective_score,
                'weight': weight,
                'weighted_score': weighted_score
            }
        # Sum only the nested dicts (skip any non-dict entries)
        scores['total'] = sum(
            s['weighted_score']  # type: ignore[index]
            for s in scores.values()
            if isinstance(s, dict)
        )
        return scores


class IndividualWaitObjective(Objective):
    """Penalises the maximum wait time experienced by any single bus.

    Promotes individual fairness by ensuring no single bus is left
    waiting excessively.  The score is the *negative* of the worst-case
    individual wait, so minimising max wait maximises the score.

    Score formula::

        score = -max(total_wait_minutes for each bus)
    """

    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """Compute score based on the maximum individual wait time.

        Args:
            result: The simulation result containing bus timelines.
            scenario: The scenario context (unused here but required by
                the interface).

        Returns:
            Negative of the maximum wait time across all buses.
            Returns ``0.0`` if there are no timelines.
        """
        if not result.bus_timelines:
            return 0.0

        # Find the single worst-case wait across the entire fleet
        max_wait = max(
            timeline.total_wait_minutes
            for timeline in result.bus_timelines.values()
        )

        # Negate so that a lower max wait yields a higher (better) score
        return -max_wait


class OperatorFairnessObjective(Objective):
    """Penalises variance in average wait times across operators.

    Promotes inter-operator fairness: if one operator's fleet waits
    much longer on average than another's, this objective penalises
    that imbalance.  The score is the *negative* of the variance of
    per-operator average wait times.

    Score formula::

        operator_avg[op] = mean(total_wait_minutes for buses of op)
        score = -variance(operator_avg values)
    """

    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """Compute score based on variance of operator average wait times.

        Args:
            result: The simulation result containing bus timelines.
            scenario: The scenario context with bus-to-operator mapping.

        Returns:
            Negative of the variance in per-operator average wait times.
            Returns ``0.0`` if there are no timelines or only one operator.
        """
        if not result.bus_timelines:
            return 0.0

        # Accumulate wait times grouped by operator
        operator_waits: Dict[str, List[int]] = defaultdict(list)
        for timeline in result.bus_timelines.values():
            bus = scenario.get_bus(timeline.bus_id)
            if bus:
                operator_waits[bus.operator].append(timeline.total_wait_minutes)

        # Variance is undefined (or trivially 0) with a single operator
        if len(operator_waits) <= 1:
            return 0.0

        # Compute the mean wait for each operator's fleet
        operator_averages = [
            np.mean(waits) for waits in operator_waits.values()
        ]

        # Population variance across operator averages — measures how
        # unevenly wait time is distributed between operators
        variance = float(np.var(operator_averages))

        # Negate so that lower variance yields a higher (better) score
        return -variance


class OverallEfficiencyObjective(Objective):
    """Penalises total wait time across all buses.

    Promotes overall system efficiency by minimising the aggregate time
    all buses spend waiting.  Unlike :class:`IndividualWaitObjective`
    this cares about the *sum*, not the worst case.

    Score formula::

        score = -sum(total_wait_minutes for each bus)
    """

    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """Compute score based on total wait time across all buses.

        Args:
            result: The simulation result containing bus timelines.
            scenario: The scenario context (unused here but required by
                the interface).

        Returns:
            Negative of the total wait time across all buses.
            Returns ``0.0`` if there are no timelines.
        """
        if not result.bus_timelines:
            return 0.0

        # Sum every bus's accumulated wait time
        total_wait = sum(
            timeline.total_wait_minutes
            for timeline in result.bus_timelines.values()
        )

        # Negate so that lower total wait yields a higher (better) score
        return -total_wait
