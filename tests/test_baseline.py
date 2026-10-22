"""
QuantumFlow — Test Suite: Fixed-Time Baseline Controller
tests/test_baseline.py
"""

import pytest

from shared.types import ApproachTiming
from shared.validators import (
    CYCLE_SEC,
    MAX_GREEN,
    MIN_GREEN,
    validate_timing_plan,
)
from simulator.baseline import (
    EW_GREEN_FIXED,
    NS_GREEN_FIXED,
    FixedTimeController,
    TrafficResponsiveController,
    fixed_time_plan,
    traffic_responsive_plan,
)
from simulator.traffic_simulator import INTERSECTIONS, TrafficSimulator


@pytest.fixture
def four_intersections():
    """Named A–D traffic input from the 4-intersection simulator."""
    return TrafficSimulator().get_traffic_input()


@pytest.fixture
def four_intersections_grid():
    return TrafficSimulator().get_traffic_input(as_grid=True)


class TestFixedTimeFourIntersections:
    def test_all_four_intersections_present(self, four_intersections):
        plan = fixed_time_plan(four_intersections)
        assert set(plan.keys()) == set(INTERSECTIONS)
        assert len(plan) == 4

    @pytest.mark.parametrize("iid", ["A", "B", "C", "D"])
    def test_equal_split_per_intersection(self, four_intersections, iid):
        plan = fixed_time_plan(four_intersections)
        assert plan[iid]["ns_green"] == 30
        assert plan[iid]["ew_green"] == 30
        assert plan[iid]["ns_green"] + plan[iid]["ew_green"] == CYCLE_SEC

    def test_cycle_and_green_limits(self, four_intersections):
        plan = fixed_time_plan(four_intersections)
        validate_timing_plan(plan, four_intersections)
        for iid, timing in plan.items():
            assert MIN_GREEN <= timing["ns_green"] <= MAX_GREEN, iid
            assert MIN_GREEN <= timing["ew_green"] <= MAX_GREEN, iid
            assert timing["ns_green"] + timing["ew_green"] == CYCLE_SEC, iid

    def test_preserves_named_key_format(self, four_intersections):
        plan = fixed_time_plan(four_intersections)
        assert set(plan.keys()) == {"A", "B", "C", "D"}

    def test_preserves_grid_key_format(self, four_intersections_grid):
        plan = fixed_time_plan(four_intersections_grid)
        assert set(plan.keys()) == {"(0,0)", "(0,1)", "(1,0)", "(1,1)"}
        for timing in plan.values():
            assert timing == {"ns_green": 30, "ew_green": 30}

    def test_ignores_queue_lengths(self, four_intersections):
        """Fixed-time split does not depend on NS/EW demand."""
        plan = fixed_time_plan(four_intersections)
        for timing in plan.values():
            assert timing["ns_green"] == NS_GREEN_FIXED
            assert timing["ew_green"] == EW_GREEN_FIXED

    def test_controller_class_matches_function(self, four_intersections):
        via_fn = fixed_time_plan(four_intersections)
        via_cls = FixedTimeController().plan(four_intersections)
        assert via_fn == via_cls

    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            fixed_time_plan({})


class TestMalformedPlans:
    def test_empty_plan_rejected(self, four_intersections):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_timing_plan({}, four_intersections)

    def test_cycle_mismatch_rejected(self, four_intersections):
        bad = {
            iid: ApproachTiming(ns_green=20, ew_green=30)
            for iid in four_intersections
        }
        with pytest.raises(ValueError, match="CYCLE_SEC"):
            validate_timing_plan(bad, four_intersections)

    def test_ns_below_min_rejected(self, four_intersections):
        bad = {
            iid: ApproachTiming(ns_green=10, ew_green=50)
            for iid in four_intersections
        }
        with pytest.raises(ValueError, match=r"\[15, 45\]"):
            validate_timing_plan(bad, four_intersections)

    def test_ns_above_max_rejected(self, four_intersections):
        bad = {
            iid: ApproachTiming(ns_green=50, ew_green=10)
            for iid in four_intersections
        }
        with pytest.raises(ValueError, match=r"\[15, 45\]"):
            validate_timing_plan(bad, four_intersections)

    def test_missing_intersection_rejected(self, four_intersections):
        incomplete = {
            "A": ApproachTiming(ns_green=30, ew_green=30),
            "B": ApproachTiming(ns_green=30, ew_green=30),
            "C": ApproachTiming(ns_green=30, ew_green=30),
        }
        with pytest.raises(ValueError, match="keys do not match"):
            validate_timing_plan(incomplete, four_intersections)

    def test_missing_field_rejected(self, four_intersections):
        bad = {iid: {"ns_green": 30} for iid in four_intersections}
        with pytest.raises(ValueError, match="missing required field"):
            validate_timing_plan(bad, four_intersections)

    def test_controller_rejects_cycle_mismatch(self, four_intersections):
        with pytest.raises(ValueError, match="CYCLE_SEC"):
            fixed_time_plan(four_intersections, ns_green=20, ew_green=30)

    def test_controller_rejects_out_of_range_green(self, four_intersections):
        with pytest.raises(ValueError, match=r"\[15, 45\]"):
            fixed_time_plan(four_intersections, ns_green=10, ew_green=50)

    def test_controller_rejects_non_integer_green(self, four_intersections):
        with pytest.raises(ValueError, match="must be an integer"):
            fixed_time_plan(four_intersections, ns_green=30.0, ew_green=30)

    def test_controller_init_rejects_malformed_split(self):
        with pytest.raises(ValueError, match="CYCLE_SEC"):
            FixedTimeController(ns_green=40, ew_green=40)


