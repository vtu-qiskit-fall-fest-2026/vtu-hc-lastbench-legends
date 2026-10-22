"""
QuantumFlow — Test Suite: Traffic Simulator
tests/test_traffic_env.py  ·  Owner: Team Lead
"""

import pytest
from simulator.traffic_env import TrafficGrid


@pytest.fixture
def grid2():
    return TrafficGrid(grid_size=2, seed=0)


@pytest.fixture
def grid4():
    return TrafficGrid(grid_size=4, seed=42)


class TestTrafficGridInit:
    def test_valid_sizes(self):
        for n in (2, 4, 10):
            g = TrafficGrid(grid_size=n)
            assert g.grid_size == n

    def test_invalid_size_low(self):
        with pytest.raises(ValueError):
            TrafficGrid(grid_size=1)

    def test_invalid_size_high(self):
        with pytest.raises(ValueError):
            TrafficGrid(grid_size=11)

    def test_empty_vehicles_on_init(self, grid4):
        assert grid4.vehicles == []


class TestGenerateVehicles:
    def test_count(self, grid4):
        vehicles = grid4.generate_vehicles(20)
        assert len(vehicles) == 20

    def test_in_bounds(self, grid4):
        vehicles = grid4.generate_vehicles(50)
        for v in vehicles:
            assert 0 <= v["row"] < 4
            assert 0 <= v["col"] < 4
            assert v["direction"] in ("N", "S", "E", "W")

    def test_deterministic_with_seed(self):
        g1 = TrafficGrid(grid_size=4, seed=99)
        g2 = TrafficGrid(grid_size=4, seed=99)
        assert g1.generate_vehicles(10) == g2.generate_vehicles(10)

    def test_zero_vehicles_raises(self, grid4):
        with pytest.raises(ValueError):
            grid4.generate_vehicles(0)


class TestComputeCongestion:
    def test_returns_traffic_input_shape(self, grid2):
        grid2.generate_vehicles(4)
        ti = grid2.compute_congestion()
        # 2×2 grid → 4 keys
        assert len(ti) == 4
        for key, counts in ti.items():
            assert "ns_count" in counts
            assert "ew_count" in counts

    def test_all_intersections_present(self, grid4):
        grid4.generate_vehicles(16)
        ti = grid4.compute_congestion()
        expected = {f"({r},{c})" for r in range(4) for c in range(4)}
        assert set(ti.keys()) == expected

    def test_counts_non_negative(self, grid4):
        grid4.generate_vehicles(20)
        ti = grid4.compute_congestion()
        for counts in ti.values():
            assert counts["ns_count"] >= 0
            assert counts["ew_count"] >= 0

    def test_total_count_matches_vehicles(self, grid2):
        grid2.generate_vehicles(6)
        ti = grid2.compute_congestion()
        total = sum(c["ns_count"] + c["ew_count"] for c in ti.values())
        assert total == 6

    def test_ns_ew_split_by_direction(self):
        """Vehicles heading N/S must go to ns_count; E/W to ew_count."""
        g = TrafficGrid(grid_size=2, seed=0)
        # Manually plant vehicles
        g.vehicles = [
            {"id": 0, "row": 0, "col": 0, "direction": "N"},
            {"id": 1, "row": 0, "col": 0, "direction": "S"},
            {"id": 2, "row": 0, "col": 0, "direction": "E"},
        ]
        ti = g.compute_congestion()
        assert ti["(0,0)"]["ns_count"] == 2
        assert ti["(0,0)"]["ew_count"] == 1


class TestRun:
    def test_run_returns_expected_keys(self, grid4):
        snap = grid4.run(num_vehicles=10, time_steps=5)
        assert "grid_size" in snap
        assert "grid" in snap
        assert "vehicle_positions" in snap
        assert "traffic_input" in snap          # G2: must NOT be "congestion_map"
        assert "congestion_map" not in snap     # G2: old key must be gone

    def test_grid_is_binary(self, grid4):
        snap = grid4.run(num_vehicles=10, time_steps=1)
        for row in snap["grid"]:
            for cell in row:
                assert cell in (0, 1)
