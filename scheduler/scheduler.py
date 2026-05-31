"""
Scheduler orchestrator for the Bus Charging Scheduler.

This module implements the main scheduling algorithm that coordinates
plan generation, constraint validation, simulation, and objective scoring
to produce optimal charging schedules for all buses.
"""

from typing import Dict, List, Optional
from datetime import datetime
from scheduler.models import Scenario, Bus, ChargingPlan, SimulationResult
from scheduler.plan_generator import generate_charging_plans
from scheduler.constraints import (
    Constraint, ConstraintValidator,
    RangeConstraint, RouteOrderConstraint, CompletionConstraint
)
from scheduler.objectives import (
    Objective, ObjectiveEvaluator,
    IndividualWaitObjective, OperatorFairnessObjective, OverallEfficiencyObjective
)
from scheduler.simulator import EventSimulator


class BusScheduler:
    """
    Main scheduler orchestrator that coordinates all components.
    
    This class implements a greedy sequential assignment algorithm:
    1. Generate candidate charging plans for all buses
    2. Filter plans that violate hard constraints
    3. Sort buses by departure time
    4. For each bus, try all its valid plans
    5. Simulate and score each plan given current assignments
    6. Select the best plan for this bus
    7. Lock in the assignment and move to next bus
    
    This greedy approach is fast and produces good results, though it may
    not find the global optimum. The sequential assignment ensures earlier
    buses get priority, which is fair given they depart first.
    """
    
    def __init__(self, scenario: Scenario):
        """
        Initialize the scheduler with a scenario.
        
        Args:
            scenario: The scenario containing route, buses, parameters, and weights
        """
        self.scenario = scenario
        
        # Initialize constraint validator with all hard constraints
        self.constraints: List[Constraint] = [
            RangeConstraint(),
            RouteOrderConstraint(),
            CompletionConstraint()
        ]
        self.constraint_validator = ConstraintValidator(self.constraints)
        
        # Initialize objective evaluator with weighted objectives
        self.objectives: List[tuple[Objective, float]] = [
            (IndividualWaitObjective(), scenario.weights.individual),
            (OperatorFairnessObjective(), scenario.weights.operator),
            (OverallEfficiencyObjective(), scenario.weights.overall)
        ]
        self.objective_evaluator = ObjectiveEvaluator(self.objectives)
        
        # Track assigned plans
        self.assigned_plans: Dict[str, ChargingPlan] = {}
    
    def schedule(self) -> SimulationResult:
        """
        Main entry point for scheduling.
        
        This method orchestrates the entire scheduling process:
        1. Generate all candidate plans for all buses
        2. Validate plans against constraints
        3. Assign buses greedily in departure order
        4. Return the final simulation result
        
        Returns:
            SimulationResult containing bus timelines and station queues
        """
        # Step 1: Generate all candidate plans
        all_plans = self._generate_all_plans()
        
        # Step 2: Validate and filter plans
        valid_plans = self._validate_plans(all_plans)
        
        # Step 3: Greedy assignment
        self._greedy_assign(valid_plans)
        
        # Step 4: Run final simulation with all assignments
        result = self._simulate_and_score(self.assigned_plans)
        
        return result
    
    def _generate_all_plans(self) -> Dict[str, List[ChargingPlan]]:
        """
        Generate all candidate charging plans for all buses.
        
        For each bus, this generates all valid combinations of charging
        stations that could potentially satisfy the range constraint.
        
        Returns:
            Dictionary mapping bus_id to list of candidate ChargingPlan objects
        """
        all_plans: Dict[str, List[ChargingPlan]] = {}
        
        for bus in self.scenario.buses:
            # Generate candidate plans for this bus
            plans = generate_charging_plans(
                bus=bus,
                route=self.scenario.route,
                params=self.scenario.parameters
            )
            all_plans[bus.id] = plans
        
        return all_plans
    
    def _validate_plans(self, all_plans: Dict[str, List[ChargingPlan]]) -> Dict[str, List[ChargingPlan]]:
        """
        Filter out plans that violate hard constraints.
        
        Args:
            all_plans: Dictionary of bus_id to list of candidate plans
            
        Returns:
            Dictionary of bus_id to list of valid plans (subset of input)
        """
        valid_plans: Dict[str, List[ChargingPlan]] = {}
        
        for bus_id, plans in all_plans.items():
            # Filter plans that pass all constraints
            valid = [
                plan for plan in plans
                if self.constraint_validator.is_valid(plan, self.scenario)
            ]
            valid_plans[bus_id] = valid
        
        return valid_plans
    
    def _greedy_assign(self, valid_plans: Dict[str, List[ChargingPlan]]) -> None:
        """
        Assign buses sequentially in departure order using greedy selection.
        
        For each bus (in departure order):
        1. Try all its valid plans
        2. Simulate each plan with current assignments
        3. Score each simulation
        4. Select the best scoring plan
        5. Lock in the assignment
        
        Args:
            valid_plans: Dictionary of bus_id to list of valid plans
        """
        # Sort buses by departure time
        sorted_buses = sorted(
            self.scenario.buses,
            key=lambda b: b.get_departure_datetime(datetime.now())
        )
        
        # Assign each bus sequentially
        for bus in sorted_buses:
            # Get valid plans for this bus
            candidates = valid_plans.get(bus.id, [])
            
            if not candidates:
                # No valid plans for this bus - this shouldn't happen if
                # plan generation and constraints are correct
                raise RuntimeError(
                    f"No valid charging plans found for bus {bus.id}. "
                    f"This may indicate the route is too long for the battery capacity."
                )
            
            # Select the best plan for this bus
            best_plan = self._select_best_plan(bus, candidates)
            
            # Lock in the assignment
            self.assigned_plans[bus.id] = best_plan
    
    def _select_best_plan(self, bus: Bus, candidates: List[ChargingPlan]) -> ChargingPlan:
        """
        Select the best charging plan for a bus from candidates.
        
        This method tries each candidate plan, simulates it with the current
        assignments, scores the result, and returns the plan with the best score.
        
        Args:
            bus: The bus to select a plan for
            candidates: List of valid candidate plans
            
        Returns:
            The best scoring ChargingPlan
        """
        best_plan: Optional[ChargingPlan] = None
        best_score: float = float('-inf')
        
        for plan in candidates:
            # Create temporary assignments including this plan
            temp_assignments = self.assigned_plans.copy()
            temp_assignments[bus.id] = plan
            
            # Simulate with these assignments
            result = self._simulate_and_score(temp_assignments)
            
            # Score the result
            score = self.objective_evaluator.evaluate(result, self.scenario)
            
            # Track best
            if score > best_score:
                best_score = score
                best_plan = plan
        
        if best_plan is None:
            # Fallback to first plan if scoring fails
            best_plan = candidates[0]
        
        return best_plan
    
    def _simulate_and_score(self, assignments: Dict[str, ChargingPlan]) -> SimulationResult:
        """
        Run simulation with given plan assignments.
        
        Args:
            assignments: Dictionary mapping bus_id to ChargingPlan
            
        Returns:
            SimulationResult containing timelines and station queues
        """
        # Create simulator
        simulator = EventSimulator(self.scenario)
        
        # Run simulation
        result = simulator.simulate(assignments)
        
        return result
