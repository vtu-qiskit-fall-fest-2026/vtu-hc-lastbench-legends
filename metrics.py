"""
QuantumFlow — Metrics Evaluation and Controller Benchmarking
Root convenience module re-exporting metrics.metrics.
"""

from metrics.metrics import (
    BaselinePercentageChange,
    ControllerComparisonResult,
    calculate_plan_metrics,
    compare_controllers,
    compute_baseline_comparison,
    evaluate_fixed_time,
    evaluate_qaoa,
    evaluate_traffic_responsive,
    format_comparison_table,
    main,
    safe_percentage_increase,
    safe_percentage_reduction,
)

__all__ = [
    "BaselinePercentageChange",
    "ControllerComparisonResult",
    "calculate_plan_metrics",
    "compare_controllers",
    "compute_baseline_comparison",
    "evaluate_fixed_time",
    "evaluate_qaoa",
    "evaluate_traffic_responsive",
    "format_comparison_table",
    "main",
    "safe_percentage_increase",
    "safe_percentage_reduction",
]

if __name__ == "__main__":
    main()
