"""
QuantumFlow — Shared Validators  (G10)
shared/validators.py  ·  Owner: Team Lead

Centralised validation so every module enforces the same constraints.
Raises ValueError with a specific field path on any violation.
"""

from __future__ import annotations
import re
from typing import List

from shared.types import TrafficInput, TimingPlan

# Cycle constants — must match docs/INTERFACES.md §1
CYCLE_SEC  = 60
MIN_GREEN  = 15
MAX_GREEN  = 45

_KEY_RE = re.compile(r"^(?:\(\d+,\d+\)|[A-D])$")
_NAMED_COORDS = {"A": (0, 0), "B": (0, 1), "C": (1, 0), "D": (1, 1)}


# ---------------------------------------------------------------------------
# TrafficInput validation
# ---------------------------------------------------------------------------
def validate_traffic_input(traffic_input: TrafficInput) -> None:
    """
    Validate a TrafficInput mapping.

    Rules:
    - Must not be empty.
    - Each key must match "(row,col)".
    - ns_count and ew_count must be non-negative integers.
    - Keys must form a complete N×N grid (square set).

    Raises:
        ValueError: with a descriptive message on the first violation found.
    """
    if not traffic_input:
        raise ValueError("traffic_input must not be empty.")

    for iid, counts in traffic_input.items():
        if not _KEY_RE.match(iid):
            raise ValueError(
                f"traffic_input: invalid intersection ID format '{iid}'. "
                "Expected '(row,col)'."
            )
        for field in ("ns_count", "ew_count"):
            val = counts.get(field)
            if val is None:
                raise ValueError(
                    f"traffic_input.{iid}: missing required field '{field}'."
                )
            if not isinstance(val, int):
                raise ValueError(
                    f"traffic_input.{iid}.{field}: must be an integer, got {type(val).__name__}."
                )
            if val < 0:
                raise ValueError(
                    f"traffic_input.{iid}.{field}: must be >= 0, got {val}."
                )

    _check_square_grid(list(traffic_input.keys()))


def _check_square_grid(keys: List[str]) -> None:
    """Verify keys form a complete N×N grid with N >= 2."""
    coords = [_parse_key(k) for k in keys]
    rows = sorted(set(r for r, _ in coords))
    cols = sorted(set(c for _, c in coords))
    if len(rows) != len(cols):
        raise ValueError(
            f"traffic_input: grid is not square — {len(rows)} row(s) vs {len(cols)} col(s)."
        )
    n = len(rows)
    if n < 2:
        raise ValueError(
            f"traffic_input: grid must be at least 2×2, got {n}×{n}."
        )
    expected = {(r, c) for r in range(n) for c in range(n)}
    actual = set(coords)
    if actual != expected:
        missing = expected - actual
        raise ValueError(
            f"traffic_input: incomplete grid — missing intersections: "
            + ", ".join(f"({r},{c})" for r, c in sorted(missing))
        )


# ---------------------------------------------------------------------------
# TimingPlan validation
# ---------------------------------------------------------------------------
def validate_timing_plan(
    timing_plan:   TimingPlan,
    traffic_input: TrafficInput | None = None,
) -> None:
    """
    Validate a TimingPlan mapping.

    Rules:
    - Must not be empty.
    - Each key must match "(row,col)".
    - MIN_GREEN <= ns_green <= MAX_GREEN  (15–45 s).
    - MIN_GREEN <= ew_green <= MAX_GREEN  (15–45 s).
    - ns_green + ew_green == CYCLE_SEC   (60 s).
    - If traffic_input provided: keys must exactly match.

    Raises:
        ValueError: with a descriptive message on the first violation found.
    """
    if not timing_plan:
        raise ValueError("timing_plan must not be empty.")

    for iid, timing in timing_plan.items():
        if not _KEY_RE.match(iid):
            raise ValueError(
                f"timing_plan: invalid intersection ID '{iid}'."
            )
        for field in ("ns_green", "ew_green"):
            val = timing.get(field)
            if val is None:
                raise ValueError(
                    f"timing_plan.{iid}: missing required field '{field}'."
                )
            if not isinstance(val, int):
                raise ValueError(
                    f"timing_plan.{iid}.{field}: must be an integer, got {type(val).__name__}."
                )
            if not (MIN_GREEN <= val <= MAX_GREEN):
                raise ValueError(
                    f"timing_plan.{iid}.{field}: {val}s is outside "
                    f"[{MIN_GREEN}, {MAX_GREEN}]."
                )
        total = timing["ns_green"] + timing["ew_green"]
        if total != CYCLE_SEC:
            raise ValueError(
                f"timing_plan.{iid}: ns_green + ew_green = {total}s, "
                f"must equal CYCLE_SEC={CYCLE_SEC}s."
            )

    if traffic_input is not None:
        tp_keys = set(timing_plan.keys())
        ti_keys = set(traffic_input.keys())
        if tp_keys != ti_keys:
            extra   = tp_keys - ti_keys
            missing = ti_keys - tp_keys
            msg_parts = []
            if missing:
                msg_parts.append(f"missing in timing_plan: {missing}")
            if extra:
                msg_parts.append(f"extra in timing_plan: {extra}")
            raise ValueError(
                "timing_plan keys do not match traffic_input: " + "; ".join(msg_parts)
            )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _parse_key(key: str) -> tuple[int, int]:
    """Parse '(row,col)' or 'A'-'D' → (int, int)."""
    if key in _NAMED_COORDS:
        return _NAMED_COORDS[key]
    stripped = key.strip("()")
    r, c = stripped.split(",")
    return int(r), int(c)
