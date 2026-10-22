"""
QuantumFlow — Flask REST API & Web Application Entry Point
api/app.py  ·  Owner: Frontend Engineer / Systems Integrator

Exposes REST endpoints for:
  - GET  /                       — Static dashboard or API service status
  - GET  /api/traffic            — Current active traffic snapshot
  - POST /api/traffic            — Update traffic input or load scenario
  - POST /api/optimize/baseline  — Fixed-time baseline controller (30s NS / 30s EW)
  - POST /api/optimize/responsive — Demand-proportional traffic-responsive controller
  - POST /api/optimize/qaoa       — Genuine QAOA quantum optimizer
  - GET  /api/results            — History of optimization runs and metrics
  - POST /api/simulate           — Run simulation grid snapshot (backward-compatible)
  - POST /api/optimize           — Generalized optimizer dispatcher (backward-compatible)
  - GET  /api/compare            — Side-by-side run comparison (backward-compatible)
  - GET  /api/health             — Liveness probe

Contract Compliance & Safety:
  - Validates request JSON strictly; returns consistent JSON responses and readable error messages.
  - Safe error handlers prevent exposing stack traces, credentials, or internal secrets to users.
  - All optimization and traffic algorithms live in independent domain modules (no Flask dependencies).
"""

from __future__ import annotations

import os
import time
from functools import wraps
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from metrics.metrics import (
    compute_baseline_comparison,
    evaluate_fixed_time,
    evaluate_qaoa,
    evaluate_traffic_responsive,
)
from metrics.evaluator import compare as evaluator_compare
from shared.types import SolverResult, TrafficInput
from shared.validators import (
    validate_timing_plan,
    validate_traffic_input,
)
from simulator.classical_solver import greedy_optimize
from simulator.traffic_env import TrafficGrid
from simulator.traffic_simulator import TrafficSimulator

# Quantum module availability
_quantum_available = True
try:
    from quantum.quantum_solver import solve_traffic_qubo
    from quantum.qaoa_runner import mock_qaoa_result, run_qaoa
except ImportError:
    _quantum_available = False


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
TEMPLATES_DIR = os.path.join(ROOT_DIR, "templates")
STATIC_DIR = os.path.join(ROOT_DIR, "static")
DASH_DIR = os.path.join(ROOT_DIR, "dashboard")

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
CORS(app)  # Allow cross-origin requests from the dashboard frontend

# In-memory session state
_results: Dict[str, Dict[str, Any]] = {}
_simulator = TrafficSimulator()
_active_traffic: TrafficInput = _simulator.get_traffic_input(as_grid=False)


# ---------------------------------------------------------------------------
# Helpers & Consistency Envelopes
# ---------------------------------------------------------------------------
def _error(message: str, code: int = 400, field: Optional[str] = None) -> Any:
    """Return a consistent error envelope without exposing stack traces."""
    body: Dict[str, Any] = {
        "status": "error",
        "code": code,
        "message": str(message),
    }
    if field:
        body["field"] = field
    return jsonify(body), code


def _ok(data: Dict[str, Any], code: int = 200) -> Any:
    """Return a consistent success envelope with status='ok'."""
    data["status"] = "ok"
    return jsonify(data), code


def _run_id(prefix: str) -> str:
    """Generate a unique run ID."""
    return f"{prefix}_{int(time.time() * 1000)}"


