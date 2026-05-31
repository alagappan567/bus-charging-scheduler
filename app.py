"""
Bus Charging Scheduler - Streamlit UI

This is the main entry point for the Streamlit web application.
It provides an interactive interface for loading scenarios, running the scheduler,
and viewing the results in both per-bus and per-station views.
"""

import streamlit as st
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from scheduler.models import Scenario, SimulationResult, BusTimeline, StationQueueEntry
from scheduler.scheduler import BusScheduler


# ============================================================================
# Page Configuration
# ============================================================================

st.set_page_config(
    page_title="Bus Charging Scheduler",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# Custom CSS Styling
# ============================================================================

st.markdown("""
<style>
    /* Main theme colors */
    :root {
        --primary-color: #1f77b4;
        --secondary-color: #ff7f0e;
        --success-color: #2ca02c;
        --warning-color: #d62728;
        --info-color: #9467bd;
    }
    
    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1.1rem;
        opacity: 0.9;
    }
    
    /* Metric cards */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        border-left: 4px solid #667eea;
        transition: transform 0.2s;
    }
    
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #667eea;
        margin: 0;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 0.5rem;
    }
    
    /* Info boxes */
    .info-box {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #667eea;
    }
    
    .success-box {
        background: linear-gradient(135deg, #d4fc79 0%, #96e6a1 100%);
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #2ca02c;
    }
    
    .warning-box {
        background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #ff7f0e;
    }
    
    /* Bus timeline cards */
    .bus-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid #1f77b4;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    
    .bus-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    
    .bus-id {
        font-size: 1.2rem;
        font-weight: 600;
        color: #1f77b4;
    }
    
    .operator-badge {
        background: #667eea;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    /* Station badges */
    .station-badge {
        display: inline-block;
        background: #f0f2f6;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        margin: 0.25rem;
        font-weight: 500;
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #f0f2f6;
        border-radius: 8px 8px 0 0;
        padding: 0 24px;
        font-weight: 600;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    
    /* Dataframe styling */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Button styling */
    .stButton>button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Helper Functions
# ============================================================================

def load_scenarios() -> Dict[str, Path]:
    """
    Load all scenario files from the scenarios/ directory.
    
    Returns:
        Dictionary mapping scenario names to file paths
    """
    scenarios_dir = Path("scenarios")
    scenario_files = {}
    
    if scenarios_dir.exists():
        for file_path in sorted(scenarios_dir.glob("*.json")):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    scenario_name = data.get("name", file_path.stem)
                    scenario_files[scenario_name] = file_path
            except Exception as e:
                st.sidebar.error(f"Error loading {file_path.name}: {e}")
    
    return scenario_files


def load_scenario(file_path: Path) -> Optional[Scenario]:
    """
    Load and parse a scenario from a JSON file.
    
    Args:
        file_path: Path to the scenario JSON file
        
    Returns:
        Parsed Scenario object or None if loading fails
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            scenario = Scenario(**data)
            return scenario
    except Exception as e:
        st.error(f"Error loading scenario: {e}")
        return None


def format_time(time_str: str) -> str:
    """
    Ensure time is formatted consistently as HH:MM.
    
    Args:
        time_str: Time string (may be HH:MM or HH:MM:SS)
        
    Returns:
        Formatted time string as HH:MM
    """
    try:
        # Handle both HH:MM and HH:MM:SS formats
        if len(time_str) > 5:
            return time_str[:5]
        return time_str
    except:
        return time_str


def calculate_summary_stats(result: SimulationResult, scenario: Scenario) -> Dict:
    """
    Calculate summary statistics from the simulation result.
    
    Args:
        result: Simulation result with timelines
        scenario: Original scenario with bus information
        
    Returns:
        Dictionary with summary statistics
    """
    if not result.bus_timelines:
        return {
            "total_wait": 0,
            "max_wait": 0,
            "avg_wait": 0,
            "operator_stats": {}
        }
    
    # Calculate overall stats
    wait_times = [timeline.total_wait_minutes for timeline in result.bus_timelines.values()]
    total_wait = sum(wait_times)
    max_wait = max(wait_times) if wait_times else 0
    avg_wait = total_wait / len(wait_times) if wait_times else 0
    
    # Calculate per-operator stats
    operator_waits: Dict[str, List[int]] = {}
    for timeline in result.bus_timelines.values():
        operator = timeline.operator
        if operator not in operator_waits:
            operator_waits[operator] = []
        operator_waits[operator].append(timeline.total_wait_minutes)
    
    operator_stats = {}
    for operator, waits in operator_waits.items():
        operator_stats[operator] = {
            "total_wait": sum(waits),
            "avg_wait": sum(waits) / len(waits) if waits else 0,
            "max_wait": max(waits) if waits else 0,
            "num_buses": len(waits)
        }
    
    return {
        "total_wait": total_wait,
        "max_wait": max_wait,
        "avg_wait": avg_wait,
        "operator_stats": operator_stats
    }


# ============================================================================
# Visualization Functions
# ============================================================================

def create_gantt_chart(result: SimulationResult, scenario: Scenario):
    """Create an interactive Gantt chart showing bus timelines."""
    tasks = []
    
    for bus_id, timeline in result.bus_timelines.items():
        bus = scenario.get_bus(bus_id)
        if not bus:
            continue
            
        # Parse departure time
        dep_time = datetime.strptime(timeline.departure_time, "%H:%M")
        arr_time = datetime.strptime(timeline.arrival_time, "%H:%M")
        
        # Handle day rollover
        if arr_time < dep_time:
            arr_time = arr_time.replace(day=dep_time.day + 1)
        
        # Add main journey
        tasks.append(dict(
            Task=f"{bus_id} ({timeline.operator})",
            Start=dep_time,
            Finish=arr_time,
            Resource="Journey",
            Description=f"Total Wait: {timeline.total_wait_minutes} min"
        ))
        
        # Add charging stops
        for stop in timeline.charging_stops:
            charge_start = datetime.strptime(stop.charge_start, "%H:%M")
            charge_end = datetime.strptime(stop.charge_end, "%H:%M")
            
            if charge_start < dep_time:
                charge_start = charge_start.replace(day=dep_time.day + 1)
            if charge_end < charge_start:
                charge_end = charge_end.replace(day=charge_start.day + 1)
            
            tasks.append(dict(
                Task=f"{bus_id} ({timeline.operator})",
                Start=charge_start,
                Finish=charge_end,
                Resource=f"Charging at {stop.station}",
                Description=f"Wait: {stop.wait_minutes} min"
            ))
    
    if not tasks:
        return None
    
    df = pd.DataFrame(tasks)
    
    fig = px.timeline(
        df, 
        x_start="Start", 
        x_end="Finish", 
        y="Task",
        color="Resource",
        hover_data=["Description"],
        title="Bus Journey Timeline"
    )
    
    fig.update_layout(
        height=max(400, len(result.bus_timelines) * 50),
        xaxis_title="Time",
        yaxis_title="Bus",
        showlegend=True,
        hovermode='closest'
    )
    
    return fig


def create_wait_time_chart(result: SimulationResult, scenario: Scenario):
    """Create a bar chart showing wait times per bus."""
    data = []
    
    for bus_id, timeline in sorted(result.bus_timelines.items()):
        data.append({
            "Bus ID": bus_id,
            "Operator": timeline.operator,
            "Wait Time (min)": timeline.total_wait_minutes
        })
    
    df = pd.DataFrame(data)
    
    fig = px.bar(
        df,
        x="Bus ID",
        y="Wait Time (min)",
        color="Operator",
        title="Wait Time by Bus",
        text="Wait Time (min)"
    )
    
    fig.update_traces(textposition='outside')
    fig.update_layout(
        height=400,
        showlegend=True,
        xaxis_title="Bus ID",
        yaxis_title="Total Wait Time (minutes)"
    )
    
    return fig


def create_operator_comparison(result: SimulationResult, scenario: Scenario):
    """Create a comparison chart for operator statistics."""
    stats = calculate_summary_stats(result, scenario)
    
    if not stats['operator_stats']:
        return None
    
    operators = []
    avg_waits = []
    max_waits = []
    num_buses = []
    
    for operator, op_stats in stats['operator_stats'].items():
        operators.append(operator.upper())
        avg_waits.append(op_stats['avg_wait'])
        max_waits.append(op_stats['max_wait'])
        num_buses.append(op_stats['num_buses'])
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('Average Wait Time', 'Maximum Wait Time'),
        specs=[[{"type": "bar"}, {"type": "bar"}]]
    )
    
    fig.add_trace(
        go.Bar(x=operators, y=avg_waits, name="Avg Wait", marker_color='#667eea'),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Bar(x=operators, y=max_waits, name="Max Wait", marker_color='#764ba2'),
        row=1, col=2
    )
    
    fig.update_layout(
        height=400,
        showlegend=False,
        title_text="Operator Fairness Comparison"
    )
    
    fig.update_yaxes(title_text="Minutes", row=1, col=1)
    fig.update_yaxes(title_text="Minutes", row=1, col=2)
    
    return fig


def create_station_utilization(result: SimulationResult, scenario: Scenario):
    """Create a chart showing station utilization."""
    station_data = []
    
    for station_id, queue in result.station_queues.items():
        # Find station name
        station_name = station_id
        for station in scenario.route.stations:
            if station.id == station_id:
                station_name = station.name
                break
        
        total_wait = 0
        for entry in queue:
            try:
                arrival = datetime.strptime(entry.arrival_time, "%H:%M")
                charge_start = datetime.strptime(entry.charge_start, "%H:%M")
                wait_minutes = int((charge_start - arrival).total_seconds() / 60)
                if wait_minutes < 0:
                    wait_minutes += 24 * 60
                total_wait += wait_minutes
            except:
                pass
        
        station_data.append({
            "Station": station_name,
            "Buses Charged": len(queue),
            "Total Wait Time": total_wait
        })
    
    df = pd.DataFrame(station_data)
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('Buses Charged per Station', 'Total Wait Time per Station'),
        specs=[[{"type": "bar"}, {"type": "bar"}]]
    )
    
    fig.add_trace(
        go.Bar(x=df["Station"], y=df["Buses Charged"], marker_color='#2ca02c'),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Bar(x=df["Station"], y=df["Total Wait Time"], marker_color='#d62728'),
        row=1, col=2
    )
    
    fig.update_layout(
        height=400,
        showlegend=False,
        title_text="Station Utilization Analysis"
    )
    
    fig.update_yaxes(title_text="Number of Buses", row=1, col=1)
    fig.update_yaxes(title_text="Minutes", row=1, col=2)
    
    return fig


