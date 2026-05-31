"""
Integration tests for the event simulator.

Tests the complete event-driven simulation system with simple scenarios.
"""

import pytest
from datetime import datetime
from scheduler.models import (
    Scenario, Route, Segment, Station, Bus, Parameters, Weights, ChargingPlan
)
from scheduler.simulator import EventSimulator, EventType, Event, ChargerState


class TestChargerState:
    """Test charger state management."""
    
    def test_charger_allocation_and_release(self):
        """Test basic charger allocation and release."""
        # Create a 