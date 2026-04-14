"""
QoSBuddy — Real Traffic Capture Agent (Windows)
Captures live network traffic via tshark + active ping metrics.
Output: qos_realtraffic.csv
"""

import subprocess
import threading
import csv
import time
import datetime
import os
import statistics
import socket

# ── CONFIG ────────────────────────────────────────────────────────────────────
TSHARK_PATH   = r"C:\Program Files\Wireshark\tshark.exe"
INTERFACE     = "4"          # Wi-Fi (index from tshark -D)
CAPTURE_DURATION = 600       # seconds total (10 min), change as needed
FLOW_WINDOW   = 5            # seconds per aggregation window
OUTPUT_CSV    = "capture_agent/qos_realtraffic.csv"


PING_TARGETS  = {
    "gateway":    None,       # auto-detected below
    "cloudflare": "1.1.1.1",
    "google":     "8.8.8.8",
    "dns_root":   "198.41.0.4",
}

# ── TRAFFIC TYPE CLASSIFIER ───────────────────────────────────────────────────
def classify_traffic(proto, dst_port, src_port):
    """Classify flow by protocol and port."""
    try:
        dst_port = int(dst_port)
        src_port = int(src_port)
    except (ValueError, TypeError):
        return "unknown"

    if proto == "UDP" and dst_port == 53:
        return "dns"
    if proto == "TCP" and dst_port in (80,):
        return "http"
    if proto == "TCP" and dst_port in (443, 8443):
        return "https"
    if proto == "UDP" and dst_port in (3478, 3479, 5349, 5350, 19302, 19305):
        return "voip_webrtc"
    if proto == "UDP" and 1024 <= dst_port <= 65535 and src_port > 1024:
        return "streaming_udp"
    if proto == "TCP" and dst_port in (25, 465, 587, 993, 995):
        return "email"
    if proto == "ICMP":
        return "icmp_probe"
    if proto == "TCP" and dst_port in (22,):
        return "ssh"
    if dst_port in (67, 68):
        return "dhcp"
    if proto == "TCP":
        return "tcp_other"
    if proto == "UDP":
        return "udp_other"
    return "unknown"

def quality_label(latency, jitter, loss):
    """Label network quality based on thresholds."""
    if loss > 5 or latency > 150 or jitter > 30:
        return "bad"
    if loss > 1 or latency > 80 or jitter > 15:
        return "degraded"
    return "good"

# ── AUTO-DETECT GATEWAY ───────────────────────────────────────────────────────
def get_gateway():
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1).NextHop"],
            capture_output=True, text=True, timeout=5
        )
        gw = result.stdout.strip()
        if gw:
            return gw
    except Exception:
        pass
    return "192.168.1.1"  # fallback

# ── ACTIVE PING METRICS ───────────────────────────────────────────────────────
ping_results = {}  # { target_name: { latency, jitter, loss } }

