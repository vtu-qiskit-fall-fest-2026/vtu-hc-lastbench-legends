"""
QuantumFlow — Test Suite: Genuine QAOA Quantum Solver
tests/test_quantum_solver.py  ·  Owner: Quantum Engineer

Validates:
  1. Execution of genuine QAOA on small known optimization example with analytical minimum.
  2. Conversion of 4-variable traffic QUBO into Qiskit QuadraticProgram.
  3. Execution of genuine QAOA on 4-variable traffic QUBO using local Aer simulator.
  4. Compliance with agreed SolverResult schema (algorithm, timing_plan, cost, metrics, runtime_ms, status, error_msg).
  5. Robust failure handling (timeouts, missing outcomes, invalid bitstrings, solver exceptions)
     without fabricating successful quantum results.
  6. Full quantum workflow benchmark and objective gap against exhaustive classical search.
  7. Architectural constraints (no Flask imports).
"""

from __future__ import annotations

import sys
from unittest.mock import patch
import numpy as np
import pytest

from quantum.binary_qubo import build_binary_qubo
from quantum.quantum_solver import (
    QAOAMeasurementSample,
    evaluate_quantum_workflow,
    execute_qaoa,
    qubo_to_quadratic_program,
    run_qaoa,
    run_small_example,
    solve_traffic_qubo,
)
from shared.types import ApproachCounts, SolverResult, TrafficInput
from shared.validators import validate_timing_plan, validate_traffic_input
from simulator.traffic_simulator import TrafficSimulator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def benchmark_traffic() -> TrafficInput:
    """Benchmark traffic from TrafficSimulator (A=45/12, B=30/20, C=10/40, D=25/15)."""
    return TrafficSimulator().get_traffic_input(as_grid=False)


@pytest.fixture
def grid_traffic() -> TrafficInput:
    """Same traffic in 2x2 grid coordinate format."""
    return TrafficSimulator().get_traffic_input(as_grid=True)


# ---------------------------------------------------------------------------
# 1. Known Small Optimization Example Tests
# ---------------------------------------------------------------------------
class TestKnownSmallExample:
    """Verify QAOA performance on analytically known 2-variable problem."""

    def test_small_example_finds_analytical_ground_state(self):
        res = run_small_example(p_layers=1, shots=1024, maxiter=50, seed=42)
        assert res["fval"] == -1.0
        assert res["best_x"] in ([0, 1], [1, 0])
        assert res["bitstring"] in ("01", "10")
        assert res["is_optimal"] is True
        assert res["runtime_ms"] > 0.0

    def test_small_example_measurement_distribution(self):
        res = run_small_example(p_layers=1, shots=1024, maxiter=50, seed=42)
        samples = res["samples"]
        assert len(samples) == 4

        # Total probability must sum to ~1.0
        prob_sum = sum(s["probability"] for s in samples)
        assert abs(prob_sum - 1.0) < 1e-4

        # Top states should be the degenerate ground states |01> and |10>
        top_two_bitstrings = {samples[0]["bitstring"], samples[1]["bitstring"]}
        assert top_two_bitstrings == {"01", "10"}

    def test_reproducibility_with_seed(self):
        res1 = run_small_example(p_layers=1, shots=512, maxiter=30, seed=123)
        res2 = run_small_example(p_layers=1, shots=512, maxiter=30, seed=123)
        assert res1["bitstring"] == res2["bitstring"]
        assert res1["fval"] == res2["fval"]
        assert len(res1["samples"]) == len(res2["samples"])
        for s1, s2 in zip(res1["samples"], res2["samples"]):
            assert s1["bitstring"] == s2["bitstring"]
            assert s1["fval"] == s2["fval"]


