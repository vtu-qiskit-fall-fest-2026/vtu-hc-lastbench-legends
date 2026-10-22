"""
QuantumFlow — Canonical Type Aliases  (G9)
shared/types.py  ·  Owner: Team Lead

ALL modules import types from here. Do NOT redefine these elsewhere.
Changes require a version bump in docs/INTERFACES.md.
"""

from __future__ import annotations
from typing import Dict, Optional
from typing_extensions import TypedDict   # works on Python 3.8+; stdlib on 3.11+


# ---------------------------------------------------------------------------
# Primitive alias
# ---------------------------------------------------------------------------
IntersectionID = str  # canonical format: "(row,col)"  e.g. "(0,1)"


# ---------------------------------------------------------------------------
# 2.1  TrafficInput
# ---------------------------------------------------------------------------
class ApproachCounts(TypedDict):
    ns_count: int   # North-South queue length (vehicles) — must be >= 0
    ew_count: int   # East-West  queue length (vehicles) — must be >= 0


TrafficInput = Dict[IntersectionID, ApproachCounts]
"""
Mapping from intersection ID to per-approach vehicle counts.
Example::
    {
        "(0,0)": {"ns_count": 5, "ew_count": 2},
        "(0,1)": {"ns_count": 0, "ew_count": 8},
    }
"""


# ---------------------------------------------------------------------------
# 2.2  TimingPlan
# ---------------------------------------------------------------------------
class ApproachTiming(TypedDict):
    ns_green: int   # North-South green duration (seconds) ∈ [MIN_GREEN, MAX_GREEN]
    ew_green: int   # East-West  green duration (seconds) ∈ [MIN_GREEN, MAX_GREEN]
    # Invariant: ns_green + ew_green == CYCLE_SEC (60)


TimingPlan = Dict[IntersectionID, ApproachTiming]
"""
Mapping from intersection ID to green-time allocation.
Every entry must satisfy:  ns_green + ew_green == 60
                            15 <= ns_green <= 45
"""


# ---------------------------------------------------------------------------
# 2.3  Metrics
# ---------------------------------------------------------------------------
class Metrics(TypedDict):
    total_vehicles:   int    # Total vehicles in simulation snapshot
    vehicles_served:  int    # Estimated vehicles that clear queue this cycle
    remaining_queue:  int    # total_vehicles - vehicles_served
    avg_wait_sec:     float  # Estimated average waiting time (seconds)
    total_delay_sec:  float  # Sum of individual vehicle delays (seconds)
    runtime_ms:       float  # Wall-clock solver time (milliseconds)


# ---------------------------------------------------------------------------
# 2.4  SolverResult
# ---------------------------------------------------------------------------
class SolverResult(TypedDict):
    algorithm:   str            # "greedy" | "qaoa" | "mock"
    timing_plan: TimingPlan     # Must pass validate_timing_plan()
    cost:        Optional[float]  # Objective value (None for classical greedy)
    metrics:     Metrics
    runtime_ms:  float          # Mirrors metrics["runtime_ms"] for convenience
    status:      str            # "ok" | "timeout" | "infeasible" | "error"
    error_msg:   Optional[str]  # Non-None only when status != "ok"
