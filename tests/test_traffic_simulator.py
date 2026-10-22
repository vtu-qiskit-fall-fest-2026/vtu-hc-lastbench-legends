"""
QuantumFlow — Traffic Simulator Test Suite
tests/test_traffic_simulator.py  ·  Owner: Team Lead

Tests:
  - Initial simulated vehicle counts (A=45/12, B=30/20, C=10/40, D=25/15)
  - Input retrieval and updating
  - Non-negative integer validation (negative, float, string, bool, None)
  - Zero traffic scenario
  - Light, medium, and heavy scenario generation
  - Scenario reproducibility with random seeds
  - Clear display and synthetic disclaimer
  - Shared contract compliance with classical solver, evaluator, and validators
"""

import pytest

from shared.validators import validate_traffic_input
from simulator.classical_solver import greedy_optimize
from simulator.traffic_simulator import (
    INTERSECTIONS,
    INTERSECTION_GRID_MAP,
    INITIAL_TRAFFIC_COUNTS,
    SIMULATION_DISCLAIMER,
    SCENARIO_BOUNDS,
    TrafficSimulator,
    create_traffic_simulator,
    get_initial_traffic_input,
    generate_scenario,
    format_traffic_state,
    validate_vehicle_count,
    validate_approach_counts,
    normalize_intersection_id,
)


# ===========================================================================
# 1. Initial Counts Tests
# ===========================================================================
class TestInitialCounts:
    """Verify initial simulated counts match the specification: A=45/12, B=30/20, C=10/40, D=25/15."""

    def test_initial_counts_per_intersection(self):
        sim = TrafficSimulator()
        data = sim.get_traffic_input()

        assert data["A"] == {"ns_count": 45, "ew_count": 12}
        assert data["B"] == {"ns_count": 30, "ew_count": 20}
        assert data["C"] == {"ns_count": 10, "ew_count": 40}
        assert data["D"] == {"ns_count": 25, "ew_count": 15}

    def test_initial_counts_tuple_getter(self):
        sim = TrafficSimulator()
        assert sim.get_counts("A") == (45, 12)
        assert sim.get_counts("B") == (30, 20)
        assert sim.get_counts("C") == (10, 40)
        assert sim.get_counts("D") == (25, 15)

    def test_initial_total_vehicle_count(self):
        sim = TrafficSimulator()
        # 45+12 + 30+20 + 10+40 + 25+15 = 57 + 50 + 50 + 40 = 197
        assert sim.total_vehicles == 197

    def test_all_four_intersections_present(self):
        sim = TrafficSimulator()
        data = sim.get_traffic_input()
        assert set(data.keys()) == {"A", "B", "C", "D"}
        assert len(sim) == 4

    def test_initial_counts_grid_format(self):
        sim = TrafficSimulator()
        grid_data = sim.get_traffic_input(as_grid=True)
        assert grid_data["(0,0)"] == {"ns_count": 45, "ew_count": 12}
        assert grid_data["(0,1)"] == {"ns_count": 30, "ew_count": 20}
        assert grid_data["(1,0)"] == {"ns_count": 10, "ew_count": 40}
        assert grid_data["(1,1)"] == {"ns_count": 25, "ew_count": 15}

    def test_initial_data_copy_isolation(self):
        """Mutating returned dict must not affect simulator internal state."""
        sim = TrafficSimulator()
        data = sim.get_traffic_input()
        data["A"]["ns_count"] = 999
        assert sim.get_traffic_input()["A"]["ns_count"] == 45

    def test_module_level_get_initial_traffic_input(self):
        data = get_initial_traffic_input()
        assert data["A"] == {"ns_count": 45, "ew_count": 12}
        grid_data = get_initial_traffic_input(as_grid=True)
        assert grid_data["(0,0)"] == {"ns_count": 45, "ew_count": 12}


