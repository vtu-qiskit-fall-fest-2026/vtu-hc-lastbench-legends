"""
QuantumFlow — Traffic Model Evaluator Tests
tests/test_traffic_model.py

Hand calculations use SERVICE_SEC_PER_VEHICLE = 2 (capacity = floor(green/2))
and leftover-red delay = remaining * opposing_green.
"""

import pytest

from metrics.traffic_model import (
    SERVICE_SEC_PER_VEHICLE,
    evaluate,
    served_and_remaining,
    service_capacity,
)
from shared.types import ApproachTiming
from shared.validators import CYCLE_SEC, MAX_GREEN, MIN_GREEN, validate_timing_plan
from simulator.baseline import fixed_time_plan, traffic_responsive_plan
from simulator.traffic_simulator import INTERSECTIONS, TrafficSimulator


def _named(ns: int, ew: int):
    return {iid: {"ns_count": ns, "ew_count": ew} for iid in INTERSECTIONS}


def _plan(ns_green: int, ew_green: int, keys=INTERSECTIONS):
    return {iid: ApproachTiming(ns_green=ns_green, ew_green=ew_green) for iid in keys}


class TestServiceCapacity:
    def test_headway_constant(self):
        assert SERVICE_SEC_PER_VEHICLE == 2

    def test_capacity_for_typical_greens(self):
        assert service_capacity(30) == 15
        assert service_capacity(15) == 7
        assert service_capacity(45) == 22
        assert service_capacity(0) == 0

    def test_served_never_exceeds_queue_or_capacity(self):
        served, remaining = served_and_remaining(10, 30)  # cap 15
        assert served == 10 and remaining == 0
        served, remaining = served_and_remaining(20, 30)  # cap 15
        assert served == 15 and remaining == 5
        served, remaining = served_and_remaining(0, 45)
        assert served == 0 and remaining == 0

    def test_remaining_never_negative(self):
        served, remaining = served_and_remaining(3, 60)
        assert remaining >= 0
        assert served + remaining == 3


class TestEmptyQueues:
    def test_all_zero_metrics(self):
        traffic = _named(0, 0)
        result = evaluate(traffic, _plan(30, 30), algorithm="test")
        m = result["metrics"]
        assert m["total_vehicles"] == 0
        assert m["vehicles_served"] == 0
        assert m["remaining_queue"] == 0
        assert m["avg_wait_sec"] == 0.0
        assert m["total_delay_sec"] == 0.0
        assert m["remaining_queue"] != m["avg_wait_sec"] or m["avg_wait_sec"] == 0.0


class TestHighDemandAndCapacity:
    def test_high_demand_leaves_remainder(self):
        traffic = _named(40, 40)
        m = evaluate(traffic, _plan(30, 30))["metrics"]
        # cap 15 per approach × 2 approaches × 4 intersections = 120 served
        assert m["total_vehicles"] == 80 * 4
        assert m["vehicles_served"] == 15 * 2 * 4
        assert m["remaining_queue"] == m["total_vehicles"] - m["vehicles_served"]
        assert m["remaining_queue"] > 0

    def test_remaining_is_count_not_wait(self):
        traffic = _named(40, 0)
        m = evaluate(traffic, _plan(30, 30))["metrics"]
        # remaining is vehicles; avg_wait_sec is modeled seconds
        assert m["remaining_queue"] == (40 - 15) * 4  # 100
        assert m["avg_wait_sec"] != m["remaining_queue"]
        assert m["total_delay_sec"] != m["remaining_queue"]


class TestInvalidTimingPlans:
    def test_cycle_mismatch_rejected(self):
        traffic = _named(2, 2)
        bad = _plan(20, 30)
        with pytest.raises(ValueError, match="CYCLE_SEC"):
            evaluate(traffic, bad)

    def test_green_below_min_rejected(self):
        traffic = _named(2, 2)
        with pytest.raises(ValueError, match=r"\[15, 45\]"):
            evaluate(traffic, _plan(10, 50))

    def test_key_mismatch_rejected(self):
        traffic = _named(2, 2)
        bad = {"(9,9)": ApproachTiming(ns_green=30, ew_green=30)}
        with pytest.raises(ValueError):
            evaluate(traffic, bad)

    def test_empty_plan_rejected(self):
        with pytest.raises(ValueError, match="must not be empty"):
            evaluate(_named(1, 1), {})


