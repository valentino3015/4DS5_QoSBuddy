"""
Shared DB helpers/constants used by both the agent and the Flask app.
Keeps INSERT column order consistent across the project.
"""

from __future__ import annotations

from typing import Mapping, Sequence, Tuple, Any


METRICS_COLUMNS: Tuple[str, ...] = (
    "timestamp",
    "source_ip",
    "destination_ip",
    "avg_rtt",
    "p95_rtt",
    "jitter",
    "packet_loss",
    "throughput",
    "bandwidth_utilization",
    "retransmission_rate",
    "response_time",
    "http_error_rate",
    "availability",
)

_PLACEHOLDERS = ", ".join(["%s"] * len(METRICS_COLUMNS))
INSERT_METRICS_SQL = (
    f"INSERT INTO network_metrics ({', '.join(METRICS_COLUMNS)}) "
    f"VALUES ({_PLACEHOLDERS})"
)


def metrics_values(metrics: Mapping[str, Any]) -> Sequence[Any]:
    """
    Return metric values in the same order as METRICS_COLUMNS.
    Raises KeyError if a required key is missing (useful for catching schema drift).
    """

    return tuple(metrics[col] for col in METRICS_COLUMNS)