# ===========================================================================
# 2. Retrieval & Updating Tests
# ===========================================================================
class TestRetrievalAndUpdating:
    """Verify retrieval, updating, partial updates, and dict-like semantics."""

    def test_single_intersection_retrieval(self):
        sim = TrafficSimulator()
        res_a = sim.get_traffic_input("A")
        assert res_a == {"ns_count": 45, "ew_count": 12}
        # Via grid pos
        res_grid = sim.get_traffic_input("(0,0)")
        assert res_grid == {"ns_count": 45, "ew_count": 12}

    def test_dict_getitem(self):
        sim = TrafficSimulator()
        assert sim["A"] == {"ns_count": 45, "ew_count": 12}
        assert sim["(0,1)"] == {"ns_count": 30, "ew_count": 20}
        assert "A" in sim
        assert "(1,1)" in sim
        assert "Z" not in sim

    def test_update_single_approach(self):
        sim = TrafficSimulator()
        sim.update_traffic_input("A", ns_count=50)
        assert sim.get_counts("A") == (50, 12)

        sim.update_traffic_input("A", ew_count=30)
        assert sim.get_counts("A") == (50, 30)

    def test_update_both_approaches(self):
        sim = TrafficSimulator()
        sim.update_counts("B", 10, 15)
        assert sim.get_counts("B") == (10, 15)

    def test_update_via_grid_coordinate(self):
        sim = TrafficSimulator()
        sim.update_traffic_input("(1,0)", ns_count=8, ew_count=12)
        assert sim.get_counts("C") == (8, 12)

    def test_dict_setitem(self):
        sim = TrafficSimulator()
        sim["C"] = {"ns_count": 14, "ew_count": 18}
        assert sim.get_counts("C") == (14, 18)

        sim["D"] = (22, 33)
        assert sim.get_counts("D") == (22, 33)

    def test_update_all_batch(self):
        sim = TrafficSimulator()
        new_counts = {
            "A": {"ns_count": 1, "ew_count": 2},
            "B": {"ns_count": 3, "ew_count": 4},
            "C": {"ns_count": 5, "ew_count": 6},
            "D": {"ns_count": 7, "ew_count": 8},
        }
        sim.update_all(new_counts)
        assert sim.total_vehicles == (1 + 2 + 3 + 4 + 5 + 6 + 7 + 8)

    def test_reset_restores_initial_counts(self):
        sim = TrafficSimulator()
        sim.update_counts("A", 0, 0)
        sim.update_counts("B", 0, 0)
        assert sim.get_counts("A") == (0, 0)
        sim.reset()
        assert sim.get_counts("A") == (45, 12)
        assert sim.get_counts("B") == (30, 20)
        assert sim.total_vehicles == 197


# ===========================================================================
# 3. Validation Tests (Non-negative Integer Enforced)
# ===========================================================================
class TestValidation:
    """Ensure negative numbers, floats, strings, booleans, and invalid keys are rejected."""

    def test_negative_ns_count_raises(self):
        sim = TrafficSimulator()
        with pytest.raises(ValueError, match=r">= 0"):
            sim.update_traffic_input("A", ns_count=-1)

    def test_negative_ew_count_raises(self):
        sim = TrafficSimulator()
        with pytest.raises(ValueError, match=r">= 0"):
            sim.update_traffic_input("B", ew_count=-10)

    def test_float_vehicle_count_raises(self):
        sim = TrafficSimulator()
        with pytest.raises(ValueError, match="must be a non-negative integer"):
            sim.update_traffic_input("A", ns_count=12.5)

        with pytest.raises(ValueError, match="must be a non-negative integer"):
            validate_vehicle_count(4.0)

    def test_string_vehicle_count_raises(self):
        sim = TrafficSimulator()
        with pytest.raises(ValueError, match="must be a non-negative integer"):
            sim.update_traffic_input("C", ns_count="25")  # type: ignore[arg-type]

    def test_boolean_vehicle_count_raises(self):
        """Booleans inherit from int in Python but must be rejected."""
        sim = TrafficSimulator()
        with pytest.raises(ValueError, match="must be a non-negative integer"):
            sim.update_traffic_input("A", ns_count=True)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="must be a non-negative integer"):
            sim.update_traffic_input("A", ew_count=False)  # type: ignore[arg-type]

    def test_unknown_intersection_raises(self):
        sim = TrafficSimulator()
        with pytest.raises(ValueError, match="Unknown intersection"):
            sim.get_traffic_input("E")

        with pytest.raises(ValueError, match="Unknown intersection"):
            sim.update_traffic_input("X", ns_count=5)

    def test_validate_approach_counts_missing_key(self):
        with pytest.raises(ValueError, match="missing required field"):
            validate_approach_counts({"ns_count": 5})

    def test_empty_update_all_raises(self):
        sim = TrafficSimulator()
        with pytest.raises(ValueError, match="must not be empty"):
            sim.update_all({})


