"""
QuantumFlow — Test Suite: Metrics Evaluation & Controller Comparison
tests/test_metrics.py  ·  Owner: Metrics Engineer / Team Lead

Validates:
  1. Hand-calculated unit tests for queue service, leftover-red delay, and average wait.
  2. Hand-calculated percentage changes against fixed-time baseline (delay reduction %, wait reduction %, throughput delta).
  3. Division-by-zero protection under empty traffic (zero counts) and undersaturated conditions (zero delay).
  4. Clear distinction between queue counts (integer vehicles) and waiting times (float seconds).
  5. Side-by-side comparison across Fixed-Time, Traffic-Responsive, and QAOA on identical traffic input.
  6. Non-fabrication guarantee: Failed / missing QAOA runs are never replaced with classical results.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest

from metrics.metrics import (
    BaselinePercentageChange,
    calculate_plan_metrics,
    compare_controllers,
    compute_baseline_comparison,
    evaluate_fixed_time,
    evaluate_qaoa,
    evaluate_traffic_responsive,
    format_comparison_table,
    safe_percentage_increase,
    safe_percentage_reduction,
)
from shared.types import ApproachCounts, ApproachTiming, SolverResult, TrafficInput
from shared.validators import CYCLE_SEC, validate_timing_plan
from simulator.traffic_simulator import INTERSECTIONS, TrafficSimulator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def benchmark_traffic() -> TrafficInput:
    """Standard 4-intersection simulator snapshot: A=45/12, B=30/20, C=10/40, D=25/15."""
    return TrafficSimulator().get_traffic_input(as_grid=False)


@pytest.fixture
def empty_traffic() -> TrafficInput:
    """All intersections with 0 vehicles."""
    return {iid: ApproachCounts(ns_count=0, ew_count=0) for iid in INTERSECTIONS}


@pytest.fixture
def undersaturated_traffic() -> TrafficInput:
    """Demand strictly below approach capacity: all queues = 5 vehicles."""
    return {iid: ApproachCounts(ns_count=5, ew_count=5) for iid in INTERSECTIONS}


# ---------------------------------------------------------------------------
# 1. Hand-Calculated Unit Tests (Exact Arithmetic Verification)
# ---------------------------------------------------------------------------
class TestHandCalculatedMetrics:
    """
    Verifies that the evaluator arithmetic matches hand calculations:
      - capacity = floor(green / 2)
      - served = min(queue, capacity)
      - remaining = max(0, queue - served)
      - delay_ns = remaining_ns * ew_green
      - delay_ew = remaining_ew * ns_green
      - total_delay = sum(delay_ns + delay_ew)
      - avg_wait = total_delay / total_vehicles (if > 0 else 0)
    """

    def test_single_congested_intersection_fixed_time_hand_calculation(self):
        # A: ns=45, ew=12. B, C, D: ns=0, ew=0. Split 30s / 30s for all.
        # cap_ns = floor(30/2) = 15. served_ns = 15, rem_ns = 30. delay_ns = 30 * 30 = 900s.
        # cap_ew = floor(30/2) = 15. served_ew = 12, rem_ew = 0. delay_ew = 0s.
        # B, C, D contributes 0 vehicles, 0 served, 0 delay.
        # Total vehicles = 57, served = 27, remaining = 30.
        # Total delay = 900s, avg_wait = 900 / 57 = 15.7894... -> 15.79s.
        traffic: TrafficInput = {
            "A": ApproachCounts(ns_count=45, ew_count=12),
            "B": ApproachCounts(ns_count=0, ew_count=0),
            "C": ApproachCounts(ns_count=0, ew_count=0),
            "D": ApproachCounts(ns_count=0, ew_count=0),
        }
        plan = {iid: ApproachTiming(ns_green=30, ew_green=30) for iid in ("A", "B", "C", "D")}

        res = calculate_plan_metrics(traffic, plan, algorithm="fixed-time")
        m = res["metrics"]

        assert m["total_vehicles"] == 57
        assert m["vehicles_served"] == 27
        assert m["remaining_queue"] == 30
        assert m["total_delay_sec"] == 900.0
        assert m["avg_wait_sec"] == 15.79

    def test_single_congested_intersection_responsive_split_hand_calculation(self):
        # A: ns=45, ew=12. B, C, D: ns=0, ew=0.
        # A split: 45s NS / 15s EW. B, C, D: 30s NS / 30s EW.
        # A: cap_ns = floor(45/2) = 22. served_ns = 22, rem_ns = 23. delay_ns = 23 * 15 = 345s.
        #    cap_ew = floor(15/2) = 7. served_ew = 7, rem_ew = 5. delay_ew = 5 * 45 = 225s.
        # Total vehicles = 57, served = 29, remaining = 28.
        # Total delay = 345 + 225 = 570s, avg_wait = 570 / 57 = 10.00s.
        traffic: TrafficInput = {
            "A": ApproachCounts(ns_count=45, ew_count=12),
            "B": ApproachCounts(ns_count=0, ew_count=0),
            "C": ApproachCounts(ns_count=0, ew_count=0),
            "D": ApproachCounts(ns_count=0, ew_count=0),
        }
        plan = {
            "A": ApproachTiming(ns_green=45, ew_green=15),
            "B": ApproachTiming(ns_green=30, ew_green=30),
            "C": ApproachTiming(ns_green=30, ew_green=30),
            "D": ApproachTiming(ns_green=30, ew_green=30),
        }

        res = calculate_plan_metrics(traffic, plan, algorithm="traffic-responsive")
        m = res["metrics"]

        assert m["total_vehicles"] == 57
        assert m["vehicles_served"] == 29
        assert m["remaining_queue"] == 28
        assert m["total_delay_sec"] == 570.0
        assert m["avg_wait_sec"] == 10.00

    def test_benchmark_snapshot_fixed_time_hand_calculation(self, benchmark_traffic):
        # 4 intersections: A(45,12), B(30,20), C(10,40), D(25,15)
        # Fixed-time (30/30) capacity is 15 veh per approach.
        # A: served=15+12=27, rem=30+0=30, delay=30*30=900
        # B: served=15+15=30, rem=15+5=20, delay=15*30 + 5*30 = 600
        # C: served=10+15=25, rem=0+25=25, delay=25*30=750
        # D: served=15+15=30, rem=10+0=10, delay=10*30=300
        # Sums: vehicles=197, served=112, rem=85, delay=2550.0s, avg_wait = 2550/197 = 12.94s
        fixed_res = evaluate_fixed_time(benchmark_traffic)
        m = fixed_res["metrics"]

        assert m["total_vehicles"] == 197
        assert m["vehicles_served"] == 112
        assert m["remaining_queue"] == 85
        assert m["total_delay_sec"] == 2550.0
        assert m["avg_wait_sec"] == 12.94

    def test_benchmark_snapshot_traffic_responsive_hand_calculation(self, benchmark_traffic):
        # Responsive plans: A(45,15), B(36,24), C(15,45), D(38,22)
        # A: delay=570, served=29, rem=28
        # B: served=18+12=30, rem=12+8=20, delay=12*24 + 8*36 = 288 + 288 = 576
        # C: served=7+22=29, rem=3+18=21, delay=3*45 + 18*15 = 135 + 270 = 405
        # D: served=19+11=30, rem=6+4=10, delay=6*22 + 4*38 = 132 + 152 = 284
        # Sums: vehicles=197, served=118, rem=79, delay=1835.0s, avg_wait = 1835/197 = 9.31s
        resp_res = evaluate_traffic_responsive(benchmark_traffic)
        m = resp_res["metrics"]

        assert m["total_vehicles"] == 197
        assert m["vehicles_served"] == 118
        assert m["remaining_queue"] == 79
        assert m["total_delay_sec"] == 1835.0
        assert m["avg_wait_sec"] == 9.31

    def test_benchmark_snapshot_qaoa_optimal_plan_hand_calculation(self, benchmark_traffic):
        # Optimal discrete QAOA bitstring '0010': A(45,15), B(45,15), C(15,45), D(45,15)
        # A: delay=570, served=29, rem=28
        # B: cap_ns=22, served_ns=22, rem_ns=8, delay_ns=8*15=120
        #    cap_ew=7, served_ew=7, rem_ew=13, delay_ew=13*45=585 -> delay_B = 705, served=29, rem=21
        # C: delay=405, served=29, rem=21
        # D: cap_ns=22, served_ns=22, rem_ns=3, delay_ns=3*15=45
        #    cap_ew=7, served_ew=7, rem_ew=8, delay_ew=8*45=360 -> delay_D = 405, served=29, rem=11
        # Sums: delay = 570 + 705 + 405 + 405 = 2085.0s, served = 29*4 = 116, rem = 81, avg_wait = 2085/197 = 10.58s
        qaoa_res = evaluate_qaoa(benchmark_traffic, seed=42)
        m = qaoa_res["metrics"]

        assert qaoa_res["status"] == "ok"
        assert m["total_vehicles"] == 197
        assert m["vehicles_served"] == 116
        assert m["remaining_queue"] == 81
        assert m["total_delay_sec"] == 2085.0
        assert m["avg_wait_sec"] == 10.58


# ---------------------------------------------------------------------------
# 2. Hand-Calculated Percentage Change Against Baseline
# ---------------------------------------------------------------------------
class TestPercentageChangeAgainstBaseline:
    """Verifies percentage changes calculated relative to the Fixed-Time baseline."""

    def test_responsive_percentage_changes(self, benchmark_traffic):
        fixed_res = evaluate_fixed_time(benchmark_traffic)
        resp_res = evaluate_traffic_responsive(benchmark_traffic)

        cmp = compute_baseline_comparison(fixed_res, resp_res)

        # Delay reduction: (2550 - 1835) / 2550 * 100 = 715 / 2550 * 100 = 28.04%
        assert cmp["delay_reduction_pct"] == pytest.approx(28.04, abs=0.01)

        # Wait reduction: (12.94 - 9.31) / 12.94 * 100 = 28.05%
        assert cmp["wait_reduction_pct"] == pytest.approx(28.05, abs=0.01)

        # Vehicles served % increase: (118 - 112) / 112 * 100 = 5.36%
        assert cmp["throughput_pct_change"] == pytest.approx(5.36, abs=0.01)

        # Throughput delta: (118 - 112) / 197 = 6 / 197 = +0.0305
        assert cmp["throughput_delta"] == pytest.approx(0.0305, abs=0.0001)

        # Remaining queue reduction: (85 - 79) / 85 * 100 = 6 / 85 * 100 = 7.06%
        assert cmp["queue_reduction_pct"] == pytest.approx(7.06, abs=0.01)

    def test_qaoa_percentage_changes(self, benchmark_traffic):
        fixed_res = evaluate_fixed_time(benchmark_traffic)
        qaoa_res = evaluate_qaoa(benchmark_traffic, seed=42)

        cmp = compute_baseline_comparison(fixed_res, qaoa_res)

        # Delay reduction: (2550 - 2085) / 2550 * 100 = 465 / 2550 * 100 = 18.24%
        assert cmp["delay_reduction_pct"] == pytest.approx(18.24, abs=0.01)

        # Wait reduction: (12.94 - 10.58) / 12.94 * 100 = 18.24%
        assert cmp["wait_reduction_pct"] == pytest.approx(18.24, abs=0.01)

        # Vehicles served % increase: (116 - 112) / 112 * 100 = 3.57%
        assert cmp["throughput_pct_change"] == pytest.approx(3.57, abs=0.01)

        # Throughput delta: (116 - 112) / 197 = 4 / 197 = +0.0203
        assert cmp["throughput_delta"] == pytest.approx(0.0203, abs=0.0001)

        # Remaining queue reduction: (85 - 81) / 85 * 100 = 4 / 85 * 100 = 4.71%
        assert cmp["queue_reduction_pct"] == pytest.approx(4.71, abs=0.01)


# ---------------------------------------------------------------------------
# 3. Division-by-Zero Protection
# ---------------------------------------------------------------------------
class TestDivisionByZeroSafety:
    """Verifies that empty traffic snapshots or zero-delay conditions never divide by zero."""

    def test_empty_traffic_input(self, empty_traffic):
        fixed_res = evaluate_fixed_time(empty_traffic)
        resp_res = evaluate_traffic_responsive(empty_traffic)
        cmp = compute_baseline_comparison(fixed_res, resp_res)

        assert fixed_res["metrics"]["total_vehicles"] == 0
        assert fixed_res["metrics"]["vehicles_served"] == 0
        assert fixed_res["metrics"]["remaining_queue"] == 0
        assert fixed_res["metrics"]["avg_wait_sec"] == 0.0
        assert fixed_res["metrics"]["total_delay_sec"] == 0.0

        assert cmp["delay_reduction_pct"] == 0.0
        assert cmp["wait_reduction_pct"] == 0.0
        assert cmp["queue_reduction_pct"] == 0.0
        assert cmp["throughput_pct_change"] == 0.0
        assert cmp["throughput_delta"] == 0.0

    def test_undersaturated_traffic_zero_delay(self, undersaturated_traffic):
        # All approaches have 5 vehicles <= capacity 15. All vehicles clear. Total delay = 0.
        fixed_res = evaluate_fixed_time(undersaturated_traffic)
        resp_res = evaluate_traffic_responsive(undersaturated_traffic)
        cmp = compute_baseline_comparison(fixed_res, resp_res)

        assert fixed_res["metrics"]["total_delay_sec"] == 0.0
        assert resp_res["metrics"]["total_delay_sec"] == 0.0
        assert fixed_res["metrics"]["remaining_queue"] == 0
        assert resp_res["metrics"]["remaining_queue"] == 0

        # Safe percentage handles baseline = 0 gracefully
        assert cmp["delay_reduction_pct"] == 0.0
        assert cmp["wait_reduction_pct"] == 0.0
        assert cmp["queue_reduction_pct"] == 0.0
        assert cmp["throughput_pct_change"] == 0.0

    def test_safe_percentage_helpers_edge_cases(self):
        assert safe_percentage_reduction(0.0, 0.0) == 0.0
        assert safe_percentage_reduction(0.0, 10.0) == -100.0
        assert safe_percentage_reduction(100.0, 50.0) == 50.0
        assert safe_percentage_reduction(100.0, 150.0) == -50.0

        assert safe_percentage_increase(0.0, 0.0) == 0.0
        assert safe_percentage_increase(0.0, 10.0) == 100.0
        assert safe_percentage_increase(100.0, 150.0) == 50.0
        assert safe_percentage_increase(100.0, 50.0) == -50.0


# ---------------------------------------------------------------------------
# 4. Queue Count vs. Waiting Time Distinction
# ---------------------------------------------------------------------------
class TestQueueCountVsWaitingTimeDistinction:
    """Confirms remaining_queue is an integer vehicle count, not a time duration."""

    def test_remaining_queue_is_vehicle_count_not_time(self, benchmark_traffic):
        res = evaluate_fixed_time(benchmark_traffic)
        m = res["metrics"]

        # Remaining queue is integer vehicles
        assert isinstance(m["remaining_queue"], int)
        assert m["remaining_queue"] == m["total_vehicles"] - m["vehicles_served"]
        assert m["remaining_queue"] == 85

        # Delay and wait are floats in seconds
        assert isinstance(m["total_delay_sec"], float)
        assert isinstance(m["avg_wait_sec"], float)
        assert m["total_delay_sec"] == 2550.0
        assert m["avg_wait_sec"] == 12.94

        # Queue count is distinctly different from delay values
        assert m["remaining_queue"] != m["total_delay_sec"]
        assert m["remaining_queue"] != m["avg_wait_sec"]


# ---------------------------------------------------------------------------
# 5. Non-Fabrication Guarantee on QAOA Failure
# ---------------------------------------------------------------------------
class TestNoFabricationOnQAOAFailure:
    """Verifies that missing or errored QAOA results are NEVER replaced with classical answers."""

    def test_qaoa_timeout_reports_timeout_without_fabricating_results(self, benchmark_traffic):
        # Force timeout
        qaoa_timeout_res = evaluate_qaoa(benchmark_traffic, timeout_sec=0.0001)
        assert qaoa_timeout_res["status"] == "timeout"
        assert qaoa_timeout_res["cost"] is None
        assert "timeout" in qaoa_timeout_res["error_msg"].lower()

        # In compare_controllers, qaoa_vs_baseline must be None
        with patch("metrics.metrics.evaluate_qaoa", return_value=qaoa_timeout_res):
            comp = compare_controllers(benchmark_traffic)
            assert comp["qaoa"]["status"] == "timeout"
            assert comp["qaoa"]["cost"] is None
            assert comp["qaoa_vs_baseline"] is None

            qaoa_row = comp["summary_rows"][2]
            assert qaoa_row["controller"] == "QAOA Quantum Solver"
            assert qaoa_row["status"] == "timeout"
            assert qaoa_row["delay_reduction_pct"] is None

    def test_qaoa_error_reports_error_without_fabricating_results(self, benchmark_traffic):
        error_res = SolverResult(
            algorithm="qaoa",
            timing_plan={"A": ApproachTiming(ns_green=30, ew_green=30)},
            cost=None,
            metrics={
                "total_vehicles": 197,
                "vehicles_served": 0,
                "remaining_queue": 197,
                "avg_wait_sec": 0.0,
                "total_delay_sec": 0.0,
                "runtime_ms": 10.0,
            },
            runtime_ms=10.0,
            status="error",
            error_msg="Simulated QPU driver failure",
        )

        with patch("metrics.metrics.evaluate_qaoa", return_value=error_res):
            comp = compare_controllers(benchmark_traffic)
            assert comp["qaoa"]["status"] == "error"
            assert comp["qaoa"]["cost"] is None
            assert comp["qaoa_vs_baseline"] is None
            assert comp["summary_rows"][2]["status"] == "error"


# ---------------------------------------------------------------------------
# 6. Full Controller Comparison Integration
# ---------------------------------------------------------------------------
class TestCompareControllersIntegration:
    """Verifies end-to-end controller comparison and table formatting."""

    def test_compare_controllers_full_benchmark(self, benchmark_traffic):
        res = compare_controllers(benchmark_traffic, p_layers=1, shots=512, maxiter=30, seed=42)

        assert res["fixed_time"]["status"] == "ok"
        assert res["traffic_responsive"]["status"] == "ok"
        assert res["qaoa"]["status"] == "ok"

        # Check summary rows
        rows = res["summary_rows"]
        assert len(rows) == 3
        assert rows[0]["controller"] == "Fixed-Time (Baseline)"
        assert rows[1]["controller"] == "Traffic-Responsive"
        assert rows[2]["controller"] == "QAOA Quantum Solver"

        # Validate timing plans for all controllers
        validate_timing_plan(res["fixed_time"]["timing_plan"], benchmark_traffic)
        validate_timing_plan(res["traffic_responsive"]["timing_plan"], benchmark_traffic)
        validate_timing_plan(res["qaoa"]["timing_plan"], benchmark_traffic)

        # Check table formatting
        table_str = format_comparison_table(res)
        assert "Fixed-Time (Baseline)" in table_str
        assert "Traffic-Responsive" in table_str
        assert "QAOA Quantum Solver" in table_str
        assert "Delay Red %" in table_str
        assert "+28.0%" in table_str
        assert "+18.2%" in table_str
