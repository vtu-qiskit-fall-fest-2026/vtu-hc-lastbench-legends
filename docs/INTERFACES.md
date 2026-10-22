# QuantumFlow — Shared Interface Contracts
**Version:** 1.0 · **Status:** AUTHORITATIVE · **Last updated:** 2026-10-21

> [!IMPORTANT]
> This is the **single source of truth** for all data structures, function signatures, API schemas,
> and file ownership. No module may silently deviate from these contracts.
> All changes require a team sync and a version bump on the line above.

---

## Table of Contents
1. [Terminology & Global Constants](#1-terminology--global-constants)
2. [Core Data Structures](#2-core-data-structures)
3. [Cycle & Green-Time Constraints](#3-cycle--green-time-constraints)
4. [Python Function Signatures](#4-python-function-signatures)
   - 4.1 Simulator
   - 4.2 Classical Controller
   - 4.3 Shared Evaluator
   - 4.4 QUBO Builder
   - 4.5 QAOA Solver
5. [JSON API Schemas](#5-json-api-schemas)
   - 5.1 `POST /api/simulate`
   - 5.2 `POST /api/optimize`
   - 5.3 `GET /api/compare`
   - 5.4 Error envelope
6. [File Ownership & Forbidden Imports](#6-file-ownership--forbidden-imports)
7. [Known Gaps & Migration Notes](#7-known-gaps--migration-notes)

---

## 1. Terminology & Global Constants

| Symbol | Value | Meaning |
|---|---|---|
| `CYCLE_SEC` | `60` | Fixed signal cycle length in seconds |
| `MIN_GREEN` | `15` | Minimum green time per approach (seconds) |
| `MAX_GREEN` | `45` | Maximum green time per approach (seconds) |
| `MAX_CAPACITY` | `3` | Soft vehicle capacity per intersection |
| `NUM_QUBO_LEVELS` | `4` | Discrete green-time levels encoded in QUBO |
| `DEFAULT_GRID` | `4` | Default grid size (intersections per side) |

> [!WARNING]
> The previously scaffolded code uses `MIN_GREEN=10` / `MAX_GREEN=90`.
> **Both files must be updated** to `MIN_GREEN=15` / `MAX_GREEN=45` before Phase 2.
> See §7 for the full migration checklist.

---

## 2. Core Data Structures

### 2.1 `TrafficInput`

```
Intersection ID → approach vehicle counts (non-negative integers).
```

**Python type alias** (defined in `shared/types.py` — to be created):

```python
# shared/types.py
from typing import TypedDict, Dict

class ApproachCounts(TypedDict):
    ns_count: int   # North-South queue length (vehicles), >= 0
    ew_count: int   # East-West  queue length (vehicles), >= 0

# IntersectionID = "(row,col)" string, e.g. "(0,1)"
TrafficInput = Dict[str, ApproachCounts]
```

**Example:**
```python
traffic_input: TrafficInput = {
    "(0,0)": {"ns_count": 5, "ew_count": 2},
    "(0,1)": {"ns_count": 0, "ew_count": 8},
    "(1,0)": {"ns_count": 3, "ew_count": 3},
}
```

**Validation rules:**
- Keys must match regex `^\(\d+,\d+\)$`
- `ns_count >= 0`, `ew_count >= 0` (integers)
- Grid must be square: keys form a complete N×N set

---

### 2.2 `TimingPlan`

```
Intersection ID → green seconds allocated to each approach.
```

```python
class ApproachTiming(TypedDict):
    ns_green: int   # North-South green duration in seconds [MIN_GREEN, MAX_GREEN]
    ew_green: int   # East-West  green duration in seconds [MIN_GREEN, MAX_GREEN]

TimingPlan = Dict[str, ApproachTiming]
```

**Example:**
```python
timing_plan: TimingPlan = {
    "(0,0)": {"ns_green": 35, "ew_green": 25},
    "(0,1)": {"ns_green": 15, "ew_green": 45},
}
```

**Validation rules (enforced by `shared/validators.py`):**
- `ns_green` ∈ `[MIN_GREEN, MAX_GREEN]`  →  `[15, 45]`
- `ew_green` ∈ `[MIN_GREEN, MAX_GREEN]`  →  `[15, 45]`
- `ns_green + ew_green == CYCLE_SEC`  →  `== 60` (**hard constraint**)
- Keys must exactly match those of the corresponding `TrafficInput`

---

### 2.3 `Metrics`

```python
class Metrics(TypedDict):
    total_vehicles:      int    # Total vehicles in the simulation snapshot
    vehicles_served:     int    # Estimated vehicles that clear queue this cycle
    remaining_queue:     int    # total_vehicles - vehicles_served
    avg_wait_sec:        float  # Estimated average waiting time (seconds)
    total_delay_sec:     float  # Sum of individual vehicle delays (seconds)
    runtime_ms:          float  # Wall-clock solver time (milliseconds)
```

---

### 2.4 `SolverResult`

```python
class SolverResult(TypedDict):
    algorithm:    str          # "greedy" | "qaoa" | "mock"
    timing_plan:  TimingPlan   # See §2.2 — must pass validation
    cost:         float        # Objective value (lower = better); None for classical
    metrics:      Metrics      # See §2.3
    runtime_ms:   float        # Mirrors metrics.runtime_ms for top-level convenience
    status:       str          # "ok" | "timeout" | "infeasible" | "error"
    error_msg:    str | None   # Non-None only when status != "ok"
```

---

## 3. Cycle & Green-Time Constraints

Every valid `TimingPlan` entry **must** satisfy:

```
ns_green + ew_green = 60        (CYCLE_SEC)
15 ≤ ns_green ≤ 45              (MIN_GREEN ≤ x ≤ MAX_GREEN)
15 ≤ ew_green ≤ 45              (same — implied by the sum constraint)
```

This means `ew_green = 60 − ns_green`, so there is **one free variable per intersection**.

**QUBO consequence:** the quantum module only needs to optimise `ns_green` per intersection; `ew_green` is derived. This reduces the search space by half.

**Discrete levels for QUBO (NUM_QUBO_LEVELS = 4):**

| Level | `ns_green` | `ew_green` |
|---|---|---|
| 0 | 15 | 45 |
| 1 | 25 | 35 |
| 2 | 35 | 25 |
| 3 | 45 | 15 |

---

## 4. Python Function Signatures

> Rules:
> - All signatures are **binding** — rename only with a version bump.
> - Docstring format is Google-style.
> - Return types match §2 exactly.
> - No module may implement its own metric calculation — use `metrics.evaluator`.

---

### 4.1 Simulator — `simulator/traffic_env.py`

```python
class TrafficGrid:
    def __init__(self, grid_size: int = 4, seed: int = 42) -> None: ...

    def generate_vehicles(self, num_vehicles: int) -> list[dict]: ...
    # Returns list of {"id": int, "row": int, "col": int, "direction": str}

    def step(self, time_steps: int = 1) -> None: ...

    def compute_congestion(self) -> TrafficInput:
        """
        Returns TrafficInput: for each intersection,
        ns_count = vehicles heading N or S at that cell,
        ew_count = vehicles heading E or W at that cell.
        """

    def get_grid_state(self) -> list[list[int]]: ...
    # 0 = empty, 1 = occupied

    def run(
        self,
        num_vehicles: int = 20,
        time_steps:   int = 10,
    ) -> dict:
        """
        Returns:
            {
                "grid_size":        int,
                "grid":             list[list[int]],
                "vehicle_positions": list[dict],
                "traffic_input":    TrafficInput,   # renamed from congestion_map
            }
        """
```

> [!NOTE]
> `compute_congestion()` **must be updated** to return `TrafficInput` (with `ns_count`/`ew_count`)
> instead of the current flat `Dict[str, float]`. The flat score is computed by `evaluator.py`.

---

### 4.2 Classical Controller — `simulator/classical_solver.py`

```python
def greedy_optimize(
    traffic_input: TrafficInput,
    cycle_sec:     int = 60,
) -> SolverResult:
    """
    Greedy baseline: allocate ns_green proportional to ns_count / total_count.
    ew_green = cycle_sec - ns_green, clamped to [MIN_GREEN, MAX_GREEN].

    Args:
        traffic_input: TrafficInput — must not be empty.
        cycle_sec:     Fixed cycle length (default 60).

    Returns:
        SolverResult with algorithm="greedy", status="ok".

    Raises:
        ValueError: if traffic_input is empty or any count is negative.
    """
```

> [!WARNING]
> The current implementation uses `congestion_map: Dict[str,float]` as input and a private
> `_compute_metrics()`. Both must be **removed** and replaced with the above signature.
> Metrics must be computed via `metrics.evaluator.evaluate()`.

---

### 4.3 Shared Evaluator — `metrics/evaluator.py`

```python
def evaluate(
    traffic_input: TrafficInput,
    timing_plan:   TimingPlan,
    algorithm:     str    = "unknown",
    runtime_ms:    float  = 0.0,
) -> SolverResult:
    """
    Compute all Metrics and package into a SolverResult.
    This is the ONLY place metrics are calculated.

    Args:
        traffic_input: TrafficInput — vehicle counts per approach.
        timing_plan:   TimingPlan  — must pass cycle + green-time constraints.
        algorithm:     Solver name for attribution.
        runtime_ms:    Wall-clock time of the calling solver.

    Returns:
        SolverResult (status="ok", error_msg=None on success).

    Raises:
        ValueError: if timing_plan violates constraints or keys mismatch.
    """

def compare(
    classical: SolverResult,
    quantum:   SolverResult,
) -> dict:
    """
    Return side-by-side comparison for dashboard rendering.

    Returns:
        {
            "classical": Metrics,
            "quantum":   Metrics,
            "advantage": {
                "throughput_delta":    float,  # quantum - classical
                "wait_reduction_pct":  float,  # % improvement in avg_wait
                "cost_delta":          float,  # quantum.cost - classical.cost
            }
        }
    """
```

> [!WARNING]
> Current `evaluate()` takes `congestion_map: Dict[str,float]` — **must be updated** to
> accept `TrafficInput`. The private `_compute_metrics()` in `classical_solver.py` **must be deleted**.

---

### 4.4 QUBO Builder — `quantum/qubo_builder.py`

```python
# Constants (module-level, must match §1 and §3)
NUM_QUBO_LEVELS: int = 4
MIN_GREEN:       int = 15   # ← update from 10
MAX_GREEN:       int = 45   # ← update from 90
CYCLE_SEC:       int = 60

DISCRETE_LEVELS: list[int] = [15, 25, 35, 45]  # ns_green choices

def build_qubo(
    traffic_input:  TrafficInput,
    penalty_lambda: float = 5.0,
) -> tuple[np.ndarray, list[str], list[str]]:
    """
    Build QUBO matrix Q for ns_green optimisation.
    One binary variable x_{i,k} per (intersection i, level k).
    Total variables: n_intersections × NUM_QUBO_LEVELS.

    Args:
        traffic_input:  TrafficInput — vehicle counts per approach.
        penalty_lambda: One-hot constraint weight.

    Returns:
        Q:          np.ndarray shape (N, N), symmetrised.
        var_labels: list[str] — e.g. ["(0,0)_lvl0", "(0,0)_lvl1", ...]
        keys:       list[str] — sorted intersection keys.

    Raises:
        ValueError: if traffic_input is empty.
    """

def decode_solution(
    bitstring: str,
    keys:      list[str],
) -> TimingPlan:
    """
    Decode QAOA bitstring → TimingPlan.
    ew_green is derived as CYCLE_SEC - ns_green.

    Args:
        bitstring: Binary string, length = len(keys) × NUM_QUBO_LEVELS.
        keys:      Same ordered keys returned by build_qubo().

    Returns:
        TimingPlan — guaranteed to satisfy all cycle constraints.

    Raises:
        ValueError: if bitstring length mismatches.
    """
```

> [!NOTE]
> `build_qubo` now takes `TrafficInput` instead of `congestion_map`.
> Internally derive a congestion score as `(ns_count + ew_count) / MAX_CAPACITY`.

---

### 4.5 QAOA Solver — `quantum/qaoa_runner.py` *(stub only — to be implemented)*

```python
def run_qaoa(
    traffic_input:  TrafficInput,
    p_layers:       int   = 1,
    shots:          int   = 1024,
    use_real_backend: bool = False,
) -> SolverResult:
    """
    Run QAOA on the Qiskit Aer simulator (or real IBMQ backend).

    Steps:
        1. Call qubo_builder.build_qubo(traffic_input) → Q, var_labels, keys
        2. Convert Q to Ising Hamiltonian (SparsePauliOp)
        3. Build QAOA ansatz with p_layers
        4. Optimise with COBYLA via qiskit_algorithms.QAOA
        5. Sample best bitstring from result
        6. Call qubo_builder.decode_solution(bitstring, keys) → TimingPlan
        7. Call metrics.evaluator.evaluate(traffic_input, timing_plan, "qaoa")

    Args:
        traffic_input:    TrafficInput — same format as classical solver.
        p_layers:         QAOA circuit depth (p). Default 1.
        shots:            Number of measurement shots. Default 1024.
        use_real_backend: If True, uses IBMQ (requires env var IBMQ_TOKEN).

    Returns:
        SolverResult with algorithm="qaoa".
        On timeout (>30 s): status="timeout", timing_plan=fallback greedy result.
        On error: status="error", error_msg=<message>.

    Raises:
        ImportError: if qiskit-aer is not installed.

    NOTE: This module must NOT import flask or any web framework.
    """

def mock_qaoa_result(traffic_input: TrafficInput) -> SolverResult:
    """
    Returns a deterministic mock SolverResult for frontend development.
    Calls greedy_optimize() and overrides algorithm to "mock".
    Use when qaoa_runner is not ready.
    """
```

---

## 5. JSON API Schemas

> Rules:
> - All endpoints accept `Content-Type: application/json`.
> - All responses include `"status": "ok" | "error"` at top level.
> - `400` on schema violation, `500` on unhandled server error.
> - Frontend must never calculate traffic metrics — call these endpoints.

---

### 5.1 `POST /api/simulate`

**Request:**
```json
{
  "grid_size":    4,
  "num_vehicles": 20,
  "time_steps":   10,
  "seed":         42
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `grid_size` | integer | yes | 2–10 |
| `num_vehicles` | integer | yes | 1–200 |
| `time_steps` | integer | no | 1–100, default 10 |
| `seed` | integer | no | default 42 |

**Response `200`:**
```json
{
  "status":    "ok",
  "grid_size": 4,
  "grid":      [[0,1,0,0],[1,0,1,0],[0,0,0,1],[1,0,0,0]],
  "vehicle_positions": [
    {"id": 0, "row": 0, "col": 1, "direction": "E"}
  ],
  "traffic_input": {
    "(0,0)": {"ns_count": 2, "ew_count": 1},
    "(0,1)": {"ns_count": 0, "ew_count": 3}
  }
}
```

---

### 5.2 `POST /api/optimize`

**Request:**
```json
{
  "traffic_input": {
    "(0,0)": {"ns_count": 2, "ew_count": 1},
    "(0,1)": {"ns_count": 0, "ew_count": 3}
  },
  "method":    "quantum",
  "p_layers":  1,
  "shots":     1024
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `traffic_input` | object | yes | TrafficInput schema |
| `method` | string | yes | `"classical"` \| `"quantum"` \| `"mock"` |
| `p_layers` | integer | no | 1–5, default 1 (quantum only) |
| `shots` | integer | no | 128–8192, default 1024 (quantum only) |

**Response `200`:**
```json
{
  "status":    "ok",
  "algorithm": "qaoa",
  "timing_plan": {
    "(0,0)": {"ns_green": 35, "ew_green": 25},
    "(0,1)": {"ns_green": 15, "ew_green": 45}
  },
  "cost": -3.14,
  "metrics": {
    "total_vehicles":   20,
    "vehicles_served":  14,
    "remaining_queue":  6,
    "avg_wait_sec":     12.3,
    "total_delay_sec":  246.0,
    "runtime_ms":       2340.0
  },
  "runtime_ms": 2340.0,
  "solver_status": "ok",
  "error_msg": null
}
```

> [!NOTE]
> When `method="mock"`, the server calls `mock_qaoa_result()` so the frontend
> can render without waiting for QAOA to be ready.

---

### 5.3 `GET /api/compare`

Query params: `?classical_id=<run_id>&quantum_id=<run_id>`  
*(run IDs are returned from `/api/optimize` responses — to be added in Phase 2)*

**Response `200`:**
```json
{
  "status": "ok",
  "classical": {
    "total_vehicles": 20, "vehicles_served": 11,
    "remaining_queue": 9, "avg_wait_sec": 18.5,
    "total_delay_sec": 370.0, "runtime_ms": 0.5
  },
  "quantum": {
    "total_vehicles": 20, "vehicles_served": 14,
    "remaining_queue": 6, "avg_wait_sec": 12.3,
    "total_delay_sec": 246.0, "runtime_ms": 2340.0
  },
  "advantage": {
    "throughput_delta":   0.15,
    "wait_reduction_pct": 33.5,
    "cost_delta":         -1.82
  }
}
```

---

### 5.4 Error Envelope

All error responses use this shape:
```json
{
  "status":    "error",
  "code":      400,
  "message":   "traffic_input: ns_count must be >= 0",
  "field":     "traffic_input.(0,1).ns_count"
}
```

---

## 6. File Ownership & Forbidden Imports

| File | Owner | May Import | Must NOT Import |
|---|---|---|---|
| `shared/types.py` | TL | `typing` only | anything else |
| `shared/validators.py` | TL | `shared/types.py`, `typing` | Flask, qiskit, numpy |
| `simulator/traffic_env.py` | TL | `shared/`, `random`, `math` | Flask, qiskit |
| `simulator/classical_solver.py` | TL | `shared/`, `metrics/evaluator.py` | Flask, qiskit |
| `metrics/evaluator.py` | TL | `shared/`, `math` | Flask, qiskit, simulator |
| `quantum/qubo_builder.py` | QE | `shared/`, `numpy` | Flask, simulator |
| `quantum/qaoa_runner.py` | QE | `shared/`, `quantum/qubo_builder.py`, `metrics/evaluator.py`, `simulator/classical_solver.py` (for mock fallback), `qiskit*` | **Flask** (hard rule) |
| `api/app.py` | FE | All of the above | direct metric calculations |
| `api/mock_quantum.py` | FE | `shared/`, `simulator/classical_solver.py` | qiskit |
| `dashboard/` (HTML/CSS/JS) | FE | Fetch API, Plotly CDN | inline traffic logic |
| `tests/` | Both | `pytest`, all modules | — |

> [!CAUTION]
> If `quantum/qaoa_runner.py` ever imports `flask`, any test that imports the quantum module
> will pull in Flask, breaking the clean separation. CI will lint-check this.

---

## 7. Known Gaps & Migration Notes

The following **existing files must be updated** to conform to this document before Phase 2 coding begins. No new feature work should start until these are resolved.

| # | File | Issue | Required Change |
|---|---|---|---|
| G1 | `simulator/traffic_env.py` | `compute_congestion()` returns `Dict[str,float]` | Update to return `TrafficInput` (with `ns_count`/`ew_count`) |
| G2 | `simulator/traffic_env.py` | `run()` returns key `"congestion_map"` | Rename key to `"traffic_input"` in returned dict |
| G3 | `simulator/classical_solver.py` | Input is `Dict[str,float]`; has private `_compute_metrics` | Replace signature; delete `_compute_metrics`; call `evaluator.evaluate()` |
| G4 | `simulator/classical_solver.py` | `MIN_GREEN=10`, `MAX_GREEN=90`, no cycle constraint | Enforce `[15,45]` range and `ns+ew=60` |
| G5 | `metrics/evaluator.py` | Input is `Dict[str,float]` congestion; output schema incomplete | Update to accept `TrafficInput`; return full `SolverResult` |
| G6 | `quantum/qubo_builder.py` | `MIN_GREEN=10`, `MAX_GREEN=90` | Update to `[15,45]`; use 4 discrete levels from §3 |
| G7 | `quantum/qubo_builder.py` | Input is `Dict[str,float]` | Update to accept `TrafficInput`; derive score internally |
| G8 | `quantum/qubo_builder.py` | `decode_solution` returns `Dict[str,int]` | Update to return `TimingPlan` (with `ns_green`/`ew_green`) |
| G9 | *(missing)* | `shared/types.py` does not exist | Create with `ApproachCounts`, `TrafficInput`, `ApproachTiming`, `TimingPlan`, `Metrics`, `SolverResult` |
| G10 | *(missing)* | `shared/validators.py` does not exist | Create with `validate_timing_plan(TimingPlan)` |
| G11 | *(missing)* | `quantum/qaoa_runner.py` does not exist | Implement per §4.5 |
| G12 | *(missing)* | `api/app.py` does not exist | Implement per §5 |
| G13 | *(missing)* | `api/mock_quantum.py` does not exist | Implement `mock_qaoa_result()` |

> [!TIP]
> Resolve G9 first (create `shared/types.py`) — every other fix depends on the type aliases
> being importable. Then G10, then G1–G8 in any order.
