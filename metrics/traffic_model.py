"""
QuantumFlow — Signal-Plan Traffic Model  (single source of truth)

This module is the ONLY place vehicles-served, remaining queues, and modeled
delay are computed. Controllers (fixed-time, traffic-responsive, greedy) and
the QAOA solver must call ``evaluate()`` here (or the thin ``metrics.evaluator``
facade) and must not invent their own queue or wait metrics.

These numbers are a **simplified teaching / benchmark model**, not field
measurements and not a production traffic-engineering analysis (no Webster
delay, no stochastic arrivals, no spillback, no pedestrians, no lost time).

-----------------------------------------------------------------------------
Documented assumptions
-----------------------------------------------------------------------------

Time horizon
    Exactly one signal cycle of ``CYCLE_SEC`` seconds (default 60 s). Metrics
    describe that horizon only; they are not a long-run average.

Vehicle arrivals
    Closed snapshot. ``ns_count`` / ``ew_count`` are vehicles already queued
    at t = 0. **No vehicles arrive during the cycle.** Demand is deterministic.

Service-rate model
    During green, each approach discharges at a constant saturation flow of
    ``1 / SERVICE_SEC_PER_VEHICLE`` vehicles per second
    (``SERVICE_SEC_PER_VEHICLE = 2`` → 0.5 veh/s).
    Approach capacity = ``floor(green_sec / SERVICE_SEC_PER_VEHICLE)``.
    During red, capacity is 0. Integer vehicles only.

Queue update (no negative queues)
    served    = min(queue, capacity)
    remaining = max(0, queue - served)
    Served cannot exceed the initial queue. Remaining cannot be negative.

Waiting time (modeled approximation — not a measured wait)
    Remaining queue is a **vehicle count**, never reported as seconds.
    Leftover vehicles miss this cycle's green. Their modeled extra delay this
    cycle equals the red interval on that approach (the opposing green),
    because they sit through red and were not served during green.
    Served vehicles contribute 0 extra delay this cycle (discharge headway is
    already encoded in the service rate and is not double-counted).

        delay_ns = remaining_ns * ew_green
        delay_ew = remaining_ew * ns_green
        total_delay_sec = sum of delay_ns + delay_ew over intersections
        avg_wait_sec    = total_delay_sec / total_vehicles   (0 if none)

    This is a deterministic leftover-red approximation for a closed snapshot,
    not observed detector delay and not Webster/HCM uniform-delay formula.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

from shared.types import Metrics, SolverResult, TrafficInput, TimingPlan
from shared.validators import (
    CYCLE_SEC,
    validate_timing_plan,
    validate_traffic_input,
)

# Seconds of effective green required to serve one vehicle (saturation headway).
SERVICE_SEC_PER_VEHICLE = 2


def service_capacity(green_sec: int) -> int:
    """Integer discharge capacity of one approach during ``green_sec`` of green."""
    if green_sec <= 0:
        return 0
    return math.floor(green_sec / SERVICE_SEC_PER_VEHICLE)


def served_and_remaining(queue: int, green_sec: int) -> Tuple[int, int]:
    """
    Apply the service-rate model to one approach.

    Returns:
        (vehicles_served, remaining_queue) with remaining >= 0 and
        served + remaining == max(queue, 0).
    """
    q = max(0, queue)
    served = min(q, service_capacity(green_sec))
    remaining = q - served
    if remaining < 0:  # defensive; should be unreachable
        remaining = 0
    return served, remaining


def evaluate(
    traffic_input: TrafficInput,
    timing_plan: TimingPlan,
    algorithm: str = "unknown",
    runtime_ms: float = 0.0,
    cost: float | None = None,
) -> SolverResult:
    """
    Score a timing plan against a traffic snapshot.

    Invalid timing plans (cycle ≠ 60 s, greens outside [15, 45], key mismatch)
    raise ValueError before any metric is computed.

    Args:
        traffic_input: Snapshot queues (TrafficInput schema — unchanged).
        timing_plan:   Candidate greens; must pass cycle + bound checks.
        algorithm:     Label stored on the SolverResult.
        runtime_ms:    Caller wall-clock time (ms); not computed here.
        cost:          Optional QUBO/QAOA objective; unused by the queue model.

    Returns:
        SolverResult with status="ok". ``avg_wait_sec`` is modeled leftover-red
        delay, not a measured waiting time.

    Raises:
        ValueError: invalid traffic_input or timing_plan.
    """
    validate_traffic_input(traffic_input)
    validate_timing_plan(timing_plan, traffic_input)

    total_vehicles = 0
    vehicles_served = 0
    total_delay = 0.0

    for iid, counts in traffic_input.items():
        ns_q = max(0, counts["ns_count"])
        ew_q = max(0, counts["ew_count"])
        ns_g = timing_plan[iid]["ns_green"]
        ew_g = timing_plan[iid]["ew_green"]

        ns_served, ns_rem = served_and_remaining(ns_q, ns_g)
        ew_served, ew_rem = served_and_remaining(ew_q, ew_g)

        total_vehicles += ns_q + ew_q
        vehicles_served += ns_served + ew_served
        # Modeled leftover-red delay (seconds), not a queue count.
        total_delay += ns_rem * ew_g + ew_rem * ns_g

    remaining_queue = max(0, total_vehicles - vehicles_served)
    avg_wait_sec = (total_delay / total_vehicles) if total_vehicles > 0 else 0.0

    metrics: Metrics = {
        "total_vehicles": total_vehicles,
        "vehicles_served": vehicles_served,
        "remaining_queue": remaining_queue,
        "avg_wait_sec": round(avg_wait_sec, 2),
        "total_delay_sec": round(total_delay, 2),
        "runtime_ms": round(runtime_ms, 1),
    }

    result: SolverResult = {
        "algorithm": algorithm,
        "timing_plan": timing_plan,
        "cost": round(cost, 4) if cost is not None else None,
        "metrics": metrics,
        "runtime_ms": round(runtime_ms, 1),
        "status": "ok",
        "error_msg": None,
    }
    return result


def compare(classical: SolverResult, quantum: SolverResult) -> Dict:
    """
    Side-by-side dashboard comparison of two SolverResults.

    Wait reduction uses modeled ``avg_wait_sec`` from this module, not
    remaining-queue counts.
    """
    cm = classical["metrics"]
    qm = quantum["metrics"]

    tv = cm["total_vehicles"] or 1
    throughput_delta = round((qm["vehicles_served"] - cm["vehicles_served"]) / tv, 4)

    c_wait = cm["avg_wait_sec"] or 1e-9
    wait_reduction_pct = round((1 - qm["avg_wait_sec"] / c_wait) * 100, 2)

    cost_delta: float | None = None
    if quantum["cost"] is not None and classical["cost"] is not None:
        cost_delta = round(quantum["cost"] - classical["cost"], 4)

    return {
        "classical": dict(cm),
        "quantum": dict(qm),
        "advantage": {
            "throughput_delta": throughput_delta,
            "wait_reduction_pct": wait_reduction_pct,
            "cost_delta": cost_delta,
        },
    }
