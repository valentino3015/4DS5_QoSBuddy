from ping3 import ping
import psutil
import requests
import time
from datetime import datetime
import socket

def collect_metrics(destination="8.8.8.8"):

    source_ip = socket.gethostbyname(socket.gethostname())
    rtts = []

    # ---- RTT + Jitter + Packet Loss ----
    for _ in range(10):
        rtt = ping(destination)
        if rtt is not None and rtt is not False:
            rtts.append(rtt * 1000)
        time.sleep(0.5)

    if not rtts:
        return None

    rtts_sorted = sorted(rtts)
    avg_rtt = sum(rtts) / len(rtts)
    # nearest-rank percentile (good enough for small N=10)
    p95_index = max(0, min(len(rtts_sorted) - 1, int(round(0.95 * (len(rtts_sorted) - 1)))))
    p95_rtt = rtts_sorted[p95_index]

    if len(rtts) > 1:
        diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
        jitter = sum(diffs) / len(diffs)
    else:
        jitter = 0
    packet_loss = (10 - len(rtts)) / 10 * 100

    # ---- Throughput ----
    net1 = psutil.net_io_counters()
    time.sleep(1)
    net2 = psutil.net_io_counters()

    throughput = (net2.bytes_sent - net1.bytes_sent) / 1024  # KB/s

    # ---- Bandwidth Utilization (ex: 100 Mbps assumed) ----
    max_bandwidth = 100 * 1024  # 100 Mbps in KB/s
    bandwidth_utilization = (throughput / max_bandwidth) * 100

    # ---- Retransmission Rate (approximation) ----
    retransmission_rate = packet_loss  # simplification académique

    # ---- Application Metrics ----
    start = time.time()
    try:
        response = requests.get("https://google.com", timeout=5)
        response_time = (time.time() - start) * 1000
        http_error_rate = 0 if response.status_code == 200 else 100
        availability = 100
    except Exception:
        response_time = 0
        http_error_rate = 100
        availability = 0

    return {
        "timestamp": datetime.now(),
        "source_ip": source_ip,
        "destination_ip": destination,
        "avg_rtt": avg_rtt,
        "p95_rtt": p95_rtt,
        "jitter": jitter,
        "packet_loss": packet_loss,
        "throughput": throughput,
        "bandwidth_utilization": bandwidth_utilization,
        "retransmission_rate": retransmission_rate,
        "response_time": response_time,
        "http_error_rate": http_error_rate,
        "availability": availability
    }
