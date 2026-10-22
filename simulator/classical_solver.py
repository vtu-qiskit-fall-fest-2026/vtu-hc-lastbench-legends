"""
QuantumFlow — Classical Greedy Signal Optimizer  (G3, G4 resolved)
simulator/classical_solver.py  ·  Owner: Team Lead

Changelog vs previous version:
  - Input changed from Dict[str,float] → TrafficInput.
  - Green-time range changed to [15, 45] with cycle = 60 s.
  - Private _compute_metrics() REMOVED; now calls metrics.evaluator.evaluate().
  - Returns SolverResult (typed).
"""

from __future__ import annotations

import time
from typing import Dict

from shared.types import TrafficInput, TimingPlan, ApproachTiming, SolverResult
from shared.validators import (
    validate_traffic_input,
    CYCLE_SEC,
    MIN_GREEN,
    MAX_GREEN,
)
from metrics.traffic_model import evaluate


def greedy_optimize(
    traffic_input: TrafficInput,
    cycle_sec:     int = CYCLE_SEC,
) -> SolverResult:
    """
    Greedy baseline: allocate ns_green proportionally to ns_count / total_count.
    ew_green = cycle_sec − ns_green, both clamped to [MIN_GREEN, MAX_GREEN].

    When both approaches are empty, defaults to equal split (30 / 30).

    Args:
        traffic_input: TrafficInput — must not be empty; counts must be >= 0.
        cycle_sec:     Fixed cycle length in seconds (default 60).

    Returns:
        SolverResult with algorithm="greedy", status="ok".

    Raises:
        ValueError: if traffic_input is empty or any count is negative.
    """
    validate_traffic_input(traffic_input)

    t0 = time.perf_counter()
    timing_plan: TimingPlan = {}

    for iid, counts in traffic_input.items():
        ns_c = counts["ns_count"]
        ew_c = counts["ew_count"]
        total = ns_c + ew_c

        if total == 0:
            ns_green = cycle_sec // 2   # equal split when no vehicles
        else:
            # Proportion of green time for NS approach
            raw_ns = round((ns_c / total) * cycle_sec)
            ns_green = max(MIN_GREEN, min(MAX_GREEN, raw_ns))

        ew_green = cycle_sec - ns_green
        # Clamp ew_green and adjust ns_green to maintain cycle
        ew_green = max(MIN_GREEN, min(MAX_GREEN, ew_green))
        ns_green = cycle_sec - ew_green   # re-derive to keep sum = cycle_sec

        timing_plan[iid] = ApproachTiming(ns_green=ns_green, ew_green=ew_green)

    runtime_ms = (time.perf_counter() - t0) * 1000

    return evaluate(
        traffic_input=traffic_input,
        timing_plan=timing_plan,
        algorithm="greedy",
        runtime_ms=runtime_ms,
        cost=None,   # no objective value for greedy
    )
