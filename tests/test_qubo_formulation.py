"""
QuantumFlow — Automated Equality Tests: 4-Variable Binary Timing QUBO
tests/test_qubo_formulation.py  ·  Owner: Quantum Engineer

Automated tests proving:
  1. The QUBO energy E(x) = x^T * Q * x + offset EXACTLY equals the intended cost
     C_intended(x) for ALL 16 bitstrings across multiple traffic scenarios.
  2. The formulation holds identically for both upper-triangular and symmetric matrices.
  3. Neighbor-coordination penalties apply strictly to the 4 defined network edges
     and vanish when adjacent intersections are synchronized.
  4. The discrete ground state of the QUBO matches the exact optimum from the
     reference enumerator.
"""

from __future__ import annotations

import sys
import numpy as np
import pytest

from quantum.binary_qubo import (
    GRID_EDGES,
    NUM_VARIABLES,
    PLAN_0_TIMING,
    PLAN_1_TIMING,
    build_binary_qubo,
    compute_intended_cost,
    compute_intersection_delay,
    evaluate_qubo_energy,
    get_edge_coordination_weights,
    verify_qubo_against_intended_cost,
)
from quantum.reference_enumerator import (
    ALL_BITSTRINGS,
    DEFAULT_INTERSECTIONS,
    GRID_INTERSECTIONS,
    find_optimal_plan,
)
from shared.types import ApproachCounts, TrafficInput
from shared.validators import validate_traffic_input


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def benchmark_traffic() -> TrafficInput:
    """Benchmark traffic counts from simulator (A=45/12, B=30/20, C=10/40, D=25/15)."""
    return {
        "A": ApproachCounts(ns_count=45, ew_count=12),
        "B": ApproachCounts(ns_count=30, ew_count=20),
        "C": ApproachCounts(ns_count=10, ew_count=40),
        "D": ApproachCounts(ns_count=25, ew_count=15),
    }


@pytest.fixture
def grid_traffic() -> TrafficInput:
    """Same benchmark counts using 2x2 grid coordinates."""
    return {
        "(0,0)": ApproachCounts(ns_count=45, ew_count=12),
        "(0,1)": ApproachCounts(ns_count=30, ew_count=20),
        "(1,0)": ApproachCounts(ns_count=10, ew_count=40),
        "(1,1)": ApproachCounts(ns_count=25, ew_count=15),
    }


@pytest.fixture
def zero_traffic() -> TrafficInput:
    """Empty grid (zero vehicles everywhere)."""
    return {
        iid: ApproachCounts(ns_count=0, ew_count=0)
        for iid in DEFAULT_INTERSECTIONS
    }


@pytest.fixture
def ns_heavy_traffic() -> TrafficInput:
    """Heavily congested North-South traffic."""
    return {
        iid: ApproachCounts(ns_count=50, ew_count=5)
        for iid in DEFAULT_INTERSECTIONS
    }


@pytest.fixture
def ew_heavy_traffic() -> TrafficInput:
    """Heavily congested East-West traffic."""
    return {
        iid: ApproachCounts(ns_count=5, ew_count=50)
        for iid in DEFAULT_INTERSECTIONS
    }