# ===========================================================================
# 4. Zero Traffic Scenario Tests
# ===========================================================================
class TestZeroTraffic:
    """Verify handling of completely empty traffic queues (0 vehicles)."""

    def test_set_zero_traffic(self):
        sim = TrafficSimulator()
        sim.set_zero_traffic()
        assert sim.total_vehicles == 0
        for node in INTERSECTIONS:
            assert sim.get_counts(node) == (0, 0)

    def test_generate_zero_scenario(self):
        sim = TrafficSimulator()
        zero_state = sim.generate_scenario("zero")
        for node in INTERSECTIONS:
            assert zero_state[node] == {"ns_count": 0, "ew_count": 0}

    def test_zero_traffic_validates_under_shared_contract(self):
        """Zero queues must be strictly valid under shared validators."""
        sim = TrafficSimulator()
        sim.set_zero_traffic()
        grid_data = sim.get_traffic_input(as_grid=True)
        validate_traffic_input(grid_data)  # must not raise

    def test_zero_traffic_display(self):
        sim = TrafficSimulator()
        sim.set_zero_traffic()
        out = sim.format_traffic_state()
        assert "Total Simulated Vehicles: 0" in out


# ===========================================================================
# 5. Traffic Scenarios Tests (Light, Medium, Heavy)
# ===========================================================================
class TestScenarios:
    """Verify generation of light, medium, and heavy traffic scenarios."""

    def test_light_scenario_bounds(self):
        sim = TrafficSimulator()
        scen = sim.generate_scenario("light", seed=42)
        low, high = SCENARIO_BOUNDS["light"]
        for node, counts in scen.items():
            assert low <= counts["ns_count"] <= high
            assert low <= counts["ew_count"] <= high

    def test_medium_scenario_bounds(self):
        sim = TrafficSimulator()
        scen = sim.generate_scenario("medium", seed=42)
        low, high = SCENARIO_BOUNDS["medium"]
        for node, counts in scen.items():
            assert low <= counts["ns_count"] <= high
            assert low <= counts["ew_count"] <= high

    def test_heavy_scenario_bounds(self):
        sim = TrafficSimulator()
        scen = sim.generate_scenario("heavy", seed=42)
        low, high = SCENARIO_BOUNDS["heavy"]
        for node, counts in scen.items():
            assert low <= counts["ns_count"] <= high
            assert low <= counts["ew_count"] <= high

    def test_scenario_progression_totals(self):
        """Light scenario must have fewer total vehicles than medium and heavy."""
        sim = TrafficSimulator()
        light = sim.generate_scenario("light", seed=10)
        med = sim.generate_scenario("medium", seed=10)
        heavy = sim.generate_scenario("heavy", seed=10)

        tot_light = sum(c["ns_count"] + c["ew_count"] for c in light.values())
        tot_med = sum(c["ns_count"] + c["ew_count"] for c in med.values())
        tot_heavy = sum(c["ns_count"] + c["ew_count"] for c in heavy.values())

        assert tot_light < tot_med < tot_heavy

    def test_unknown_scenario_name_raises(self):
        sim = TrafficSimulator()
        with pytest.raises(ValueError, match="Unknown scenario"):
            sim.generate_scenario("super_heavy")

    def test_set_scenario_mutates_state(self):
        sim = TrafficSimulator()
        sim.set_scenario("light", seed=7)
        curr = sim.get_traffic_input()
        low, high = SCENARIO_BOUNDS["light"]
        assert low <= curr["A"]["ns_count"] <= high


