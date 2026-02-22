import time
import numpy as np
import requests
from typing import Dict, List, Tuple
import config

# --- Sensitivity settings for network traffic ---
Z_THRESHOLD = 3.5           # Lower Z-score threshold for sensitive detection
ROLLING_WINDOW = 10         # How many recent points to consider
PERSISTENCE_REQUIRED = 1    # Number of consecutive anomalies before alerting
CHECK_INTERVAL = 1          # seconds
NETWORK_MONITOR_URL = getattr(config, 'NETWORK_MONITOR_URL', 'http://localhost:5000')

# Absolute thresholds (hard limits)
ABSOLUTE_THRESHOLDS = {
    "rtt": 100.0,
    "jitter": 20.0,
    "loss": 5.0,
    "error": 5.0,
    "availability": 95.0
}

# Track consecutive anomalies
consecutive_anomalies = {}

# Track timestamps that have already been alerted to avoid duplicate alerts
alerted_timestamps = set()

# --- Detect anomalies with rolling Z-score + absolute thresholds ---
def detect_anomalies(chart_data: Dict) -> Tuple[List[bool], List[Dict]]:
    anomalies = []
    detailed_anomalies = []

    # Only monitor critical metrics
    metrics = {k: np.array(chart_data.get(k, [])) for k in ABSOLUTE_THRESHOLDS.keys()}
    timestamps = chart_data.get("timestamps", [])

    if not timestamps:
        return [], []

    # Only check the most recent data point to avoid re-checking old data
    # This prevents the same timestamp from being flagged repeatedly
    check_range = range(max(0, len(timestamps) - 1), len(timestamps))
    
    for i in check_range:
        anomalous_metrics = []

        for metric_name, values in metrics.items():
            if len(values) < 5 or i >= len(values):
                continue

            current_value = float(values[i])
            window_start = max(0, i - ROLLING_WINDOW + 1)
            window = values[window_start:i+1]
            mean = float(np.mean(window))
            std = float(np.std(window))

            # Absolute threshold check
            absolute_threshold = ABSOLUTE_THRESHOLDS.get(metric_name)
            is_absolute_anomaly = False
            if absolute_threshold is not None:
                if metric_name == "availability":
                    is_absolute_anomaly = current_value < absolute_threshold
                else:
                    is_absolute_anomaly = current_value > absolute_threshold

            # Rolling Z-score
            is_zscore_anomaly = False
            z_score = 0.0
            if std > 0:
                z = abs((current_value - mean) / std)
                z_score = float(z)
                is_zscore_anomaly = z > Z_THRESHOLD

            # Flag anomaly if either threshold exceeded
            if is_absolute_anomaly or is_zscore_anomaly:
                anomalous_metrics.append({
                    "metric": metric_name,
                    "value": current_value,
                    "mean": mean,
                    "std": std,
                    "z_score": z_score,
                    "threshold_type": "absolute" if is_absolute_anomaly else "statistical",
                    "absolute_threshold": absolute_threshold if is_absolute_anomaly else None
                })

        # Persistence check
        is_anomaly = len(anomalous_metrics) > 0
        ts_key = timestamps[i]
        if is_anomaly:
            consecutive_anomalies[ts_key] = consecutive_anomalies.get(ts_key, 0) + 1
            if consecutive_anomalies[ts_key] < PERSISTENCE_REQUIRED:
                is_anomaly = False  # wait for persistence
        else:
            consecutive_anomalies[ts_key] = 0

        anomalies.append(is_anomaly)

        if is_anomaly:
            ts_key = timestamps[i]
            # Only add to detailed_anomalies if we haven't already alerted for this timestamp
            if ts_key not in alerted_timestamps:
                detailed_anomalies.append({
                    "timestamp": ts_key,
                    "anomaly_score": len(anomalous_metrics),
                    "metrics": anomalous_metrics
                })
                alerted_timestamps.add(ts_key)

    return anomalies, detailed_anomalies

# --- Fetch metrics from network monitor API ---
def fetch_metrics_from_network_monitor() -> Dict:
    try:
        response = requests.get(f"{NETWORK_MONITOR_URL}/api/metrics?limit=30", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Error fetching metrics: {e}")
        return {}

# --- Print anomaly details ---
def print_anomaly_details(anomaly_details: Dict):
    print(f"\n🚨 ANOMALY DETECTED at {anomaly_details['timestamp']}")
    print(f"   Anomaly Score: {anomaly_details['anomaly_score']} metrics exceeded threshold")
    print("   Affected Metrics:")
    for metric_info in anomaly_details['metrics']:
        metric_name = metric_info['metric']
        value = metric_info['value']
        mean = metric_info['mean']
        z_score = metric_info['z_score']

        metric_display = {
            "rtt": "RTT (ms)",
            "jitter": "Jitter (ms)",
            "loss": "Packet Loss (%)",
            "error": "Error Rate (%)",
            "availability": "Availability (%)"
        }.get(metric_name, metric_name)

        threshold_type = metric_info.get("threshold_type", "statistical")
        absolute_threshold = metric_info.get("absolute_threshold")
        status_parts = []

        if threshold_type == "absolute" and absolute_threshold is not None:
            if metric_name == "availability":
                status_parts.append(f"BELOW threshold ({absolute_threshold}%)")
            else:
                status_parts.append(f"ABOVE threshold ({absolute_threshold})")
        if z_score > 0:
            deviation = ((value - mean) / mean * 100) if mean != 0 else 0
            direction = "↑" if value > mean else "↓"
            status_parts.append(f"Z-score: {z_score:.2f} ({direction} {abs(deviation):.1f}% from mean)")

        status = " | ".join(status_parts) if status_parts else "Anomaly detected"
        print(f"      • {metric_display}: {value:.2f} - {status}")
    print()

# --- Continuous monitoring loop ---
def start_anomaly_agent():
    print("🔍 Sensitive Network Anomaly Detection Agent started")
    print(f"   Monitoring: {NETWORK_MONITOR_URL}/api/metrics")
    print(f"   Check interval: {CHECK_INTERVAL} seconds")
    print(f"   Rolling Z-score threshold: {Z_THRESHOLD}")
    print(f"   Rolling window size: {ROLLING_WINDOW}")
    print(f"   Persistence required: {PERSISTENCE_REQUIRED} cycles")
    print("   Absolute thresholds:", ABSOLUTE_THRESHOLDS)
    print()

    while True:
        try:
            chart_data = fetch_metrics_from_network_monitor()
            if not chart_data or not chart_data.get("timestamps"):
                print("⚠️  No metrics data available, waiting...")
                time.sleep(CHECK_INTERVAL)
                continue

            anomalies, detailed_anomalies = detect_anomalies(chart_data)

            if detailed_anomalies:
                for anomaly_detail in detailed_anomalies:
                    print_anomaly_details(anomaly_detail)
            else:

                print(f"✓ No anomalies detected at {time.strftime('%H:%M:%S')}")
            
            # Clean up old timestamps from alerted_timestamps to prevent memory growth
            # Keep only timestamps from the current data batch
            if chart_data.get("timestamps"):
                current_timestamps = set(chart_data.get("timestamps", []))
                # Remove timestamps that are no longer in the current data
                alerted_timestamps.intersection_update(current_timestamps)

        except KeyboardInterrupt:
            print("\n🛑 Anomaly Detection Agent stopped")
            break
        except Exception as e:
            print(f"❌ Error in anomaly detection: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    start_anomaly_agent()
