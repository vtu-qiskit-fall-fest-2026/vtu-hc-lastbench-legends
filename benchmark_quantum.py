"""
QuantumFlow — Comprehensive Quantum Solver Benchmark & Gap Analysis
Evaluates QAOA vs. Reference Enumerator across multiple traffic scenarios and repeated runs.
"""

import time
from typing import Dict
from simulator.traffic_simulator import TrafficSimulator
from quantum.quantum_solver import evaluate_quantum_workflow, solve_traffic_qubo
from quantum.reference_enumerator import find_optimal_plan
from shared.types import ApproachCounts, TrafficInput
from shared.validators import validate_timing_plan

def main():
    sim = TrafficSimulator()

    scenarios: Dict[str, TrafficInput] = {
        "Benchmark (Initial)": sim.get_traffic_input(as_grid=False),
        "Light Traffic": sim.generate_scenario("light", seed=10),
        "Medium Traffic": sim.generate_scenario("medium", seed=20),
        "Heavy Traffic": sim.generate_scenario("heavy", seed=30),
        "NS-Dominant": {iid: ApproachCounts(ns_count=45, ew_count=5) for iid in ("A", "B", "C", "D")},
        "EW-Dominant": {iid: ApproachCounts(ns_count=5, ew_count=45) for iid in ("A", "B", "C", "D")},
        "Checkerboard": {
            "A": ApproachCounts(ns_count=40, ew_count=10),
            "B": ApproachCounts(ns_count=10, ew_count=40),
            "C": ApproachCounts(ns_count=40, ew_count=10),
            "D": ApproachCounts(ns_count=10, ew_count=40),
        },
        "Zero Traffic": {iid: ApproachCounts(ns_count=0, ew_count=0) for iid in ("A", "B", "C", "D")},
    }

    print("=" * 105)
    print("PART 1: MULTI-SCENARIO BENCHMARK (QAOA vs. EXHAUSTIVE REFERENCE)")
    print("=" * 105)
    header = f"{'Scenario':<22} | {'QAOA Bit':<8} | {'QAOA Delay':<10} | {'Ex Bit':<8} | {'Ex Delay':<10} | {'Gap (s)':<8} | {'QAOA ms':<8} | {'Ex ms':<6}"
    print(header)
    print("-" * 105)

    all_timing_valid = True

    for name, ti in scenarios.items():
        res = evaluate_quantum_workflow(ti, coord_weight=0.0, p_layers=1, shots=1024, maxiter=50, seed=42)
        gap = res["objective_gap"] if res["objective_gap"] is not None else 0.0
        q_bit = res["qaoa_bitstring"] or "None"
        q_delay = res["qaoa_total_delay_sec"] if res["qaoa_total_delay_sec"] is not None else 0.0
        ex_bit = res["exhaustive_bitstring"]
        ex_delay = res["exhaustive_total_delay_sec"]
        q_ms = res["qaoa_runtime_ms"]
        ex_ms = res["exhaustive_runtime_ms"]

        # Validate timing plan constraints
        try:
            validate_timing_plan(res["qaoa_result"]["timing_plan"], ti)
        except Exception as exc:
            all_timing_valid = False
            print(f"Timing validation failed for {name}: {exc}")

        print(f"{name:<22} | {q_bit:<8} | {q_delay:<10.1f} | {ex_bit:<8} | {ex_delay:<10.1f} | {gap:<8.1f} | {q_ms:<8.1f} | {ex_ms:<6.1f}")

    print("-" * 105)
    print(f"All Decoded Timing Plans Passed Validation: {all_timing_valid}")

    # Part 2: Repeated runs on benchmark to check stability across seeds
    print("\n" + "=" * 105)
    print("PART 2: REPEATED RUNS ON BENCHMARK SCENARIO (SEEDS 1 to 5)")
    print("=" * 105)
    rep_header = f"{'Run / Seed':<12} | {'Measured Bit':<12} | {'QAOA Cost':<10} | {'Total Delay':<11} | {'Avg Wait':<9} | {'Veh Served':<10} | {'Runtime ms':<10}"
    print(rep_header)
    print("-" * 105)

    bench_ti = scenarios["Benchmark (Initial)"]
    for run_idx, seed in enumerate([42, 101, 2024, 7, 999], 1):
        sol = solve_traffic_qubo(bench_ti, coord_weight=0.0, p_layers=1, shots=1024, maxiter=50, seed=seed)
        m = sol["metrics"]
        print(f"Run {run_idx} (seed {seed:<4}) | {sol['bitstring']:<12} | {sol['cost']:<10.1f} | {m['total_delay_sec']:<11.1f} | {m['avg_wait_sec']:<9.2f} | {m['vehicles_served']:<10} | {sol['runtime_ms']:<10.1f}")

    print("=" * 105)

if __name__ == "__main__":
    main()