# ===========================================================================
# 6. Scenario Reproducibility Tests
# ===========================================================================
class TestScenarioReproducibility:
    """Verify that specifying seeds guarantees identical, reproducible outputs."""

    def test_reproducible_light_scenario(self):
        sim1 = TrafficSimulator()
        sim2 = TrafficSimulator()
        run1 = sim1.generate_scenario("light", seed=12345)
        run2 = sim2.generate_scenario("light", seed=12345)
        assert run1 == run2

    def test_reproducible_heavy_scenario(self):
        sim = TrafficSimulator()
        run1 = sim.generate_scenario("heavy", seed=999)
        run2 = sim.generate_scenario("heavy", seed=999)
        assert run1 == run2

    def test_different_seeds_produce_different_counts(self):
        sim = TrafficSimulator()
        run1 = sim.generate_scenario("medium", seed=1)
        run2 = sim.generate_scenario("medium", seed=2)
        assert run1 != run2

    def test_module_level_generate_scenario_reproducible(self):
        run1 = generate_scenario("heavy", seed=777)
        run2 = generate_scenario("heavy", seed=777)
        assert run1 == run2


# ===========================================================================
# 7. Clear Display & Synthetic Disclaimer Tests
# ===========================================================================
class TestDisplayAndDisclaimer:
    """Verify clear display output and explicit non-real-world measurement disclaimer."""

    def test_display_contains_disclaimer(self):
        sim = TrafficSimulator()
        text = sim.format_traffic_state()
        assert "not real-world measurements" in text.lower()
        assert SIMULATION_DISCLAIMER in text

    def test_display_contains_all_intersections(self):
        sim = TrafficSimulator()
        text = sim.format_traffic_state()
        for node in ("A", "B", "C", "D"):
            assert node in text
        assert "Total Simulated Vehicles" in text

    def test_display_traffic_state_method(self, capsys):
        sim = TrafficSimulator()
        output = sim.display_traffic_state()
        captured = capsys.readouterr().out
        assert "QuantumFlow Traffic Simulation State" in captured
        assert output == sim.format_traffic_state()

    def test_format_traffic_state_standalone(self):
        inp = get_initial_traffic_input()
        text = format_traffic_state(inp)
        assert "45" in text
        assert "12" in text


# ===========================================================================
# 8. Shared Contract Compliance Tests
# ===========================================================================
class TestSharedContractCompliance:
    """Ensure TrafficSimulator outputs comply directly with the shared interface contract."""

    def test_named_traffic_input_passes_validator(self):
        sim = TrafficSimulator()
        ti = sim.get_traffic_input()
        validate_traffic_input(ti)  # must not raise

    def test_grid_traffic_input_passes_validator(self):
        sim = TrafficSimulator()
        grid_ti = sim.get_traffic_input(as_grid=True)
        validate_traffic_input(grid_ti)  # must not raise

    def test_classical_solver_runs_on_simulator_output(self):
        """Simulator output should be directly optimizable by classical greedy_optimize."""
        sim = TrafficSimulator()
        ti = sim.get_traffic_input()
        result = greedy_optimize(ti)
        assert result["status"] == "ok"
        assert result["algorithm"] == "greedy"
        assert "timing_plan" in result
        assert "metrics" in result

    def test_classical_solver_runs_on_grid_output(self):
        sim = TrafficSimulator()
        grid_ti = sim.get_traffic_input(as_grid=True)
        result = greedy_optimize(grid_ti)
        assert result["status"] == "ok"
        assert result["metrics"]["total_vehicles"] == 197

    def test_build_qubo_on_simulator_output(self):
        from quantum.qubo_builder import build_qubo
        sim = TrafficSimulator()
        Q, labels, keys = build_qubo(sim.get_traffic_input())
        assert Q.shape == (16, 16)
        assert len(labels) == 16
        assert len(keys) == 4

    def test_mock_qaoa_on_simulator_output(self):
        from quantum.qaoa_runner import mock_qaoa_result
        sim = TrafficSimulator()
        res = mock_qaoa_result(sim.get_traffic_input())
        assert res["status"] == "ok"
        assert res["algorithm"] == "mock"
        assert res["metrics"]["total_vehicles"] == 197
