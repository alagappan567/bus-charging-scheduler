"""
Objective system for the Bus Charging Scheduler.

This module defines the objective evaluation framework and implements
soft objectives that are optimized through weighted scoring.
"""

from abc import ABC, abstractmethod
from typing import List, Dict
from collections import defaultdict
import numpy as np
from scheduler.models import SimulationResult, Scenario


class Objective(ABC):
    """
    Abstract base class for all objectives.
    
    An objective is a soft rule that scores a simulation result.
    Higher scores are better. Objectives are combined using weighted sums
    to produce a total score for a charging plan.
    """
    
    @abstractmethod
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """
        Compute a score for this objective.
        
        Args:
            result: The simulation result to score
            scenario: The scenario context (route, buses, parameters, weights)
            
        Returns:
            A score value where higher is better. Typically negative values
            are used to represent penalties (minimization objectives).
        """
        pass


class ObjectiveEvaluator:
    """
    Evaluates simulation results using multiple weighted objectives.
    
    This class combines multiple objectives into a single score by computing
    a weighted sum. Each objective is multiplied by its weight and summed
    to produce the total score.
    """
    
    def __init__(self, objectives: List[tuple[Objective, float]]):
        """
        Initialize the evaluator with objectives and their weights.
        
        Args:
            objectives: List of (objective, weight) tuples where:
                - objective: An Objective instance
                - weight: A non-negative weight coefficient
        """
        self.objectives = objectives
    
    def evaluate(self, result: SimulationResult, scenario: Scenario) -> float:
        """
        Compute the total weighted score for a simulation result.
        
        Args:
            result: The simulation result to evaluate
            scenario: The scenario context
            
        Returns:
            Total weighted score (higher is better)
        """
        total_score = 0.0
        for objective, weight in self.objectives:
            objective_score = objective.score(result, scenario)
            total_score += weight * objective_score
        return total_score
    
    def evaluate_detailed(self, result: SimulationResult, scenario: Scenario) -> Dict[str, float]:
        """
        Compute detailed scores for each objective.
        
        Args:
            result: The simulation result to evaluate
            scenario: The scenario context
            
        Returns:
            Dictionary mapping objective names to their weighted scores
        """
        scores = {}
        for objective, weight in self.objectives:
            objective_name = objective.__class__.__name__
            objective_score = objective.score(result, scenario)
            weighted_score = weight * objective_score
            scores[objective_name] = {
                'raw_score': objective_score,
                'weight': weight,
                'weighted_score': weighted_score
            }
        scores['total'] = sum(s['weighted_score'] for s in scores.values() if isinstance(s, dict))
        return scores


class IndividualWaitObjective(Objective):
    """
    Penalizes the maximum wait time experienced by any single bus.
    
    This objective promotes individual fairness by ensuring no single bus
    experiences excessive wait times. It focuses on the worst-case individual
    experience rather than average performance.
    
    Score: -max_wait_time (negative because we want to minimize)
    """
    
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """
        Compute score based on maximum individual wait time.
        
        Args:
            result: The simulation result containing bus timelines
            scenario: The scenario context
            
        Returns:
            Negative of the maximum wait time across all buses
        """
        if not result.bus_timelines:
            return 0.0
        
        # Find the maximum wait time across all buses
        max_wait = max(
            timeline.total_wait_minutes 
            for timeline in result.bus_timelines.values()
        )
        
        # Return negative value (higher score = lower max wait)
        return -max_wait


class OperatorFairnessObjective(Objective):
    """
    Penalizes variance in average wait times across operators.
    
    This objective promotes fairness between operators by ensuring that
    no operator's fleet experiences significantly different wait times
    compared to other operators. It measures the variance in average
    wait times across operators.
    
    Score: -variance (negative because we want to minimize variance)
    """
    
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """
        Compute score based on variance of operator average wait times.
        
        Args:
            result: The simulation result containing bus timelines
            scenario: The scenario context with bus operator information
            
        Returns:
            Negative of the variance in average wait times across operators
        """
        if not result.bus_timelines:
            return 0.0
        
        # Group wait times by operator
        operator_waits: Dict[str, List[int]] = defaultdict(list)
        
        for timeline in result.bus_timelines.values():
            bus = scenario.get_bus(timeline.bus_id)
            if bus:
                operator_waits[bus.operator].append(timeline.total_wait_minutes)
        
        # If only one operator or no operators, variance is 0
        if len(operator_waits) <= 1:
            return 0.0
        
        # Calculate average wait time for each operator
        operator_averages = [
            np.mean(waits) for waits in operator_waits.values()
        ]
        
        # Calculate variance across operator averages
        variance = np.var(operator_averages)
        
        # Return negative value (higher score = lower variance)
        return -variance


class OverallEfficiencyObjective(Objective):
    """
    Penalizes total wait time across all buses.
    
    This objective promotes overall system efficiency by minimizing the
    total time all buses spend waiting. It focuses on aggregate performance
    rather than individual or operator-level fairness.
    
    Score: -total_wait_time (negative because we want to minimize)
    """
    
    def score(self, result: SimulationResult, scenario: Scenario) -> float:
        """
        Compute score based on total wait time across all buses.
        
        Args:
            result: The simulation result containing bus timelines
            scenario: The scenario context
            
        Returns:
            Negative of the total wait time across all buses
        """
        if not result.bus_timelines:
            return 0.0
        
        # Sum all wait times
        total_wait = sum(
            timeline.total_wait_minutes 
            for timeline in result.bus_timelines.values()
        )
        
        # Return negative value (higher score = lower total wait)
        return -total_wait
