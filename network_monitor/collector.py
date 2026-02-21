from ping3 import ping
import psutil
import requests
import time
from datetime import datetime
import socket

def collect_metrics(destination="8.8.8.8"):

    source_ip = socket.gethostbyname(socket.gethostname())
    rtts = []

    # ---- RTT + Jitter + Packet Loss (fast: 5 pings, 0.2s apart) ----
    num_pings = 5
    for _ in range(num_pings):
        rtt = ping(destination)
        if rtt is not None and rtt is not False:
            rtts.append(rtt * 1000)
        time.sleep(0.2)

    if not rtts:
        return None

    rtts_sorted = sorted(rtts)
    avg_rtt = sum(rtts) / len(rtts)
    p95_index = max(0, min(len(rtts_sorted) - 1, int(round(0.95 * (len(rtts_sorted) - 1)))))
    p95_rtt = rtts_sorted[p95_index]

    if len(rtts) > 1:
        diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
        jitter = sum(diffs) / len(diffs)
    else:
        jitter = 0
    packet_loss = (num_pings - len(rtts)) / num_pings * 100

    # ---- Throughput (down = recv, up = sent), 0.5s sample ----
    net1 = psutil.net_io_counters()
    time.sleep(0.5)
    net2 = psutil.net_io_counters()
    # Scale to KB/s (sample was 0.5s, so multiply by 2)
    throughput_down = (net2.bytes_recv - net1.bytes_recv) / 1024 * 2   # KB/s
    throughput_up = (net2.bytes_sent - net1.bytes_sent) / 1024 * 2     # KB/s

    # ---- Bandwidth Utilization (ex: 100 Mbps assumed) ----
    max_bandwidth = 20 * 1024  # 100 Mbps in KB/s
    bandwidth_utilization = ((throughput_down + throughput_up) / max_bandwidth) * 100

    # ---- Retransmission Rate (approximation) ----
    retransmission_rate = packet_loss  # simplification académique

    # ---- Application Metrics (short timeout for faster collection) ----
    start = time.time()
    try:
        response = requests.get("https://google.com", timeout=2)
        response_time = (time.time() - start) * 1000
        http_error_rate = 0 if response.status_code == 200 else 100
        availability = 100
    except Exception:
        response_time = 0
        http_error_rate = 100
        availability = 0

    return {
        "timestamp": datetime.now().replace(microsecond=0),
        "source_ip": source_ip,
        "destination_ip": destination,
        "avg_rtt": avg_rtt,
        "p95_rtt": p95_rtt,
        "jitter": jitter,
        "packet_loss": packet_loss,
        "throughput_down": throughput_down,
        "throughput_up": throughput_up,
        "bandwidth_utilization": bandwidth_utilization,
        "retransmission_rate": retransmission_rate,
        "response_time": response_time,
        "http_error_rate": http_error_rate,
        "availability": availability
    }