def _require_json(fn):
    """Decorator ensuring that request has JSON content-type."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not request.is_json:
            return _error("Request must have Content-Type: application/json", code=400)
        return fn(*args, **kwargs)
    return wrapper


def _get_active_traffic(data: Optional[Dict[str, Any]] = None) -> TrafficInput:
    """Retrieve explicit traffic_input from payload or fall back to active traffic."""
    global _active_traffic
    if data and "traffic_input" in data and data["traffic_input"] is not None:
        return data["traffic_input"]
    return _active_traffic


# ---------------------------------------------------------------------------
# Error Handlers (No Stack Traces or Secrets Leaked)
# ---------------------------------------------------------------------------
@app.errorhandler(400)
def handle_bad_request(exc):
    return _error(getattr(exc, "description", "Bad request."), code=400)


@app.errorhandler(404)
def handle_not_found(exc):
    return _error("Resource not found.", code=404)


@app.errorhandler(405)
def handle_method_not_allowed(exc):
    return _error("Method not allowed.", code=405)


@app.errorhandler(500)
def handle_internal_error(exc):
    return _error("Internal server error.", code=500)


# ---------------------------------------------------------------------------
# GET / — Static Dashboard or Service Status
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Serve dashboard index.html if available, or return API status JSON."""
    tmpl_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.isfile(tmpl_path):
        return send_from_directory(TEMPLATES_DIR, "index.html")
    dash_path = os.path.join(DASH_DIR, "index.html")
    if os.path.isfile(dash_path):
        return send_from_directory(DASH_DIR, "index.html")
    return _ok({
        "service": "QuantumFlow Traffic API",
        "version": "1.0.0",
        "message": "QuantumFlow API server running successfully.",
        "endpoints": [
            "GET  /api/traffic",
            "POST /api/traffic",
            "POST /api/optimize/baseline",
            "POST /api/optimize/responsive",
            "POST /api/optimize/qaoa",
            "GET  /api/results",
            "POST /api/simulate",
            "POST /api/optimize",
            "GET  /api/compare",
            "GET  /api/health",
        ],
    })


@app.route("/static/<path:filename>")
def static_files(filename: str):
    """Serve static dashboard assets from static/ or dashboard/static/."""
    root_file = os.path.join(STATIC_DIR, filename)
    if os.path.isfile(root_file):
        return send_from_directory(STATIC_DIR, filename)
    dash_file = os.path.join(DASH_DIR, "static", filename)
    if os.path.isfile(dash_file):
        return send_from_directory(os.path.join(DASH_DIR, "static"), filename)
    return _error(f"Static asset '{filename}' not found.", code=404)


# ---------------------------------------------------------------------------
# GET /api/health — Liveness Probe
# ---------------------------------------------------------------------------
@app.route("/api/health")
def health():
    return _ok({
        "quantum_available": _quantum_available,
        "version": "1.0.0",
    })


# ---------------------------------------------------------------------------
# GET /api/traffic & POST /api/traffic
# ---------------------------------------------------------------------------
@app.route("/api/traffic", methods=["GET", "POST"])
def traffic_route():
    global _active_traffic, _simulator

    if request.method == "GET":
        total_veh = sum(
            counts["ns_count"] + counts["ew_count"]
            for counts in _active_traffic.values()
        )
        return _ok({
            "traffic_input": _active_traffic,
            "total_vehicles": total_veh,
            "num_intersections": len(_active_traffic),
        })

    # POST /api/traffic
    if not request.is_json:
        return _error("Request must have Content-Type: application/json", code=400)

    data = request.get_json() or {}

    # Option A: Preset Scenario ("light", "medium", "heavy", "zero")
    if "scenario" in data:
        scenario = str(data["scenario"]).lower()
        seed = int(data.get("seed", 42))
        try:
            _active_traffic = _simulator.generate_scenario(scenario, seed=seed)
        except ValueError as exc:
            return _error(f"Invalid scenario: {exc}", code=400, field="scenario")
        total_veh = sum(c["ns_count"] + c["ew_count"] for c in _active_traffic.values())
        return _ok({
            "scenario": scenario,
            "traffic_input": _active_traffic,
            "total_vehicles": total_veh,
        })

    # Option B: Explicit traffic_input
    if "traffic_input" in data:
        t_in = data["traffic_input"]
        try:
            validate_traffic_input(t_in)
        except ValueError as exc:
            return _error(str(exc), code=400, field="traffic_input")
        _active_traffic = t_in
        total_veh = sum(c["ns_count"] + c["ew_count"] for c in _active_traffic.values())
        return _ok({
            "traffic_input": _active_traffic,
            "total_vehicles": total_veh,
        })

    # Option C: Grid simulation generation
    if "grid_size" in data or "num_vehicles" in data:
        grid_size = data.get("grid_size", 2)
        num_vehicles = data.get("num_vehicles", 20)
        time_steps = data.get("time_steps", 10)
        seed = data.get("seed", 42)
        try:
            grid_obj = TrafficGrid(grid_size=int(grid_size), seed=int(seed))
            snapshot = grid_obj.run(num_vehicles=int(num_vehicles), time_steps=int(time_steps))
            _active_traffic = snapshot["traffic_input"]
        except Exception as exc:
            return _error(str(exc), code=400)
        total_veh = sum(c["ns_count"] + c["ew_count"] for c in _active_traffic.values())
        return _ok({
            "traffic_input": _active_traffic,
            "total_vehicles": total_veh,
            "grid": snapshot["grid"],
        })

    return _error("Must provide 'traffic_input', 'scenario', or simulation parameters.", code=400)


