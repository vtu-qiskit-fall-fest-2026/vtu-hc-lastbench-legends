"""
QuantumFlow — 4-Bit Reference Enumerator
Root convenience module re-exporting quantum.reference_enumerator.
"""

from quantum.reference_enumerator import (
    ALL_BITSTRINGS,
    DEFAULT_CANDIDATE_PLANS,
    DEFAULT_INTERSECTIONS,
    GRID_CANDIDATE_PLANS,
    GRID_INTERSECTIONS,
    NUM_CANDIDATES_PER_INTERSECTION,
    NUM_COMBINATIONS,
    NUM_INTERSECTIONS,
    PLAN_EW_PRIORITY,
    PLAN_NS_PRIORITY,
    EnumerationRecord,
    ReferenceEnumerator,
    decode_bitstring,
    enumerate_all_plans,
    evaluate_bitstring,
    find_optimal_plan,
    resolve_candidate_plans,
    validate_candidate_pair,
)

__all__ = [
    "ALL_BITSTRINGS",
    "DEFAULT_CANDIDATE_PLANS",
    "DEFAULT_INTERSECTIONS",
    "GRID_CANDIDATE_PLANS",
    "GRID_INTERSECTIONS",
    "NUM_CANDIDATES_PER_INTERSECTION",
    "NUM_COMBINATIONS",
    "NUM_INTERSECTIONS",
    "PLAN_EW_PRIORITY",
    "PLAN_NS_PRIORITY",
    "EnumerationRecord",
    "ReferenceEnumerator",
    "decode_bitstring",
    "enumerate_all_plans",
    "evaluate_bitstring",
    "find_optimal_plan",
    "resolve_candidate_plans",
    "validate_candidate_pair",
]
