"""
QuantumFlow — Test Suite: QUBO Builder
tests/test_qubo.py  ·  Owner: Quantum Engineer
"""

import pytest
import numpy as np
from shared.types import ApproachCounts
from shared.validators import CYCLE_SEC
from quantum.qubo_builder import (
    build_qubo,
    decode_solution,
    NUM_QUBO_LEVELS,
    DISCRETE_LEVELS,
    MIN_GREEN,
    MAX_GREEN,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def small_input():
    return {
        "(0,0)": ApproachCounts(ns_count=3, ew_count=1),
        "(0,1)": ApproachCounts(ns_count=0, ew_count=5),
        "(1,0)": ApproachCounts(ns_count=2, ew_count=2),
        "(1,1)": ApproachCounts(ns_count=1, ew_count=4),
    }


# ---------------------------------------------------------------------------
# build_qubo
# ---------------------------------------------------------------------------
class TestBuildQUBO:
    def test_matrix_shape(self, small_input):
        Q, labels, keys = build_qubo(small_input)
        n = len(small_input) * NUM_QUBO_LEVELS
        assert Q.shape == (n, n), f"Expected ({n},{n}), got {Q.shape}"

    def test_matrix_is_symmetric(self, small_input):
        Q, _, _ = build_qubo(small_input)
        np.testing.assert_array_almost_equal(Q, Q.T, decimal=10,
                                             err_msg="QUBO matrix must be symmetric")

    def test_var_labels_count(self, small_input):
        _, labels, keys = build_qubo(small_input)
        assert len(labels) == len(small_input) * NUM_QUBO_LEVELS

    def test_keys_sorted(self, small_input):
        _, _, keys = build_qubo(small_input)
        assert keys == sorted(small_input.keys())

    def test_label_format(self, small_input):
        _, labels, _ = build_qubo(small_input)
        for label in labels:
            assert "_lvl" in label, f"Unexpected label format: {label}"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            build_qubo({})

    def test_1x1_grid(self):
        """Single intersection — valid minimal case if validator allows it."""
        # 1×1 is not a valid grid (requires 2×2 min from validator).
        # Confirm ValueError is raised.
        with pytest.raises(ValueError):
            build_qubo({"(0,0)": ApproachCounts(ns_count=1, ew_count=1)})

    def test_diagonal_dominated_by_congestion(self, small_input):
        """High-congestion intersections should have more negative diagonal entries."""
        Q_high, _, _ = build_qubo({
            "(0,0)": ApproachCounts(ns_count=9, ew_count=0),
            "(0,1)": ApproachCounts(ns_count=0, ew_count=0),
            "(1,0)": ApproachCounts(ns_count=0, ew_count=0),
            "(1,1)": ApproachCounts(ns_count=0, ew_count=0),
        })
        Q_zero, _, _ = build_qubo({
            f"({r},{c})": ApproachCounts(ns_count=0, ew_count=0)
            for r in range(2) for c in range(2)
        })
        # Intersection 0's diagonal block should be more negative for high congestion
        sum_high = Q_high[:NUM_QUBO_LEVELS, :NUM_QUBO_LEVELS].diagonal().sum()
        sum_zero = Q_zero[:NUM_QUBO_LEVELS, :NUM_QUBO_LEVELS].diagonal().sum()
        assert sum_high < sum_zero, \
            "Congested intersection should have more negative diagonals"


# ---------------------------------------------------------------------------
# decode_solution
# ---------------------------------------------------------------------------
class TestDecodeSolution:
    def test_returns_timing_plan_keys(self, small_input):
        _, _, keys = build_qubo(small_input)
        bits = "0" * (len(keys) * NUM_QUBO_LEVELS)
        plan = decode_solution(bits, keys)
        assert set(plan.keys()) == set(keys)

    def test_cycle_constraint(self, small_input):
        _, _, keys = build_qubo(small_input)
        bits = "1000" * len(keys)   # level 0 for each intersection
        plan = decode_solution(bits, keys)
        for iid, timing in plan.items():
            assert timing["ns_green"] + timing["ew_green"] == CYCLE_SEC, \
                f"{iid}: cycle violated"

    def test_green_bounds(self, small_input):
        _, _, keys = build_qubo(small_input)
        for pattern in ["1000", "0100", "0010", "0001"]:
            bits = pattern * len(keys)
            plan = decode_solution(bits, keys)
            for iid, timing in plan.items():
                assert MIN_GREEN <= timing["ns_green"] <= MAX_GREEN
                assert MIN_GREEN <= timing["ew_green"] <= MAX_GREEN

    def test_level_0_gives_min_ns_green(self, small_input):
        _, _, keys = build_qubo(small_input)
        bits = "1000" * len(keys)
        plan = decode_solution(bits, keys)
        for timing in plan.values():
            assert timing["ns_green"] == DISCRETE_LEVELS[0] == MIN_GREEN

    def test_level_3_gives_max_ns_green(self, small_input):
        _, _, keys = build_qubo(small_input)
        bits = "0001" * len(keys)
        plan = decode_solution(bits, keys)
        for timing in plan.values():
            assert timing["ns_green"] == DISCRETE_LEVELS[3] == MAX_GREEN

    def test_wrong_bitstring_length_raises(self, small_input):
        _, _, keys = build_qubo(small_input)
        with pytest.raises(ValueError, match="Bitstring length"):
            decode_solution("101", keys)

    def test_all_zero_bitstring_defaults(self, small_input):
        """All-zero bitstring (no level set) → equal split fallback."""
        _, _, keys = build_qubo(small_input)
        bits = "0000" * len(keys)
        plan = decode_solution(bits, keys)
        for timing in plan.values():
            assert timing["ns_green"] == CYCLE_SEC // 2
            assert timing["ew_green"] == CYCLE_SEC // 2
