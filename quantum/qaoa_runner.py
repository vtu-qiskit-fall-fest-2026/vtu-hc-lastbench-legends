"""
QuantumFlow — QAOA Solver  (G11)
quantum/qaoa_runner.py  ·  Owner: Quantum Engineer

MUST NOT import flask or any web framework — enforced by CI lint check.

Implements:
  - run_qaoa()        — full QAOA via Qiskit Aer (or real IBMQ)
  - mock_qaoa_result() — deterministic mock for frontend development
"""

from __future__ import annotations

import os
import time
import warnings
from typing import Optional

import numpy as np

from shared.types import TrafficInput, SolverResult
from shared.validators import validate_traffic_input
from quantum.qubo_builder import build_qubo, decode_solution
from metrics.traffic_model import evaluate
from simulator.classical_solver import greedy_optimize   # used for timeout fallback


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_qaoa(
    traffic_input:    TrafficInput,
    p_layers:         int  = 1,
    shots:            int  = 1024,
    use_real_backend: bool = False,
) -> SolverResult:
    """
    Run QAOA on the Qiskit Aer simulator (or real IBMQ backend).

    Steps:
        1. Validate input.
        2. Build QUBO matrix via qubo_builder.build_qubo().
        3. Convert QUBO → Ising Hamiltonian (SparsePauliOp).
        4. Build QAOA ansatz with p_layers depth.
        5. Optimise with COBYLA via qiskit_algorithms.minimum_eigensolvers.QAOA.
        6. Sample best bitstring from result.
        7. Decode → TimingPlan via qubo_builder.decode_solution().
        8. Evaluate → SolverResult via metrics.traffic_model.evaluate().

    Args:
        traffic_input:    TrafficInput — same format as classical solver.
        p_layers:         QAOA circuit depth p (1–5). Default 1.
        shots:            Measurement shots. Default 1024.
        use_real_backend: If True, uses IBMQ (requires env var IBMQ_TOKEN).
                          Falls back to Aer if token is missing.

    Returns:
        SolverResult with algorithm="qaoa".
        On timeout (> 60 s):  status="timeout", timing_plan from greedy fallback.
        On error:             status="error",   error_msg=<message>.

    Raises:
        ImportError: if qiskit or qiskit-aer is not installed.
    """
    validate_traffic_input(traffic_input)

    # -- Import guard (gives a clean error if qiskit isn't installed) --------
    try:
        from qiskit_algorithms import QAOA
        from qiskit_algorithms.optimizers import COBYLA
        from qiskit.quantum_info import SparsePauliOp
        from qiskit_aer.primitives import Sampler as AerSampler
    except ImportError as exc:
        return _error_result(
            traffic_input,
            f"Qiskit import failed: {exc}. Run: pip install qiskit qiskit-aer qiskit-algorithms",
        )

    t0 = time.perf_counter()

    try:
        # 1. Build QUBO
        Q, var_labels, keys = build_qubo(traffic_input)
        n_vars = len(var_labels)

        # 2. QUBO → Ising (Z-basis Hamiltonian)
        hamiltonian, offset = _qubo_to_ising(Q, n_vars)

        # 3. Sampler
        if use_real_backend:
            sampler = _get_real_sampler()
        else:
            sampler = AerSampler()
            sampler.set_options(shots=shots)

        # 4. QAOA
        optimizer   = COBYLA(maxiter=200)
        qaoa_solver = QAOA(sampler=sampler, optimizer=optimizer, reps=p_layers)

        # 5. Solve
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # suppress DeprecationWarnings
            result = qaoa_solver.compute_minimum_eigenvalue(hamiltonian)

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Timeout guard
        if elapsed_ms > 60_000:
            fallback = greedy_optimize(traffic_input)
            return _timeout_result(traffic_input, elapsed_ms, fallback)

        # 6. Extract best bitstring
        bitstring = _best_bitstring(result, n_vars)

        # 7. Decode
        timing_plan = decode_solution(bitstring, keys)

        # 8. Evaluate
        raw_cost = float(np.real(result.eigenvalue)) + offset
        return evaluate(
            traffic_input=traffic_input,
            timing_plan=timing_plan,
            algorithm="qaoa",
            runtime_ms=elapsed_ms,
            cost=raw_cost,
        )

    except Exception as exc:  # pylint: disable=broad-except
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return _error_result(traffic_input, str(exc), runtime_ms=elapsed_ms)


