from ping3 import ping
import psutil
import requests
import time
from datetime import datetime
import socket

def collect_metrics(destinations):
    metrics_list = []

    source_ip = socket.gethostbyname(socket.gethostname())

    # ---- System-wide throughput ----
    net1 = psutil.net_io_counters()
    time.sleep(1)
    net2 = psutil.net_io_counters()

    throughput_down = (net2.bytes_recv - net1.bytes_recv) / 1024   # KB/s
    throughput_up = (net2.bytes_sent - net1.bytes_sent) / 1024     # KB/s
    max_bandwidth = 20 * 1024  # 100 Mbps in KB/s
    bandwidth_utilization = ((throughput_down + throughput_up) / max_bandwidth) * 100

    # ---- Collect per-destination metrics ----
    for dest in destinations:
        try:
            # HTTP / HTTPS
            if dest.startswith("http"):
                start = time.time()
                try:
                    response = requests.get(dest, timeout=5)
                    response_time = (time.time() - start) * 1000
                    http_error_rate = 0 if response.status_code == 200 else 100
                    availability = 100
                except Exception:
                    response_time = 0
                    http_error_rate = 100
                    availability = 0

                metrics = {
                    "timestamp": datetime.now().replace(microsecond=0),
                    "source_ip": source_ip,
                    "destination_ip": dest,
                    "response_time": response_time,
                    "http_error_rate": http_error_rate,
                    "availability": availability,
                    "throughput_down": throughput_down,
                    "throughput_up": throughput_up,
                    "bandwidth_utilization": bandwidth_utilization
                }

            # Ping for IPs
            else:
                rtt = ping(dest)
                if rtt is None:
                    continue
                metrics = {
                    "timestamp": datetime.now().replace(microsecond=0),
                    "source_ip": source_ip,
                    "destination_ip": dest,
                    "avg_rtt": rtt * 1000,  # ms
                    "throughput_down": throughput_down,
                    "throughput_up": throughput_up,
                    "bandwidth_utilization": bandwidth_utilization
                }

            metrics_list.append(metrics)

        except Exception as e:
            print(f"⚠️ Error collecting metrics for {dest}: {e}")

    return metrics_list

def get_active_targets():
    """
    Return a set of hostnames or IPs your computer is currently connected to.
    """
    targets = set()
    connections = psutil.net_connections(kind='inet')
    for conn in connections:
        raddr = conn.raddr
        if raddr:
            ip = raddr.ip
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except Exception:
                hostname = ip
            targets.add(hostname)
    return targets