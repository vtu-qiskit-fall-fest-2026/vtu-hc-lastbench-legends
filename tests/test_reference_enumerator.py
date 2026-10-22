"""
QuantumFlow — Test Suite: 4-Bit Reference Enumerator
tests/test_reference_enumerator.py  ·  Owner: Quantum Engineer / Team Lead

Tests proving:
  1. Every one of the candidate plans and all 16 decoded plans are valid under
     docs/INTERFACES.md cycle (60 s) and green duration (15–45 s) constraints.
  2. Every 4-bit string ("0000" to "1111") is decoded correctly according to the
     documented bit ordering (Bit 0 -> A, Bit 1 -> B, Bit 2 -> C, Bit 3 -> D).
  3. The pure Python enumerator correctly evaluates all 16 combinations using the
     shared traffic evaluator (metrics.traffic_model.evaluate).
  4. Invalid inputs (bitstring length, non-binary characters, wrong types) raise ValueError.
  5. The enumerator functions as an exact reference baseline for identifying the discrete optimum.
"""

from __future__ import annotations

import sys
import pytest

from metrics.traffic_model import evaluate as evaluate_traffic
from quantum.reference_enumerator import (
    ALL_BITSTRINGS,
    DEFAULT_CANDIDATE_PLANS,
    DEFAULT_INTERSECTIONS,
    GRID_CANDIDATE_PLANS,
    GRID_INTERSECTIONS,
    NUM_COMBINATIONS,
    NUM_INTERSECTIONS,
    PLAN_EW_PRIORITY,
    PLAN_NS_PRIORITY,
    EnumerationRecord,
    ReferenceEnumerator,
    decode_bitstring,
    enumerate_all_plans,
    evaluate_bitstring,
    find_optimal_plan,
    resolve_candidate_plans,
    validate_candidate_pair,
)
from shared.types import ApproachCounts, ApproachTiming, SolverResult, TimingPlan, TrafficInput
from shared.validators import (
    CYCLE_SEC,
    MAX_GREEN,
    MIN_GREEN,
    validate_timing_plan,
    validate_traffic_input,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def named_traffic_input() -> TrafficInput:
    """Standard 4-intersection named snapshot (A, B, C, D)."""
    return {
        "A": ApproachCounts(ns_count=45, ew_count=12),
        "B": ApproachCounts(ns_count=30, ew_count=20),
        "C": ApproachCounts(ns_count=10, ew_count=40),
        "D": ApproachCounts(ns_count=25, ew_count=15),
    }


@pytest.fixture
def grid_traffic_input() -> TrafficInput:
    """Standard 2x2 grid snapshot ((0,0), (0,1), (1,0), (1,1))."""
    return {
        "(0,0)": ApproachCounts(ns_count=45, ew_count=12),
        "(0,1)": ApproachCounts(ns_count=30, ew_count=20),
        "(1,0)": ApproachCounts(ns_count=10, ew_count=40),
        "(1,1)": ApproachCounts(ns_count=25, ew_count=15),
    }


@pytest.fixture
def ns_dominant_input() -> TrafficInput:
    """All intersections heavily congested along North-South."""
    return {
        iid: ApproachCounts(ns_count=40, ew_count=5)
        for iid in DEFAULT_INTERSECTIONS
    }


@pytest.fixture
def ew_dominant_input() -> TrafficInput:
    """All intersections heavily congested along East-West."""
    return {
        iid: ApproachCounts(ns_count=5, ew_count=40)
        for iid in DEFAULT_INTERSECTIONS
    }


# ---------------------------------------------------------------------------
# 1. Candidate Signal Plans Validation
# ---------------------------------------------------------------------------
class TestCandidatePlansDefinition:
    """Tests proving the defined candidate signal plans are strictly valid."""

    def test_default_intersections_count(self):
        assert len(DEFAULT_INTERSECTIONS) == 4
        assert DEFAULT_INTERSECTIONS == ("A", "B", "C", "D")

    def test_grid_intersections_count(self):
        assert len(GRID_INTERSECTIONS) == 4
        assert GRID_INTERSECTIONS == ("(0,0)", "(0,1)", "(1,0)", "(1,1)")

    def test_all_16_bitstrings_count_and_format(self):
        assert len(ALL_BITSTRINGS) == 16
        assert ALL_BITSTRINGS[0] == "0000"
        assert ALL_BITSTRINGS[15] == "1111"
        for i, b in enumerate(ALL_BITSTRINGS):
            assert len(b) == 4
            assert int(b, 2) == i

    @pytest.mark.parametrize("iid", DEFAULT_INTERSECTIONS)
    def test_named_candidate_plans_meet_cycle_constraints(self, iid):
        plan_0, plan_1 = DEFAULT_CANDIDATE_PLANS[iid]

        # Plan 0 (NS-priority): ns=45, ew=15
        assert plan_0["ns_green"] == 45
        assert plan_0["ew_green"] == 15
        assert plan_0["ns_green"] + plan_0["ew_green"] == CYCLE_SEC
        assert MIN_GREEN <= plan_0["ns_green"] <= MAX_GREEN
        assert MIN_GREEN <= plan_0["ew_green"] <= MAX_GREEN

        # Plan 1 (EW-priority): ns=15, ew=45
        assert plan_1["ns_green"] == 15
        assert plan_1["ew_green"] == 45
        assert plan_1["ns_green"] + plan_1["ew_green"] == CYCLE_SEC
        assert MIN_GREEN <= plan_1["ns_green"] <= MAX_GREEN
        assert MIN_GREEN <= plan_1["ew_green"] <= MAX_GREEN

    @pytest.mark.parametrize("iid", GRID_INTERSECTIONS)
    def test_grid_candidate_plans_meet_cycle_constraints(self, iid):
        plan_0, plan_1 = GRID_CANDIDATE_PLANS[iid]
        assert plan_0["ns_green"] + plan_0["ew_green"] == CYCLE_SEC
        assert plan_1["ns_green"] + plan_1["ew_green"] == CYCLE_SEC
        assert MIN_GREEN <= plan_0["ns_green"] <= MAX_GREEN
        assert MIN_GREEN <= plan_1["ew_green"] <= MAX_GREEN

    def test_validate_candidate_pair_success(self):
        p0 = ApproachTiming(ns_green=35, ew_green=25)
        p1 = ApproachTiming(ns_green=20, ew_green=40)
        # Should not raise
        validate_candidate_pair(p0, p1, iid="test_int")

    def test_validate_candidate_pair_bad_cycle(self):
        p0 = ApproachTiming(ns_green=30, ew_green=25)  # sum = 55 != 60
        p1 = ApproachTiming(ns_green=30, ew_green=30)
        with pytest.raises(ValueError, match="must equal CYCLE_SEC"):
            validate_candidate_pair(p0, p1)

    def test_validate_candidate_pair_green_out_of_bounds(self):
        p0 = ApproachTiming(ns_green=50, ew_green=10)  # 50 > 45, 10 < 15
        p1 = ApproachTiming(ns_green=30, ew_green=30)
        with pytest.raises(ValueError, match="outside \\[15, 45\\]"):
            validate_candidate_pair(p0, p1)


# ---------------------------------------------------------------------------
# 2. Bitstring Decoding Correctness
# ---------------------------------------------------------------------------
class TestBitstringDecoding:
    """Tests proving every bitstring is decoded correctly per documented bit ordering."""

    def test_bitstring_0000_all_ns_priority(self):
        plan = decode_bitstring("0000")
        for iid in DEFAULT_INTERSECTIONS:
            assert plan[iid]["ns_green"] == 45
            assert plan[iid]["ew_green"] == 15

    def test_bitstring_1111_all_ew_priority(self):
        plan = decode_bitstring("1111")
        for iid in DEFAULT_INTERSECTIONS:
            assert plan[iid]["ns_green"] == 15
            assert plan[iid]["ew_green"] == 45

    def test_bit_0_controls_intersection_A(self):
        """Bit 0 (MSB, index 0) must control intersection A."""
        plan_0 = decode_bitstring("0000")
        plan_1 = decode_bitstring("1000")
        # Only A changes
        assert plan_0["A"]["ns_green"] == 45 and plan_0["A"]["ew_green"] == 15
        assert plan_1["A"]["ns_green"] == 15 and plan_1["A"]["ew_green"] == 45
        for iid in ("B", "C", "D"):
            assert plan_0[iid] == plan_1[iid]

    def test_bit_1_controls_intersection_B(self):
        """Bit 1 (index 1) must control intersection B."""
        plan_0 = decode_bitstring("0000")
        plan_1 = decode_bitstring("0100")
        assert plan_0["B"]["ns_green"] == 45 and plan_0["B"]["ew_green"] == 15
        assert plan_1["B"]["ns_green"] == 15 and plan_1["B"]["ew_green"] == 45
        for iid in ("A", "C", "D"):
            assert plan_0[iid] == plan_1[iid]

    def test_bit_2_controls_intersection_C(self):
        """Bit 2 (index 2) must control intersection C."""
        plan_0 = decode_bitstring("0000")
        plan_1 = decode_bitstring("0010")
        assert plan_0["C"]["ns_green"] == 45 and plan_0["C"]["ew_green"] == 15
        assert plan_1["C"]["ns_green"] == 15 and plan_1["C"]["ew_green"] == 45
        for iid in ("A", "B", "D"):
            assert plan_0[iid] == plan_1[iid]

    def test_bit_3_controls_intersection_D(self):
        """Bit 3 (LSB, index 3) must control intersection D."""
        plan_0 = decode_bitstring("0000")
        plan_1 = decode_bitstring("0001")
        assert plan_0["D"]["ns_green"] == 45 and plan_0["D"]["ew_green"] == 15
        assert plan_1["D"]["ns_green"] == 15 and plan_1["D"]["ew_green"] == 45
        for iid in ("A", "B", "C"):
            assert plan_0[iid] == plan_1[iid]

    @pytest.mark.parametrize("bitstring", ALL_BITSTRINGS)
    def test_every_bitstring_decodes_expected_approach_timing(self, bitstring):
        """Verify for every one of the 16 combinations that each bit matches the choice."""
        plan = decode_bitstring(bitstring)
        for i, iid in enumerate(DEFAULT_INTERSECTIONS):
            bit = bitstring[i]
            expected_ns = 45 if bit == "0" else 15
            expected_ew = 15 if bit == "0" else 45
            assert plan[iid]["ns_green"] == expected_ns, f"{bitstring} int {iid} ns_green"
            assert plan[iid]["ew_green"] == expected_ew, f"{bitstring} int {iid} ew_green"

    def test_grid_intersections_decoding(self):
        plan = decode_bitstring("0110", intersections=GRID_INTERSECTIONS)
        assert plan["(0,0)"]["ns_green"] == 45  # bit 0 = 0 -> Plan 0
        assert plan["(0,1)"]["ns_green"] == 15  # bit 1 = 1 -> Plan 1
        assert plan["(1,0)"]["ns_green"] == 15  # bit 2 = 1 -> Plan 1
        assert plan["(1,1)"]["ns_green"] == 45  # bit 3 = 0 -> Plan 0

    def test_custom_candidate_plans_decoding(self):
        custom_candidates = {
            "A": (ApproachTiming(ns_green=40, ew_green=20), ApproachTiming(ns_green=20, ew_green=40)),
            "B": (ApproachTiming(ns_green=35, ew_green=25), ApproachTiming(ns_green=25, ew_green=35)),
            "C": (ApproachTiming(ns_green=30, ew_green=30), ApproachTiming(ns_green=15, ew_green=45)),
            "D": (ApproachTiming(ns_green=45, ew_green=15), ApproachTiming(ns_green=25, ew_green=35)),
        }
        plan = decode_bitstring("0101", candidate_plans=custom_candidates)
        assert plan["A"] == {"ns_green": 40, "ew_green": 20}
        assert plan["B"] == {"ns_green": 25, "ew_green": 35}
        assert plan["C"] == {"ns_green": 30, "ew_green": 30}
        assert plan["D"] == {"ns_green": 25, "ew_green": 35}


# ---------------------------------------------------------------------------
# 3. Validity of Every Plan Under Shared Contract
# ---------------------------------------------------------------------------
class TestEveryPlanValidity:
    """Tests proving EVERY one of the 16 decoded plans strictly passes shared validators."""

    @pytest.mark.parametrize("bitstring", ALL_BITSTRINGS)
    def test_all_16_named_plans_pass_validator(self, bitstring, named_traffic_input):
        plan = decode_bitstring(bitstring, DEFAULT_INTERSECTIONS)
        # Must not raise ValueError
        validate_timing_plan(plan, named_traffic_input)
        for iid in DEFAULT_INTERSECTIONS:
            ns = plan[iid]["ns_green"]
            ew = plan[iid]["ew_green"]
            assert ns + ew == CYCLE_SEC
            assert MIN_GREEN <= ns <= MAX_GREEN
            assert MIN_GREEN <= ew <= MAX_GREEN

    @pytest.mark.parametrize("bitstring", ALL_BITSTRINGS)
    def test_all_16_grid_plans_pass_validator(self, bitstring, grid_traffic_input):
        plan = decode_bitstring(bitstring, GRID_INTERSECTIONS)
        # Must not raise ValueError
        validate_timing_plan(plan, grid_traffic_input)
        for iid in GRID_INTERSECTIONS:
            ns = plan[iid]["ns_green"]
            ew = plan[iid]["ew_green"]
            assert ns + ew == CYCLE_SEC
            assert MIN_GREEN <= ns <= MAX_GREEN
            assert MIN_GREEN <= ew <= MAX_GREEN


# ---------------------------------------------------------------------------
# 4. Error Handling for Invalid Inputs
# ---------------------------------------------------------------------------
class TestInvalidInputs:
    """Tests proving invalid bitstrings or configurations raise ValueError."""

    @pytest.mark.parametrize("bad_bits", ["", "0", "01", "101", "00000", "010101"])
    def test_wrong_bitstring_length_raises(self, bad_bits):
        with pytest.raises(ValueError, match="Bitstring length must be 4"):
            decode_bitstring(bad_bits)

    @pytest.mark.parametrize("bad_bits", ["0002", "111a", "0 01", "true", "abcd"])
    def test_non_binary_characters_raise(self, bad_bits):
        with pytest.raises(ValueError, match="Must contain only '0' and '1'"):
            decode_bitstring(bad_bits)

    def test_non_string_type_raises(self):
        with pytest.raises(ValueError, match="bitstring must be a string"):
            decode_bitstring(1010)  # type: ignore

    def test_wrong_intersections_count_raises(self):
        with pytest.raises(ValueError, match="Expected 4 intersections"):
            decode_bitstring("0000", intersections=["A", "B", "C"])

    def test_missing_intersection_in_custom_candidate_plans_raises(self):
        incomplete = {
            "A": (ApproachTiming(ns_green=45, ew_green=15), ApproachTiming(ns_green=15, ew_green=45)),
            "B": (ApproachTiming(ns_green=45, ew_green=15), ApproachTiming(ns_green=15, ew_green=45)),
            # missing C and D
        }
        with pytest.raises(ValueError, match="Missing candidate plans for intersection"):
            decode_bitstring("0000", candidate_plans=incomplete)


# ---------------------------------------------------------------------------
# 5. Exhaustive Enumeration of All 16 Combinations
# ---------------------------------------------------------------------------
class TestEnumeratorExecution:
    """Tests proving the enumerator evaluates all 16 combinations via shared traffic evaluator."""

    def test_evaluates_exactly_16_records(self, named_traffic_input):
        records = enumerate_all_plans(named_traffic_input)
        assert len(records) == 16

    def test_records_contain_all_required_keys_and_valid_results(self, named_traffic_input):
        records = enumerate_all_plans(named_traffic_input)
        for i, rec in enumerate(records):
            assert rec["integer_value"] == i
            assert rec["bitstring"] == ALL_BITSTRINGS[i]
            assert "timing_plan" in rec
            assert "solver_result" in rec

            res = rec["solver_result"]
            assert res["status"] == "ok"
            assert res["error_msg"] is None
            assert res["algorithm"] == "reference_enumerator"

            metrics = res["metrics"]
            assert rec["avg_wait_sec"] == metrics["avg_wait_sec"]
            assert rec["total_delay_sec"] == metrics["total_delay_sec"]
            assert rec["vehicles_served"] == metrics["vehicles_served"]
            assert rec["remaining_queue"] == metrics["remaining_queue"]
            assert metrics["total_vehicles"] == 45 + 12 + 30 + 20 + 10 + 40 + 25 + 15

    def test_evaluate_matches_direct_traffic_model_evaluate(self, named_traffic_input):
        """Cross-check that enumerator results exactly match direct evaluate() calls."""
        records = enumerate_all_plans(named_traffic_input)
        for rec in records:
            direct_res = evaluate_traffic(
                traffic_input=named_traffic_input,
                timing_plan=rec["timing_plan"],
                algorithm="reference_enumerator",
            )
            assert rec["avg_wait_sec"] == direct_res["metrics"]["avg_wait_sec"]
            assert rec["total_delay_sec"] == direct_res["metrics"]["total_delay_sec"]
            assert rec["vehicles_served"] == direct_res["metrics"]["vehicles_served"]
            assert rec["remaining_queue"] == direct_res["metrics"]["remaining_queue"]

    def test_evaluate_bitstring_standalone(self, named_traffic_input):
        res = evaluate_bitstring("0101", named_traffic_input)
        assert res["status"] == "ok"
        assert res["timing_plan"]["A"]["ns_green"] == 45
        assert res["timing_plan"]["B"]["ns_green"] == 15
        assert res["timing_plan"]["C"]["ns_green"] == 45
        assert res["timing_plan"]["D"]["ns_green"] == 15


# ---------------------------------------------------------------------------
# 6. Optimization Landscape & Best Plan Identification
# ---------------------------------------------------------------------------
class TestOptimizationLandscape:
    """Tests proving the enumerator correctly identifies the optimal discrete configuration."""

    def test_ns_dominant_traffic_selects_all_ns_priority(self, ns_dominant_input):
        """When NS is congested at all intersections, optimal plan must be 0000."""
        best = find_optimal_plan(ns_dominant_input, objective="avg_wait_sec")
        assert best["bitstring"] == "0000"
        assert best["integer_value"] == 0

        # Compare against 1111 (all EW)
        records_by_bits = {r["bitstring"]: r for r in enumerate_all_plans(ns_dominant_input)}
        assert best["total_delay_sec"] < records_by_bits["1111"]["total_delay_sec"]
        assert best["vehicles_served"] > records_by_bits["1111"]["vehicles_served"]

    def test_ew_dominant_traffic_selects_all_ew_priority(self, ew_dominant_input):
        """When EW is congested at all intersections, optimal plan must be 1111."""
        best = find_optimal_plan(ew_dominant_input, objective="avg_wait_sec")
        assert best["bitstring"] == "1111"
        assert best["integer_value"] == 15

        records_by_bits = {r["bitstring"]: r for r in enumerate_all_plans(ew_dominant_input)}
        assert best["total_delay_sec"] < records_by_bits["0000"]["total_delay_sec"]
        assert best["vehicles_served"] > records_by_bits["0000"]["vehicles_served"]

    def test_mixed_traffic_selects_direction_matching_bits(self):
        """
        Intersections demand:
          A: NS dominant (40/5) -> Bit 0 = 0
          B: EW dominant (5/40) -> Bit 1 = 1
          C: NS dominant (40/5) -> Bit 2 = 0
          D: EW dominant (5/40) -> Bit 3 = 1
        Expected optimal bitstring: "0101".
        """
        traffic: TrafficInput = {
            "A": ApproachCounts(ns_count=40, ew_count=5),
            "B": ApproachCounts(ns_count=5, ew_count=40),
            "C": ApproachCounts(ns_count=40, ew_count=5),
            "D": ApproachCounts(ns_count=5, ew_count=40),
        }
        best = find_optimal_plan(traffic, objective="avg_wait_sec")
        assert best["bitstring"] == "0101"

    def test_vehicles_served_objective(self, ns_dominant_input):
        best = find_optimal_plan(ns_dominant_input, objective="vehicles_served")
        assert best["bitstring"] == "0000"

    def test_invalid_objective_raises(self, ns_dominant_input):
        with pytest.raises(ValueError, match="Unsupported objective"):
            find_optimal_plan(ns_dominant_input, objective="invalid_objective")


# ---------------------------------------------------------------------------
# 7. Object-Oriented Interface & Class Encapsulation
# ---------------------------------------------------------------------------
class TestReferenceEnumeratorClass:
    """Tests proving the ReferenceEnumerator class functions correctly."""

    def test_initialization_defaults(self):
        enumerator = ReferenceEnumerator()
        assert enumerator.intersections == DEFAULT_INTERSECTIONS
        assert set(enumerator.candidate_plans.keys()) == set(DEFAULT_INTERSECTIONS)

    def test_initialization_custom_intersections(self):
        enumerator = ReferenceEnumerator(intersections=GRID_INTERSECTIONS)
        assert enumerator.intersections == GRID_INTERSECTIONS
        assert set(enumerator.candidate_plans.keys()) == set(GRID_INTERSECTIONS)

    def test_initialization_bad_intersections_raises(self):
        with pytest.raises(ValueError, match="requires exactly 4 intersections"):
            ReferenceEnumerator(intersections=["A", "B", "C"])

    def test_class_decode_and_evaluate(self, named_traffic_input):
        enumerator = ReferenceEnumerator()
        plan = enumerator.decode("0011")
        assert plan["A"]["ns_green"] == 45
        assert plan["B"]["ns_green"] == 45
        assert plan["C"]["ns_green"] == 15
        assert plan["D"]["ns_green"] == 15

        records = enumerator.evaluate_all(named_traffic_input)
        assert len(records) == 16

        best = enumerator.find_optimal(named_traffic_input)
        assert best["bitstring"] in ALL_BITSTRINGS


# ---------------------------------------------------------------------------
# 8. Architectural Separations & Forbidden Imports Check
# ---------------------------------------------------------------------------
class TestArchitecturalSeparation:
    """Verify that enumerator does not violate import restrictions."""

    def test_no_flask_in_enumerator(self):
        import quantum.reference_enumerator as re_mod
        assert "flask" not in sys.modules or "flask" not in dir(re_mod)
        with open(re_mod.__file__, "r", encoding="utf-8") as f:
            content = f.read()
        assert "import flask" not in content
        assert "from flask" not in content

    def test_no_qiskit_in_enumerator(self):
        """Reference enumerator is pure Python and must not depend on qiskit."""
        import quantum.reference_enumerator as re_mod
        with open(re_mod.__file__, "r", encoding="utf-8") as f:
            content = f.read()
        assert "import qiskit" not in content
        assert "from qiskit" not in content