def mock_qaoa_result(traffic_input: TrafficInput) -> SolverResult:
    """
    Deterministic mock SolverResult for frontend development.

    Calls greedy_optimize() and overrides algorithm to "mock".
    Adds a synthetic cost value and slight metric noise so the UI
    comparison panel has visually distinct values.

    Returns:
        SolverResult with algorithm="mock", status="ok".
    """
    validate_traffic_input(traffic_input)
    base = greedy_optimize(traffic_input)

    # Tweak metrics slightly upward vs classical to make comparison visible
    m = base["metrics"]
    mock_served  = min(m["total_vehicles"], m["vehicles_served"] + max(1, m["vehicles_served"] // 8))
    mock_wait    = round(m["avg_wait_sec"] * 0.82, 2)   # 18% improvement
    mock_delay   = round(m["total_delay_sec"] * 0.82, 2)
    mock_queue   = m["total_vehicles"] - mock_served

    return SolverResult(
        algorithm="mock",
        timing_plan=base["timing_plan"],
        cost=-2.718,                    # synthetic Euler's number as placeholder
        metrics={
            "total_vehicles":  m["total_vehicles"],
            "vehicles_served": mock_served,
            "remaining_queue": mock_queue,
            "avg_wait_sec":    mock_wait,
            "total_delay_sec": mock_delay,
            "runtime_ms":      42.0,    # synthetic
        },
        runtime_ms=42.0,
        status="ok",
        error_msg=None,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _qubo_to_ising(
    Q: np.ndarray,
    n: int,
) -> tuple:
    """
    Convert an n×n QUBO matrix Q to an Ising SparsePauliOp.

    Substitution: x_i = (1 - Z_i) / 2
    Returns (hamiltonian: SparsePauliOp, offset: float).
    """
    from qiskit.quantum_info import SparsePauliOp

    pauli_list = []
    offset     = 0.0

    for i in range(n):
        # Diagonal: Q_ii * x_i  →  Q_ii/2 * (I - Z_i)
        q_ii = Q[i, i]
        if q_ii != 0:
            offset     += q_ii / 2
            pauli_str   = "I" * (n - i - 1) + "Z" + "I" * i
            pauli_list.append((pauli_str, -q_ii / 2))

    for i in range(n):
        for j in range(i + 1, n):
            # Off-diagonal: Q_ij * x_i * x_j  →  Q_ij/4 * (I - Z_i - Z_j + Z_i Z_j)
            q_ij = Q[i, j]
            if q_ij == 0:
                continue
            offset += q_ij / 4
            # -Z_i term
            z_i = "I" * (n - i - 1) + "Z" + "I" * i
            pauli_list.append((z_i, -q_ij / 4))
            # -Z_j term
            z_j = "I" * (n - j - 1) + "Z" + "I" * j
            pauli_list.append((z_j, -q_ij / 4))
            # +Z_i Z_j term
            z_ij_arr = ["I"] * n
            z_ij_arr[n - i - 1] = "Z"
            z_ij_arr[n - j - 1] = "Z"
            pauli_list.append(("".join(z_ij_arr), q_ij / 4))

    if not pauli_list:
        pauli_list = [("I" * n, 0.0)]

    hamiltonian = SparsePauliOp.from_list(pauli_list).simplify()
    return hamiltonian, offset


def _best_bitstring(result, n_vars: int) -> str:
    """Extract the highest-probability bitstring from QAOA result."""
    try:
        # qiskit-algorithms >= 0.3 returns quasi-distributions
        quasi = result.best_measurement
        if quasi and "bitstring" in quasi:
            return quasi["bitstring"]
    except AttributeError:
        pass

    try:
        counts = result.eigenstate
        if hasattr(counts, "binary_probabilities"):
            probs   = counts.binary_probabilities()
            best_bs = max(probs, key=probs.get)
            return best_bs.zfill(n_vars)
    except Exception:  # pylint: disable=broad-except
        pass

    # Last resort: return a zero bitstring (will decode to default equal split)
    return "0" * n_vars


def _get_real_sampler():
    """Return an IBMQ sampler if token is available, else fall back to Aer."""
    from qiskit_aer.primitives import Sampler as AerSampler

    token = os.getenv("IBMQ_TOKEN")
    if not token:
        warnings.warn(
            "IBMQ_TOKEN not set — falling back to Aer simulator.", stacklevel=2
        )
        return AerSampler()

    try:
        from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as IBMQSampler
        service = QiskitRuntimeService(channel="ibm_quantum", token=token)
        backend = service.least_busy(operational=True, simulator=False)
        return IBMQSampler(mode=backend)
    except Exception as exc:
        warnings.warn(
            f"IBMQ connection failed ({exc}) — falling back to Aer.", stacklevel=2
        )
        return AerSampler()


def _timeout_result(
    traffic_input: TrafficInput,
    elapsed_ms:    float,
    fallback:      SolverResult,
) -> SolverResult:
    return SolverResult(
        algorithm="qaoa",
        timing_plan=fallback["timing_plan"],
        cost=None,
        metrics=fallback["metrics"],
        runtime_ms=round(elapsed_ms, 1),
        status="timeout",
        error_msg=f"QAOA exceeded 60 s timeout ({elapsed_ms:.0f} ms). Greedy fallback used.",
    )


def _error_result(
    traffic_input: TrafficInput,
    msg:           str,
    runtime_ms:    float = 0.0,
) -> SolverResult:
    fallback = greedy_optimize(traffic_input)
    return SolverResult(
        algorithm="qaoa",
        timing_plan=fallback["timing_plan"],
        cost=None,
        metrics=fallback["metrics"],
        runtime_ms=round(runtime_ms, 1),
        status="error",
        error_msg=msg,
    )
