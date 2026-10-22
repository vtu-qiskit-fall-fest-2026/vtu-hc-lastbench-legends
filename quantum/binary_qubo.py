"""
QuantumFlow — 4-Variable Binary Timing QUBO Formulation
quantum/binary_qubo.py  ·  Owner: Quantum Engineer

Mathematically consistent Quadratic Unconstrained Binary Optimization (QUBO)
formulation for QuantumFlow's four binary intersection timing choices.

-----------------------------------------------------------------------------
1. PROBLEM FORMULATION & VARIABLE ORDERING
-----------------------------------------------------------------------------
We consider a 2x2 grid of 4 intersections:
    - Index 0: Intersection A (grid coordinate (0,0))
    - Index 1: Intersection B (grid coordinate (0,1))
    - Index 2: Intersection C (grid coordinate (1,0))
    - Index 3: Intersection D (grid coordinate (1,1))

Each intersection i in {0, 1, 2, 3} has a single binary decision variable:
    x_i in {0, 1}

Binary variable choice maps directly to candidate signal plans:
    x_i = 0  ->  Candidate Plan 0: North-South Priority
                 ns_green = 45 s, ew_green = 15 s
    x_i = 1  ->  Candidate Plan 1: East-West Priority
                 ns_green = 15 s, ew_green = 45 s

Variable vector:
    x = [x_0, x_1, x_2, x_3]^T in {0, 1}^4
Bitstring representation:
    b = b_0 b_1 b_2 b_3 where x_i = int(b_i)

-----------------------------------------------------------------------------
2. DOCUMENTED TRAFFIC-DELAY OBJECTIVE
-----------------------------------------------------------------------------
From `metrics.traffic_model` (single source of truth for queue & delay):
Saturation headway: SERVICE_SEC_PER_VEHICLE = 2 s/veh.
Discharge capacity: C = floor(green_sec / 2).

For intersection i with snapshot queues q_{i,ns} and q_{i,ew}:
- Under Plan 0 (x_i = 0):
    C_ns^(0) = floor(45/2) = 22 veh,   red_ns^(0) = 15 s
    C_ew^(0) = floor(15/2) = 7 veh,    red_ew^(0) = 45 s
    rem_{i,ns}^(0) = max(0, q_{i,ns} - 22)
    rem_{i,ew}^(0) = max(0, q_{i,ew} - 7)
    D_i(0) = rem_{i,ns}^(0) * 15 + rem_{i,ew}^(0) * 45

- Under Plan 1 (x_i = 1):
    C_ns^(1) = floor(15/2) = 7 veh,    red_ns^(1) = 45 s
    C_ew^(1) = floor(45/2) = 22 veh,   red_ew^(1) = 15 s
    rem_{i,ns}^(1) = max(0, q_{i,ns} - 7)
    rem_{i,ew}^(1) = max(0, q_{i,ew} - 22)
    D_i(1) = rem_{i,ns}^(1) * 45 + rem_{i,ew}^(1) * 15

Since x_i in {0, 1}, the local delay at intersection i is EXACTLY linear:
    D_i(x_i) = D_i(0) + [D_i(1) - D_i(0)] * x_i

Total network delay (uncoordinated):
    D_total(x) = sum_{i=0}^3 D_i(x_i) = c_delay + sum_{i=0}^3 h_i * x_i
where:
    c_delay = sum_{i=0}^3 D_i(0)
    h_i = D_i(1) - D_i(0)

-----------------------------------------------------------------------------
3. NETWORK EDGES & CORRIDOR COORDINATION PENALTIES
-----------------------------------------------------------------------------
The 2x2 grid network topology defines 4 physical undirected edges E:
    Horizontal (East-West corridors):
        - Edge (A, B) = (0, 1) along Row 0
        - Edge (C, D) = (2, 3) along Row 1
    Vertical (North-South corridors):
        - Edge (A, C) = (0, 2) along Column 0
        - Edge (B, D) = (1, 3) along Column 1
    (Diagonals (0, 3) and (1, 2) are NOT edges in the grid.)

Traffic Engineering Justification:
When adjacent intersections along a corridor choose opposing priorities
(e.g., x_u = 1 and x_v = 0), platoon green-wave progression is severed.
Vehicles clearing intersection u under priority green hit a red signal
at intersection v, incurring stop-and-go spillback delay.

The phase mismatch across edge (u, v) in E is given by:
    Mismatch(x_u, x_v) = (x_u - x_v)^2 = x_u + x_v - 2 * x_u * x_v
Notice:
    - If x_u == x_v (synchronized phases): (x_u - x_v)^2 = 0
    - If x_u != x_v (desynchronized phases): (x_u - x_v)^2 = 1

For each edge (u, v) in E, we associate a coordination penalty gamma_{uv} >= 0:
    C_coord(x) = sum_{(u, v) in E} gamma_{uv} * (x_u - x_v)^2
               = sum_{(u, v) in E} gamma_{uv} * (x_u + x_v - 2 * x_u * x_v)
               = sum_{i=0}^3 ( sum_{v in N(i)} gamma_{iv} ) * x_i
                 - 2 * sum_{(u, v) in E, u < v} gamma_{uv} * x_u * x_v

-----------------------------------------------------------------------------
4. COMPLETE QUBO MATHEMATICAL FORMULATION
-----------------------------------------------------------------------------
Total intended cost:
    C_intended(x) = D_total(x) + C_coord(x)
                  = c_offset + x^T * Q * x

Constant offset:
    c_offset = sum_{i=0}^3 D_i(0)

Linear terms (diagonal of Q):
    Q_{ii} = [D_i(1) - D_i(0)] + sum_{v in N(i)} gamma_{iv}

Quadratic pairwise terms (off-diagonal of upper-triangular Q):
    Q_{uv} = -2 * gamma_{uv}   for (u, v) in E with u < v
    Q_{uv} = 0                 for (u, v) not in E

In symmetric form Q_sym:
    Q_sym_{ii} = Q_{ii}
    Q_sym_{uv} = Q_sym_{vu} = -gamma_{uv}   for (u, v) in E with u != v

MATHEMATICAL CONSISTENCY THEOREM:
Because both D_total(x) and C_coord(x) are polynomials of degree <= 2 in
binary variables x_i in {0, 1}, the QUBO representation:
    E(x) = x^T * Q * x + c_offset
equals C_intended(x) IDENTICALLY for ALL 16 bitstrings x in {0, 1}^4.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from shared.types import ApproachTiming, TimingPlan, TrafficInput
from shared.validators import validate_traffic_input
from metrics.traffic_model import served_and_remaining

# ---------------------------------------------------------------------------
# Topology Constants
# ---------------------------------------------------------------------------
NUM_VARIABLES: int = 4
DEFAULT_INTERSECTIONS: Tuple[str, ...] = ("A", "B", "C", "D")
GRID_INTERSECTIONS: Tuple[str, ...] = ("(0,0)", "(0,1)", "(1,0)", "(1,1)")

# Network edges: 4 undirected grid edges (horizontal and vertical)
# Index mapping: 0: A (0,0), 1: B (0,1), 2: C (1,0), 3: D (1,1)
GRID_EDGES: Tuple[Tuple[int, int], ...] = (
    (0, 1),  # East-West Row 0:    (A, B) / ((0,0), (0,1))
    (0, 2),  # North-South Col 0:  (A, C) / ((0,0), (1,0))
    (1, 3),  # North-South Col 1:  (B, D) / ((0,1), (1,1))
    (2, 3),  # East-West Row 1:    (C, D) / ((1,0), (1,1))
)

# Candidate signal timings
PLAN_0_TIMING = {"ns_green": 45, "ew_green": 15}  # Bit = 0: NS Priority
PLAN_1_TIMING = {"ns_green": 15, "ew_green": 45}  # Bit = 1: EW Priority


# ---------------------------------------------------------------------------
# Helper: Local Intersection Delays
# ---------------------------------------------------------------------------
def compute_intersection_delay(
    ns_count: int,
    ew_count: int,
    choice: int,
) -> float:
    """
    Compute delay (in seconds) at one intersection for binary choice (0 or 1).

    Uses the exact formula from metrics.traffic_model:
        delay = rem_ns * ew_green + rem_ew * ns_green
    """
    if choice == 0:
        ns_g, ew_g = PLAN_0_TIMING["ns_green"], PLAN_0_TIMING["ew_green"]
    else:
        ns_g, ew_g = PLAN_1_TIMING["ns_green"], PLAN_1_TIMING["ew_green"]

    _, rem_ns = served_and_remaining(ns_count, ns_g)
    _, rem_ew = served_and_remaining(ew_count, ew_g)

    # Opposing green is the red interval:
    return float(rem_ns * ew_g + rem_ew * ns_g)


def compute_local_delay_terms(
    traffic_input: TrafficInput,
    intersections: Sequence[str] = DEFAULT_INTERSECTIONS,
) -> Tuple[float, np.ndarray]:
    """
    Compute the constant offset and linear delay coefficients for all 4 intersections.

    Returns:
        (c_delay, h) where:
            c_delay = sum_i D_i(0)
            h = array of [D_i(1) - D_i(0)] for i in {0, 1, 2, 3}
    """
    c_delay = 0.0
    h = np.zeros(NUM_VARIABLES, dtype=np.float64)

    for i, iid in enumerate(intersections):
        counts = traffic_input[iid]
        ns_c = counts["ns_count"]
        ew_c = counts["ew_count"]

        d0 = compute_intersection_delay(ns_c, ew_c, choice=0)
        d1 = compute_intersection_delay(ns_c, ew_c, choice=1)

        c_delay += d0
        h[i] = d1 - d0

    return c_delay, h


# ---------------------------------------------------------------------------
# Edge Coordination Penalty Mapping
# ---------------------------------------------------------------------------
def get_edge_coordination_weights(
    traffic_input: TrafficInput,
    intersections: Sequence[str] = DEFAULT_INTERSECTIONS,
    coord_weight: float = 0.0,
    custom_edge_weights: Optional[Dict[Tuple[int, int], float]] = None,
) -> Dict[Tuple[int, int], float]:
    """
    Resolve the coordination penalty gamma_{uv} for each edge in GRID_EDGES.

    Justification:
    When coord_weight > 0, each desynchronized adjacent intersection pair incurs
    penalty gamma_{uv} representing stop-and-go queue delay along the corridor.
    If custom_edge_weights is provided, it explicitly sets gamma_{uv}.
    Otherwise:
        gamma_{uv} = coord_weight * min(demand_u, demand_v)
    where demand is the corridor queue (EW count for horizontal edges, NS count for vertical edges).
    If demand is zero, a baseline penalty of coord_weight is applied.
    """
    gamma: Dict[Tuple[int, int], float] = {}

    for u, v in GRID_EDGES:
        edge = (min(u, v), max(u, v))
        if custom_edge_weights is not None and edge in custom_edge_weights:
            gamma[edge] = float(custom_edge_weights[edge])
            continue

        if coord_weight <= 0.0:
            gamma[edge] = 0.0
            continue

        # Determine corridor axis:
        # (0,1) and (2,3) are East-West corridors
        # (0,2) and (1,3) are North-South corridors
        u_id = intersections[u]
        v_id = intersections[v]

        if (u, v) in ((0, 1), (2, 3)):
            # East-West corridor: coordination depends on EW vehicles
            demand = min(traffic_input[u_id]["ew_count"], traffic_input[v_id]["ew_count"])
        else:
            # North-South corridor: coordination depends on NS vehicles
            demand = min(traffic_input[u_id]["ns_count"], traffic_input[v_id]["ns_count"])

        # Physical penalty in delay seconds:
        # Proportional to corridor vehicles plus fixed synchronization headway
        gamma[edge] = float(coord_weight * max(demand, 1))

    return gamma


# ---------------------------------------------------------------------------
# QUBO Builder: 4 Binary Variables
# ---------------------------------------------------------------------------
def build_binary_qubo(
    traffic_input: TrafficInput,
    coord_weight: float = 0.0,
    intersections: Optional[Sequence[str]] = None,
    custom_edge_weights: Optional[Dict[Tuple[int, int], float]] = None,
    symmetrize: bool = False,
) -> Tuple[np.ndarray, float, List[str]]:
    """
    Construct the mathematically exact QUBO matrix Q and constant offset c
    for QuantumFlow's 4 binary timing variables.

    Objective:
        minimize E(x) = x^T * Q * x + offset
    where:
        x in {0, 1}^4
        x_i = 0 -> Candidate Plan 0 (45s NS / 15s EW)
        x_i = 1 -> Candidate Plan 1 (15s NS / 45s EW)

    Args:
        traffic_input: Vehicle queues per approach for all 4 intersections.
        coord_weight: Weight for neighbor-coordination penalties along grid edges.
                      Set to 0.0 for pure documented traffic delay.
        intersections: Ordered 4-intersection IDs (default ("A", "B", "C", "D") or grid IDs).
        custom_edge_weights: Optional explicit mapping (u, v) -> gamma_{uv}.
        symmetrize: If True, returns symmetric Q where Q_{ij} = Q_{ji} = -gamma_{ij}.
                    If False (default), returns upper-triangular Q where Q_{ij} = -2*gamma_{ij} (i < j).

    Returns:
        (Q, offset, var_labels)
        - Q: np.ndarray shape (4, 4)
        - offset: float constant scalar
        - var_labels: list of strings, e.g. ["x_A", "x_B", "x_C", "x_D"]

    Raises:
        ValueError: if traffic_input is invalid or does not contain 4 intersections.
    """
    validate_traffic_input(traffic_input)

    if intersections is None:
        keys = list(traffic_input.keys())
        if len(keys) == NUM_VARIABLES:
            if set(keys) == set(DEFAULT_INTERSECTIONS):
                inter_list = list(DEFAULT_INTERSECTIONS)
            elif set(keys) == set(GRID_INTERSECTIONS):
                inter_list = list(GRID_INTERSECTIONS)
            else:
                inter_list = sorted(keys)
        else:
            inter_list = list(DEFAULT_INTERSECTIONS)
    else:
        inter_list = list(intersections)

    if len(inter_list) != NUM_VARIABLES:
        raise ValueError(
            f"Expected {NUM_VARIABLES} intersections, got {len(inter_list)}"
        )

    # 1. Base traffic delay terms (c_delay and linear h_i)
    c_delay, h = compute_local_delay_terms(traffic_input, inter_list)

    # 2. Edge coordination weights gamma_{uv}
    gamma = get_edge_coordination_weights(
        traffic_input=traffic_input,
        intersections=inter_list,
        coord_weight=coord_weight,
        custom_edge_weights=custom_edge_weights,
    )

    # 3. Assemble QUBO matrix
    Q = np.zeros((NUM_VARIABLES, NUM_VARIABLES), dtype=np.float64)

    # Diagonal: linear terms L_i = h_i + sum_{v in N(i)} gamma_{iv}
    for i in range(NUM_VARIABLES):
        incident_gamma_sum = sum(
            gamma[(min(i, v), max(i, v))]
            for v in range(NUM_VARIABLES)
            if (min(i, v), max(i, v)) in gamma
        )
        Q[i, i] = h[i] + incident_gamma_sum

    # Off-diagonal: quadratic pairwise terms
    for u, v in GRID_EDGES:
        edge = (min(u, v), max(u, v))
        g_uv = gamma.get(edge, 0.0)
        if symmetrize:
            Q[edge[0], edge[1]] = -g_uv
            Q[edge[1], edge[0]] = -g_uv
        else:
            Q[edge[0], edge[1]] = -2.0 * g_uv

    offset = float(c_delay)
    var_labels = [f"x_{iid}" for iid in inter_list]

    return Q, offset, var_labels


# ---------------------------------------------------------------------------
# Intended Cost & Energy Verification
# ---------------------------------------------------------------------------
def compute_intended_cost(
    traffic_input: TrafficInput,
    bitstring: str,
    coord_weight: float = 0.0,
    intersections: Optional[Sequence[str]] = None,
    custom_edge_weights: Optional[Dict[Tuple[int, int], float]] = None,
) -> float:
    """
    Compute the exact intended ground-truth cost for a 4-bit candidate combination.

    Intended cost = (Total traffic delay from traffic_model) + (Neighbor coordination penalties)
    """
    if len(bitstring) != NUM_VARIABLES:
        raise ValueError(f"Bitstring length must be {NUM_VARIABLES}, got {len(bitstring)}")

    inter_list = list(intersections) if intersections is not None else list(DEFAULT_INTERSECTIONS)

    # 1. Base local traffic delay
    total_delay = 0.0
    x_vals = [int(b) for b in bitstring]
    for i, iid in enumerate(inter_list):
        counts = traffic_input[iid]
        d = compute_intersection_delay(counts["ns_count"], counts["ew_count"], choice=x_vals[i])
        total_delay += d

    # 2. Coordination penalty along grid edges
    gamma = get_edge_coordination_weights(
        traffic_input=traffic_input,
        intersections=inter_list,
        coord_weight=coord_weight,
        custom_edge_weights=custom_edge_weights,
    )
    coord_penalty = 0.0
    for u, v in GRID_EDGES:
        edge = (min(u, v), max(u, v))
        g_uv = gamma.get(edge, 0.0)
        mismatch = (x_vals[u] - x_vals[v]) ** 2
        coord_penalty += g_uv * mismatch

    return float(total_delay + coord_penalty)


def evaluate_qubo_energy(
    Q: np.ndarray,
    offset: float,
    bitstring: str,
) -> float:
    """
    Evaluate the QUBO objective energy for a given binary bitstring:
        E(x) = x^T * Q * x + offset
    """
    if len(bitstring) != NUM_VARIABLES:
        raise ValueError(f"Bitstring length must be {NUM_VARIABLES}, got {len(bitstring)}")

    x = np.array([int(b) for b in bitstring], dtype=np.float64)
    energy = float(x.T @ Q @ x + offset)
    return energy


def verify_qubo_against_intended_cost(
    traffic_input: TrafficInput,
    coord_weight: float = 0.0,
    intersections: Optional[Sequence[str]] = None,
    custom_edge_weights: Optional[Dict[Tuple[int, int], float]] = None,
    tolerance: float = 1e-9,
) -> Dict[str, Any]:
    """
    Verify exact equality between QUBO energy and intended cost across all 16 bitstrings.

    Returns:
        Dict containing:
            "all_passed": bool
            "max_discrepancy": float
            "evaluations": list of dicts for each of the 16 bitstrings
            "Q_upper": upper-triangular Q matrix
            "Q_symmetric": symmetric Q matrix
            "offset": constant offset
    """
    inter_list = list(intersections) if intersections is not None else list(DEFAULT_INTERSECTIONS)

    # Build both upper-triangular and symmetric QUBO matrices
    Q_upper, offset_upper, labels = build_binary_qubo(
        traffic_input=traffic_input,
        coord_weight=coord_weight,
        intersections=inter_list,
        custom_edge_weights=custom_edge_weights,
        symmetrize=False,
    )
    Q_sym, offset_sym, _ = build_binary_qubo(
        traffic_input=traffic_input,
        coord_weight=coord_weight,
        intersections=inter_list,
        custom_edge_weights=custom_edge_weights,
        symmetrize=True,
    )

    evaluations: List[Dict[str, Any]] = []
    max_disc = 0.0
    all_passed = True

    for int_val in range(1 << NUM_VARIABLES):
        b = f"{int_val:04b}"
        intended = compute_intended_cost(
            traffic_input=traffic_input,
            bitstring=b,
            coord_weight=coord_weight,
            intersections=inter_list,
            custom_edge_weights=custom_edge_weights,
        )
        e_upper = evaluate_qubo_energy(Q_upper, offset_upper, b)
        e_sym = evaluate_qubo_energy(Q_sym, offset_sym, b)

        disc_upper = abs(intended - e_upper)
        disc_sym = abs(intended - e_sym)
        max_disc = max(max_disc, disc_upper, disc_sym)

        passed = (disc_upper <= tolerance) and (disc_sym <= tolerance)
        if not passed:
            all_passed = False

        evaluations.append({
            "bitstring": b,
            "integer_value": int_val,
            "intended_cost": intended,
            "energy_upper": e_upper,
            "energy_symmetric": e_sym,
            "discrepancy": max(disc_upper, disc_sym),
            "passed": passed,
        })

    return {
        "all_passed": all_passed,
        "max_discrepancy": max_disc,
        "evaluations": evaluations,
        "Q_upper": Q_upper,
        "Q_symmetric": Q_sym,
        "offset": offset_upper,
        "labels": labels,
    }