# ---------------------------------------------------------------------------
# 2. QUBO to QuadraticProgram Conversion Tests
# ---------------------------------------------------------------------------
class TestQUBOToQuadraticProgram:
    """Verify matrix conversion preserves linear, quadratic, and constant terms."""

    def test_upper_triangular_qubo_conversion(self, benchmark_traffic):
        Q, offset, labels = build_binary_qubo(benchmark_traffic, coord_weight=5.0, symmetrize=False)
        qp = qubo_to_quadratic_program(Q, offset, labels)

        assert qp.get_num_binary_vars() == 4
        assert [v.name for v in qp.variables] == labels
        assert abs(qp.objective.constant - offset) < 1e-9

        # Linear coefficients match diagonal
        for i, name in enumerate(labels):
            assert abs(qp.objective.linear[name] - Q[i, i]) < 1e-9

    def test_symmetric_qubo_conversion_yields_identical_qp(self, benchmark_traffic):
        Q_upper, offset_upper, labels = build_binary_qubo(benchmark_traffic, coord_weight=5.0, symmetrize=False)
        Q_sym, offset_sym, _ = build_binary_qubo(benchmark_traffic, coord_weight=5.0, symmetrize=True)

        qp_upper = qubo_to_quadratic_program(Q_upper, offset_upper, labels)
        qp_sym = qubo_to_quadratic_program(Q_sym, offset_sym, labels)

        assert qp_upper.objective.constant == qp_sym.objective.constant
        assert qp_upper.objective.linear.to_dict() == qp_sym.objective.linear.to_dict()
        assert qp_upper.objective.quadratic.to_dict() == qp_sym.objective.quadratic.to_dict()

    def test_dimension_mismatch_raises(self):
        Q = np.zeros((3, 3))
        with pytest.raises(ValueError, match="does not match"):
            qubo_to_quadratic_program(Q, 0.0, ["x0", "x1", "x2", "x3"])


# ---------------------------------------------------------------------------
# 3. SolverResult Schema & Full Traffic QAOA Execution
# ---------------------------------------------------------------------------
class TestSolveTrafficQUBO:
    """Verify genuine QAOA execution and SolverResult schema compliance."""

    def test_solver_result_schema_compliance(self, benchmark_traffic):
        res = solve_traffic_qubo(
            traffic_input=benchmark_traffic,
            coord_weight=0.0,
            p_layers=1,
            shots=512,
            maxiter=30,
            seed=42,
        )

        # 1. Exact top-level SolverResult keys per docs/INTERFACES.md §2.4
        for expected_key in ("algorithm", "timing_plan", "cost", "metrics", "runtime_ms", "status", "error_msg"):
            assert expected_key in res, f"Missing required SolverResult key: {expected_key}"

        assert res["algorithm"] == "qaoa"
        assert res["status"] == "ok"
        assert res["error_msg"] is None
        assert isinstance(res["cost"], float)
        assert res["runtime_ms"] > 0.0

        # 2. Timing plan validation
        validate_timing_plan(res["timing_plan"], benchmark_traffic)
        for iid in ("A", "B", "C", "D"):
            assert iid in res["timing_plan"]
            timing = res["timing_plan"][iid]
            assert timing["ns_green"] + timing["ew_green"] == 60
            assert 15 <= timing["ns_green"] <= 45
            assert 15 <= timing["ew_green"] <= 45

        # 3. Metrics compliance with shared traffic model
        m = res["metrics"]
        assert m["total_vehicles"] == 197
        assert 0 <= m["vehicles_served"] <= 197
        assert m["remaining_queue"] == 197 - m["vehicles_served"]
        assert m["avg_wait_sec"] >= 0.0
        assert m["total_delay_sec"] >= 0.0
        assert m["runtime_ms"] == res["runtime_ms"]

        # 4. Quantum diagnostics attached
        assert "bitstring" in res
        assert len(res["bitstring"]) == 4
        assert res["variable_names"] == ["x_A", "x_B", "x_C", "x_D"]

    def test_solve_traffic_qubo_with_grid_input(self, grid_traffic):
        res = solve_traffic_qubo(
            traffic_input=grid_traffic,
            coord_weight=0.0,
            p_layers=1,
            shots=512,
            maxiter=30,
            seed=42,
        )
        assert res["status"] == "ok"
        validate_timing_plan(res["timing_plan"], grid_traffic)
        assert set(res["timing_plan"].keys()) == {"(0,0)", "(0,1)", "(1,0)", "(1,1)"}

    def test_solve_traffic_qubo_p2_layers(self, benchmark_traffic):
        res = solve_traffic_qubo(
            traffic_input=benchmark_traffic,
            coord_weight=0.0,
            p_layers=2,
            shots=256,
            maxiter=20,
            seed=42,
        )
        assert res["status"] == "ok"
        assert len(res["bitstring"]) == 4
        validate_timing_plan(res["timing_plan"], benchmark_traffic)