# ---------------------------------------------------------------------------
# POST /api/optimize/baseline
# ---------------------------------------------------------------------------
@app.route("/api/optimize/baseline", methods=["POST"])
def optimize_baseline():
    """Run Fixed-Time Baseline controller (30s NS / 30s EW)."""
    if request.data and not request.is_json:
        return _error("Request must have Content-Type: application/json", code=400)

    data = request.get_json(silent=True) or {}
    traffic_input = _get_active_traffic(data)

    try:
        validate_traffic_input(traffic_input)
    except ValueError as exc:
        return _error(str(exc), code=400, field="traffic_input")

    try:
        result = evaluate_fixed_time(traffic_input)
    except Exception as exc:
        return _error(f"Baseline solver error: {exc}", code=500)

    run_id = _run_id("baseline")
    _results[run_id] = {
        "run_id": run_id,
        "type": "optimize",
        "algorithm": "fixed-time",
        "result": result,
        "timestamp": time.time(),
    }

    return _ok({
        "run_id": run_id,
        "algorithm": result["algorithm"],
        "timing_plan": result["timing_plan"],
        "cost": result["cost"],
        "metrics": result["metrics"],
        "runtime_ms": result["runtime_ms"],
        "solver_status": result["status"],
        "error_msg": result["error_msg"],
    })


# ---------------------------------------------------------------------------
# POST /api/optimize/responsive
# ---------------------------------------------------------------------------
@app.route("/api/optimize/responsive", methods=["POST"])
def optimize_responsive():
    """Run Traffic-Responsive controller and compare against baseline."""
    if request.data and not request.is_json:
        return _error("Request must have Content-Type: application/json", code=400)

    data = request.get_json(silent=True) or {}
    traffic_input = _get_active_traffic(data)

    try:
        validate_traffic_input(traffic_input)
    except ValueError as exc:
        return _error(str(exc), code=400, field="traffic_input")

    try:
        resp_res = evaluate_traffic_responsive(traffic_input)
        base_res = evaluate_fixed_time(traffic_input)
        baseline_comp = compute_baseline_comparison(base_res, resp_res)
    except Exception as exc:
        return _error(f"Responsive solver error: {exc}", code=500)

    run_id = _run_id("responsive")
    _results[run_id] = {
        "run_id": run_id,
        "type": "optimize",
        "algorithm": "traffic-responsive",
        "result": resp_res,
        "baseline_comparison": baseline_comp,
        "timestamp": time.time(),
    }

    return _ok({
        "run_id": run_id,
        "algorithm": resp_res["algorithm"],
        "timing_plan": resp_res["timing_plan"],
        "cost": resp_res["cost"],
        "metrics": resp_res["metrics"],
        "runtime_ms": resp_res["runtime_ms"],
        "solver_status": resp_res["status"],
        "error_msg": resp_res["error_msg"],
        "baseline_comparison": baseline_comp,
    })