def _uniform_named(ns_count: int, ew_count: int):
    """2×2 named TrafficInput with the same counts at A–D."""
    return {
        iid: {"ns_count": ns_count, "ew_count": ew_count}
        for iid in INTERSECTIONS
    }


class TestTrafficResponsiveBoundaries:
    def test_zero_vehicles_equal_split(self):
        traffic = _uniform_named(0, 0)
        plan = traffic_responsive_plan(traffic)
        validate_timing_plan(plan, traffic)
        for timing in plan.values():
            assert timing["ns_green"] == NS_GREEN_FIXED
            assert timing["ew_green"] == EW_GREEN_FIXED

    def test_equal_counts_equal_split(self):
        traffic = _uniform_named(7, 7)
        plan = traffic_responsive_plan(traffic)
        for timing in plan.values():
            assert timing["ns_green"] == timing["ew_green"] == CYCLE_SEC // 2

    def test_extreme_ns_imbalance_clamps_to_max(self):
        traffic = _uniform_named(1000, 0)
        plan = traffic_responsive_plan(traffic)
        validate_timing_plan(plan, traffic)
        for timing in plan.values():
            assert timing["ns_green"] == MAX_GREEN
            assert timing["ew_green"] == MIN_GREEN

    def test_extreme_ew_imbalance_clamps_to_min_ns(self):
        traffic = _uniform_named(0, 1000)
        plan = traffic_responsive_plan(traffic)
        validate_timing_plan(plan, traffic)
        for timing in plan.values():
            assert timing["ns_green"] == MIN_GREEN
            assert timing["ew_green"] == MAX_GREEN

    def test_one_sided_single_vehicle(self):
        traffic = _uniform_named(1, 0)
        plan = traffic_responsive_plan(traffic)
        for timing in plan.values():
            assert timing["ns_green"] == MAX_GREEN
            assert timing["ew_green"] == MIN_GREEN
            assert timing["ns_green"] + timing["ew_green"] == CYCLE_SEC

    def test_mixed_boundary_intersections(self):
        traffic = {
            "A": {"ns_count": 0, "ew_count": 0},
            "B": {"ns_count": 4, "ew_count": 4},
            "C": {"ns_count": 90, "ew_count": 1},
            "D": {"ns_count": 1, "ew_count": 90},
        }
        plan = traffic_responsive_plan(traffic)
        validate_timing_plan(plan, traffic)
        assert plan["A"] == {"ns_green": 30, "ew_green": 30}
        assert plan["B"] == {"ns_green": 30, "ew_green": 30}
        assert plan["C"]["ns_green"] == MAX_GREEN
        assert plan["D"]["ew_green"] == MAX_GREEN

    def test_always_respects_cycle_and_limits(self, four_intersections):
        plan = traffic_responsive_plan(four_intersections)
        validate_timing_plan(plan, four_intersections)
        for iid, timing in plan.items():
            assert MIN_GREEN <= timing["ns_green"] <= MAX_GREEN, iid
            assert MIN_GREEN <= timing["ew_green"] <= MAX_GREEN, iid
            assert timing["ns_green"] + timing["ew_green"] == CYCLE_SEC, iid

    def test_preserves_input_key_format(self, four_intersections, four_intersections_grid):
        named = traffic_responsive_plan(four_intersections)
        grid = traffic_responsive_plan(four_intersections_grid)
        assert set(named.keys()) == {"A", "B", "C", "D"}
        assert set(grid.keys()) == {"(0,0)", "(0,1)", "(1,0)", "(1,1)"}

    def test_controller_class_matches_function(self, four_intersections):
        via_fn = traffic_responsive_plan(four_intersections)
        via_cls = TrafficResponsiveController().plan(four_intersections)
        assert via_fn == via_cls

    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            traffic_responsive_plan({})


class TestResponsiveVsFixedTime:
    def test_zero_traffic_matches_fixed_time(self):
        traffic = _uniform_named(0, 0)
        assert traffic_responsive_plan(traffic) == fixed_time_plan(traffic)

    def test_equal_counts_match_fixed_time(self):
        traffic = _uniform_named(12, 12)
        assert traffic_responsive_plan(traffic) == fixed_time_plan(traffic)

    def test_imbalance_differs_from_fixed_time(self, four_intersections):
        """Default simulator queues are unbalanced, so splits should diverge."""
        fixed = fixed_time_plan(four_intersections)
        responsive = traffic_responsive_plan(four_intersections)
        assert set(responsive.keys()) == set(fixed.keys())
        assert responsive != fixed
        # A is NS-heavy (45/12); C is EW-heavy (10/40)
        assert responsive["A"]["ns_green"] > fixed["A"]["ns_green"]
        assert responsive["C"]["ew_green"] > fixed["C"]["ew_green"]

    def test_ns_heavy_gets_more_green_than_fixed(self):
        traffic = _uniform_named(9, 1)
        fixed = fixed_time_plan(traffic)
        responsive = traffic_responsive_plan(traffic)
        for iid in traffic:
            assert responsive[iid]["ns_green"] > fixed[iid]["ns_green"]
            assert responsive[iid]["ew_green"] < fixed[iid]["ew_green"]

    def test_ew_heavy_gets_more_green_than_fixed(self):
        traffic = _uniform_named(1, 9)
        fixed = fixed_time_plan(traffic)
        responsive = traffic_responsive_plan(traffic)
        for iid in traffic:
            assert responsive[iid]["ew_green"] > fixed[iid]["ew_green"]
            assert responsive[iid]["ns_green"] < fixed[iid]["ns_green"]
