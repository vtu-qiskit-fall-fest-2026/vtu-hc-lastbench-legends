"""
QuantumFlow — Test Suite: Classical Solver & Evaluator
tests/test_solvers.py  ·  Owner: Team Lead
"""

import pytest
from shared.types import ApproachCounts, ApproachTiming
from shared.validators import CYCLE_SEC, MIN_GREEN, MAX_GREEN
from simulator.classical_solver import greedy_optimize
from metrics.evaluator import evaluate, compare


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def uniform_input():
    """All intersections equally congested."""
    return {
        f"({r},{c})": ApproachCounts(ns_count=2, ew_count=2)
        for r in range(2) for c in range(2)
    }


@pytest.fixture
def ns_heavy_input():
    """NS approach heavily congested."""
    return {
        f"({r},{c})": ApproachCounts(ns_count=9, ew_count=1)
        for r in range(2) for c in range(2)
    }


@pytest.fixture
def ew_heavy_input():
    """EW approach heavily congested."""
    return {
        f"({r},{c})": ApproachCounts(ns_count=1, ew_count=9)
        for r in range(2) for c in range(2)
    }


@pytest.fixture
def empty_input():
    """No vehicles anywhere."""
    return {
        f"({r},{c})": ApproachCounts(ns_count=0, ew_count=0)
        for r in range(2) for c in range(2)
    }


# ---------------------------------------------------------------------------
# greedy_optimize
# ---------------------------------------------------------------------------
class TestGreedyOptimize:
    def test_returns_solver_result_keys(self, uniform_input):
        result = greedy_optimize(uniform_input)
        for key in ("algorithm", "timing_plan", "cost", "metrics",
                    "runtime_ms", "status", "error_msg"):
            assert key in result, f"Missing key: {key}"

    def test_algorithm_is_greedy(self, uniform_input):
        assert greedy_optimize(uniform_input)["algorithm"] == "greedy"

    def test_status_ok(self, uniform_input):
        assert greedy_optimize(uniform_input)["status"] == "ok"

    def test_cost_is_none(self, uniform_input):
        assert greedy_optimize(uniform_input)["cost"] is None

    def test_cycle_constraint_all_intersections(self, uniform_input):
        plan = greedy_optimize(uniform_input)["timing_plan"]
        for iid, timing in plan.items():
            total = timing["ns_green"] + timing["ew_green"]
            assert total == CYCLE_SEC, f"{iid}: {timing['ns_green']}+{timing['ew_green']}={total}"

    def test_green_time_bounds(self, uniform_input):
        plan = greedy_optimize(uniform_input)["timing_plan"]
        for iid, timing in plan.items():
            assert MIN_GREEN <= timing["ns_green"] <= MAX_GREEN, f"{iid} ns_green out of bounds"
            assert MIN_GREEN <= timing["ew_green"] <= MAX_GREEN, f"{iid} ew_green out of bounds"

    def test_ns_heavy_favours_ns_green(self, ns_heavy_input):
        plan = greedy_optimize(ns_heavy_input)["timing_plan"]
        for timing in plan.values():
            assert timing["ns_green"] >= timing["ew_green"], \
                "NS-heavy input should give more green to NS approach"

    def test_ew_heavy_favours_ew_green(self, ew_heavy_input):
        plan = greedy_optimize(ew_heavy_input)["timing_plan"]
        for timing in plan.values():
            assert timing["ew_green"] >= timing["ns_green"], \
                "EW-heavy input should give more green to EW approach"

    def test_empty_input_gives_equal_split(self, empty_input):
        plan = greedy_optimize(empty_input)["timing_plan"]
        for timing in plan.values():
            assert timing["ns_green"] == timing["ew_green"] == CYCLE_SEC // 2

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            greedy_optimize({})

    def test_keys_match_input(self, uniform_input):
        plan = greedy_optimize(uniform_input)["timing_plan"]
        assert set(plan.keys()) == set(uniform_input.keys())


# ---------------------------------------------------------------------------
# evaluate (shared evaluator)
# ---------------------------------------------------------------------------
class TestEvaluate:
    def test_returns_solver_result(self, uniform_input):
        plan = {k: ApproachTiming(ns_green=30, ew_green=30) for k in uniform_input}
        result = evaluate(uniform_input, plan, algorithm="test")
        assert result["algorithm"] == "test"
        assert result["status"] == "ok"

    def test_metrics_present(self, uniform_input):
        plan = {k: ApproachTiming(ns_green=30, ew_green=30) for k in uniform_input}
        m = evaluate(uniform_input, plan)["metrics"]
        for field in ("total_vehicles", "vehicles_served", "remaining_queue",
                      "avg_wait_sec", "total_delay_sec", "runtime_ms"):
            assert field in m, f"Metrics missing field: {field}"

    def test_vehicles_served_le_total(self, uniform_input):
        plan = {k: ApproachTiming(ns_green=30, ew_green=30) for k in uniform_input}
        m = evaluate(uniform_input, plan)["metrics"]
        assert m["vehicles_served"] <= m["total_vehicles"]

    def test_remaining_queue_correct(self, uniform_input):
        plan = {k: ApproachTiming(ns_green=30, ew_green=30) for k in uniform_input}
        m = evaluate(uniform_input, plan)["metrics"]
        assert m["remaining_queue"] == m["total_vehicles"] - m["vehicles_served"]

    def test_key_mismatch_raises(self, uniform_input):
        bad_plan = {"(9,9)": ApproachTiming(ns_green=30, ew_green=30)}
        with pytest.raises(ValueError):
            evaluate(uniform_input, bad_plan)

    def test_max_green_for_ns_serves_more(self, ns_heavy_input):
        """More green for congested approach → more vehicles served."""
        plan_ns_max = {k: ApproachTiming(ns_green=MAX_GREEN, ew_green=MIN_GREEN)
                       for k in ns_heavy_input}
        plan_ns_min = {k: ApproachTiming(ns_green=MIN_GREEN, ew_green=MAX_GREEN)
                       for k in ns_heavy_input}
        served_max = evaluate(ns_heavy_input, plan_ns_max)["metrics"]["vehicles_served"]
        served_min = evaluate(ns_heavy_input, plan_ns_min)["metrics"]["vehicles_served"]
        assert served_max >= served_min, \
            "Max NS green should serve at least as many NS vehicles"


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------
class TestCompare:
    def test_compare_structure(self, uniform_input):
        plan = {k: ApproachTiming(ns_green=30, ew_green=30) for k in uniform_input}
        c = evaluate(uniform_input, plan, algorithm="greedy")
        q = evaluate(uniform_input, plan, algorithm="qaoa", cost=-1.5)
        out = compare(c, q)
        assert "classical" in out
        assert "quantum" in out
        assert "advantage" in out
        assert "throughput_delta" in out["advantage"]
        assert "wait_reduction_pct" in out["advantage"]