# ---------------------------------------------------------------------------
# POST /api/optimize/qaoa
# ---------------------------------------------------------------------------
@app.route("/api/optimize/qaoa", methods=["POST"])
def optimize_qaoa():
    """Run genuine QAOA quantum solver and compare against baseline."""
    if not _quantum_available:
        return _error("Qiskit or quantum solver dependencies are not installed.", code=503)

    if request.data and not request.is_json:
        return _error("Request must have Content-Type: application/json", code=400)

    data = request.get_json(silent=True) or {}
    traffic_input = _get_active_traffic(data)

    try:
        validate_traffic_input(traffic_input)
    except ValueError as exc:
        return _error(str(exc), code=400, field="traffic_input")

    # Parameter parsing and range validation
    try:
        p_layers = int(data.get("p_layers", 1))
        shots = int(data.get("shots", 1024))
        maxiter = int(data.get("maxiter", 50))
        seed = int(data.get("seed", 42)) if data.get("seed") is not None else 42
        timeout_sec = float(data.get("timeout_sec", 30.0))
        coord_weight = float(data.get("coord_weight", 0.0))
    except (TypeError, ValueError):
        return _error("Numeric solver parameters must be valid numbers.", code=400)

    if not (1 <= p_layers <= 5):
        return _error("p_layers must be between 1 and 5.", code=400, field="p_layers")
    if not (128 <= shots <= 8192):
        return _error("shots must be between 128 and 8192.", code=400, field="shots")
    if not (1 <= maxiter <= 200):
        return _error("maxiter must be between 1 and 200.", code=400, field="maxiter")
    if timeout_sec <= 0:
        return _error("timeout_sec must be positive.", code=400, field="timeout_sec")

    # Execute genuine QAOA (handles errors, timeouts, and empty samples safely)
    try:
        qaoa_res = evaluate_qaoa(
            traffic_input=traffic_input,
            coord_weight=coord_weight,
            p_layers=p_layers,
            shots=shots,
            maxiter=maxiter,
            seed=seed,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        # Catch unexpected fatal simulator exceptions without leaking stack trace
        return _error(f"Quantum simulation failed: {exc}", code=500)

    # Compute comparison vs baseline only if solver succeeded
    baseline_comp = None
    if qaoa_res["status"] == "ok":
        base_res = evaluate_fixed_time(traffic_input)
        baseline_comp = compute_baseline_comparison(base_res, qaoa_res)

    run_id = _run_id("qaoa")
    _results[run_id] = {
        "run_id": run_id,
        "type": "optimize",
        "algorithm": "qaoa",
        "result": qaoa_res,
        "baseline_comparison": baseline_comp,
        "timestamp": time.time(),
    }

    return _ok({
        "run_id": run_id,
        "algorithm": qaoa_res["algorithm"],
        "timing_plan": qaoa_res["timing_plan"],
        "cost": qaoa_res["cost"],
        "metrics": qaoa_res["metrics"],
        "runtime_ms": qaoa_res["runtime_ms"],
        "solver_status": qaoa_res["status"],
        "error_msg": qaoa_res["error_msg"],
        "bitstring": qaoa_res.get("bitstring"),
        "baseline_comparison": baseline_comp,
    })


# ---------------------------------------------------------------------------
# GET /api/results
# ---------------------------------------------------------------------------
@app.route("/api/results", methods=["GET"])
def get_results():
    """Retrieve history of recent optimization results and metrics."""
    limit = request.args.get("limit", default=50, type=int)
    if limit is None or limit <= 0:
        limit = 50

    # Sort results newest first
    sorted_items = sorted(
        _results.values(),
        key=lambda item: item.get("timestamp", 0),
        reverse=True,
    )
    selected = sorted_items[:limit]

    # Compact summary for frontend listing
    summaries: List[Dict[str, Any]] = []
    for item in selected:
        res = item.get("result", {})
        summaries.append({
            "run_id": item.get("run_id"),
            "algorithm": item.get("algorithm", res.get("algorithm")),
            "type": item.get("type"),
            "timestamp": item.get("timestamp"),
            "status": res.get("status"),
            "metrics": res.get("metrics"),
            "cost": res.get("cost"),
            "runtime_ms": res.get("runtime_ms"),
            "baseline_comparison": item.get("baseline_comparison"),
        })

    return _ok({
        "count": len(summaries),
        "total_recorded": len(_results),
        "results": summaries,
    })


# ---------------------------------------------------------------------------
# Backward-Compatible Endpoints (docs/INTERFACES.md §5)
# ---------------------------------------------------------------------------
@app.route("/api/simulate", methods=["POST"])
@_require_json
def simulate():
    """Simulate traffic grid (backward-compatible)."""
    data = request.get_json()

    grid_size = data.get("grid_size")
    num_vehicles = data.get("num_vehicles")
    if grid_size is None:
        return _error("Missing required field 'grid_size'.", field="grid_size")
    if num_vehicles is None:
        return _error("Missing required field 'num_vehicles'.", field="num_vehicles")

    try:
        grid_size = int(grid_size)
        num_vehicles = int(num_vehicles)
    except (TypeError, ValueError):
        return _error("grid_size and num_vehicles must be integers.")

    if not (2 <= grid_size <= 10):
        return _error("grid_size must be between 2 and 10.", field="grid_size")
    if not (1 <= num_vehicles <= 200):
        return _error("num_vehicles must be between 1 and 200.", field="num_vehicles")

    time_steps = int(data.get("time_steps", 10))
    seed = int(data.get("seed", 42))

    if not (1 <= time_steps <= 100):
        return _error("time_steps must be between 1 and 100.", field="time_steps")

    try:
        grid_obj = TrafficGrid(grid_size=grid_size, seed=seed)
        snapshot = grid_obj.run(num_vehicles=num_vehicles, time_steps=time_steps)
    except ValueError as exc:
        return _error(str(exc))

    run_id = _run_id("sim")
    _results[run_id] = {"run_id": run_id, "type": "simulate", "snapshot": snapshot, "timestamp": time.time()}

    return _ok({
        "run_id": run_id,
        "grid_size": snapshot["grid_size"],
        "grid": snapshot["grid"],
        "vehicle_positions": snapshot["vehicle_positions"],
        "traffic_input": snapshot["traffic_input"],
    })


@app.route("/api/optimize", methods=["POST"])
@_require_json
def optimize():
    """Optimize dispatch endpoint (backward-compatible)."""
    data = request.get_json()
    traffic_input = data.get("traffic_input")
    method = data.get("method", "classical")

    if traffic_input is None:
        return _error("Missing required field 'traffic_input'.", field="traffic_input")
    if method not in ("classical", "quantum", "mock"):
        return _error("method must be 'classical', 'quantum', or 'mock'.", field="method")

    try:
        validate_traffic_input(traffic_input)
    except ValueError as exc:
        return _error(str(exc), field="traffic_input")

    try:
        if method == "classical":
            result = greedy_optimize(traffic_input)
        elif method == "mock":
            if not _quantum_available:
                return _error("Qiskit not installed; mock mode unavailable.", code=503)
            result = mock_qaoa_result(traffic_input)
        else:  # quantum
            if not _quantum_available:
                return _error("Qiskit not installed.", code=503)
            p_layers = int(data.get("p_layers", 1))
            shots = int(data.get("shots", 1024))
            if not (1 <= p_layers <= 5):
                return _error("p_layers must be between 1 and 5.", field="p_layers")
            if not (128 <= shots <= 8192):
                return _error("shots must be between 128 and 8192.", field="shots")
            result = run_qaoa(traffic_input, p_layers=p_layers, shots=shots)
    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:
        return _error(f"Solver error: {exc}", code=500)

    run_id = _run_id(method)
    _results[run_id] = {"run_id": run_id, "type": "optimize", "method": method, "result": result, "timestamp": time.time()}

    return _ok({
        "run_id": run_id,
        "algorithm": result["algorithm"],
        "timing_plan": result["timing_plan"],
        "cost": result["cost"],
        "metrics": result["metrics"],
        "runtime_ms": result["runtime_ms"],
        "solver_status": result["status"],
        "error_msg": result["error_msg"],
    })


@app.route("/api/compare", methods=["GET"])
def compare():
    """Compare two previously computed SolverResults (backward-compatible)."""
    c_id = request.args.get("classical_id")
    q_id = request.args.get("quantum_id")

    if not c_id or not q_id:
        return _error("Provide both 'classical_id' and 'quantum_id' query parameters.")

    c_entry = _results.get(c_id)
    q_entry = _results.get(q_id)

    if c_entry is None:
        return _error(f"Run ID '{c_id}' not found.", code=404)
    if q_entry is None:
        return _error(f"Run ID '{q_id}' not found.", code=404)

    if c_entry.get("type") != "optimize":
        return _error(f"Run ID '{c_id}' is not an optimize result.")
    if q_entry.get("type") != "optimize":
        return _error(f"Run ID '{q_id}' is not an optimize result.")

    comparison = evaluator_compare(c_entry["result"], q_entry["result"])
    return _ok(comparison)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"\n[QuantumFlow] API running on http://localhost:{port}")
    print(f"   Quantum solver available: {_quantum_available}")
    print(f"   Endpoints: GET /, GET /api/traffic, POST /api/traffic,")
    print(f"              POST /api/optimize/baseline, POST /api/optimize/responsive,")
    print(f"              POST /api/optimize/qaoa, GET /api/results\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
