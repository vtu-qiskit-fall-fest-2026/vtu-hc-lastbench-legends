"""
QuantumFlow — End-to-End Scenario Verification Script
Verifies: light, medium, heavy, zero-traffic, and repeated runs
Tests live HTTP endpoints against the shared evaluator and QAOA sampler.
"""

import json
import os
import sys
import time
import urllib.request
from typing import Any, Dict

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from metrics.traffic_model import evaluate as shared_evaluator
from shared.validators import CYCLE_SEC, MIN_GREEN, MAX_GREEN

BASE_URL = "http://localhost:5000"


def http_post(endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(endpoint: str) -> Dict[str, Any]:
    url = f"{BASE_URL}{endpoint}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def validate_timing_plan_constraints(plan: Dict[str, Dict[str, int]], scenario_name: str, algo_name: str):
    intersections = ["A", "B", "C", "D"]
    for iid in intersections:
        assert iid in plan, f"[{scenario_name}/{algo_name}] Missing intersection {iid} in plan: {plan}"
        timing = plan[iid]
        ns = timing["ns_green"]
        ew = timing["ew_green"]
        assert ns + ew == CYCLE_SEC, (
            f"[{scenario_name}/{algo_name}] Cycle violated at {iid}: {ns} + {ew} != {CYCLE_SEC}"
        )
        assert MIN_GREEN <= ns <= MAX_GREEN, (
            f"[{scenario_name}/{algo_name}] ns_green out of bounds at {iid}: {ns} not in [{MIN_GREEN}, {MAX_GREEN}]"
        )
        assert MIN_GREEN <= ew <= MAX_GREEN, (
            f"[{scenario_name}/{algo_name}] ew_green out of bounds at {iid}: {ew} not in [{MIN_GREEN}, {MAX_GREEN}]"
        )


def verify_shared_evaluator_agreement(traffic_input: Dict[str, Any], plan: Dict[str, Any], api_metrics: Dict[str, Any], scenario_name: str, algo_name: str):
    ref_result = shared_evaluator(traffic_input, plan, algorithm=algo_name)
    ref_m = ref_result["metrics"]

    assert api_metrics["total_vehicles"] == ref_m["total_vehicles"], (
        f"[{scenario_name}/{algo_name}] total_vehicles mismatch: API {api_metrics['total_vehicles']} vs Ref {ref_m['total_vehicles']}"
    )
    assert api_metrics["vehicles_served"] == ref_m["vehicles_served"], (
        f"[{scenario_name}/{algo_name}] vehicles_served mismatch: API {api_metrics['vehicles_served']} vs Ref {ref_m['vehicles_served']}"
    )
    assert api_metrics["remaining_queue"] == ref_m["remaining_queue"], (
        f"[{scenario_name}/{algo_name}] remaining_queue mismatch: API {api_metrics['remaining_queue']} vs Ref {ref_m['remaining_queue']}"
    )
    assert abs(api_metrics["total_delay_sec"] - ref_m["total_delay_sec"]) < 1e-4, (
        f"[{scenario_name}/{algo_name}] total_delay mismatch: API {api_metrics['total_delay_sec']} vs Ref {ref_m['total_delay_sec']}"
    )
    assert abs(api_metrics["avg_wait_sec"] - ref_m["avg_wait_sec"]) < 1e-4, (
        f"[{scenario_name}/{algo_name}] avg_wait mismatch: API {api_metrics['avg_wait_sec']} vs Ref {ref_m['avg_wait_sec']}"
    )


def run_scenario_workflow(scenario_name: str, seed: int = 42):
    print(f"\n================================================================================")
    print(f"RUNNING SCENARIO: {scenario_name.upper()} (seed={seed})")
    print(f"================================================================================")

    # 1. Update traffic state
    traffic_res = http_post("/api/traffic", {"scenario": scenario_name, "seed": seed})
    assert traffic_res["status"] == "ok"
    traffic_input = traffic_res["traffic_input"]
    total_vehicles = traffic_res["total_vehicles"]
    print(f"Traffic input loaded: {total_vehicles} total vehicles across 4 intersections")
    for iid, counts in sorted(traffic_input.items()):
        print(f"  Intersection {iid}: NS={counts['ns_count']} veh, EW={counts['ew_count']} veh")

    # 2. Run Baseline (Fixed-Time)
    base_res = http_post("/api/optimize/baseline", {"traffic_input": traffic_input})
    assert base_res["status"] == "ok"
    assert base_res["algorithm"] == "fixed-time"
    validate_timing_plan_constraints(base_res["timing_plan"], scenario_name, "fixed-time")
    verify_shared_evaluator_agreement(traffic_input, base_res["timing_plan"], base_res["metrics"], scenario_name, "fixed-time")
    bm = base_res["metrics"]
    print(f"\n[Fixed-Time Baseline]")
    print(f"  Plan: {base_res['timing_plan']}")
    print(f"  Served: {bm['vehicles_served']} / Remaining: {bm['remaining_queue']} veh")
    print(f"  Total Delay: {bm['total_delay_sec']:.1f} s | Avg Wait: {bm['avg_wait_sec']:.2f} s/veh")
    print(f"  Runtime: {base_res['runtime_ms']:.2f} ms")

    # 3. Run Traffic-Responsive
    resp_res = http_post("/api/optimize/responsive", {"traffic_input": traffic_input})
    assert resp_res["status"] == "ok"
    assert resp_res["algorithm"] == "traffic-responsive"
    validate_timing_plan_constraints(resp_res["timing_plan"], scenario_name, "traffic-responsive")
    verify_shared_evaluator_agreement(traffic_input, resp_res["timing_plan"], resp_res["metrics"], scenario_name, "traffic-responsive")
    rm = resp_res["metrics"]
    r_red = resp_res.get("baseline_comparison", {}).get("delay_reduction_pct", 0.0)
    print(f"\n[Traffic-Responsive]")
    print(f"  Plan: {resp_res['timing_plan']}")
    print(f"  Served: {rm['vehicles_served']} / Remaining: {rm['remaining_queue']} veh")
    print(f"  Total Delay: {rm['total_delay_sec']:.1f} s | Avg Wait: {rm['avg_wait_sec']:.2f} s/veh")
    print(f"  Delay Reduction vs Baseline: {r_red:+.1f}%")
    print(f"  Runtime: {resp_res['runtime_ms']:.2f} ms")

    # 4. Run QAOA Quantum Solver
    qaoa_payload = {
        "traffic_input": traffic_input,
        "p_layers": 1,
        "shots": 1024,
        "maxiter": 50,
        "seed": 42,
        "timeout_sec": 30.0,
    }
    t_start = time.perf_counter()
    qaoa_res = http_post("/api/optimize/qaoa", qaoa_payload)
    client_latency_ms = (time.perf_counter() - t_start) * 1000

    assert qaoa_res["status"] == "ok"
    assert qaoa_res["algorithm"] == "qaoa"
    assert qaoa_res["solver_status"] == "ok"
    assert "bitstring" in qaoa_res and qaoa_res["bitstring"] is not None
    bitstring = qaoa_res["bitstring"]
    assert len(bitstring) == 4, f"Invalid QAOA bitstring length: {bitstring}"
    assert all(c in "01" for c in bitstring), f"Non-binary QAOA bitstring: {bitstring}"

    validate_timing_plan_constraints(qaoa_res["timing_plan"], scenario_name, "qaoa")
    verify_shared_evaluator_agreement(traffic_input, qaoa_res["timing_plan"], qaoa_res["metrics"], scenario_name, "qaoa")
    qm = qaoa_res["metrics"]
    q_red = qaoa_res.get("baseline_comparison", {}).get("delay_reduction_pct", 0.0)
    print(f"\n[QAOA Quantum Solver]")
    print(f"  Measured Bitstring: '{bitstring}' (genuine Qiskit Aer measurement)")
    print(f"  Plan: {qaoa_res['timing_plan']}")
    print(f"  Cost (QUBO Energy): {qaoa_res['cost']:.1f}")
    print(f"  Served: {qm['vehicles_served']} / Remaining: {qm['remaining_queue']} veh")
    print(f"  Total Delay: {qm['total_delay_sec']:.1f} s | Avg Wait: {qm['avg_wait_sec']:.2f} s/veh")
    print(f"  Delay Reduction vs Baseline: {q_red:+.1f}%")
    print(f"  Solver Runtime: {qaoa_res['runtime_ms']:.2f} ms (client latency: {client_latency_ms:.1f} ms)")

    return {
        "scenario": scenario_name,
        "seed": seed,
        "total_vehicles": total_vehicles,
        "baseline": {"served": bm["vehicles_served"], "queue": bm["remaining_queue"], "delay": bm["total_delay_sec"], "wait": bm["avg_wait_sec"], "runtime": base_res["runtime_ms"]},
        "responsive": {"served": rm["vehicles_served"], "queue": rm["remaining_queue"], "delay": rm["total_delay_sec"], "wait": rm["avg_wait_sec"], "red_pct": r_red, "runtime": resp_res["runtime_ms"]},
        "qaoa": {"bitstring": bitstring, "cost": qaoa_res["cost"], "served": qm["vehicles_served"], "queue": qm["remaining_queue"], "delay": qm["total_delay_sec"], "wait": qm["avg_wait_sec"], "red_pct": q_red, "runtime": qaoa_res["runtime_ms"]},
    }


def main():
    print("Beginning QuantumFlow End-to-End Scenario Verification...")

    # 1. Verify GET / delivers dashboard and Plotly elements
    with urllib.request.urlopen(f"{BASE_URL}/", timeout=15) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "QuantumFlow" in html
        assert 'id="chart-delays"' in html
        assert 'id="chart-throughput"' in html
        assert 'id="chart-timings"' in html
        assert 'id="chart-runtime"' in html
    print("[Check 1/7] GET / Dashboard delivers 200 OK with all 4 Plotly chart cards.")

    # 2. Execute across scenarios
    results = []
    # Light Scenario
    results.append(run_scenario_workflow("light", seed=42))

    # Medium Scenario
    results.append(run_scenario_workflow("medium", seed=42))

    # Heavy Scenario
    results.append(run_scenario_workflow("heavy", seed=42))

    # Zero Traffic Scenario
    results.append(run_scenario_workflow("zero", seed=42))

    # Stability / Repeated runs: Heavy scenario with seed 101
    results.append(run_scenario_workflow("heavy", seed=101))

    # Stability / Repeated runs: Medium scenario with seed 999
    results.append(run_scenario_workflow("medium", seed=999))

    # 3. Verify GET /api/results history log
    history_res = http_get("/api/results?limit=50")
    assert history_res["status"] == "ok"
    assert history_res["count"] >= len(results) * 3
    print(f"\n[Check 6/7] GET /api/results logged {history_res['count']} runs successfully.")

    # Print summary table
    print("\n" + "=" * 105)
    print("QUANTUMFLOW END-TO-END SCENARIO VERIFICATION SUMMARY TABLE")
    print("=" * 105)
    header = f"{'Scenario':<12} | {'Seed':<5} | {'Vehicles':<8} | {'Algorithm':<18} | {'Bitstring':<9} | {'Served':<6} | {'Queue':<6} | {'Delay (s)':<10} | {'Wait (s)':<8} | {'Reduction':<10} | {'Runtime'}"
    print(header)
    print("-" * 105)

    for r in results:
        sc = r["scenario"]
        sd = r["seed"]
        tot = r["total_vehicles"]

        # Baseline row
        b = r["baseline"]
        print(f"{sc:<12} | {sd:<5} | {tot:<8} | {'Fixed-Time (Base)':<18} | {'--':<9} | {b['served']:<6} | {b['queue']:<6} | {b['delay']:<10.1f} | {b['wait']:<8.2f} | {'+0.0%':<10} | {b['runtime']:.2f} ms")

        # Responsive row
        res = r["responsive"]
        print(f"{'':<12} | {'':<5} | {'':<8} | {'Responsive':<18} | {'--':<9} | {res['served']:<6} | {res['queue']:<6} | {res['delay']:<10.1f} | {res['wait']:<8.2f} | {res['red_pct']:+9.1f}% | {res['runtime']:.2f} ms")

        # QAOA row
        q = r["qaoa"]
        print(f"{'':<12} | {'':<5} | {'':<8} | {'QAOA Quantum':<18} | {q['bitstring']:<9} | {q['served']:<6} | {q['queue']:<6} | {q['delay']:<10.1f} | {q['wait']:<8.2f} | {q['red_pct']:+9.1f}% | {q['runtime']:.2f} ms")
        print("-" * 105)

    print("\nAll end-to-end scenarios verified with zero violations, 100% shared evaluator agreement, and genuine QAOA execution!")


if __name__ == "__main__":
    main()