# ---------------------------------------------------------------------------
# 1. Exact Equality Tests: QUBO Energy == Intended Cost
# ---------------------------------------------------------------------------
class TestQUBOEnergyExactEquality:
    """Automated equality tests proving E(x) == C_intended(x) for all 16 bitstrings."""

    @pytest.mark.parametrize("bitstring", ALL_BITSTRINGS)
    def test_pure_delay_exact_equality(self, benchmark_traffic, bitstring):
        """Pure delay (coord_weight = 0.0): E(x) must match C(x) exactly."""
        Q_upper, offset, _ = build_binary_qubo(benchmark_traffic, coord_weight=0.0, symmetrize=False)
        Q_sym, _, _ = build_binary_qubo(benchmark_traffic, coord_weight=0.0, symmetrize=True)

        intended = compute_intended_cost(benchmark_traffic, bitstring, coord_weight=0.0)
        e_upper = evaluate_qubo_energy(Q_upper, offset, bitstring)
        e_sym = evaluate_qubo_energy(Q_sym, offset, bitstring)

        assert abs(e_upper - intended) < 1e-9, f"Bitstring {bitstring}: upper energy mismatch"
        assert abs(e_sym - intended) < 1e-9, f"Bitstring {bitstring}: symmetric energy mismatch"

    @pytest.mark.parametrize("bitstring", ALL_BITSTRINGS)
    def test_delay_plus_coordination_exact_equality(self, benchmark_traffic, bitstring):
        """Delay + neighbor coordination (coord_weight = 5.0): E(x) must match C(x) exactly."""
        coord_weight = 5.0
        Q_upper, offset, _ = build_binary_qubo(benchmark_traffic, coord_weight=coord_weight, symmetrize=False)
        Q_sym, _, _ = build_binary_qubo(benchmark_traffic, coord_weight=coord_weight, symmetrize=True)

        intended = compute_intended_cost(benchmark_traffic, bitstring, coord_weight=coord_weight)
        e_upper = evaluate_qubo_energy(Q_upper, offset, bitstring)
        e_sym = evaluate_qubo_energy(Q_sym, offset, bitstring)

        assert abs(e_upper - intended) < 1e-9, f"Bitstring {bitstring}: upper energy mismatch"
        assert abs(e_sym - intended) < 1e-9, f"Bitstring {bitstring}: symmetric energy mismatch"

    def test_comprehensive_verification_report(self, benchmark_traffic):
        report = verify_qubo_against_intended_cost(benchmark_traffic, coord_weight=10.0)
        assert report["all_passed"] is True
        assert report["max_discrepancy"] < 1e-9
        assert len(report["evaluations"]) == 16


# ---------------------------------------------------------------------------
# 2. Multi-Scenario Validation
# ---------------------------------------------------------------------------
class TestMultiScenarioValidation:
    """Verify exact equality across diverse traffic scenarios."""

    def test_grid_coordinate_traffic_input(self, grid_traffic):
        report = verify_qubo_against_intended_cost(
            grid_traffic,
            coord_weight=7.5,
            intersections=GRID_INTERSECTIONS,
        )
        assert report["all_passed"] is True
        assert report["max_discrepancy"] < 1e-9

    def test_zero_traffic_all_energies_zero(self, zero_traffic):
        report = verify_qubo_against_intended_cost(zero_traffic, coord_weight=0.0)
        assert report["all_passed"] is True
        assert report["max_discrepancy"] < 1e-9
        for ev in report["evaluations"]:
            assert ev["intended_cost"] == 0.0
            assert ev["energy_upper"] == 0.0

    def test_ns_heavy_traffic(self, ns_heavy_traffic):
        report = verify_qubo_against_intended_cost(ns_heavy_traffic, coord_weight=4.0)
        assert report["all_passed"] is True
        assert report["max_discrepancy"] < 1e-9

    def test_ew_heavy_traffic(self, ew_heavy_traffic):
        report = verify_qubo_against_intended_cost(ew_heavy_traffic, coord_weight=4.0)
        assert report["all_passed"] is True
        assert report["max_discrepancy"] < 1e-9


