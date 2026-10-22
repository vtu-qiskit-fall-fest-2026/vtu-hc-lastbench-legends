"""
QuantumFlow — Test Suite: Flask API
tests/test_api.py  ·  Owner: Frontend Engineer
"""

import json
import pytest
from api.app import app as flask_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


VALID_TRAFFIC_INPUT = {
    "(0,0)": {"ns_count": 3, "ew_count": 1},
    "(0,1)": {"ns_count": 0, "ew_count": 5},
    "(1,0)": {"ns_count": 2, "ew_count": 2},
    "(1,1)": {"ns_count": 1, "ew_count": 0},
}


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data),
                       content_type="application/json")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_200(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_health_has_status_ok(self, client):
        data = r = client.get("/api/health").get_json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/simulate
# ---------------------------------------------------------------------------
class TestSimulate:
    def test_valid_request_200(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 2, "num_vehicles": 8})
        assert r.status_code == 200

    def test_response_has_traffic_input(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 2, "num_vehicles": 4})
        data = r.get_json()
        assert "traffic_input" in data
        assert "congestion_map" not in data   # old key must not appear

    def test_response_has_run_id(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 2, "num_vehicles": 4})
        assert "run_id" in r.get_json()

    def test_missing_grid_size_400(self, client):
        r = post_json(client, "/api/simulate", {"num_vehicles": 5})
        assert r.status_code == 400

    def test_missing_num_vehicles_400(self, client):
        r = post_json(client, "/api/simulate", {"grid_size": 2})
        assert r.status_code == 400

    def test_grid_too_large_400(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 99, "num_vehicles": 5})
        assert r.status_code == 400

    def test_non_json_400(self, client):
        r = client.post("/api/simulate", data="not json",
                        content_type="text/plain")
        assert r.status_code == 400

    def test_grid_is_square_nxn(self, client):
        r = post_json(client, "/api/simulate",
                      {"grid_size": 3, "num_vehicles": 10})
        data = r.get_json()
        grid = data["grid"]
        assert len(grid) == 3
        for row in grid:
            assert len(row) == 3


# ---------------------------------------------------------------------------
# POST /api/optimize — classical
# ---------------------------------------------------------------------------
class TestOptimizeClassical:
    def test_valid_classical_200(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "classical"})
        assert r.status_code == 200

    def test_algorithm_is_greedy(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "classical"})
        assert r.get_json()["algorithm"] == "greedy"

    def test_timing_plan_in_response(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "classical"})
        data = r.get_json()
        assert "timing_plan" in data
        for iid, timing in data["timing_plan"].items():
            assert "ns_green" in timing
            assert "ew_green" in timing
            assert timing["ns_green"] + timing["ew_green"] == 60

    def test_metrics_in_response(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "classical"})
        m = r.get_json()["metrics"]
        for field in ("total_vehicles", "vehicles_served", "remaining_queue",
                      "avg_wait_sec", "total_delay_sec", "runtime_ms"):
            assert field in m

    def test_invalid_traffic_input_400(self, client):
        bad = {"(0,0)": {"ns_count": -1, "ew_count": 0},
               "(0,1)": {"ns_count": 0,  "ew_count": 0},
               "(1,0)": {"ns_count": 0,  "ew_count": 0},
               "(1,1)": {"ns_count": 0,  "ew_count": 0}}
        r = post_json(client, "/api/optimize",
                      {"traffic_input": bad, "method": "classical"})
        assert r.status_code == 400

    def test_missing_traffic_input_400(self, client):
        r = post_json(client, "/api/optimize", {"method": "classical"})
        assert r.status_code == 400

    def test_invalid_method_400(self, client):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": "magic"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/compare
# ---------------------------------------------------------------------------
class TestCompare:
    def _get_run_id(self, client, method="classical"):
        r = post_json(client, "/api/optimize",
                      {"traffic_input": VALID_TRAFFIC_INPUT, "method": method})
        return r.get_json()["run_id"]

    def test_compare_200(self, client):
        c_id = self._get_run_id(client, "classical")
        q_id = self._get_run_id(client, "mock")
        r = client.get(f"/api/compare?classical_id={c_id}&quantum_id={q_id}")
        assert r.status_code == 200

    def test_compare_structure(self, client):
        c_id = self._get_run_id(client, "classical")
        q_id = self._get_run_id(client, "mock")
        data = client.get(f"/api/compare?classical_id={c_id}&quantum_id={q_id}").get_json()
        assert "classical" in data
        assert "quantum"   in data
        assert "advantage" in data

    def test_compare_missing_params_400(self, client):
        r = client.get("/api/compare")
        assert r.status_code == 400

    def test_compare_bad_id_404(self, client):
        r = client.get("/api/compare?classical_id=fake&quantum_id=also_fake")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET / (Index Dashboard & Status)
# ---------------------------------------------------------------------------
class TestIndexEndpoint:
    def test_get_index_200(self, client):
        r = client.get("/")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET & POST /api/traffic