class TestHandCalculatedExamples:
    """Independent arithmetic checks of the documented formulas."""

    def test_undersaturated_equal_split(self):
        # 10 NS + 4 EW, 30/30 green → both queues < capacity 15 → all served.
        traffic = _named(10, 4)
        m = evaluate(traffic, _plan(30, 30))["metrics"]
        assert m["total_vehicles"] == 14 * 4
        assert m["vehicles_served"] == 14 * 4
        assert m["remaining_queue"] == 0
        assert m["total_delay_sec"] == 0.0
        assert m["avg_wait_sec"] == 0.0

    def test_ns_overflow_one_cycle(self):
        # Per intersection: ns=20, ew=10, greens 30/30.
        # cap_ns=15 → served 15, rem 5, delay_ns = 5 * 30 = 150
        # cap_ew=15 → served 10, rem 0
        # 4 intersections: vehicles=120, served=100, rem=20, delay=600, avg=5.00
        traffic = _named(20, 10)
        m = evaluate(traffic, _plan(30, 30))["metrics"]
        assert m["total_vehicles"] == 120
        assert m["vehicles_served"] == 100
        assert m["remaining_queue"] == 20
        assert m["total_delay_sec"] == 600.0
        assert m["avg_wait_sec"] == 5.0

    def test_max_green_increases_ns_capacity(self):
        traffic = _named(40, 2)
        max_ns = evaluate(traffic, _plan(MAX_GREEN, MIN_GREEN))["metrics"]
        min_ns = evaluate(traffic, _plan(MIN_GREEN, MAX_GREEN))["metrics"]
        # floor(45/2)=22 vs floor(15/2)=7 NS served per intersection
        assert max_ns["vehicles_served"] > min_ns["vehicles_served"]
        assert max_ns["remaining_queue"] < min_ns["remaining_queue"]


class TestConventionalControllersSameInput:
    def test_compare_fixed_and_responsive_on_simulator_snapshot(self):
        traffic = TrafficSimulator().get_traffic_input()
        fixed_plan = fixed_time_plan(traffic)
        resp_plan = traffic_responsive_plan(traffic)
        validate_timing_plan(fixed_plan, traffic)
        validate_timing_plan(resp_plan, traffic)

        fixed = evaluate(traffic, fixed_plan, algorithm="fixed-time")
        resp = evaluate(traffic, resp_plan, algorithm="traffic-responsive")

        assert set(fixed["timing_plan"].keys()) == set(resp["timing_plan"].keys())
        assert fixed["metrics"]["total_vehicles"] == resp["metrics"]["total_vehicles"]
        assert fixed["metrics"]["remaining_queue"] >= 0
        assert resp["metrics"]["remaining_queue"] >= 0
        assert fixed["metrics"]["vehicles_served"] <= fixed["metrics"]["total_vehicles"]
        assert resp["metrics"]["vehicles_served"] <= resp["metrics"]["total_vehicles"]
        # Unbalanced default queues (A=45/12, C=10/40) → plans differ
        assert fixed["timing_plan"] != resp["timing_plan"]
        # Demand-proportional split should not serve fewer vehicles overall
        assert resp["metrics"]["vehicles_served"] >= fixed["metrics"]["vehicles_served"]

    def test_equal_demand_controllers_agree(self):
        traffic = _named(8, 8)
        fixed = evaluate(traffic, fixed_time_plan(traffic), algorithm="fixed-time")
        resp = evaluate(
            traffic, traffic_responsive_plan(traffic), algorithm="traffic-responsive"
        )
        assert fixed["timing_plan"] == resp["timing_plan"]
        assert fixed["metrics"]["vehicles_served"] == resp["metrics"]["vehicles_served"]
        assert fixed["metrics"]["avg_wait_sec"] == resp["metrics"]["avg_wait_sec"]

    def test_evaluator_is_plan_source_of_truth(self):
        """Controllers only produce plans; scores always come from evaluate()."""
        traffic = TrafficSimulator().get_traffic_input()
        plan = traffic_responsive_plan(traffic)
        a = evaluate(traffic, plan, algorithm="traffic-responsive")
        b = evaluate(traffic, plan, algorithm="traffic-responsive")
        assert a["metrics"] == b["metrics"]
        assert a["metrics"]["remaining_queue"] == (
            a["metrics"]["total_vehicles"] - a["metrics"]["vehicles_served"]
        )
