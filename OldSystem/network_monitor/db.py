"""
Shared DB helpers/constants used by both the agent and the Flask app.
Keeps INSERT column order consistent across the project.

If upgrading from a schema that had a single 'throughput' column, run:
  ALTER TABLE network_metrics ADD COLUMN throughput_down DOUBLE, ADD COLUMN throughput_up DOUBLE;
  ALTER TABLE network_metrics DROP COLUMN throughput;
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
    "throughput_down",
    "throughput_up",
    "bandwidth_utilization",
    "retransmission_rate",
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
    Numeric values are formatted to 2 decimal places (e.g. "12.12") for VARCHAR storage.
    Raises KeyError if a required key is missing (useful for catching schema drift).
    """
    result = []
    for col in METRICS_COLUMNS:
        value = metrics[col]
        if value is not None and isinstance(value, (int, float)):
            result.append(f"{float(value):.2f}")
        else:
            result.append(value)
    return tuple(result)
    return tuple(metrics[col] for col in METRICS_COLUMNS)


