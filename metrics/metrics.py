"""
QuantumFlow — Metrics Evaluation and Controller Benchmarking
metrics/metrics.py  ·  Owner: Metrics Engineer / Team Lead

Calculates and compares traffic performance metrics across fixed-time,
traffic-responsive, and genuine QAOA controllers using the existing
traffic evaluator (metrics.traffic_model.evaluate) and agreed interfaces.

Documented Metrics:
  - total_vehicles: total vehicles in simulation snapshot (integer count)
  - vehicles_served: estimated vehicles that clear queue during green (integer count)
  - remaining_queue: leftover queued vehicles after cycle (integer count, NOT seconds)
  - avg_wait_sec: modeled leftover-red delay per vehicle (seconds, NOT queue count)
  - total_delay_sec: sum of modeled leftover-red delays across all intersections (seconds)
  - runtime_ms: solver execution wall-clock time (milliseconds)
  - percentage change against the fixed-time baseline (e.g. delay reduction %, wait reduction %)

Key Invariants & Guarantees:
  1. Identical traffic input and evaluation assumptions (metrics.traffic_model) for all controllers.
  2. Division-by-zero protection when queues, delays, or baselines are zero.
  3. Clear distinction between queue counts (integer vehicles) and waiting times (float seconds).
  4. Non-fabrication guarantee: Missing/failed QAOA results are NEVER replaced with classical results.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple, Union
from typing_extensions import TypedDict

from metrics.traffic_model import (
    SERVICE_SEC_PER_VEHICLE,
    evaluate as evaluate_traffic_plan,
    served_and_remaining,
    service_capacity,
)
from shared.types import Metrics, SolverResult, TimingPlan, TrafficInput
from shared.validators import (
    CYCLE_SEC,
    MAX_GREEN,
    MIN_GREEN,
    validate_timing_plan,
    validate_traffic_input,
)
from simulator.baseline import fixed_time_plan, traffic_responsive_plan


# ---------------------------------------------------------------------------
# TypedDict Definitions for Baseline Comparison
# ---------------------------------------------------------------------------
class BaselinePercentageChange(TypedDict):
    """
    Percentage changes and deltas evaluated against the Fixed-Time Baseline.
    
    Positive reduction values indicate improvement (less delay / shorter wait / smaller queue).
    Positive throughput values indicate improvement (more vehicles served).
    """
    delay_reduction_pct: float       # (baseline_delay - target_delay) / baseline_delay * 100
    wait_reduction_pct: float        # (baseline_wait - target_wait) / baseline_wait * 100
    queue_reduction_pct: float       # (baseline_rem - target_rem) / baseline_rem * 100
    throughput_pct_change: float     # (target_served - baseline_served) / baseline_served * 100
    throughput_delta: float          # (target_served - baseline_served) / total_vehicles
    cost_delta: Optional[float]      # target_cost - baseline_cost (if costs are defined)


class ControllerComparisonResult(TypedDict):
    """Side-by-side comparison of fixed-time, traffic-responsive, and QAOA controllers."""
    traffic_input: TrafficInput
    fixed_time: SolverResult
    traffic_responsive: SolverResult
    qaoa: SolverResult
    responsive_vs_baseline: BaselinePercentageChange
    qaoa_vs_baseline: Optional[BaselinePercentageChange]
    summary_rows: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Safe Percentage & Ratio Calculations (Division-by-Zero Protection)
# ---------------------------------------------------------------------------
def safe_percentage_reduction(baseline_val: float, target_val: float) -> float:
    """
    Calculate percentage reduction: (baseline - target) / baseline * 100.
    Positive indicates reduction (improvement for delay/wait/queue).
    
    Guards against division-by-zero:
      - If baseline_val == 0.0 and target_val == 0.0 -> returns 0.0.
      - If baseline_val == 0.0 and target_val > 0.0  -> returns -100.0 (worse).
    """
    if abs(baseline_val) < 1e-12:
        if abs(target_val) < 1e-12:
            return 0.0
        return -100.0 if target_val > 0 else 100.0
    return round(((baseline_val - target_val) / baseline_val) * 100.0, 2)


def safe_percentage_increase(baseline_val: float, target_val: float) -> float:
    """
    Calculate percentage increase: (target - baseline) / baseline * 100.
    Positive indicates increase (improvement for throughput / vehicles served).
    
    Guards against division-by-zero:
      - If baseline_val == 0.0 and target_val == 0.0 -> returns 0.0.
      - If baseline_val == 0.0 and target_val > 0.0  -> returns 100.0.
    """
    if abs(baseline_val) < 1e-12:
        if abs(target_val) < 1e-12:
            return 0.0
        return 100.0 if target_val > 0 else -100.0
    return round(((target_val - baseline_val) / baseline_val) * 100.0, 2)


# ---------------------------------------------------------------------------
# Core Metric Evaluation
# ---------------------------------------------------------------------------
def calculate_plan_metrics(
    traffic_input: TrafficInput,
    timing_plan: TimingPlan,
    algorithm: str = "unknown",
    runtime_ms: float = 0.0,
    cost: Optional[float] = None,
) -> SolverResult:
    """
    Evaluate a candidate TimingPlan using the shared traffic model evaluator.
    This is the single source of truth for queue counts and delay metrics.

    Args:
        traffic_input: Snapshot queue counts (TrafficInput).
        timing_plan: Green-time allocations to evaluate (TimingPlan).
        algorithm: Attribution string (e.g. "fixed-time", "traffic-responsive", "qaoa").
        runtime_ms: Wall-clock execution time of the controller in milliseconds.
        cost: Optional mathematical objective value.

    Returns:
        SolverResult adhering strictly to docs/INTERFACES.md §2.4.
    """
    return evaluate_traffic_plan(
        traffic_input=traffic_input,
        timing_plan=timing_plan,
        algorithm=algorithm,
        runtime_ms=runtime_ms,
        cost=cost,
    )


def compute_baseline_comparison(
    baseline_result: SolverResult,
    target_result: SolverResult,
) -> BaselinePercentageChange:
    """
    Compute percentage changes and throughput deltas of target_result relative to baseline_result.
    
    Args:
        baseline_result: Benchmark baseline result (typically Fixed-Time).
        target_result: Candidate controller result (e.g. Traffic-Responsive or QAOA).

    Returns:
        BaselinePercentageChange dictionary containing delay, wait, queue, and throughput changes.
    """
    b_m = baseline_result["metrics"]
    t_m = target_result["metrics"]

    total_veh = b_m["total_vehicles"]

    # Reductions: positive = improvement
    delay_red = safe_percentage_reduction(b_m["total_delay_sec"], t_m["total_delay_sec"])
    wait_red = safe_percentage_reduction(b_m["avg_wait_sec"], t_m["avg_wait_sec"])
    queue_red = safe_percentage_reduction(float(b_m["remaining_queue"]), float(t_m["remaining_queue"]))

    # Throughput: positive = improvement
    tp_pct = safe_percentage_increase(float(b_m["vehicles_served"]), float(t_m["vehicles_served"]))
    tp_delta = (
        round((t_m["vehicles_served"] - b_m["vehicles_served"]) / total_veh, 4)
        if total_veh > 0
        else 0.0
    )

    cost_delta: Optional[float] = None
    if target_result.get("cost") is not None and baseline_result.get("cost") is not None:
        cost_delta = round(float(target_result["cost"]) - float(baseline_result["cost"]), 4)

    return {
        "delay_reduction_pct": delay_red,
        "wait_reduction_pct": wait_red,
        "queue_reduction_pct": queue_red,
        "throughput_pct_change": tp_pct,
        "throughput_delta": tp_delta,
        "cost_delta": cost_delta,
    }


# ---------------------------------------------------------------------------
# Individual Controller Evaluators
# ---------------------------------------------------------------------------
def evaluate_fixed_time(
    traffic_input: TrafficInput,
    ns_green: int = 30,
    ew_green: int = 30,
    cycle_sec: int = CYCLE_SEC,
) -> SolverResult:
    """
    Evaluate the Fixed-Time baseline controller (default 30s NS / 30s EW).
    Wall-clock runtime is timed accurately.
    """
    t0 = time.perf_counter()
    plan = fixed_time_plan(traffic_input, ns_green=ns_green, ew_green=ew_green, cycle_sec=cycle_sec)
    runtime_ms = (time.perf_counter() - t0) * 1000.0

    return calculate_plan_metrics(
        traffic_input=traffic_input,
        timing_plan=plan,
        algorithm="fixed-time",
        runtime_ms=runtime_ms,
        cost=None,
    )


def evaluate_traffic_responsive(
    traffic_input: TrafficInput,
    cycle_sec: int = CYCLE_SEC,
) -> SolverResult:
    """
    Evaluate the Traffic-Responsive controller (demand-proportional split clamped to [15, 45]).
    Wall-clock runtime is timed accurately.
    """
    t0 = time.perf_counter()
    plan = traffic_responsive_plan(traffic_input, cycle_sec=cycle_sec)
    runtime_ms = (time.perf_counter() - t0) * 1000.0

    return calculate_plan_metrics(
        traffic_input=traffic_input,
        timing_plan=plan,
        algorithm="traffic-responsive",
        runtime_ms=runtime_ms,
        cost=None,
    )


def evaluate_qaoa(
    traffic_input: TrafficInput,
    coord_weight: float = 0.0,
    p_layers: int = 1,
    shots: int = 1024,
    maxiter: int = 50,
    seed: Optional[int] = 42,
    timeout_sec: float = 30.0,
) -> SolverResult:
    """
    Execute genuine QAOA on the traffic input and return the SolverResult.
    
    NO FABRICATION:
    If QAOA times out, fails, or produces an error, returns the actual status
    (e.g. status='timeout' or 'error') with cost=None. Never substitutes classical results.
    """
    from quantum.quantum_solver import solve_traffic_qubo

    return solve_traffic_qubo(
        traffic_input=traffic_input,
        coord_weight=coord_weight,
        p_layers=p_layers,
        shots=shots,
        maxiter=maxiter,
        seed=seed,
        timeout_sec=timeout_sec,
    )


# ---------------------------------------------------------------------------
# Comprehensive Controller Comparison
# ---------------------------------------------------------------------------
def compare_controllers(
    traffic_input: TrafficInput,
    p_layers: int = 1,
    shots: int = 1024,
    maxiter: int = 50,
    seed: Optional[int] = 42,
    timeout_sec: float = 30.0,
) -> ControllerComparisonResult:
    """
    Compare Fixed-Time, Traffic-Responsive, and QAOA on IDENTICAL traffic input
    and identical evaluation assumptions.

    Calculates:
      - Total vehicles, estimated vehicles served, remaining queue (vehicles)
      - Estimated average waiting time (seconds)
      - Estimated total delay (seconds)
      - Solver runtime (ms)
      - Percentage change against the fixed-time baseline
    """
    validate_traffic_input(traffic_input)

    # 1. Fixed-Time Baseline
    fixed_res = evaluate_fixed_time(traffic_input)

    # 2. Traffic-Responsive Controller
    resp_res = evaluate_traffic_responsive(traffic_input)
    resp_vs_base = compute_baseline_comparison(fixed_res, resp_res)

    # 3. Genuine QAOA Solver (No fabrication on error)
    qaoa_res = evaluate_qaoa(
        traffic_input=traffic_input,
        coord_weight=0.0,
        p_layers=p_layers,
        shots=shots,
        maxiter=maxiter,
        seed=seed,
        timeout_sec=timeout_sec,
    )

    qaoa_vs_base: Optional[BaselinePercentageChange] = None
    if qaoa_res["status"] == "ok":
        qaoa_vs_base = compute_baseline_comparison(fixed_res, qaoa_res)

    # 4. Assemble Summary Rows
    summary_rows: List[Dict[str, Any]] = [
        {
            "controller": "Fixed-Time (Baseline)",
            "algorithm": fixed_res["algorithm"],
            "total_vehicles": fixed_res["metrics"]["total_vehicles"],
            "vehicles_served": fixed_res["metrics"]["vehicles_served"],
            "remaining_queue": fixed_res["metrics"]["remaining_queue"],
            "avg_wait_sec": fixed_res["metrics"]["avg_wait_sec"],
            "total_delay_sec": fixed_res["metrics"]["total_delay_sec"],
            "runtime_ms": fixed_res["runtime_ms"],
            "delay_reduction_pct": 0.0,
            "wait_reduction_pct": 0.0,
            "status": fixed_res["status"],
        },
        {
            "controller": "Traffic-Responsive",
            "algorithm": resp_res["algorithm"],
            "total_vehicles": resp_res["metrics"]["total_vehicles"],
            "vehicles_served": resp_res["metrics"]["vehicles_served"],
            "remaining_queue": resp_res["metrics"]["remaining_queue"],
            "avg_wait_sec": resp_res["metrics"]["avg_wait_sec"],
            "total_delay_sec": resp_res["metrics"]["total_delay_sec"],
            "runtime_ms": resp_res["runtime_ms"],
            "delay_reduction_pct": resp_vs_base["delay_reduction_pct"],
            "wait_reduction_pct": resp_vs_base["wait_reduction_pct"],
            "status": resp_res["status"],
        },
        {
            "controller": "QAOA Quantum Solver",
            "algorithm": qaoa_res["algorithm"],
            "total_vehicles": qaoa_res["metrics"]["total_vehicles"],
            "vehicles_served": qaoa_res["metrics"]["vehicles_served"],
            "remaining_queue": qaoa_res["metrics"]["remaining_queue"],
            "avg_wait_sec": qaoa_res["metrics"]["avg_wait_sec"],
            "total_delay_sec": qaoa_res["metrics"]["total_delay_sec"],
            "runtime_ms": qaoa_res["runtime_ms"],
            "delay_reduction_pct": qaoa_vs_base["delay_reduction_pct"] if qaoa_vs_base else None,
            "wait_reduction_pct": qaoa_vs_base["wait_reduction_pct"] if qaoa_vs_base else None,
            "status": qaoa_res["status"],
        },
    ]

    return {
        "traffic_input": traffic_input,
        "fixed_time": fixed_res,
        "traffic_responsive": resp_res,
        "qaoa": qaoa_res,
        "responsive_vs_baseline": resp_vs_base,
        "qaoa_vs_baseline": qaoa_vs_base,
        "summary_rows": summary_rows,
    }


def format_comparison_table(res: ControllerComparisonResult) -> str:
    """Format controller comparison into a human-readable text table."""
    lines: List[str] = []
    lines.append("=" * 115)
    lines.append("QUANTUMFLOW CONTROLLER PERFORMANCE COMPARISON (IDENTICAL EVALUATION ASSUMPTIONS)")
    lines.append("=" * 115)
    header = (
        f"{'Controller':<24} | {'Vehicles':<8} | {'Served':<7} | {'Queue':<6} | "
        f"{'Wait (s)':<8} | {'Delay (s)':<10} | {'Delay Red %':<11} | {'Runtime ms':<10} | {'Status':<8}"
    )
    lines.append(header)
    lines.append("-" * 115)

    for row in res["summary_rows"]:
        c_name = row["controller"]
        tot = row["total_vehicles"]
        srv = row["vehicles_served"]
        rem = row["remaining_queue"]
        wait = f"{row['avg_wait_sec']:.2f}"
        delay = f"{row['total_delay_sec']:.1f}"
        red = f"{row['delay_reduction_pct']:+.1f}%" if row["delay_reduction_pct"] is not None else "N/A"
        rt = f"{row['runtime_ms']:.1f}"
        st = row["status"]
        lines.append(
            f"{c_name:<24} | {tot:<8} | {srv:<7} | {rem:<6} | {wait:<8} | {delay:<10} | {red:<11} | {rt:<10} | {st:<8}"
        )

    lines.append("=" * 115)
    lines.append("NOTES ON EVALUATION METRICS:")
    lines.append("  1. 'Queue' is an integer vehicle count (NOT seconds).")
    lines.append("  2. 'Wait (s)' and 'Delay (s)' are modeled leftover-red durations in seconds (NOT vehicle counts).")
    lines.append("  3. Baseline is Fixed-Time (30s NS / 30s EW). 'Delay Red %' is relative to Fixed-Time.")
    lines.append("  4. Actual observed QAOA outputs are reported directly without substitution.")
    lines.append("=" * 115)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Demonstration Runner
# ---------------------------------------------------------------------------
def main() -> None:
    """Run comparison on simulator benchmark snapshot and print results."""
    from simulator.traffic_simulator import TrafficSimulator

    sim = TrafficSimulator()
    traffic_input = sim.get_traffic_input(as_grid=False)

    print("\nRunning Controller Comparison on Simulator Benchmark Traffic Snapshot...")
    result = compare_controllers(traffic_input, p_layers=1, shots=1024, maxiter=50, seed=42)
    print(format_comparison_table(result))


if __name__ == "__main__":
    main()
