"""
QuantumFlow — Automated Pytest Suite for End-to-End Scenarios
tests/test_end_to_end_scenarios.py
"""

import pytest
from api.app import app
from metrics.traffic_model import evaluate as shared_evaluator
from shared.validators import CYCLE_SEC, MIN_GREEN, MAX_GREEN


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.mark.parametrize("scenario_name,seed", [
    ("light", 42),
    ("medium", 42),
    ("heavy", 42),
    ("zero", 42),
    ("heavy", 101),
    ("medium", 999),
])
def test_full_scenario_workflow(client, scenario_name, seed):
    """Test full browser-to-backend-to-solver workflow for a scenario."""
    # 1. Update traffic state
    t_res = client.post("/api/traffic", json={"scenario": scenario_name, "seed": seed})
    assert t_res.status_code == 200
    t_data = t_res.get_json()
    assert t_data["status"] == "ok"
    traffic_input = t_data["traffic_input"]

    # 2. Fixed-Time Baseline
    base_res = client.post("/api/optimize/baseline", json={"traffic_input": traffic_input})
    assert base_res.status_code == 200
    base_data = base_res.get_json()
    assert base_data["status"] == "ok"
    _validate_timing_plan(base_data["timing_plan"])
    _validate_shared_evaluator(traffic_input, base_data["timing_plan"], base_data["metrics"], "fixed-time")

    # 3. Traffic-Responsive
    resp_res = client.post("/api/optimize/responsive", json={"traffic_input": traffic_input})
    assert resp_res.status_code == 200
    resp_data = resp_res.get_json()
    assert resp_data["status"] == "ok"
    _validate_timing_plan(resp_data["timing_plan"])
    _validate_shared_evaluator(traffic_input, resp_data["timing_plan"], resp_data["metrics"], "traffic-responsive")

    # 4. QAOA Quantum Solver
    qaoa_res = client.post("/api/optimize/qaoa", json={
        "traffic_input": traffic_input,
        "p_layers": 1,
        "shots": 256,
        "maxiter": 20,
        "seed": 42,
    })
    assert qaoa_res.status_code == 200
    qaoa_data = qaoa_res.get_json()
    assert qaoa_data["status"] == "ok"
    assert qaoa_data["algorithm"] == "qaoa"
    assert qaoa_data["solver_status"] == "ok"
    assert "bitstring" in qaoa_data and len(qaoa_data["bitstring"]) == 4
    _validate_timing_plan(qaoa_data["timing_plan"])
    _validate_shared_evaluator(traffic_input, qaoa_data["timing_plan"], qaoa_data["metrics"], "qaoa")

    # 5. Verify results history
    hist_res = client.get("/api/results?limit=5")
    assert hist_res.status_code == 200
    hist_data = hist_res.get_json()
    assert hist_data["status"] == "ok"
    assert hist_data["count"] >= 3


def _validate_timing_plan(plan):
    for iid in ["A", "B", "C", "D"]:
        assert iid in plan
        ns = plan[iid]["ns_green"]
        ew = plan[iid]["ew_green"]
        assert ns + ew == CYCLE_SEC
        assert MIN_GREEN <= ns <= MAX_GREEN
        assert MIN_GREEN <= ew <= MAX_GREEN


def _validate_shared_evaluator(traffic_input, plan, api_metrics, algo_name):
    ref_m = shared_evaluator(traffic_input, plan, algorithm=algo_name)["metrics"]
    assert api_metrics["total_vehicles"] == ref_m["total_vehicles"]
    assert api_metrics["vehicles_served"] == ref_m["vehicles_served"]
    assert api_metrics["remaining_queue"] == ref_m["remaining_queue"]
    assert abs(api_metrics["total_delay_sec"] - ref_m["total_delay_sec"]) < 1e-4
    assert abs(api_metrics["avg_wait_sec"] - ref_m["avg_wait_sec"]) < 1e-4
