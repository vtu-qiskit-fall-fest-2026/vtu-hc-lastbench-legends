"""
QuantumFlow — Test Suite: Shared Types & Validators
tests/test_validators.py  ·  Owner: Team Lead
"""

import pytest
from shared.types import ApproachCounts, ApproachTiming
from shared.validators import (
    validate_traffic_input,
    validate_timing_plan,
    CYCLE_SEC,
    MIN_GREEN,
    MAX_GREEN,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def small_input():
    return {
        "(0,0)": ApproachCounts(ns_count=3, ew_count=1),
        "(0,1)": ApproachCounts(ns_count=0, ew_count=5),
        "(1,0)": ApproachCounts(ns_count=2, ew_count=2),
        "(1,1)": ApproachCounts(ns_count=1, ew_count=0),
    }


@pytest.fixture
def valid_plan():
    return {
        "(0,0)": ApproachTiming(ns_green=35, ew_green=25),
        "(0,1)": ApproachTiming(ns_green=15, ew_green=45),
        "(1,0)": ApproachTiming(ns_green=30, ew_green=30),
        "(1,1)": ApproachTiming(ns_green=45, ew_green=15),
    }


# ---------------------------------------------------------------------------
# validate_traffic_input
# ---------------------------------------------------------------------------
class TestValidateTrafficInput:
    def test_valid_2x2(self, small_input):
        validate_traffic_input(small_input)   # must not raise

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_traffic_input({})

    def test_bad_key_format(self):
        with pytest.raises(ValueError, match="invalid intersection ID"):
            validate_traffic_input({"0,0": ApproachCounts(ns_count=1, ew_count=0)})

    def test_negative_ns_count(self):
        bad = {"(0,0)": ApproachCounts(ns_count=-1, ew_count=0)}
        with pytest.raises(ValueError, match="must be >= 0"):
            validate_traffic_input(bad)

    def test_negative_ew_count(self):
        bad = {"(0,0)": ApproachCounts(ns_count=0, ew_count=-3)}
        with pytest.raises(ValueError, match="must be >= 0"):
            validate_traffic_input(bad)

    def test_non_square_grid(self):
        incomplete = {
            "(0,0)": ApproachCounts(ns_count=1, ew_count=0),
            "(0,1)": ApproachCounts(ns_count=0, ew_count=1),
            # (1,0) and (1,1) missing → not square
        }
        with pytest.raises(ValueError, match="incomplete grid|not square"):
            validate_traffic_input(incomplete)

    def test_zero_counts_valid(self):
        """All-zero counts are valid (empty intersection)."""
        inp = {
            "(0,0)": ApproachCounts(ns_count=0, ew_count=0),
            "(0,1)": ApproachCounts(ns_count=0, ew_count=0),
            "(1,0)": ApproachCounts(ns_count=0, ew_count=0),
            "(1,1)": ApproachCounts(ns_count=0, ew_count=0),
        }
        validate_traffic_input(inp)   # must not raise


# ---------------------------------------------------------------------------
# validate_timing_plan
# ---------------------------------------------------------------------------
class TestValidateTimingPlan:
    def test_valid_plan(self, valid_plan, small_input):
        validate_timing_plan(valid_plan, small_input)   # must not raise

    def test_empty_raises(self, small_input):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_timing_plan({}, small_input)

    def test_ns_below_min(self, small_input):
        bad = {k: ApproachTiming(ns_green=10, ew_green=50) for k in small_input}
        with pytest.raises(ValueError, match=r"\[15, 45\]"):
            validate_timing_plan(bad, small_input)

    def test_ns_above_max(self, small_input):
        bad = {k: ApproachTiming(ns_green=50, ew_green=10) for k in small_input}
        with pytest.raises(ValueError, match=r"\[15, 45\]"):
            validate_timing_plan(bad, small_input)

    def test_cycle_violated(self, small_input):
        bad = {k: ApproachTiming(ns_green=30, ew_green=35) for k in small_input}
        with pytest.raises(ValueError, match=f"CYCLE_SEC={CYCLE_SEC}"):
            validate_timing_plan(bad, small_input)

    def test_key_mismatch(self, valid_plan):
        extra_input = {"(9,9)": ApproachCounts(ns_count=1, ew_count=1),
                       "(9,8)": ApproachCounts(ns_count=0, ew_count=0),
                       "(8,9)": ApproachCounts(ns_count=1, ew_count=0),
                       "(8,8)": ApproachCounts(ns_count=0, ew_count=1)}
        with pytest.raises(ValueError, match="keys do not match"):
            validate_timing_plan(valid_plan, extra_input)

    def test_boundary_values_valid(self, small_input):
        plan = {k: ApproachTiming(ns_green=MIN_GREEN, ew_green=MAX_GREEN) for k in small_input}
        validate_timing_plan(plan, small_input)
        plan2 = {k: ApproachTiming(ns_green=MAX_GREEN, ew_green=MIN_GREEN) for k in small_input}
        validate_timing_plan(plan2, small_input)
