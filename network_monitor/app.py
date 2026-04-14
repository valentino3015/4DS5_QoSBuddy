from __future__ import annotations

from typing import Any, Dict, List, Sequence

from flask import Flask, jsonify, render_template, request
from flask_mysqldb import MySQL

import config
from collector import collect_metrics
from db import INSERT_METRICS_SQL, metrics_values

app = Flask(__name__)
app.config.from_object(config)
mysql = MySQL(app)


def _time_label(ts: Any) -> str:
    """
    Return a compact label suitable for chart x-axis.
    Works with datetime-like objects from MySQLdb or string timestamps.
    """

    if hasattr(ts, "strftime"):
        return ts.strftime("%H:%M:%S")
    return str(ts)

def _rows_to_chart_data(rows: Sequence[Sequence[Any]]) -> Dict[str, List[Any]]:
    """
    Convert raw DB rows to chart series in chronological order.

    Expected schema (by index): (id, timestamp, source_ip, destination_ip, avg_rtt, p95_rtt,
    jitter, packet_loss, throughput_down, throughput_up, bandwidth_utilization, retransmission_rate,
    response_time, http_error_rate, availability)
    """

    # rows are fetched DESC; charts should render left->right old->new
    rows_chrono = list(reversed(rows))

    timestamps: List[str] = []
    rtt: List[float] = []
    jitter: List[float] = []
    loss: List[float] = []
    throughput_down: List[float] = []
    throughput_up: List[float] = []
    util: List[float] = []
    resp_time: List[float] = []
    error: List[float] = []
    availability: List[float] = []

    for row in rows_chrono:
        timestamps.append(_time_label(row[0]))
        rtt.append(round(float(row[3] or 0), 2))
        jitter.append(round(float(row[5] or 0), 2))
        loss.append(round(float(row[6] or 0), 2))
        throughput_down.append(round(float(row[7] or 0), 2))
        throughput_up.append(round(float(row[8] or 0), 2))
        util.append(round(float(row[9] or 0), 2))
        resp_time.append(round(float(row[10] or 0), 2))
        error.append(round(float(row[11] or 0), 2))
        availability.append(round(float(row[12] or 0), 2))

    return {
        "timestamps": timestamps,
        "rtt": rtt,
        "jitter": jitter,
        "loss": loss,
        "throughputDown": throughput_down,
        "throughputUp": throughput_up,
        "util": util,
        "respTime": resp_time,
        "error": error,
        "availability": availability,
    }


@app.route("/")
def dashboard():
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
    SELECT timestamp, source_ip, destination_ip, avg_rtt, p95_rtt, jitter,
    packet_loss, throughput_down, throughput_up, bandwidth_utilization,
    response_time, http_error_rate, availability
    FROM network_metrics
    ORDER BY timestamp DESC
    LIMIT 30
""")
        data = cur.fetchall()
    finally:
        cur.close()
    chart_data = _rows_to_chart_data(data)
    return render_template("dashboard.html", data=data, chart_data=chart_data)


@app.get("/api/metrics")
def api_metrics():
    limit = request.args.get("limit", default=30, type=int)
    limit = max(1, min(limit, 500))

    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT * FROM network_metrics ORDER BY timestamp DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    finally:
        cur.close()

    return jsonify(_rows_to_chart_data(rows))

@app.post("/api/metrics/raw")
def ingest_metrics_raw():
    """
    Ingest a single aggregated QoS window from an agent (e.g., Mariam capture_agent).
    Expects JSON payload with at least: timestamp, window_id.
    Stores into qos_metrics_raw table.
    """
    data = request.get_json(silent=True) or {}

    ts = data.get("timestamp")
    window_id = data.get("window_id")

    if not ts or window_id is None:
        return jsonify({"status": "error", "message": "timestamp and window_id are required"}), 400

    # Metrics (all optional)
    avg_rtt_ms = data.get("avg_rtt_ms")
    jitter_ms = data.get("jitter_ms")
    packet_loss_pct = data.get("packet_loss_pct")
    throughput_up_mbps = data.get("throughput_up_mbps")
    throughput_down_mbps = data.get("throughput_down_mbps")
    retransmission_rate_pct = data.get("retransmission_rate_pct")
    dns_time_ms = data.get("dns_time_ms")

    cur = mysql.connection.cursor()
    try:
        cur.execute(
            """
            INSERT INTO qos_metrics_raw
            (timestamp, window_id, avg_rtt_ms, jitter_ms, packet_loss_pct,
             throughput_up_mbps, throughput_down_mbps, retransmission_rate_pct, dns_time_ms)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                ts,
                int(window_id),
                avg_rtt_ms, jitter_ms, packet_loss_pct,
                throughput_up_mbps, throughput_down_mbps,
                retransmission_rate_pct, dns_time_ms,
            ),
        )
        mysql.connection.commit()
    finally:
        cur.close()

    return jsonify({"status": "ok"})

@app.route("/collect")
def collect():
    metrics = collect_metrics()

    if metrics:
        cur = mysql.connection.cursor()
        try:
            cur.execute(INSERT_METRICS_SQL, metrics_values(metrics))
            mysql.connection.commit()
        finally:
            cur.close()

    return "Metrics collected successfully!"


if __name__ == "__main__":
    
    app.run(debug=False)
