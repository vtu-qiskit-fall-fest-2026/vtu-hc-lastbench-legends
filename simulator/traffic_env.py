"""
QuantumFlow — Traffic Environment Simulator  (G1, G2 resolved)
simulator/traffic_env.py  ·  Owner: Team Lead

Changelog vs previous version:
  - compute_congestion() now returns TrafficInput (ns_count / ew_count)
    instead of Dict[str, float].
  - run() key renamed from "congestion_map" → "traffic_input".
"""

from __future__ import annotations

import random
from typing import Dict, List

from shared.types import ApproachCounts, TrafficInput


class TrafficGrid:
    """
    Represents an N×N intersection grid.
    Each cell is an intersection node; edges are road segments.
    """

    def __init__(self, grid_size: int = 4, seed: int = 42) -> None:
        if grid_size < 2 or grid_size > 10:
            raise ValueError("grid_size must be between 2 and 10.")
        self.grid_size = grid_size
        self.seed = seed
        self.rng = random.Random(seed)
        self.grid: List[List[int]] = [[0] * grid_size for _ in range(grid_size)]
        self.vehicles: List[Dict] = []
        self.traffic_input: TrafficInput = {}

    # ------------------------------------------------------------------
    # Vehicle management
    # ------------------------------------------------------------------
    def generate_vehicles(self, num_vehicles: int) -> List[Dict]:
        """
        Randomly place vehicles on the grid.

        Returns:
            List of vehicle dicts:
            {"id": int, "row": int, "col": int, "direction": "N"|"S"|"E"|"W"}
        """
        if num_vehicles < 1:
            raise ValueError("num_vehicles must be >= 1.")
        self.vehicles = []
        for i in range(num_vehicles):
            row = self.rng.randint(0, self.grid_size - 1)
            col = self.rng.randint(0, self.grid_size - 1)
            direction = self.rng.choice(["N", "S", "E", "W"])
            self.vehicles.append(
                {"id": i, "row": row, "col": col, "direction": direction}
            )
        return self.vehicles

    def step(self, time_steps: int = 1) -> None:
        """Advance simulation by `time_steps` ticks, moving vehicles."""
        for _ in range(time_steps):
            for v in self.vehicles:
                dr, dc = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1)}[
                    v["direction"]
                ]
                v["row"] = (v["row"] + dr) % self.grid_size
                v["col"] = (v["col"] + dc) % self.grid_size
                # 10 % chance to change direction at each tick
                if self.rng.random() < 0.1:
                    v["direction"] = self.rng.choice(["N", "S", "E", "W"])

    # ------------------------------------------------------------------
    # Congestion / TrafficInput  (G1)
    # ------------------------------------------------------------------
    def compute_congestion(self) -> TrafficInput:
        """
        Compute per-approach vehicle counts for every intersection.

        N- and S-heading vehicles contribute to ns_count.
        E- and W-heading vehicles contribute to ew_count.

        Returns:
            TrafficInput — mapping "(row,col)" → ApproachCounts.
            All N×N intersections are present (zero-count intersections included).
        """
        ns_counts: Dict[str, int] = {}
        ew_counts: Dict[str, int] = {}

        for v in self.vehicles:
            key = f"({v['row']},{v['col']})"
            if v["direction"] in ("N", "S"):
                ns_counts[key] = ns_counts.get(key, 0) + 1
            else:
                ew_counts[key] = ew_counts.get(key, 0) + 1

        self.traffic_input = {}
        for row in range(self.grid_size):
            for col in range(self.grid_size):
                key = f"({row},{col})"
                self.traffic_input[key] = ApproachCounts(
                    ns_count=ns_counts.get(key, 0),
                    ew_count=ew_counts.get(key, 0),
                )

        return self.traffic_input

    def get_grid_state(self) -> List[List[int]]:
        """Return binary occupancy grid (1 if any vehicle present, else 0)."""
        state = [[0] * self.grid_size for _ in range(self.grid_size)]
        for v in self.vehicles:
            state[v["row"]][v["col"]] = 1
        self.grid = state
        return state

    # ------------------------------------------------------------------
    # Full simulation run  (G2)
    # ------------------------------------------------------------------
    def run(self, num_vehicles: int = 20, time_steps: int = 10) -> Dict:
        """
        Run a full simulation and return snapshot.

        Returns:
            {
                "grid_size":         int,
                "grid":              list[list[int]],
                "vehicle_positions": list[dict],
                "traffic_input":     TrafficInput,   # ← renamed from congestion_map
            }
        """
        self.generate_vehicles(num_vehicles)
        self.step(time_steps)
        grid = self.get_grid_state()
        traffic_input = self.compute_congestion()

        return {
            "grid_size": self.grid_size,
            "grid": grid,
            "vehicle_positions": self.vehicles,
            "traffic_input": traffic_input,   # G2: was "congestion_map"
        }