# ============================================================================
# Main Application
# ============================================================================

def main():
    """Main application entry point."""
    
    # Custom header
    st.markdown("""
    <div class="main-header">
        <h1>🚌 Bus Charging Scheduler</h1>
        <p>Intelligent optimization for electric bus charging schedules</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box">
        <strong>🎯 What this does:</strong> This application schedules electric bus charging along a fixed route, 
        optimizing for tunable objectives while respecting hard constraints like battery range and charger capacity.
        <br><br>
        <strong>📊 Features:</strong> Real-time scheduling • Multi-objective optimization • Interactive visualizations • Scenario comparison
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar: Scenario selection
    st.sidebar.header("Scenario Selection")
    
    # Load available scenarios
    scenario_files = load_scenarios()
    
    if not scenario_files:
        st.error("No scenario files found in the scenarios/ directory.")
        return
    
    # Scenario dropdown
    scenario_names = list(scenario_files.keys())
    selected_scenario_name = st.sidebar.selectbox(
        "Choose a scenario:",
        scenario_names,
        help="Select a scenario to load its configuration"
    )
    
    # Load selected scenario
    selected_file = scenario_files[selected_scenario_name]
    scenario = load_scenario(selected_file)
    
    if scenario is None:
        st.error("Failed to load scenario. Please check the file format.")
        return
    
    # Display scenario name
    st.header(f"📋 {scenario.name}")
    
    # Create tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Scenario Configuration", "🚌 Bus Timelines", "🔌 Station Queues"])
    
    # ========================================================================
    # Tab 1: Scenario Configuration
    # ========================================================================
    with tab1:
        st.subheader("Scenario Configuration")
        
        # Parameters section
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🔋 Parameters")
            st.markdown(f"""
            - **Battery Capacity:** {scenario.parameters.battery_capacity_km} km
            - **Charge Duration:** {scenario.parameters.charge_duration_minutes} minutes
            - **Average Speed:** {scenario.parameters.speed_kmh} km/h
            """)
            
            st.markdown("### ⚖️ Objective Weights")
            st.markdown(f"""
            - **Individual Wait:** {scenario.weights.individual}
            - **Operator Fairness:** {scenario.weights.operator}
            - **Overall Efficiency:** {scenario.weights.overall}
            """)
        
        with col2:
            st.markdown("### 🛣️ Route Structure")
            st.markdown(f"**Route:** {scenario.route.origin} → {scenario.route.destination}")
            
            # Display segments
            st.markdown("**Segments:**")
            for segment in scenario.route.segments:
                st.markdown(f"- {segment.from_location} → {segment.to_location}: {segment.distance_km} km")
            
            # Display stations
            st.markdown("**Charging Stations:**")
            for station in scenario.route.stations:
                st.markdown(f"- **{station.name}** (ID: {station.id}): {station.num_chargers} charger(s)")
        
        # Bus list
        st.markdown("### 🚌 Bus Schedule")
        bus_data = []
        for bus in scenario.buses:
            direction = f"{bus.origin} → {bus.destination}"
            bus_data.append({
                "Bus ID": bus.id,
                "Operator": bus.operator,
                "Direction": direction,
                "Departure Time": format_time(bus.departure_time)
            })
        
        st.dataframe(bus_data, width="stretch", hide_index=True)
    
    # ========================================================================
    # Run Scheduler Button
    # ========================================================================
    st.sidebar.markdown("---")
    run_button = st.sidebar.button("▶️ Run Scheduler", type="primary", use_container_width=True)
    
    # Initialize session state for results
    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'current_scenario' not in st.session_state:
        st.session_state.current_scenario = None
    
    # Clear results if scenario changed
    if st.session_state.current_scenario != selected_scenario_name:
        st.session_state.result = None
        st.session_state.current_scenario = selected_scenario_name
    
    # Run scheduler when button is clicked
    if run_button:
        with st.spinner("🔄 Running scheduler... This may take a few seconds."):
            try:
                scheduler = BusScheduler(scenario)
                result = scheduler.schedule()
                st.session_state.result = result
                st.sidebar.success("✅ Scheduling complete!")
            except Exception as e:
                st.sidebar.error(f"❌ Scheduling failed: {e}")
                st.session_state.result = None
    
    # Display results if available
    result = st.session_state.result
    
    if result is None:
        st.info("👆 Click 'Run Scheduler' in the sidebar to generate the charging schedule.")
        return
    
    # ========================================================================
    # Tab 2: Bus Timelines
    # ========================================================================
    with tab2:
        st.subheader("🚌 Bus Timelines & Analytics")
        
        # Summary statistics with enhanced styling
        stats = calculate_summary_stats(result, scenario)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{stats['total_wait']}</div>
                <div class="metric-label">Total Wait Time (min)</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{stats['max_wait']}</div>
                <div class="metric-label">Max Wait Time (min)</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{stats['avg_wait']:.1f}</div>
                <div class="metric-label">Avg Wait Time (min)</div>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{len(result.bus_timelines)}</div>
                <div class="metric-label">Total Buses</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Visualizations
        col1, col2 = st.columns(2)
        
        with col1:
            wait_chart = create_wait_time_chart(result, scenario)
            if wait_chart:
                st.plotly_chart(wait_chart, use_container_width=True)
        
        with col2:
            operator_chart = create_operator_comparison(result, scenario)
            if operator_chart:
                st.plotly_chart(operator_chart, use_container_width=True)
        
        # Gantt chart
        st.markdown("### 📊 Interactive Timeline")
        gantt = create_gantt_chart(result, scenario)
        if gantt:
            st.plotly_chart(gantt, use_container_width=True)
        
        # Per-operator statistics with enhanced styling
        if stats['operator_stats']:
            st.markdown("### 👥 Operator Performance")
            operator_cols = st.columns(len(stats['operator_stats']))
            for idx, (operator, op_stats) in enumerate(stats['operator_stats'].items()):
                with operator_cols[idx]:
                    st.markdown(f"""
                    <div class="info-box">
                        <h3 style="margin-top:0; color:#667eea;">{operator.upper()}</h3>
                        <p><strong>Buses:</strong> {op_stats['num_buses']}</p>
                        <p><strong>Total Wait:</strong> {op_stats['total_wait']} min</p>
                        <p><strong>Avg Wait:</strong> {op_stats['avg_wait']:.1f} min</p>
                        <p><strong>Max Wait:</strong> {op_stats['max_wait']} min</p>
                    </div>
                    """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### 🚌 Detailed Bus Timelines")
        
        # Add filtering and sorting options
        col1, col2, col3 = st.columns([2, 2, 2])
        
        with col1:
            # Operator filter
            all_operators = sorted(set(timeline.operator for timeline in result.bus_timelines.values()))
            selected_operators = st.multiselect(
                "Filter by Operator",
                options=all_operators,
                default=all_operators,
                help="Select operators to display"
            )
        
        with col2:
            # Sort option
            sort_option = st.selectbox(
                "Sort by",
                options=["Bus ID", "Departure Time", "Wait Time (Low to High)", "Wait Time (High to Low)", "Arrival Time"],
                help="Choose how to sort the bus timelines"
            )
        
        with col3:
            # Wait time filter
            max_wait_in_data = max((timeline.total_wait_minutes for timeline in result.bus_timelines.values()), default=0)
            if max_wait_in_data > 0:
                wait_filter = st.slider(
                    "Max Wait Time (min)",
                    min_value=0,
                    max_value=int(max_wait_in_data),
                    value=int(max_wait_in_data),
                    help="Show only buses with wait time up to this value"
                )
            else:
                wait_filter = 0
                st.info("No wait times to filter")
        
        # Filter timelines by operator and wait time
        filtered_timelines = {
            bus_id: timeline 
            for bus_id, timeline in result.bus_timelines.items()
            if timeline.operator in selected_operators and timeline.total_wait_minutes <= wait_filter
        }
        
        # Sort timelines based on selected option
        if sort_option == "Bus ID":
            sorted_timelines = sorted(filtered_timelines.items())
        elif sort_option == "Departure Time":
            sorted_timelines = sorted(filtered_timelines.items(), key=lambda x: x[1].departure_time)
        elif sort_option == "Wait Time (Low to High)":
            sorted_timelines = sorted(filtered_timelines.items(), key=lambda x: x[1].total_wait_minutes)
        elif sort_option == "Wait Time (High to Low)":
            sorted_timelines = sorted(filtered_timelines.items(), key=lambda x: x[1].total_wait_minutes, reverse=True)
        elif sort_option == "Arrival Time":
            sorted_timelines = sorted(filtered_timelines.items(), key=lambda x: x[1].arrival_time)
        else:
            sorted_timelines = sorted(filtered_timelines.items())
        
        # Show count of filtered results
        if len(filtered_timelines) < len(result.bus_timelines):
            st.info(f"Showing {len(filtered_timelines)} of {len(result.bus_timelines)} buses")
        
        # Display each bus timeline with enhanced styling
        for bus_id, timeline in sorted_timelines:
            wait_color = "success-box" if timeline.total_wait_minutes == 0 else "warning-box" if timeline.total_wait_minutes < 10 else "info-box"
            
            with st.expander(
                f"🚌 {timeline.bus_id} ({timeline.operator}) - "
                f"Departs: {format_time(timeline.departure_time)}, "
                f"Arrives: {format_time(timeline.arrival_time)}, "
                f"Total Wait: {timeline.total_wait_minutes} min",
                expanded=False
            ):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown(f"""
                    <div class="{wait_color}">
                        <strong>Direction:</strong> {timeline.direction}<br>
                        <strong>Departure:</strong> {format_time(timeline.departure_time)}<br>
                        <strong>Arrival:</strong> {format_time(timeline.arrival_time)}<br>
                        <strong>Total Wait Time:</strong> {timeline.total_wait_minutes} minutes
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    if timeline.charging_stops:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-value">{len(timeline.charging_stops)}</div>
                            <div class="metric-label">Charging Stops</div>
                        </div>
                        """, unsafe_allow_html=True)
                
                if timeline.charging_stops:
                    st.markdown("#### ⚡ Charging Stops")
                    stop_data = []
                    for stop in timeline.charging_stops:
                        stop_data.append({
                            "Station": stop.station,
                            "Arrival": format_time(stop.arrival_time),
                            "Wait (min)": stop.wait_minutes,
                            "Charge Start": format_time(stop.charge_start),
                            "Charge End": format_time(stop.charge_end)
                        })
                    st.dataframe(stop_data, use_container_width=True, hide_index=True)
                else:
                    st.info("✅ No charging stops needed for this bus.")
    
    # ========================================================================
    # Tab 3: Station Queues
    # ========================================================================
    with tab3:
        st.subheader("🔌 Station Queues & Utilization")
        
        # Station utilization chart
        station_util = create_station_utilization(result, scenario)
        if station_util:
            st.plotly_chart(station_util, use_container_width=True)
        
        st.markdown("---")
        
        # Get all station IDs
        station_ids = sorted(result.station_queues.keys())
        
        if not station_ids:
            st.info("No station queue data available.")
            return
        
        # Create tabs for each station
        station_tabs = st.tabs([f"🔌 Station {sid}" for sid in station_ids])
        
        for idx, station_id in enumerate(station_ids):
            with station_tabs[idx]:
                queue = result.station_queues[station_id]
                
                if not queue:
                    st.info(f"No buses charged at Station {station_id}.")
                    continue
                
                # Find station name
                station_name = station_id
                for station in scenario.route.stations:
                    if station.id == station_id:
                        station_name = station.name
                        break
                
                # Calculate station statistics
                total_wait_at_station = 0
                buses_with_wait = 0
                
                queue_data = []
                for entry in queue:
                    # Calculate wait time
                    try:
                        arrival = datetime.strptime(entry.arrival_time, "%H:%M")
                        charge_start = datetime.strptime(entry.charge_start, "%H:%M")
                        wait_minutes = int((charge_start - arrival).total_seconds() / 60)
                        if wait_minutes < 0:
                            wait_minutes += 24 * 60  # Handle day rollover
                    except:
                        wait_minutes = 0
                    
                    if wait_minutes > 0:
                        buses_with_wait += 1
                        total_wait_at_station += wait_minutes
                    
                    queue_data.append({
                        "Bus ID": entry.bus_id,
                        "Arrival": format_time(entry.arrival_time),
                        "Wait (min)": wait_minutes,
                        "Charge Start": format_time(entry.charge_start),
                        "Charge End": format_time(entry.charge_end)
                    })
                
                # Display station header with metrics
                st.markdown(f"""
                <div class="info-box">
                    <h2 style="margin-top:0; color:#667eea;">⚡ {station_name}</h2>
                </div>
                """, unsafe_allow_html=True)
                
                # Display station stats
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{len(queue)}</div>
                        <div class="metric-label">Buses Charged</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{buses_with_wait}</div>
                        <div class="metric-label">Buses with Wait</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{total_wait_at_station}</div>
                        <div class="metric-label">Total Wait (min)</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Display queue table with highlighting
                st.markdown("### 📋 Charging Queue")
                
                # Convert to DataFrame for styling
                df_queue = pd.DataFrame(queue_data)
                
                # Apply styling to highlight rows with wait > 0
                def highlight_wait(row):
                    if row['Wait (min)'] > 0:
                        return ['background-color: #ffecd2'] * len(row)
                    return [''] * len(row)
                
                styled_df = df_queue.style.apply(highlight_wait, axis=1)
                
                st.dataframe(
                    styled_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Highlight buses with wait time
                if buses_with_wait > 0:
                    st.markdown(f"""
                    <div class="warning-box">
                        ⚠️ <strong>{buses_with_wait} bus(es)</strong> experienced wait time at this station.
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="success-box">
                        ✅ <strong>No wait times!</strong> All buses were able to charge immediately.
                    </div>
                    """, unsafe_allow_html=True)


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    main()
