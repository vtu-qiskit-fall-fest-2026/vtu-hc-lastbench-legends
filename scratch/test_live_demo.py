"""
QuantumFlow — Live Demonstration Automated Verification Script
Verifies:
- GET / (Dashboard HTML)
- GET /api/traffic (Current Snapshot)
- POST /api/optimize/baseline (Fixed-Time Baseline Button)
- POST /api/optimize/responsive (Traffic-Responsive Button)
- POST /api/optimize/qaoa (QAOA Quantum Solver Button - standard & fast tuning)
"""
import json
import time
import urllib.request

BASE_URL = "http://localhost:5000"

def test_live_demo():
    print("=================================================================")
    print("QUANTUMFLOW LIVE DEMONSTRATION VERIFICATION")
    print("=================================================================")

    # 1. GET /
    t0 = time.perf_counter()
    with urllib.request.urlopen(f"{BASE_URL}/") as r:
        html = r.read().decode("utf-8")
        assert r.status == 200
        assert "QuantumFlow" in html
        lat_index = (time.perf_counter() - t0) * 1000
    print(f"[1/5] GET / Dashboard: HTTP {r.status} OK ({lat_index:.1f} ms, {len(html)} bytes)")

    # 2. GET /api/traffic
    t0 = time.perf_counter()
    with urllib.request.urlopen(f"{BASE_URL}/api/traffic") as r:
        t_data = json.loads(r.read().decode("utf-8"))
        traffic_input = t_data["traffic_input"]
        tot_veh = t_data["total_vehicles"]
        lat_traffic = (time.perf_counter() - t0) * 1000
    print(f"[2/5] GET /api/traffic: HTTP {r.status} OK ({lat_traffic:.1f} ms, {tot_veh} vehicles)")

    # 3. POST /api/optimize/baseline
    t0 = time.perf_counter()
    req = urllib.request.Request(
        f"{BASE_URL}/api/optimize/baseline",
        data=json.dumps({"traffic_input": traffic_input}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        base_res = json.loads(r.read().decode("utf-8"))
        lat_base = (time.perf_counter() - t0) * 1000
    print(f"[3/5] POST /api/optimize/baseline (Fixed-Time):")
    print(f"      Status: {base_res['status']} | Latency: {lat_base:.1f} ms | Solver: {base_res['runtime_ms']:.2f} ms")
    print(f"      Total Delay: {base_res['metrics']['total_delay_sec']:.1f} s | Served: {base_res['metrics']['vehicles_served']} veh")

    # 4. POST /api/optimize/responsive
    t0 = time.perf_counter()
    req = urllib.request.Request(
        f"{BASE_URL}/api/optimize/responsive",
        data=json.dumps({"traffic_input": traffic_input}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        resp_res = json.loads(r.read().decode("utf-8"))
        lat_resp = (time.perf_counter() - t0) * 1000
    red_resp = resp_res.get("baseline_comparison", {}).get("delay_reduction_pct", 0.0)
    print(f"[4/5] POST /api/optimize/responsive (Adaptive):")
    print(f"      Status: {resp_res['status']} | Latency: {lat_resp:.1f} ms | Solver: {resp_res['runtime_ms']:.2f} ms")
    print(f"      Total Delay: {resp_res['metrics']['total_delay_sec']:.1f} s | Delay Reduction: {red_resp:+.1f}%")

    # 5. POST /api/optimize/qaoa (Standard: 1024 shots, 50 maxiter)
    t0 = time.perf_counter()
    req = urllib.request.Request(
        f"{BASE_URL}/api/optimize/qaoa",
        data=json.dumps({
            "traffic_input": traffic_input,
            "p_layers": 1,
            "shots": 1024,
            "maxiter": 50,
            "seed": 42
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        qaoa_res = json.loads(r.read().decode("utf-8"))
        lat_qaoa = (time.perf_counter() - t0) * 1000
    red_qaoa = qaoa_res.get("baseline_comparison", {}).get("delay_reduction_pct", 0.0)
    print(f"[5/5] POST /api/optimize/qaoa (Genuine Quantum Simulator - Qiskit Aer):")
    print(f"      Status: {qaoa_res['status']} ({qaoa_res.get('solver_status')}) | Latency: {lat_qaoa:.1f} ms | Solver: {qaoa_res['runtime_ms']:.2f} ms")
    print(f"      Measured Bitstring: '{qaoa_res.get('bitstring')}' | QUBO Energy: {qaoa_res.get('cost')}")
    print(f"      Total Delay: {qaoa_res['metrics']['total_delay_sec']:.1f} s | Delay Reduction: {red_qaoa:+.1f}%")

    # Fast demonstration tuning verification (shots=256, maxiter=20)
    t0 = time.perf_counter()
    req = urllib.request.Request(
        f"{BASE_URL}/api/optimize/qaoa",
        data=json.dumps({
            "traffic_input": traffic_input,
            "p_layers": 1,
            "shots": 256,
            "maxiter": 20,
            "seed": 42
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        qaoa_fast = json.loads(r.read().decode("utf-8"))
        lat_fast = (time.perf_counter() - t0) * 1000
    print(f"\n[Optional Fast Demo Mode] QAOA with 256 shots, maxiter=20:")
    print(f"      Status: {qaoa_fast['status']} | Latency: {lat_fast:.1f} ms | Solver: {qaoa_fast['runtime_ms']:.2f} ms | Bitstring: '{qaoa_fast.get('bitstring')}'")

    print("\nAll live demonstration endpoints successfully verified!")

if __name__ == "__main__":
    test_live_demo()