# ---------------------------------------------------------------------------
class TestTrafficEndpoints:
    def test_get_traffic_returns_current_snapshot(self, client):
        r = client.get("/api/traffic")
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert "traffic_input" in data
        assert "total_vehicles" in data
        assert data["total_vehicles"] >= 0

    def test_post_traffic_with_explicit_input(self, client):
        custom_input = {
            "A": {"ns_count": 10, "ew_count": 5},
            "B": {"ns_count": 20, "ew_count": 10},
            "C": {"ns_count": 15, "ew_count": 25},
            "D": {"ns_count": 30, "ew_count": 15},
        }
        r = post_json(client, "/api/traffic", {"traffic_input": custom_input})
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert data["total_vehicles"] == 130
        assert data["traffic_input"] == custom_input

        # Verify subsequent GET returns updated input
        r_get = client.get("/api/traffic")
        assert r_get.get_json()["traffic_input"] == custom_input

    def test_post_traffic_with_scenario_preset(self, client):
        for scenario in ("light", "medium", "heavy"):
            r = post_json(client, "/api/traffic", {"scenario": scenario, "seed": 42})
            assert r.status_code == 200
            data = r.get_json()
            assert data["status"] == "ok"
            assert data["scenario"] == scenario
            assert data["total_vehicles"] > 0

    def test_post_traffic_invalid_scenario_400(self, client):
        r = post_json(client, "/api/traffic", {"scenario": "alien_invasion"})
        assert r.status_code == 400
        data = r.get_json()
        assert data["status"] == "error"
        assert "alien_invasion" in data["message"].lower()

    def test_post_traffic_negative_queue_400(self, client):
        bad_input = {
            "A": {"ns_count": -5, "ew_count": 5},
            "B": {"ns_count": 20, "ew_count": 10},
            "C": {"ns_count": 15, "ew_count": 25},
            "D": {"ns_count": 30, "ew_count": 15},
        }
        r = post_json(client, "/api/traffic", {"traffic_input": bad_input})
        assert r.status_code == 400
        assert r.get_json()["status"] == "error"

    def test_post_traffic_non_json_400(self, client):
        r = client.post("/api/traffic", data="text content", content_type="text/plain")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/optimize/baseline
# ---------------------------------------------------------------------------
class TestOptimizeBaselineEndpoint:
    def test_baseline_success(self, client):
        r = post_json(client, "/api/optimize/baseline", {"traffic_input": VALID_TRAFFIC_INPUT})
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert data["algorithm"] == "fixed-time"
        assert data["solver_status"] == "ok"
        assert data["cost"] is None

        # Fixed-time split must be 30/30 for all intersections
        plan = data["timing_plan"]
        for timing in plan.values():
            assert timing["ns_green"] == 30
            assert timing["ew_green"] == 30

        # Metrics present
        m = data["metrics"]
        assert m["total_vehicles"] > 0
        assert m["vehicles_served"] > 0
        assert m["remaining_queue"] >= 0

    def test_baseline_uses_active_traffic_when_payload_empty(self, client):
        r = post_json(client, "/api/optimize/baseline", {})
        assert r.status_code == 200
        data = r.get_json()
        assert data["algorithm"] == "fixed-time"

    def test_baseline_invalid_traffic_input_400(self, client):
        bad = {"A": {"ns_count": -1, "ew_count": 0}}
        r = post_json(client, "/api/optimize/baseline", {"traffic_input": bad})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/optimize/responsive
# ---------------------------------------------------------------------------
class TestOptimizeResponsiveEndpoint:
    def test_responsive_success(self, client):
        r = post_json(client, "/api/optimize/responsive", {"traffic_input": VALID_TRAFFIC_INPUT})
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert data["algorithm"] == "traffic-responsive"
        assert data["solver_status"] == "ok"

        # Baseline comparison must be attached
        assert "baseline_comparison" in data
        b_cmp = data["baseline_comparison"]
        assert "delay_reduction_pct" in b_cmp
        assert "wait_reduction_pct" in b_cmp
        assert "throughput_pct_change" in b_cmp

    def test_responsive_invalid_input_400(self, client):
        bad = {"A": {"ns_count": "invalid", "ew_count": 10}}
        r = post_json(client, "/api/optimize/responsive", {"traffic_input": bad})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/optimize/qaoa
