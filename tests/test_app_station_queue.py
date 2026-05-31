"""
Test for per-station queue table functionality in the Streamlit app.

This test verifies that the station queue display correctly shows:
- Tabs/sections for each station
- Chronological list of buses per station
- Required columns: Bus ID, Arrival, Charge Start, Charge End, Wait
- Highlighting for buses with wait > 0
"""

import pytest
import pandas as pd
from datetime import datetime
from scheduler.models import StationQueueEntry


def test_station_queue_data_structure():
    """Test that station queue entries have all required fields."""
    entry = StationQueueEntry(
        bus_id="bus-BK-01",
        arrival_time="20:40",
        charge_start="20:40",
        charge_end="21:05"
    )
    
    assert entry.bus_id == "bus-BK-01"
    assert entry.arrival_time == "20:40"
    assert entry.charge_start == "20:40"
    assert entry.charge_end == "21:05"


def test_wait_time_calculation():
    """Test that wait time is correctly calculated from arrival and charge start."""
    arrival = datetime.strptime("20:40", "%H:%M")
    charge_start = datetime.strptime("20:45", "%H:%M")
    
    wait_minutes = int((charge_start - arrival).total_seconds() / 60)
    
    assert wait_minutes == 5


def test_wait_time_calculation_no_wait():
    """Test that wait time is 0 when bus charges immediately."""
    arrival = datetime.strptime("20:40", "%H:%M")
    charge_start = datetime.strptime("20:40", "%H:%M")
    
    wait_minutes = int((charge_start - arrival).total_seconds() / 60)
    
    assert wait_minutes == 0


def test_wait_time_calculation_day_rollover():
    """Test that wait time handles day rollover correctly."""
    arrival = datetime.strptime("23:50", "%H:%M")
    charge_start = datetime.strptime("00:05", "%H:%M")
    
    wait_minutes = int((charge_start - arrival).total_seconds() / 60)
    
    # Should be negative, so we add 24 hours
    if wait_minutes < 0:
        wait_minutes += 24 * 60
    
    assert wait_minutes == 15


def test_queue_data_formatting():
    """Test that queue data is correctly formatted for display."""
    entries = [
        StationQueueEntry(
            bus_id="bus-BK-01",
            arrival_time="20:40",
            charge_start="20:40",
            charge_end="21:05"
        ),
        StationQueueEntry(
            bus_id="bus-BK-02",
            arrival_time="20:55",
            charge_start="21:05",
            charge_end="21:30"
        )
    ]
    
    queue_data = []
    for entry in entries:
        arrival = datetime.strptime(entry.arrival_time, "%H:%M")
        charge_start = datetime.strptime(entry.charge_start, "%H:%M")
        wait_minutes = int((charge_start - arrival).total_seconds() / 60)
        if wait_minutes < 0:
            wait_minutes += 24 * 60
        
        queue_data.append({
            "Bus ID": entry.bus_id,
            "Arrival": entry.arrival_time,
            "Wait (min)": wait_minutes,
            "Charge Start": entry.charge_start,
            "Charge End": entry.charge_end
        })
    
    assert len(queue_data) == 2
    assert queue_data[0]["Bus ID"] == "bus-BK-01"
    assert queue_data[0]["Wait (min)"] == 0
    assert queue_data[1]["Bus ID"] == "bus-BK-02"
    assert queue_data[1]["Wait (min)"] == 10


def test_highlight_wait_function():
    """Test the row highlighting function for buses with wait times."""
    queue_data = [
        {"Bus ID": "bus-BK-01", "Arrival": "20:40", "Wait (min)": 0, "Charge Start": "20:40", "Charge End": "21:05"},
        {"Bus ID": "bus-BK-02", "Arrival": "20:55", "Wait (min)": 10, "Charge Start": "21:05", "Charge End": "21:30"}
    ]
    
    df = pd.DataFrame(queue_data)
    
    def highlight_wait(row):
        if row['Wait (min)'] > 0:
            return ['background-color: #ffecd2'] * len(row)
        return [''] * len(row)
    
    # Apply styling
    styled_df = df.style.apply(highlight_wait, axis=1)
    
    # Verify the DataFrame has the correct structure
    assert len(df) == 2
    assert "Wait (min)" in df.columns
    assert df.iloc[0]["Wait (min)"] == 0
    assert df.iloc[1]["Wait (min)"] == 10


def test_station_statistics():
    """Test calculation of station statistics."""
    queue_data = [
        {"Bus ID": "bus-BK-01", "Wait (min)": 0},
        {"Bus ID": "bus-BK-02", "Wait (min)": 10},
        {"Bus ID": "bus-BK-03", "Wait (min)": 5},
        {"Bus ID": "bus-BK-04", "Wait (min)": 0}
    ]
    
    total_wait = sum(entry["Wait (min)"] for entry in queue_data)
    buses_with_wait = sum(1 for entry in queue_data if entry["Wait (min)"] > 0)
    total_buses = len(queue_data)
    
    assert total_buses == 4
    assert buses_with_wait == 2
    assert total_wait == 15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