# ---------------------------------------------------------------------------
# 4. Error, Timeout, and Failure Handling (Never Fabricating Results)
# ---------------------------------------------------------------------------
class TestFailureHandlingWithoutFabrication:
    """Verify that timeouts, missing outcomes, and exceptions do NOT fabricate 'ok' status."""

    def test_timeout_returns_timeout_status_and_no_cost(self, benchmark_traffic):
        # Set timeout_sec to 0.0001s to force timeout
        res = solve_traffic_qubo(
            traffic_input=benchmark_traffic,
            timeout_sec=0.0001,
        )
        assert res["status"] == "timeout"
        assert res["cost"] is None  # Never fabricate quantum cost on timeout
        assert res["error_msg"] is not None
        assert "timeout" in res["error_msg"].lower()
        # Fallback plan is present and valid
        validate_timing_plan(res["timing_plan"], benchmark_traffic)

    def test_solver_exception_returns_error_status_and_no_cost(self, benchmark_traffic):
        # Force exception by patching execute_qaoa
        with patch("quantum.quantum_solver.execute_qaoa", side_effect=RuntimeError("Simulated quantum crash")):
            res = solve_traffic_qubo(benchmark_traffic)
            assert res["status"] == "error"
            assert res["cost"] is None
            assert res["error_msg"] is not None
            assert "Simulated quantum crash" in res["error_msg"]
            validate_timing_plan(res["timing_plan"], benchmark_traffic)

    def test_missing_samples_returns_infeasible_status(self, benchmark_traffic):
        # Mock empty samples
        empty_output = {
            "best_x": [0, 0, 0, 0],
            "bitstring": "0000",
            "fval": 0.0,
            "samples": [],
            "runtime_ms": 10.0,
            "optimal_parameters": None,
            "var_names": ["x_A", "x_B", "x_C", "x_D"],
        }
        with patch("quantum.quantum_solver.execute_qaoa", return_value=empty_output):
            res = solve_traffic_qubo(benchmark_traffic)
            assert res["status"] == "infeasible"
            assert res["cost"] is None
            assert "Missing measurement outcomes" in res["error_msg"]

    def test_invalid_bitstring_returns_infeasible_status(self, benchmark_traffic):
        bad_output = {
            "best_x": [0, 0],
            "bitstring": "00",  # Only 2 bits instead of 4
            "fval": 100.0,
            "samples": [{"bitstring": "00", "fval": 100.0, "probability": 1.0, "status": "SUCCESS"}],
            "runtime_ms": 10.0,
            "optimal_parameters": None,
            "var_names": ["x_A", "x_B", "x_C", "x_D"],
        }
        with patch("quantum.quantum_solver.execute_qaoa", return_value=bad_output):
            res = solve_traffic_qubo(benchmark_traffic)
            assert res["status"] == "infeasible"
            assert res["cost"] is None
            assert "Invalid measurement bitstring" in res["error_msg"]

    def test_invalid_traffic_input_returns_error(self):
        res = solve_traffic_qubo({})
        assert res["status"] == "error"
        assert res["cost"] is None
        assert "Invalid traffic input" in res["error_msg"]


# ---------------------------------------------------------------------------
# 5. Full Quantum Workflow & Gap Analysis Tests
# ---------------------------------------------------------------------------
class TestQuantumWorkflowAndGapAnalysis:
    """Verify complete workflow and gap comparison against classical search."""

    def test_evaluate_quantum_workflow_finds_optimum_on_benchmark(self, benchmark_traffic):
        report = evaluate_quantum_workflow(
            traffic_input=benchmark_traffic,
            coord_weight=0.0,
            p_layers=1,
            shots=1024,
            maxiter=50,
            seed=42,
        )

        assert report["status"] == "ok"
        assert report["qaoa_bitstring"] == "0010"
        assert report["exhaustive_bitstring"] == "0010"
        assert report["is_exact_optimum"] is True

        # Objective gap: E_qaoa - E_exact == 0.0
        assert report["objective_gap"] == 0.0
        assert report["wait_gap_sec"] == 0.0
        assert report["qaoa_total_delay_sec"] == 2085.0
        assert report["exhaustive_total_delay_sec"] == 2085.0
        assert report["qaoa_avg_wait_sec"] == 10.58
        assert report["qaoa_vehicles_served"] == 116
        assert report["qaoa_runtime_ms"] > 0.0
        assert report["exhaustive_runtime_ms"] > 0.0