def ping_target(name, ip, count=10):
    """Run ping and extract latency/jitter/loss."""
    while True:
        try:
            result = subprocess.run(
                ["ping", "-n", str(count), ip],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout
            times = []
            for line in output.split("\n"):
                if "temps=" in line or "time=" in line:
                    for part in line.split():
                        if part.startswith("temps=") or part.startswith("time="):
                            val = part.split("=")[1].replace("ms", "").replace("<", "")
                            try:
                                times.append(float(val))
                            except ValueError:
                                pass

            total_sent = count
            loss_pct = 0.0
            for line in output.split("\n"):
                if "%" in line and ("perdus" in line.lower() or "lost" in line.lower()):
                    for part in line.split():
                        if "%" in part:
                            try:
                                loss_pct = float(part.replace("(", "").replace("%", ""))
                            except ValueError:
                                pass

            if times:
                latency = statistics.mean(times)
                jitter = statistics.stdev(times) if len(times) > 1 else 0.0
            else:
                latency, jitter = 0.0, 0.0

            ping_results[name] = {
                "latency_ms": round(latency, 2),
                "jitter_ms":  round(jitter, 2),
                "loss_pct":   round(loss_pct, 2),
            }
        except Exception as e:
            ping_results[name] = {"latency_ms": 0.0, "jitter_ms": 0.0, "loss_pct": 100.0}

        time.sleep(FLOW_WINDOW)

# ── DNS TIMING ────────────────────────────────────────────────────────────────
dns_time_ms = 0.0

def measure_dns():
    global dns_time_ms
    targets = ["google.com", "netflix.com", "youtube.com", "github.com"]
    while True:
        times = []
        for host in targets:
            try:
                t0 = time.perf_counter()
                socket.getaddrinfo(host, None)
                t1 = time.perf_counter()
                times.append((t1 - t0) * 1000)
            except Exception:
                pass
        if times:
            dns_time_ms = round(statistics.mean(times), 2)
        time.sleep(10)

# ── TSHARK PASSIVE CAPTURE ────────────────────────────────────────────────────
def run_tshark_window(duration_sec):
    """
    Run tshark for `duration_sec` seconds and return parsed flow list.
    Fields: frame.time_epoch, ip.src, ip.dst, tcp.srcport, tcp.dstport,
            udp.srcport, udp.dstport, _ws.col.Protocol, frame.len,
            tcp.analysis.retransmission, ip.ttl
    """
    cmd = [
        TSHARK_PATH,
        "-i", INTERFACE,
        "-a", f"duration:{duration_sec}",
        "-T", "fields",
        "-e", "frame.time_epoch",
        "-e", "ip.src",
        "-e", "ip.dst",
        "-e", "tcp.srcport",
        "-e", "tcp.dstport",
        "-e", "udp.srcport",
        "-e", "udp.dstport",
        "-e", "_ws.col.Protocol",
        "-e", "frame.len",
        "-e", "tcp.analysis.retransmission",
        "-E", "separator=|",
        "-E", "quote=n",
        "-E", "occurrence=f",
        # exclude loopback
        "-f", "not (src host 127.0.0.1 or dst host 127.0.0.1)",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_sec + 10)
        return result.stdout.strip().split("\n")
    except subprocess.TimeoutExpired:
        return []
    except Exception as e:
        print(f"[tshark error] {e}")
        return []

def parse_tshark_output(lines):
    """
    Aggregate tshark packet lines into flow-level stats.
    Returns a list of flow dicts.
    """
    flows = {}  # key: (src_ip, dst_ip, proto, dst_port)

    for line in lines:
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 9:
            continue

        try:
            ts        = float(parts[0]) if parts[0] else 0.0
            src_ip    = parts[1]
            dst_ip    = parts[2]
            tcp_sport = parts[3]
            tcp_dport = parts[4]
            udp_sport = parts[5]
            udp_dport = parts[6]
            proto     = parts[7]
            pkt_len   = int(parts[8]) if parts[8] else 0
            retrans   = 1 if parts[9].strip() == "1" else 0 if len(parts) > 9 else 0
        except (ValueError, IndexError):
            continue

        # Determine ports
        src_port = tcp_sport or udp_sport or "0"
        dst_port = tcp_dport or udp_dport or "0"

        traffic_type = classify_traffic(proto, dst_port, src_port)
        key = (src_ip, dst_ip, proto, dst_port, traffic_type)

        if key not in flows:
            flows[key] = {
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "proto": proto,
                "dst_port": dst_port,
                "traffic_type": traffic_type,
                "packets": 0,
                "bytes": 0,
                "retransmissions": 0,
                "timestamps": [],
            }

        flows[key]["packets"] += 1
        flows[key]["bytes"]   += pkt_len
        flows[key]["retransmissions"] += retrans
        if ts > 0:
            flows[key]["timestamps"].append(ts)

    # Convert to metrics
    result = []
    for key, f in flows.items():
        if f["packets"] < 2:
            continue

        timestamps = sorted(f["timestamps"])
        duration = (timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else FLOW_WINDOW
        duration = max(duration, 0.001)

        bandwidth_mbps = round((f["bytes"] * 8) / (duration * 1_000_000), 4)

        # Inter-arrival jitter
        if len(timestamps) > 2:
            intervals = [(timestamps[i+1] - timestamps[i]) * 1000
                         for i in range(len(timestamps)-1)]
            passive_jitter = round(statistics.stdev(intervals), 3) if len(intervals) > 1 else 0.0
        else:
            passive_jitter = 0.0

        retrans_rate = round(f["retransmissions"] / f["packets"] * 100, 2) if f["proto"] == "TCP" else 0.0

        result.append({
            "src_ip":           f["src_ip"],
            "dst_ip":           f["dst_ip"],
            "protocol":         f["proto"],
            "dst_port":         f["dst_port"],
            "traffic_type":     f["traffic_type"],
            "duration_s":       round(duration, 3),
            "packets_total":    f["packets"],
            "bytes_total":      f["bytes"],
            "bandwidth_mbps":   bandwidth_mbps,
            "passive_jitter_ms":passive_jitter,
            "retrans_rate_pct": retrans_rate,
        })

    return result

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  QoSBuddy — Real Traffic Capture Agent")
    print("=" * 60)

    # Detect gateway
    gw = get_gateway()
    PING_TARGETS["gateway"] = gw
    print(f"[+] Gateway detected: {gw}")
    print(f"[+] Interface: Wi-Fi (index {INTERFACE})")
    print(f"[+] Output: {OUTPUT_CSV}")
    print(f"[+] Window: {FLOW_WINDOW}s | Total: {CAPTURE_DURATION}s")
    print()

    # Start ping threads
    for name, ip in PING_TARGETS.items():
        if ip:
            t = threading.Thread(target=ping_target, args=(name, ip), daemon=True)
            t.start()
            print(f"[+] Ping thread started → {name} ({ip})")

    # Start DNS thread
    t_dns = threading.Thread(target=measure_dns, daemon=True)
    t_dns.start()
    print("[+] DNS measurement thread started")
    print()
    time.sleep(3)  # let pings warm up

    # CSV setup
    fieldnames = [
        "timestamp", "window_id",
        "src_ip", "dst_ip", "protocol", "dst_port", "traffic_type",
        "duration_s", "packets_total", "bytes_total", "bandwidth_mbps",
        "passive_jitter_ms", "retrans_rate_pct",
        "dns_time_ms",
        "ping_gateway_latency_ms", "ping_gateway_jitter_ms", "ping_gateway_loss_pct",
        "ping_cloudflare_latency_ms", "ping_cloudflare_jitter_ms", "ping_cloudflare_loss_pct",
        "ping_google_latency_ms", "ping_google_jitter_ms", "ping_google_loss_pct",
        "quality_label",
    ]

    file_exists = os.path.isfile(OUTPUT_CSV)
    csvfile = open(OUTPUT_CSV, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    if not file_exists:
        writer.writeheader()

    window_id = 0
    elapsed = 0

    print("[*] Starting capture... (Ctrl+C to stop)\n")

    try:
        while elapsed < CAPTURE_DURATION:
            window_id += 1
            ts = datetime.datetime.now().isoformat()
            print(f"[Window {window_id:03d}] Capturing {FLOW_WINDOW}s of traffic...", end=" ", flush=True)

            raw_lines = run_tshark_window(FLOW_WINDOW)
            flows = parse_tshark_output(raw_lines)

            # Collect active metrics snapshot
            gw_m  = ping_results.get("gateway",    {"latency_ms": 0, "jitter_ms": 0, "loss_pct": 0})
            cf_m  = ping_results.get("cloudflare", {"latency_ms": 0, "jitter_ms": 0, "loss_pct": 0})
            gg_m  = ping_results.get("google",     {"latency_ms": 0, "jitter_ms": 0, "loss_pct": 0})

            # Quality label based on best available ping
            best_latency = gw_m["latency_ms"] or cf_m["latency_ms"] or gg_m["latency_ms"]
            best_jitter  = gw_m["jitter_ms"]  or cf_m["jitter_ms"]  or gg_m["jitter_ms"]
            best_loss    = max(gw_m["loss_pct"], cf_m["loss_pct"])
            qlabel = quality_label(best_latency, best_jitter, best_loss)

            if not flows:
                # Write one row with just active metrics even if no flows captured
                flows = [{
                    "src_ip": "-", "dst_ip": "-", "protocol": "-",
                    "dst_port": "-", "traffic_type": "no_traffic",
                    "duration_s": FLOW_WINDOW, "packets_total": 0,
                    "bytes_total": 0, "bandwidth_mbps": 0,
                    "passive_jitter_ms": 0, "retrans_rate_pct": 0,
                }]

            for flow in flows:
                row = {
                    "timestamp":    ts,
                    "window_id":    window_id,
                    **flow,
                    "dns_time_ms":  dns_time_ms,
                    "ping_gateway_latency_ms":    gw_m["latency_ms"],
                    "ping_gateway_jitter_ms":     gw_m["jitter_ms"],
                    "ping_gateway_loss_pct":      gw_m["loss_pct"],
                    "ping_cloudflare_latency_ms": cf_m["latency_ms"],
                    "ping_cloudflare_jitter_ms":  cf_m["jitter_ms"],
                    "ping_cloudflare_loss_pct":   cf_m["loss_pct"],
                    "ping_google_latency_ms":     gg_m["latency_ms"],
                    "ping_google_jitter_ms":      gg_m["jitter_ms"],
                    "ping_google_loss_pct":       gg_m["loss_pct"],
                    "quality_label": qlabel,
                }
                writer.writerow(row)

            csvfile.flush()
            elapsed += FLOW_WINDOW
            print(f"{len(flows)} flows | quality={qlabel} | latency={best_latency}ms | loss={best_loss}%")

    except KeyboardInterrupt:
        print("\n[!] Stopped by user.")

    finally:
        csvfile.close()
        print(f"\n[✓] Dataset saved to: {OUTPUT_CSV}")
        print(f"[✓] Total windows captured: {window_id}")

if __name__ == "__main__":
    main()