"""
QuantumFlow — Shared Metrics Evaluator  (G5)

Public facade required by docs/INTERFACES.md §4.3.

All queue, service-rate, and delay math lives in ``metrics.traffic_model``.
This module re-exports ``evaluate`` and ``compare`` so existing imports keep
working. Do not add a second metric implementation here.
"""

from __future__ import annotations

from metrics.traffic_model import (  # noqa: F401
    SERVICE_SEC_PER_VEHICLE,
    compare,
    evaluate,
    served_and_remaining,
    service_capacity,
)

__all__ = [
    "SERVICE_SEC_PER_VEHICLE",
    "compare",
    "evaluate",
    "served_and_remaining",
    "service_capacity",
]