# ---------------------------------------------------------------------------
# 6. Multi-Scenario Benchmarking & Repeated Runs
# ---------------------------------------------------------------------------
class TestMultiScenarioAndRepeatedRuns:
    """Verify timing constraints, gap comparison, and reproducibility across scenarios."""

    @pytest.mark.parametrize("scenario_name, generator_fn", [
        ("light", lambda sim: sim.generate_scenario("light", seed=10)),
        ("medium", lambda sim: sim.generate_scenario("medium", seed=20)),
        ("heavy", lambda sim: sim.generate_scenario("heavy", seed=30)),
        ("ns_dominant", lambda sim: {iid: ApproachCounts(ns_count=45, ew_count=5) for iid in ("A", "B", "C", "D")}),
        ("ew_dominant", lambda sim: {iid: ApproachCounts(ns_count=5, ew_count=45) for iid in ("A", "B", "C", "D")}),
        ("checkerboard", lambda sim: {
            "A": ApproachCounts(ns_count=40, ew_count=10),
            "B": ApproachCounts(ns_count=10, ew_count=40),
            "C": ApproachCounts(ns_count=40, ew_count=10),
            "D": ApproachCounts(ns_count=10, ew_count=40),
        }),
        ("zero", lambda sim: {iid: ApproachCounts(ns_count=0, ew_count=0) for iid in ("A", "B", "C", "D")}),
    ])
    def test_scenarios_satisfy_timing_constraints_and_compare_to_classical(self, scenario_name, generator_fn):
        sim = TrafficSimulator()
        traffic_input = generator_fn(sim)

        report = evaluate_quantum_workflow(
            traffic_input=traffic_input,
            coord_weight=0.0,
            p_layers=1,
            shots=1024,
            maxiter=50,
            seed=42,
        )

        assert report["status"] == "ok"
        # Validate all timing constraints
        validate_timing_plan(report["qaoa_result"]["timing_plan"], traffic_input)

        # Gap comparison: QAOA should equal or closely approximate exact classical optimum
        assert report["objective_gap"] is not None
        assert report["objective_gap"] >= -1e-6  # QAOA can never be lower than exact classical global minimum
        assert report["objective_gap"] == pytest.approx(0.0, abs=1e-3)
        assert report["is_exact_optimum"] is True

        # Runtimes must be honestly positive
        assert report["qaoa_runtime_ms"] > 0.0
        assert report["exhaustive_runtime_ms"] > 0.0

    @pytest.mark.parametrize("seed", [42, 101, 2024, 7, 999])
    def test_repeated_runs_stability(self, benchmark_traffic, seed):
        sol = solve_traffic_qubo(
            traffic_input=benchmark_traffic,
            coord_weight=0.0,
            p_layers=1,
            shots=1024,
            maxiter=50,
            seed=seed,
        )
        assert sol["status"] == "ok"
        assert sol["cost"] is not None
        # Must strictly satisfy timing constraints
        validate_timing_plan(sol["timing_plan"], benchmark_traffic)
        # Should converge to global optimum bitstring 0010
        assert sol["bitstring"] == "0010"
        assert sol["cost"] == pytest.approx(2085.0, abs=1e-3)


# ---------------------------------------------------------------------------
# 7. Architecture and File Ownership Constraints
# ---------------------------------------------------------------------------
class TestQuantumSolverArchitecture:
    """Verify architectural boundaries and forbidden import checks."""

    def test_no_flask_in_quantum_solver(self):
        import quantum.quantum_solver as qs_mod
        with open(qs_mod.__file__, "r", encoding="utf-8") as f:
            content = f.read()
        assert "flask" not in content, "quantum_solver.py must NOT import flask"

    def test_root_quantum_solver_no_flask(self):
        with open("quantum_solver.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "flask" not in content, "Root quantum_solver.py must NOT import flask"

