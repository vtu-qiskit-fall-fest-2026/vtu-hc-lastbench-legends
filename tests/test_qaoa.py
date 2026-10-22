"""
QuantumFlow — Test Suite: Quantum Environment & QAOA Runner
tests/test_qaoa.py  ·  Owner: Quantum Engineer

Validates:
  - Python / Qiskit / Qiskit-Aer / Qiskit-Optimization compatibility
  - Minimal measured quantum circuit execution on local Aer simulator
  - Qiskit Optimization QuadraticProgram formulation
  - QAOA solver execution on local simulator with real traffic inputs
  - Architecture constraint: no Flask imports in quantum modules
"""

import sys
import pytest

from shared.types import ApproachCounts
from shared.validators import validate_timing_plan, validate_traffic_input
from simulator.traffic_simulator import TrafficSimulator


# ===========================================================================
# 1. Quantum Environment Compatibility Tests
# ===========================================================================
class TestQuantumEnvironment:
    """Check that quantum packages are installed and mutually compatible."""

    def test_qiskit_version(self):
        import qiskit
        assert qiskit.__version__.startswith("1.2."), f"Unexpected Qiskit version: {qiskit.__version__}"

    def test_qiskit_aer_version(self):
        import qiskit_aer
        assert qiskit_aer.__version__.startswith("0.14."), f"Unexpected Qiskit Aer version: {qiskit_aer.__version__}"

    def test_qiskit_algorithms_version(self):
        import qiskit_algorithms
        assert qiskit_algorithms.__version__.startswith("0.3."), f"Unexpected Qiskit Algorithms version: {qiskit_algorithms.__version__}"

    def test_qiskit_optimization_version(self):
        import qiskit_optimization
        assert qiskit_optimization.__version__.startswith("0.7."), f"Unexpected Qiskit Optimization version: {qiskit_optimization.__version__}"

    def test_numpy_compatibility(self):
        import numpy as np
        # Qiskit 1.2 and Aer 0.14 require NumPy 1.x (specifically <= 1.26.4 for binary wheels)
        assert np.__version__.startswith("1."), f"NumPy version must be 1.x for Qiskit Aer C-extensions, got {np.__version__}"


# ===========================================================================
# 2. Minimal Measured Quantum Circuit on Local Simulator
# ===========================================================================
class TestMinimalQuantumCircuit:
    """Run a minimal 2-qubit entangled Bell State on local Aer simulator."""

    def test_bell_state_measurement(self):
        from qiskit import QuantumCircuit
        from qiskit_aer import AerSimulator

        # Prepare |Phi+> = (|00> + |11>) / sqrt(2)
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        sim = AerSimulator()
        shots = 1024
        job = sim.run(qc, shots=shots)
        result = job.result()
        counts = result.get_counts()

        # In an ideal simulation of |Phi+>, only '00' and '11' are measured
        assert set(counts.keys()).issubset({"00", "11"})
        assert "00" in counts
        assert "11" in counts
        assert "01" not in counts
        assert "10" not in counts
        assert sum(counts.values()) == shots
        # Rough balance check (both states should have > 35% probability)
        assert counts["00"] > 350
        assert counts["11"] > 350


# ===========================================================================
# 3. Qiskit Optimization Integration Tests
# ===========================================================================
class TestQiskitOptimization:
    """Test QuadraticProgram formulation and MinimumEigenOptimizer integration."""

    def test_quadratic_program_solve(self):
        from qiskit_optimization import QuadraticProgram
        from qiskit_optimization.algorithms import MinimumEigenOptimizer
        from qiskit_algorithms import QAOA
        from qiskit_algorithms.optimizers import COBYLA
        from qiskit_aer.primitives import Sampler

        qp = QuadraticProgram("traffic_mini")
        qp.binary_var("x0")
        qp.binary_var("x1")
        # Objective: minimize -x0 - x1 + 2*x0*x1  (Optimal is [1, 0] or [0, 1] with val -1)
        qp.minimize(linear={"x0": -1, "x1": -1}, quadratic={("x0", "x1"): 2})

        sampler = Sampler()
        qaoa = QAOA(sampler=sampler, optimizer=COBYLA(maxiter=50), reps=1)
        optimizer = MinimumEigenOptimizer(qaoa)
        result = optimizer.solve(qp)

        assert result.fval == -1.0
        assert list(result.x) in ([1.0, 0.0], [0.0, 1.0])


# ===========================================================================
# 4. QAOA Runner Execution on Traffic Inputs
# ===========================================================================
class TestQAOARunner:
    """Verify run_qaoa() executes on Aer simulator and produces valid plans."""

    def test_run_qaoa_success(self):
        from quantum.qaoa_runner import run_qaoa

        traffic = TrafficSimulator().get_traffic_input(as_grid=True)
        validate_traffic_input(traffic)

        # Run with fast parameters for test execution (1 layer, 256 shots)
        res = run_qaoa(traffic, p_layers=1, shots=256)

        assert res["status"] == "ok"
        assert res["algorithm"] == "qaoa"
        assert res["cost"] is not None
        assert isinstance(res["cost"], float)
        assert res["error_msg"] is None

        # Verify timing plan satisfies all interface invariants
        validate_timing_plan(res["timing_plan"], traffic)

        # Verify metrics structure
        m = res["metrics"]
        assert m["total_vehicles"] == 197
        assert 0 <= m["vehicles_served"] <= m["total_vehicles"]
        assert m["remaining_queue"] == m["total_vehicles"] - m["vehicles_served"]
        assert m["avg_wait_sec"] >= 0.0

    def test_run_qaoa_with_named_intersections(self):
        from quantum.qaoa_runner import run_qaoa

        traffic = TrafficSimulator().get_traffic_input(as_grid=False)
        res = run_qaoa(traffic, p_layers=1, shots=128)

        assert res["status"] == "ok"
        assert set(res["timing_plan"].keys()) == {"A", "B", "C", "D"}
        validate_timing_plan(res["timing_plan"], traffic)


# ===========================================================================
# 5. Architecture & File Ownership Constraints
# ===========================================================================
class TestQuantumArchitectureConstraints:
    """Verify quantum module compliance with docs/INTERFACES.md §6."""

    def test_no_flask_in_quantum_modules(self):
        import ast

        for filepath in ("quantum/qubo_builder.py", "quantum/qaoa_runner.py"):
            with open(filepath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=filepath)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name != "flask", f"{filepath} imports flask directly"
                elif isinstance(node, ast.ImportFrom):
                    assert node.module != "flask", f"{filepath} imports from flask"
