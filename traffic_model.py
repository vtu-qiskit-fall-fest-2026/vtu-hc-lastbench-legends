"""
QuantumFlow — Signal-Plan Traffic Model
Root convenience module re-exporting metrics.traffic_model.
"""

from metrics.traffic_model import (
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