# ---------------------------------------------------------------------------
# 3. Matrix Topology & Edge Constraints
# ---------------------------------------------------------------------------
class TestQUBOMatrixTopology:
    """Verify matrix dimensions, edge sparsity, and symmetry properties."""

    def test_matrix_shape_and_labels(self, benchmark_traffic):
        Q, offset, labels = build_binary_qubo(benchmark_traffic)
        assert Q.shape == (NUM_VARIABLES, NUM_VARIABLES)
        assert labels == ["x_A", "x_B", "x_C", "x_D"]
        assert isinstance(offset, float)

    def test_non_edges_are_strictly_zero(self, benchmark_traffic):
        """In a 2x2 grid, diagonals (0,3) and (1,2) have no physical edge and must be 0."""
        Q, _, _ = build_binary_qubo(benchmark_traffic, coord_weight=10.0, symmetrize=False)
        # Non-edge (A, D) = (0, 3)
        assert Q[0, 3] == 0.0
        # Non-edge (B, C) = (1, 2)
        assert Q[1, 2] == 0.0

    def test_symmetric_matrix_is_symmetric(self, benchmark_traffic):
        Q_sym, _, _ = build_binary_qubo(benchmark_traffic, coord_weight=8.0, symmetrize=True)
        np.testing.assert_array_almost_equal(Q_sym, Q_sym.T, decimal=12)

    def test_edge_coordination_vanishes_when_synchronized(self):
        """When x_u == x_v across all edges, coordination penalty must be exactly 0."""
        # '0000' and '1111' have all intersections synchronized
        counts: TrafficInput = {
            iid: ApproachCounts(ns_count=10, ew_count=10)
            for iid in DEFAULT_INTERSECTIONS
        }
        for synch_b in ("0000", "1111"):
            cost_coord = compute_intended_cost(counts, synch_b, coord_weight=10.0)
            cost_uncoord = compute_intended_cost(counts, synch_b, coord_weight=0.0)
            assert cost_coord == cost_uncoord, f"Coordination penalty did not vanish for {synch_b}"

    def test_custom_edge_weights(self, benchmark_traffic):
        custom_weights = {
            (0, 1): 25.0,  # A-B East-West corridor
            (0, 2): 15.0,  # A-C North-South corridor
            (1, 3): 10.0,  # B-D North-South corridor
            (2, 3): 30.0,  # C-D East-West corridor
        }
        Q_upper, offset, _ = build_binary_qubo(
            benchmark_traffic,
            custom_edge_weights=custom_weights,
            symmetrize=False,
        )
        # Verify off-diagonal entries match -2 * gamma
        assert Q_upper[0, 1] == -2.0 * 25.0
        assert Q_upper[0, 2] == -2.0 * 15.0
        assert Q_upper[1, 3] == -2.0 * 10.0
        assert Q_upper[2, 3] == -2.0 * 30.0

        report = verify_qubo_against_intended_cost(
            benchmark_traffic,
            custom_edge_weights=custom_weights,
        )
        assert report["all_passed"] is True


# ---------------------------------------------------------------------------
# 4. Ground State & Optimality Alignment
# ---------------------------------------------------------------------------
class TestOptimalityAlignment:
    """Verify that QUBO ground state matches the exact discrete optimum."""

    def test_ground_state_matches_reference_enumerator(self, benchmark_traffic):
        # 1. Reference enumerator optimum
        best_ref = find_optimal_plan(benchmark_traffic, objective="total_delay_sec")

        # 2. Minimum QUBO energy state
        Q, offset, _ = build_binary_qubo(benchmark_traffic, coord_weight=0.0)
        energies = {b: evaluate_qubo_energy(Q, offset, b) for b in ALL_BITSTRINGS}
        best_qubo_bitstring = min(energies, key=energies.get)

        assert best_qubo_bitstring == best_ref["bitstring"]
        assert abs(energies[best_qubo_bitstring] - best_ref["total_delay_sec"]) < 1e-9


# ---------------------------------------------------------------------------
# 5. Integration and Architectural Separation
# ---------------------------------------------------------------------------
class TestQUBOModuleIntegration:
    """Verify module exports, import restrictions, and error handling."""

    def test_re_exported_in_qubo_builder(self):
        from quantum.qubo_builder import (
            build_binary_qubo as builder_build_binary,
            GRID_EDGES as builder_edges,
        )
        assert builder_build_binary is build_binary_qubo
        assert builder_edges == GRID_EDGES

    def test_no_forbidden_imports(self):
        import quantum.binary_qubo as bq_mod
        with open(bq_mod.__file__, "r", encoding="utf-8") as f:
            content = f.read()
        assert "flask" not in content
        assert "qiskit" not in content

    def test_invalid_bitstring_length_raises(self, benchmark_traffic):
        Q, offset, _ = build_binary_qubo(benchmark_traffic)
        with pytest.raises(ValueError, match="Bitstring length"):
            evaluate_qubo_energy(Q, offset, "01")

    def test_invalid_traffic_input_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_binary_qubo({})
