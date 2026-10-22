"""
QuantumFlow — Baseline Signal Controllers
simulator/baseline.py  ·  Owner: Team Lead

Simplified teaching / benchmark controllers — NOT a production traffic-light
controller. There is no yellow or all-red interval, no pedestrian phase,
no corridor coordination, and no detector smoothing. Green times are a
one-shot integer split of a fixed 60 s cycle.

Controllers:
  - Fixed-time: 30 s North-South / 30 s East-West, ignoring queues.
  - Traffic-responsive: split the cycle in proportion to ns_count / ew_count,
    then clamp each approach to [MIN_GREEN, MAX_GREEN] (15–45 s) so the
    cycle still sums to 60 s.

Returns a TimingPlan in the same key format as the supplied TrafficInput
(named A–D or grid '(r,c)'). Does not mutate simulator state or data shapes.
"""

from __future__ import annotations

from metrics.traffic_model import evaluate as evaluate_signal_plan
from shared.types import ApproachTiming, SolverResult, TrafficInput, TimingPlan
from shared.validators import (
    CYCLE_SEC,
    MAX_GREEN,
    MIN_GREEN,
    validate_timing_plan,
    validate_traffic_input,
)

NS_GREEN_FIXED = CYCLE_SEC // 2  # 30 s
EW_GREEN_FIXED = CYCLE_SEC // 2  # 30 s


def _validate_green_split(ns_green: int, ew_green: int, cycle_sec: int) -> None:
    """Reject green times that violate cycle or per-approach limits."""
    for name, value in (("ns_green", ns_green), ("ew_green", ew_green)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"{name} must be an integer, got {type(value).__name__}."
            )
        if not (MIN_GREEN <= value <= MAX_GREEN):
            raise ValueError(
                f"{name}: {value}s is outside [{MIN_GREEN}, {MAX_GREEN}]."
            )
    total = ns_green + ew_green
    if total != cycle_sec:
        raise ValueError(
            f"ns_green + ew_green = {total}s, must equal CYCLE_SEC={cycle_sec}s."
        )


def fixed_time_plan(
    traffic_input: TrafficInput,
    ns_green: int = NS_GREEN_FIXED,
    ew_green: int = EW_GREEN_FIXED,
    cycle_sec: int = CYCLE_SEC,
) -> TimingPlan:
    """
    Build a fixed-time TimingPlan for every intersection in traffic_input.

    Default split is 30 s NS / 30 s EW. Queue lengths are ignored.

    Args:
        traffic_input: TrafficInput — keys must match the simulator format.
        ns_green:      North-South green seconds (default 30).
        ew_green:      East-West green seconds (default 30).
        cycle_sec:     Cycle length in seconds (default 60).

    Returns:
        TimingPlan with one ApproachTiming per intersection.

    Raises:
        ValueError: if traffic_input is invalid, or the green split violates
            cycle / MIN_GREEN / MAX_GREEN constraints.
    """
    validate_traffic_input(traffic_input)
    _validate_green_split(ns_green, ew_green, cycle_sec)

    timing_plan: TimingPlan = {
        iid: ApproachTiming(ns_green=ns_green, ew_green=ew_green)
        for iid in traffic_input
    }
    validate_timing_plan(timing_plan, traffic_input)
    return timing_plan


class FixedTimeController:
    """Fixed-time controller with a configurable equal-cycle split."""

    def __init__(
        self,
        ns_green: int = NS_GREEN_FIXED,
        ew_green: int = EW_GREEN_FIXED,
        cycle_sec: int = CYCLE_SEC,
    ) -> None:
        _validate_green_split(ns_green, ew_green, cycle_sec)
        self.ns_green = ns_green
        self.ew_green = ew_green
        self.cycle_sec = cycle_sec

    def plan(self, traffic_input: TrafficInput) -> TimingPlan:
        """Return a validated TimingPlan for the given traffic snapshot."""
        return fixed_time_plan(
            traffic_input,
            ns_green=self.ns_green,
            ew_green=self.ew_green,
            cycle_sec=self.cycle_sec,
        )

    def evaluate(self, traffic_input: TrafficInput) -> SolverResult:
        """Score this controller's plan with the shared traffic model."""
        return evaluate_signal_plan(
            traffic_input,
            self.plan(traffic_input),
            algorithm="fixed-time",
        )


def _allocate_responsive_greens(
    ns_count: int,
    ew_count: int,
    cycle_sec: int = CYCLE_SEC,
) -> tuple[int, int]:
    """
    Map approach counts to an integer (ns_green, ew_green) pair.

    Rules:
      - Zero vehicles on both approaches → equal 30 / 30 split.
      - Equal non-zero counts → equal 30 / 30 split.
      - Otherwise ns_green ≈ round(ns_share * cycle), clamped to [15, 45];
        ew_green is derived as cycle_sec − ns_green (also clamped).
      - Extreme imbalance (all demand on one approach) saturates at 45 / 15.
    """
    total = ns_count + ew_count
    if total == 0 or ns_count == ew_count:
        ns_green = cycle_sec // 2
    else:
        raw_ns = round((ns_count / total) * cycle_sec)
        ns_green = max(MIN_GREEN, min(MAX_GREEN, raw_ns))

    ew_green = cycle_sec - ns_green
    ew_green = max(MIN_GREEN, min(MAX_GREEN, ew_green))
    ns_green = cycle_sec - ew_green
    return ns_green, ew_green


def traffic_responsive_plan(
    traffic_input: TrafficInput,
    cycle_sec: int = CYCLE_SEC,
) -> TimingPlan:
    """
    Build a demand-proportional TimingPlan for every intersection.

    This is a simplified queue-ratio split, not a production actuated or
    adaptive traffic-light controller.

    Args:
        traffic_input: TrafficInput — same schema as the simulator (unchanged).
        cycle_sec:     Cycle length in seconds (default 60).

    Returns:
        TimingPlan with one ApproachTiming per intersection. Each entry
        satisfies MIN_GREEN ≤ green ≤ MAX_GREEN and ns + ew == cycle_sec.

    Raises:
        ValueError: if traffic_input is invalid.
    """
    validate_traffic_input(traffic_input)

    timing_plan: TimingPlan = {}
    for iid, counts in traffic_input.items():
        ns_green, ew_green = _allocate_responsive_greens(
            counts["ns_count"],
            counts["ew_count"],
            cycle_sec,
        )
        timing_plan[iid] = ApproachTiming(ns_green=ns_green, ew_green=ew_green)

    validate_timing_plan(timing_plan, traffic_input)
    return timing_plan


class TrafficResponsiveController:
    """Simplified demand-proportional controller (not for field deployment)."""

    def __init__(self, cycle_sec: int = CYCLE_SEC) -> None:
        self.cycle_sec = cycle_sec

    def plan(self, traffic_input: TrafficInput) -> TimingPlan:
        """Return a validated demand-proportional TimingPlan."""
        return traffic_responsive_plan(traffic_input, cycle_sec=self.cycle_sec)

    def evaluate(self, traffic_input: TrafficInput) -> SolverResult:
        """Score this controller's plan with the shared traffic model."""
        return evaluate_signal_plan(
            traffic_input,
            self.plan(traffic_input),
            algorithm="traffic-responsive",
        )
