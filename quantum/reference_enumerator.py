"""
QuantumFlow — 4-Bit Candidate Signal Plan Reference Enumerator
quantum/reference_enumerator.py  ·  Owner: Quantum Engineer

Validation reference implementation for exhaustive enumeration of candidate
traffic signal timing plans across 4 intersections.

-----------------------------------------------------------------------------
OVERVIEW & PURPOSE
-----------------------------------------------------------------------------
This enumerator serves as an exact classical validation baseline (oracle)
for comparing discrete signal configurations and benchmarking optimization
algorithms (such as QAOA, greedy heuristics, and fixed-time baselines).

IT IS A VALIDATION REFERENCE ONLY, NOT QAOA.
It does not invoke quantum circuits or external solvers. It evaluates all 16
possible combinations of binary choices using the shared traffic model
evaluator (``metrics.traffic_model.evaluate`` / ``metrics.evaluator.evaluate``),
which is the single source of truth for queue and delay calculations.

-----------------------------------------------------------------------------
CYCLE & GREEN-TIME CONSTRAINTS (docs/INTERFACES.md §1 & §3)
-----------------------------------------------------------------------------
- Signal Cycle Length: CYCLE_SEC = 60 seconds (fixed).
- Approach Green Duration Limits: MIN_GREEN = 15 s, MAX_GREEN = 45 s.
- Invariant for each intersection: ns_green + ew_green == 60 seconds.

-----------------------------------------------------------------------------
CANDIDATE SIGNAL PLANS PER INTERSECTION
-----------------------------------------------------------------------------
Each intersection has exactly TWO candidate signal plans:

* Candidate Plan 0 (Bit = 0) — North-South Priority:
    - ns_green = 45 seconds (MAX_GREEN)
    - ew_green = 15 seconds (MIN_GREEN)
    - 75% green allocated to North-South approach, 25% to East-West.
    - Capacity (at 2 s/veh): NS = 22 vehicles, EW = 7 vehicles.
    - Status: Strictly valid (45 + 15 = 60, both in [15, 45]).

* Candidate Plan 1 (Bit = 1) — East-West Priority:
    - ns_green = 15 seconds (MIN_GREEN)
    - ew_green = 45 seconds (MAX_GREEN)
    - 25% green allocated to North-South approach, 75% to East-West.
    - Capacity (at 2 s/veh): NS = 7 vehicles, EW = 22 vehicles.
    - Status: Strictly valid (15 + 45 = 60, both in [15, 45]).

-----------------------------------------------------------------------------
BINARY REPRESENTATION & BIT ORDERING
-----------------------------------------------------------------------------
The network consists of 4 intersections:
    - Named IDs:  ["A", "B", "C", "D"]
    - Grid IDs:   ["(0,0)", "(0,1)", "(1,0)", "(1,1)"]

Each intersection's choice is represented by exactly ONE binary variable:
    x_i in {0, 1} for i in {0, 1, 2, 3}.

A 4-bit binary string:
    b = b_0 b_1 b_2 b_3  (from left to right, Big-Endian index)
maps to the 4 intersections as follows:

    Bit Position  Index  Named ID  Grid ID  Description
    -------------------------------------------------------------------------
    b_0 (MSB)       0       A       (0,0)   Intersection 0 signal plan choice
    b_1             1       B       (0,1)   Intersection 1 signal plan choice
    b_2             2       C       (1,0)   Intersection 2 signal plan choice
    b_3 (LSB)       3       D       (1,1)   Intersection 3 signal plan choice

For each intersection i:
    b_i == '0' -> Candidate Plan 0 (ns_green = 45, ew_green = 15)
    b_i == '1' -> Candidate Plan 1 (ns_green = 15, ew_green = 45)

-----------------------------------------------------------------------------
COMPLETE 16-COMBINATION STATE TABLE (2^4 = 16)
-----------------------------------------------------------------------------
Int  Bitstring   Int A (0,0)     Int B (0,1)     Int C (1,0)     Int D (1,1)
-----------------------------------------------------------------------------
 0    "0000"     Plan 0 (45/15)  Plan 0 (45/15)  Plan 0 (45/15)  Plan 0 (45/15)
 1    "0001"     Plan 0 (45/15)  Plan 0 (45/15)  Plan 0 (45/15)  Plan 1 (15/45)
 2    "0010"     Plan 0 (45/15)  Plan 0 (45/15)  Plan 1 (15/45)  Plan 0 (45/15)
 3    "0011"     Plan 0 (45/15)  Plan 0 (45/15)  Plan 1 (15/45)  Plan 1 (15/45)
 4    "0100"     Plan 0 (45/15)  Plan 1 (15/45)  Plan 0 (45/15)  Plan 0 (45/15)
 5    "0101"     Plan 0 (45/15)  Plan 1 (15/45)  Plan 0 (45/15)  Plan 1 (15/45)
 6    "0110"     Plan 0 (45/15)  Plan 1 (15/45)  Plan 1 (15/45)  Plan 0 (45/15)
 7    "0111"     Plan 0 (45/15)  Plan 1 (15/45)  Plan 1 (15/45)  Plan 1 (15/45)
 8    "1000"     Plan 1 (15/45)  Plan 0 (45/15)  Plan 0 (45/15)  Plan 0 (45/15)
 9    "1001"     Plan 1 (15/45)  Plan 0 (45/15)  Plan 0 (45/15)  Plan 1 (15/45)
10    "1010"     Plan 1 (15/45)  Plan 0 (45/15)  Plan 1 (15/45)  Plan 0 (45/15)
11    "1011"     Plan 1 (15/45)  Plan 0 (45/15)  Plan 1 (15/45)  Plan 1 (15/45)
12    "1100"     Plan 1 (15/45)  Plan 1 (15/45)  Plan 0 (45/15)  Plan 0 (45/15)
13    "1101"     Plan 1 (15/45)  Plan 1 (15/45)  Plan 0 (45/15)  Plan 1 (15/45)
14    "1110"     Plan 1 (15/45)  Plan 1 (15/45)  Plan 1 (15/45)  Plan 0 (45/15)
15    "1111"     Plan 1 (15/45)  Plan 1 (15/45)  Plan 1 (15/45)  Plan 1 (15/45)
-----------------------------------------------------------------------------
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from typing_extensions import TypedDict

from metrics.traffic_model import evaluate as evaluate_traffic
from shared.types import (
    ApproachTiming,
    IntersectionID,
    Metrics,
    SolverResult,
    TimingPlan,
    TrafficInput,
)
from shared.validators import (
    CYCLE_SEC,
    MAX_GREEN,
    MIN_GREEN,
    validate_timing_plan,
    validate_traffic_input,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NUM_INTERSECTIONS: int = 4
NUM_CANDIDATES_PER_INTERSECTION: int = 2
NUM_COMBINATIONS: int = 1 << NUM_INTERSECTIONS  # 2^4 = 16

DEFAULT_INTERSECTIONS: Tuple[str, ...] = ("A", "B", "C", "D")
GRID_INTERSECTIONS: Tuple[str, ...] = ("(0,0)", "(0,1)", "(1,0)", "(1,1)")

# Standard candidate plans for each intersection
# Index 0: Plan 0 (NS-priority, ns_green=45, ew_green=15)
# Index 1: Plan 1 (EW-priority, ns_green=15, ew_green=45)
PLAN_NS_PRIORITY = ApproachTiming(ns_green=45, ew_green=15)
PLAN_EW_PRIORITY = ApproachTiming(ns_green=15, ew_green=45)

DEFAULT_CANDIDATE_PLANS: Dict[str, Tuple[ApproachTiming, ApproachTiming]] = {
    iid: (
        ApproachTiming(ns_green=PLAN_NS_PRIORITY["ns_green"], ew_green=PLAN_NS_PRIORITY["ew_green"]),
        ApproachTiming(ns_green=PLAN_EW_PRIORITY["ns_green"], ew_green=PLAN_EW_PRIORITY["ew_green"]),
    )
    for iid in DEFAULT_INTERSECTIONS
}

GRID_CANDIDATE_PLANS: Dict[str, Tuple[ApproachTiming, ApproachTiming]] = {
    iid: (
        ApproachTiming(ns_green=PLAN_NS_PRIORITY["ns_green"], ew_green=PLAN_NS_PRIORITY["ew_green"]),
        ApproachTiming(ns_green=PLAN_EW_PRIORITY["ns_green"], ew_green=PLAN_EW_PRIORITY["ew_green"]),
    )
    for iid in GRID_INTERSECTIONS
}

# Precomputed tuple of all 16 4-bit strings: ("0000", "0001", ..., "1111")
ALL_BITSTRINGS: Tuple[str, ...] = tuple(f"{i:04b}" for i in range(NUM_COMBINATIONS))


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------
class EnumerationRecord(TypedDict):
    """Result of evaluating a single 4-bit candidate timing plan."""
    bitstring: str
    integer_value: int
    timing_plan: TimingPlan
    solver_result: SolverResult
    avg_wait_sec: float
    total_delay_sec: float
    vehicles_served: int
    remaining_queue: int


# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------
def validate_candidate_pair(
    plan_0: ApproachTiming,
    plan_1: ApproachTiming,
    iid: str = "intersection",
    cycle_sec: int = CYCLE_SEC,
    min_green: int = MIN_GREEN,
    max_green: int = MAX_GREEN,
) -> None:
    """
    Validate that two candidate plans for an intersection satisfy signal constraints.

    Raises:
        ValueError: if either candidate violates cycle or green constraints.
    """
    for idx, plan in enumerate((plan_0, plan_1)):
        ns_g = plan.get("ns_green")
        ew_g = plan.get("ew_green")
        if not isinstance(ns_g, int) or isinstance(ns_g, bool):
            raise ValueError(
                f"{iid} candidate plan {idx}: ns_green must be int, got {type(ns_g).__name__}"
            )
        if not isinstance(ew_g, int) or isinstance(ew_g, bool):
            raise ValueError(
                f"{iid} candidate plan {idx}: ew_green must be int, got {type(ew_g).__name__}"
            )
        if not (min_green <= ns_g <= max_green):
            raise ValueError(
                f"{iid} candidate plan {idx}: ns_green={ns_g}s outside [{min_green}, {max_green}]"
            )
        if not (min_green <= ew_g <= max_green):
            raise ValueError(
                f"{iid} candidate plan {idx}: ew_green={ew_g}s outside [{min_green}, {max_green}]"
            )
        if ns_g + ew_g != cycle_sec:
            raise ValueError(
                f"{iid} candidate plan {idx}: ns_green + ew_green = {ns_g + ew_g}s, "
                f"must equal CYCLE_SEC={cycle_sec}s"
            )


def resolve_candidate_plans(
    intersections: Sequence[str],
    candidate_plans: Optional[Dict[str, Tuple[ApproachTiming, ApproachTiming]]] = None,
) -> Dict[str, Tuple[ApproachTiming, ApproachTiming]]:
    """
    Resolve and validate candidate plans for the specified intersections.

    If candidate_plans is None, defaults to DEFAULT_CANDIDATE_PLANS (for A-D)
    or GRID_CANDIDATE_PLANS (for (r,c)), or generates standard 45/15 and 15/45 pairs.
    """
    if candidate_plans is not None:
        # Validate caller-provided plans
        resolved = dict(candidate_plans)
        for iid in intersections:
            if iid not in resolved:
                raise ValueError(f"Missing candidate plans for intersection '{iid}'")
            validate_candidate_pair(resolved[iid][0], resolved[iid][1], iid=iid)
        return resolved

    # Auto-select based on key format
    is_grid = any(k.startswith("(") for k in intersections)
    if is_grid:
        base = GRID_CANDIDATE_PLANS
    else:
        base = DEFAULT_CANDIDATE_PLANS

    resolved: Dict[str, Tuple[ApproachTiming, ApproachTiming]] = {}
    for iid in intersections:
        if iid in base:
            resolved[iid] = base[iid]
        else:
            resolved[iid] = (
                ApproachTiming(ns_green=45, ew_green=15),
                ApproachTiming(ns_green=15, ew_green=45),
            )
    return resolved


# ---------------------------------------------------------------------------
# Bitstring Decoding
# ---------------------------------------------------------------------------
def decode_bitstring(
    bitstring: str,
    intersections: Optional[Sequence[str]] = None,
    candidate_plans: Optional[Dict[str, Tuple[ApproachTiming, ApproachTiming]]] = None,
) -> TimingPlan:
    """
    Decode a 4-bit binary string into a complete TimingPlan.

    Bit Ordering (Left-to-Right, index i in [0..3]):
        bitstring[i] == '0' -> candidate plan 0 for intersections[i]
        bitstring[i] == '1' -> candidate plan 1 for intersections[i]

    Args:
        bitstring: 4-character binary string, e.g. "0000", "0101", "1111".
        intersections: Ordered sequence of 4 intersection IDs (default: ("A", "B", "C", "D")).
        candidate_plans: Optional mapping from intersection ID to (Plan0, Plan1).

    Returns:
        TimingPlan dictionary mapping each intersection ID to its ApproachTiming.

    Raises:
        ValueError: if bitstring length != 4 or contains non-binary characters.
        ValueError: if candidate plans violate constraints.
    """
    if not isinstance(bitstring, str):
        raise ValueError(
            f"bitstring must be a string, got {type(bitstring).__name__}"
        )

    clean_bits = bitstring.strip()
    if len(clean_bits) != NUM_INTERSECTIONS:
        raise ValueError(
            f"Bitstring length must be {NUM_INTERSECTIONS}, got {len(clean_bits)} ('{bitstring}')"
        )

    for char in clean_bits:
        if char not in ("0", "1"):
            raise ValueError(
                f"Invalid bit '{char}' in bitstring '{bitstring}'. Must contain only '0' and '1'."
            )

    inter_list = list(intersections) if intersections is not None else list(DEFAULT_INTERSECTIONS)
    if len(inter_list) != NUM_INTERSECTIONS:
        raise ValueError(
            f"Expected {NUM_INTERSECTIONS} intersections, got {len(inter_list)}"
        )

    resolved_candidates = resolve_candidate_plans(inter_list, candidate_plans)

    plan: TimingPlan = {}
    for i, iid in enumerate(inter_list):
        bit = clean_bits[i]
        choice_idx = 0 if bit == "0" else 1
        chosen_timing = resolved_candidates[iid][choice_idx]
        plan[iid] = ApproachTiming(
            ns_green=chosen_timing["ns_green"],
            ew_green=chosen_timing["ew_green"],
        )

    return plan


# ---------------------------------------------------------------------------
# Evaluation Functions
# ---------------------------------------------------------------------------
def evaluate_bitstring(
    bitstring: str,
    traffic_input: TrafficInput,
    intersections: Optional[Sequence[str]] = None,
    candidate_plans: Optional[Dict[str, Tuple[ApproachTiming, ApproachTiming]]] = None,
    algorithm: str = "reference_enumerator",
) -> SolverResult:
    """
    Decode and evaluate a single bitstring against the traffic input snapshot.

    Uses the authoritative shared traffic model evaluator (metrics.traffic_model.evaluate).

    Args:
        bitstring: 4-bit binary string.
        traffic_input: Snapshot queue lengths for all intersections.
        intersections: Ordered intersection list. Defaults to traffic_input keys or ("A", "B", "C", "D").
        candidate_plans: Optional custom candidate plans.
        algorithm: Label for attribution in SolverResult.

    Returns:
        SolverResult containing metrics, timing plan, status, and attribution.
    """
    validate_traffic_input(traffic_input)

    if intersections is None:
        # Match order from traffic_input keys if they are a known 4-set, else default
        keys = list(traffic_input.keys())
        if len(keys) == NUM_INTERSECTIONS:
            # Sort or preserve named order
            if set(keys) == set(DEFAULT_INTERSECTIONS):
                inter_list = list(DEFAULT_INTERSECTIONS)
            elif set(keys) == set(GRID_INTERSECTIONS):
                inter_list = list(GRID_INTERSECTIONS)
            else:
                inter_list = sorted(keys)
        else:
            inter_list = list(DEFAULT_INTERSECTIONS)
    else:
        inter_list = list(intersections)

    t0 = time.perf_counter()
    plan = decode_bitstring(bitstring, inter_list, candidate_plans)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return evaluate_traffic(
        traffic_input=traffic_input,
        timing_plan=plan,
        algorithm=algorithm,
        runtime_ms=elapsed_ms,
    )


def enumerate_all_plans(
    traffic_input: TrafficInput,
    intersections: Optional[Sequence[str]] = None,
    candidate_plans: Optional[Dict[str, Tuple[ApproachTiming, ApproachTiming]]] = None,
    algorithm: str = "reference_enumerator",
) -> List[EnumerationRecord]:
    """
    Exhaustively evaluate all 16 candidate signal plans using the shared evaluator.

    This pure Python enumerator explores the entire 4-bit discrete search space
    ("0000" through "1111") without heuristics, approximations, or QAOA circuits.

    Args:
        traffic_input: Snapshot queue lengths.
        intersections: Ordered 4-intersection list. Defaults to traffic_input keys.
        candidate_plans: Optional custom candidate plans per intersection.
        algorithm: Algorithm label on results.

    Returns:
        List of 16 EnumerationRecord dicts, ordered from "0000" (0) to "1111" (15).
    """
    validate_traffic_input(traffic_input)

    if intersections is None:
        keys = list(traffic_input.keys())
        if len(keys) == NUM_INTERSECTIONS:
            if set(keys) == set(DEFAULT_INTERSECTIONS):
                inter_list = list(DEFAULT_INTERSECTIONS)
            elif set(keys) == set(GRID_INTERSECTIONS):
                inter_list = list(GRID_INTERSECTIONS)
            else:
                inter_list = sorted(keys)
        else:
            inter_list = list(DEFAULT_INTERSECTIONS)
    else:
        inter_list = list(intersections)

    resolved_candidates = resolve_candidate_plans(inter_list, candidate_plans)

    records: List[EnumerationRecord] = []
    for int_val, bitstring in enumerate(ALL_BITSTRINGS):
        t0 = time.perf_counter()
        plan = decode_bitstring(bitstring, inter_list, resolved_candidates)
        # Ensure plan strictly passes shared validator
        validate_timing_plan(plan, traffic_input)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        solver_res = evaluate_traffic(
            traffic_input=traffic_input,
            timing_plan=plan,
            algorithm=algorithm,
            runtime_ms=elapsed_ms,
        )
        m = solver_res["metrics"]
        record: EnumerationRecord = {
            "bitstring": bitstring,
            "integer_value": int_val,
            "timing_plan": plan,
            "solver_result": solver_res,
            "avg_wait_sec": m["avg_wait_sec"],
            "total_delay_sec": m["total_delay_sec"],
            "vehicles_served": m["vehicles_served"],
            "remaining_queue": m["remaining_queue"],
        }
        records.append(record)

    return records


def find_optimal_plan(
    traffic_input: TrafficInput,
    intersections: Optional[Sequence[str]] = None,
    candidate_plans: Optional[Dict[str, Tuple[ApproachTiming, ApproachTiming]]] = None,
    objective: str = "avg_wait_sec",
) -> EnumerationRecord:
    """
    Find the optimal signal timing plan among all 16 candidate combinations.

    Tie-breaking:
    When objective is "avg_wait_sec" or "total_delay_sec", ties are broken by
    higher vehicles_served, then smaller integer_value (earlier bitstring).

    Args:
        traffic_input: Snapshot queue lengths.
        intersections: Ordered 4-intersection list.
        candidate_plans: Optional candidate plans.
        objective: Primary criterion ("avg_wait_sec", "total_delay_sec", or "vehicles_served").

    Returns:
        The best EnumerationRecord among all 16 combinations.
    """
    records = enumerate_all_plans(
        traffic_input=traffic_input,
        intersections=intersections,
        candidate_plans=candidate_plans,
    )

    if objective in ("avg_wait_sec", "total_delay_sec"):
        # Minimize wait / delay; maximize served on tie; prefer lower bitstring on tie
        best = min(
            records,
            key=lambda r: (r[objective], -r["vehicles_served"], r["integer_value"]),
        )
    elif objective == "vehicles_served":
        # Maximize served; minimize wait on tie; prefer lower bitstring on tie
        best = max(
            records,
            key=lambda r: (r["vehicles_served"], -r["avg_wait_sec"], -r["integer_value"]),
        )
    else:
        raise ValueError(
            f"Unsupported objective '{objective}'. Choose 'avg_wait_sec', 'total_delay_sec', or 'vehicles_served'."
        )

    return best


# ---------------------------------------------------------------------------
# Object-Oriented Interface
# ---------------------------------------------------------------------------
class ReferenceEnumerator:
    """
    Validation reference enumerator encapsulating candidate plans and bit mapping.

    Provides a clean, reusable interface for validating solver solutions against
    the true discrete optimum of the 4-bit candidate signal subspace.
    """

    def __init__(
        self,
        intersections: Optional[Sequence[str]] = None,
        candidate_plans: Optional[Dict[str, Tuple[ApproachTiming, ApproachTiming]]] = None,
    ) -> None:
        self.intersections: Tuple[str, ...] = tuple(
            intersections if intersections is not None else DEFAULT_INTERSECTIONS
        )
        if len(self.intersections) != NUM_INTERSECTIONS:
            raise ValueError(
                f"ReferenceEnumerator requires exactly {NUM_INTERSECTIONS} intersections, "
                f"got {len(self.intersections)}"
            )
        self.candidate_plans = resolve_candidate_plans(self.intersections, candidate_plans)

    def decode(self, bitstring: str) -> TimingPlan:
        """Decode a 4-bit string to a TimingPlan."""
        return decode_bitstring(
            bitstring=bitstring,
            intersections=self.intersections,
            candidate_plans=self.candidate_plans,
        )

    def evaluate_bitstring(
        self,
        bitstring: str,
        traffic_input: TrafficInput,
        algorithm: str = "reference_enumerator",
    ) -> SolverResult:
        """Evaluate a single 4-bit plan against traffic_input."""
        return evaluate_bitstring(
            bitstring=bitstring,
            traffic_input=traffic_input,
            intersections=self.intersections,
            candidate_plans=self.candidate_plans,
            algorithm=algorithm,
        )

    def evaluate_all(
        self,
        traffic_input: TrafficInput,
        algorithm: str = "reference_enumerator",
    ) -> List[EnumerationRecord]:
        """Exhaustively evaluate all 16 candidate combinations."""
        return enumerate_all_plans(
            traffic_input=traffic_input,
            intersections=self.intersections,
            candidate_plans=self.candidate_plans,
            algorithm=algorithm,
        )

    def find_optimal(
        self,
        traffic_input: TrafficInput,
        objective: str = "avg_wait_sec",
    ) -> EnumerationRecord:
        """Find the optimal plan among the 16 combinations."""
        return find_optimal_plan(
            traffic_input=traffic_input,
            intersections=self.intersections,
            candidate_plans=self.candidate_plans,
            objective=objective,
        )
