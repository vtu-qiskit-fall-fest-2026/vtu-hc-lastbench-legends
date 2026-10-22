"""
QuantumFlow — QUBO Builder  (G6, G7, G8 resolved)
quantum/qubo_builder.py  ·  Owner: Quantum Engineer

MUST NOT import flask or any web framework.

Changelog vs previous version:
  - MIN_GREEN updated 10 → 15, MAX_GREEN updated 90 → 45 (cycle = 60 s).
  - DISCRETE_LEVELS = [15, 25, 35, 45]  (4 ns_green choices, ew_green derived).
  - build_qubo() now accepts TrafficInput; derives congestion score internally.
  - decode_solution() now returns TimingPlan (ns_green + ew_green) instead of
    Dict[str, int].
"""

from __future__ import annotations

import numpy as np
from typing import List, Tuple

from shared.types import TrafficInput, TimingPlan, ApproachTiming
from shared.validators import validate_traffic_input, CYCLE_SEC

# ---------------------------------------------------------------------------
# Constants  (must match docs/INTERFACES.md §1 and §3)
# ---------------------------------------------------------------------------
MIN_GREEN:        int       = 15
MAX_GREEN:        int       = 45
NUM_QUBO_LEVELS:  int       = 4
DISCRETE_LEVELS:  List[int] = [15, 25, 35, 45]   # ns_green choices
MAX_CAPACITY:     int       = 3                   # soft vehicles/intersection


# ---------------------------------------------------------------------------
# build_qubo
# ---------------------------------------------------------------------------
def build_qubo(
    traffic_input:  TrafficInput,
    penalty_lambda: float = 5.0,
) -> Tuple[np.ndarray, List[str], List[str]]:
    """
    Build QUBO matrix Q for ns_green optimisation.

    Variables: one binary var x_{i,k} per (intersection i, level k).
    Total variables: n_intersections × NUM_QUBO_LEVELS.
    ew_green is derived as CYCLE_SEC − ns_green; not a separate variable.

    Objective:
        - Reward high ns_green for congested NS approaches.
        - Reward high ew_green (= low ns_green) for congested EW approaches.
        - Penalise adjacent intersections both selecting max green for same axis.

    Constraints:
        - One-hot: exactly one level k selected per intersection.

    Args:
        traffic_input:  TrafficInput — vehicle counts per approach.
        penalty_lambda: One-hot constraint weight (default 5.0).

    Returns:
        Q:          np.ndarray shape (N, N), symmetrised upper-triangular.
        var_labels: list[str] e.g. ["(0,0)_lvl0", "(0,0)_lvl1", ...]
        keys:       list[str] — sorted intersection IDs (same order throughout).

    Raises:
        ValueError: if traffic_input is empty.
    """
    validate_traffic_input(traffic_input)

    keys      = sorted(traffic_input.keys())
    n_inter   = len(keys)
    n_vars    = n_inter * NUM_QUBO_LEVELS
    Q         = np.zeros((n_vars, n_vars))

    def idx(i: int, k: int) -> int:
        return i * NUM_QUBO_LEVELS + k

    for i, key in enumerate(keys):
        counts  = traffic_input[key]
        ns_c    = counts["ns_count"]
        ew_c    = counts["ew_count"]
        total   = ns_c + ew_c
        # Congestion score per approach ∈ [0, 1]
        ns_score = min(ns_c / MAX_CAPACITY, 1.0)
        ew_score = min(ew_c / MAX_CAPACITY, 1.0)

        # -- Objective (diagonal) -------------------------------------------
        for k, ns_green in enumerate(DISCRETE_LEVELS):
            ew_green      = CYCLE_SEC - ns_green
            ns_fraction   = ns_green / CYCLE_SEC
            ew_fraction   = ew_green / CYCLE_SEC
            # Reward: high ns_green when NS congested, high ew_green when EW congested
            reward = ns_score * ns_fraction + ew_score * ew_fraction
            Q[idx(i, k), idx(i, k)] -= reward

        # -- One-hot constraint (penalty) ------------------------------------
        for k1 in range(NUM_QUBO_LEVELS):
            Q[idx(i, k1), idx(i, k1)] -= penalty_lambda   # linear term
            for k2 in range(k1 + 1, NUM_QUBO_LEVELS):
                Q[idx(i, k1), idx(i, k2)] += penalty_lambda

        # -- Neighbour conflict penalty --------------------------------------
        r_i, c_i = _parse_key(key)
        for j in range(i + 1, n_inter):
            other_key = keys[j]
            r_j, c_j  = _parse_key(other_key)
            if abs(r_i - r_j) + abs(c_i - c_j) != 1:
                continue   # only direct neighbours
            # Penalise both choosing the same maximum-green level
            ns_conflict = min(ns_score, min(traffic_input[other_key]["ns_count"] / MAX_CAPACITY, 1.0))
            ew_conflict = min(ew_score, min(traffic_input[other_key]["ew_count"] / MAX_CAPACITY, 1.0))
            conflict = (ns_conflict + ew_conflict) / 2
            for k in range(NUM_QUBO_LEVELS):
                Q[idx(i, k), idx(j, k)] += conflict * 2.0

    # Symmetrise
    Q = (Q + Q.T) / 2

    var_labels = [f"{key}_lvl{k}" for key in keys for k in range(NUM_QUBO_LEVELS)]
    return Q, var_labels, keys


