"""
QuantumFlow — Traffic Simulator Interface
Root convenience module re-exporting simulator.traffic_simulator.
"""

from simulator.traffic_simulator import (
    INTERSECTIONS,
    INTERSECTION_GRID_MAP,
    GRID_TO_INTERSECTION_MAP,
    INITIAL_TRAFFIC_COUNTS,
    SCENARIO_BOUNDS,
    SIMULATION_DISCLAIMER,
    validate_vehicle_count,
    validate_approach_counts,
    normalize_intersection_id,
    TrafficSimulator,
    get_initial_traffic_input,
    create_traffic_simulator,
    generate_scenario,
    format_traffic_state,
)

__all__ = [
    "INTERSECTIONS",
    "INTERSECTION_GRID_MAP",
    "GRID_TO_INTERSECTION_MAP",
    "INITIAL_TRAFFIC_COUNTS",
    "SCENARIO_BOUNDS",
    "SIMULATION_DISCLAIMER",
    "validate_vehicle_count",
    "validate_approach_counts",
    "normalize_intersection_id",
    "TrafficSimulator",
    "get_initial_traffic_input",
    "create_traffic_simulator",
    "generate_scenario",
    "format_traffic_state",
]