# ---------------------------------------------------------------------------
class TestOptimizeQAOAEndpoint:
    def test_qaoa_success(self, client):
        r = post_json(client, "/api/optimize/qaoa", {
            "traffic_input": VALID_TRAFFIC_INPUT,
            "p_layers": 1,
            "shots": 256,
            "maxiter": 20,
            "seed": 42,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert data["algorithm"] == "qaoa"
        assert data["solver_status"] == "ok"
        assert isinstance(data["cost"], float)
        assert len(data["bitstring"]) == 4
        assert "baseline_comparison" in data

    def test_qaoa_p_layers_out_of_range_400(self, client):
        r = post_json(client, "/api/optimize/qaoa", {
            "traffic_input": VALID_TRAFFIC_INPUT,
            "p_layers": 0,
        })
        assert r.status_code == 400
        assert "p_layers" in r.get_json()["message"]

        r2 = post_json(client, "/api/optimize/qaoa", {
            "traffic_input": VALID_TRAFFIC_INPUT,
            "p_layers": 10,
        })
        assert r2.status_code == 400

    def test_qaoa_shots_out_of_range_400(self, client):
        r = post_json(client, "/api/optimize/qaoa", {
            "traffic_input": VALID_TRAFFIC_INPUT,
            "shots": 10,
        })
        assert r.status_code == 400
        assert "shots" in r.get_json()["message"]

    def test_qaoa_invalid_timeout_400(self, client):
        r = post_json(client, "/api/optimize/qaoa", {
            "traffic_input": VALID_TRAFFIC_INPUT,
            "timeout_sec": -1.0,
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Zero Traffic Handling Across Endpoints
# ---------------------------------------------------------------------------
class TestZeroTrafficHandling:
    def test_zero_traffic_workflow(self, client):
        # 1. Set zero traffic
        r_set = post_json(client, "/api/traffic", {"scenario": "zero"})
        assert r_set.status_code == 200
        assert r_set.get_json()["total_vehicles"] == 0

        # 2. Baseline on zero traffic
        r_base = post_json(client, "/api/optimize/baseline", {})
        assert r_base.status_code == 200
        m_base = r_base.get_json()["metrics"]
        assert m_base["total_delay_sec"] == 0.0
        assert m_base["avg_wait_sec"] == 0.0

        # 3. Responsive on zero traffic
        r_resp = post_json(client, "/api/optimize/responsive", {})
        assert r_resp.status_code == 200
        m_resp = r_resp.get_json()["metrics"]
        assert m_resp["total_delay_sec"] == 0.0
        assert r_resp.get_json()["baseline_comparison"]["delay_reduction_pct"] == 0.0

        # 4. QAOA on zero traffic
        r_qaoa = post_json(client, "/api/optimize/qaoa", {"shots": 256, "maxiter": 10})
        assert r_qaoa.status_code == 200
        m_qaoa = r_qaoa.get_json()["metrics"]
        assert m_qaoa["total_delay_sec"] == 0.0
        assert r_qaoa.get_json()["solver_status"] == "ok"


# ---------------------------------------------------------------------------
# Solver Failure & Safety (No Stack Traces or Secrets Leaked)
# ---------------------------------------------------------------------------
class TestSolverFailureAndSafety:
    def test_qaoa_timeout_handled_gracefully(self, client):
        # Trigger timeout with tiny threshold
        r = post_json(client, "/api/optimize/qaoa", {
            "traffic_input": VALID_TRAFFIC_INPUT,
            "timeout_sec": 0.0001,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["solver_status"] == "timeout"
        assert data["cost"] is None
        assert "timeout" in data["error_msg"].lower()
        # Fallback plan is provided
        assert "timing_plan" in data

    def test_qaoa_fatal_error_sanitized(self, client):
        from unittest.mock import patch
        with patch("api.app.evaluate_qaoa", side_effect=RuntimeError("Simulated quantum chip failure")):
            r = post_json(client, "/api/optimize/qaoa", {"traffic_input": VALID_TRAFFIC_INPUT})
            assert r.status_code == 500
            data = r.get_json()
            assert data["status"] == "error"
            assert "Simulated quantum chip failure" in data["message"]
            # Must NOT expose tracebacks or internal file paths in body
            assert "Traceback" not in data["message"]
            assert "File " not in data["message"]

    def test_error_handlers_do_not_expose_stack_traces(self, client):
        r_404 = client.get("/api/nonexistent_endpoint")
        assert r_404.status_code == 404
        assert r_404.get_json()["status"] == "error"

        r_405 = client.post("/api/results", json={})
        assert r_405.status_code == 405
        assert r_405.get_json()["status"] == "error"


# ---------------------------------------------------------------------------
# GET /api/results
# ---------------------------------------------------------------------------
class TestResultsEndpoint:
    def test_get_results_returns_history(self, client):
        # Run a baseline and responsive optimization
        post_json(client, "/api/optimize/baseline", {"traffic_input": VALID_TRAFFIC_INPUT})
        post_json(client, "/api/optimize/responsive", {"traffic_input": VALID_TRAFFIC_INPUT})

        r = client.get("/api/results")
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert data["count"] >= 2
        assert len(data["results"]) >= 2

        # Results contain required fields
        item = data["results"][0]
        assert "run_id" in item
        assert "algorithm" in item
        assert "metrics" in item

    def test_get_results_with_limit(self, client):
        r = client.get("/api/results?limit=1")
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["results"]) <= 1


# ---------------------------------------------------------------------------
# Algorithm Independence from Flask
# ---------------------------------------------------------------------------
class TestAlgorithmsIndependentOfFlask:
    """Verify that domain modules do NOT import flask."""

    @pytest.mark.parametrize("filepath", [
        "quantum/quantum_solver.py",
        "quantum/binary_qubo.py",
        "quantum/reference_enumerator.py",
        "metrics/metrics.py",
        "metrics/traffic_model.py",
        "simulator/baseline.py",
        "simulator/classical_solver.py",
        "simulator/traffic_simulator.py",
    ])
    def test_module_has_no_flask_dependency(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "import flask" not in content and "from flask" not in content, \
            f"{filepath} must remain independent of Flask"