# ---------------------------------------------------------------------------
# decode_solution  (G8)
# ---------------------------------------------------------------------------
def decode_solution(
    bitstring: str,
    keys:      List[str],
) -> TimingPlan:
    """
    Decode a QAOA/QUBO bitstring → TimingPlan.

    ew_green is derived as CYCLE_SEC − ns_green.
    If no bit is set for an intersection (invalid), defaults to equal split (30/30).

    Args:
        bitstring: Binary string, length == len(keys) × NUM_QUBO_LEVELS.
        keys:      Ordered intersection IDs from build_qubo().

    Returns:
        TimingPlan — every entry guaranteed to satisfy cycle constraints.

    Raises:
        ValueError: if bitstring length mismatches.
    """
    expected = len(keys) * NUM_QUBO_LEVELS
    if len(bitstring) != expected:
        raise ValueError(
            f"Bitstring length {len(bitstring)} != expected {expected} "
            f"({len(keys)} intersections × {NUM_QUBO_LEVELS} levels)."
        )

    timing_plan: TimingPlan = {}
    for i, key in enumerate(keys):
        segment  = bitstring[i * NUM_QUBO_LEVELS : (i + 1) * NUM_QUBO_LEVELS]
        ns_green = CYCLE_SEC // 2  # default: equal split

        for k, bit in enumerate(segment):
            if bit == "1":
                ns_green = DISCRETE_LEVELS[k]
                break    # one-hot: use first active level

        ew_green = CYCLE_SEC - ns_green
        timing_plan[key] = ApproachTiming(ns_green=ns_green, ew_green=ew_green)

    return timing_plan


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_NAMED_COORDS = {"A": (0, 0), "B": (0, 1), "C": (1, 0), "D": (1, 1)}

def _parse_key(key: str) -> Tuple[int, int]:
    """Parse '(row,col)' or 'A'-'D' → (int, int)."""
    if key in _NAMED_COORDS:
        return _NAMED_COORDS[key]
    stripped = key.strip("()")
    r, c = stripped.split(",")
    return int(r), int(c)


# ---------------------------------------------------------------------------
# 4-Variable Binary Timing QUBO Formulation
# ---------------------------------------------------------------------------
from quantum.binary_qubo import (  # noqa: E402
    GRID_EDGES,
    NUM_VARIABLES,
    PLAN_0_TIMING,
    PLAN_1_TIMING,
    build_binary_qubo,
    compute_intended_cost,
    compute_intersection_delay,
    compute_local_delay_terms,
    evaluate_qubo_energy,
    get_edge_coordination_weights,
    verify_qubo_against_intended_cost,
)

