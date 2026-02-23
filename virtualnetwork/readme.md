QoSBuddy — Network Capture Agent & Live Dashboard
Monitor your real network traffic in real time and save it as a labeled dataset.

What's in this folder

capture_agent.py -> Captures live network traffic and saves metrics to CSV
dashboard_live.py -> Live dashboard — reads the CSV and displays charts in your browser
qos_realtraffic.csv -> the dataset (auto-generated when the agent runs)

Requirements

Python 3.8+
Wireshark (includes tshark) → wireshark.org
Run PowerShell as Administrator (required for tshark to capture packets)

Install Python dependencies:
pip install pandas

Step 1 — Check your Wi-Fi interface number
Open PowerShell as Administrator and run:
C:\Program Files\Wireshark\tshark.exe
Find the line that says (Wi-Fi) and note its number (e.g. 6).
Open capture_agent.py and make sure this line matches:
pythonINTERFACE = "6"   # ← change this if needed

Step 2 — Run the capture agent
Open PowerShell as Administrator, go to your project folder, and run:
python capture_agent.py
You will see something like:
[+] Gateway detected: 192.168.1.1
[+] Interface: Wi-Fi (index 6)
[Window 001] Capturing 5s of traffic... 87 flows | quality=good | latency=12.3ms | loss=0.0%
[Window 002] Capturing 5s of traffic... 103 flows | quality=good | latency=11.8ms | loss=0.0%
The agent captures a 5-second window of traffic every 5 seconds and writes
each flow as a row in qos_realtraffic.csv.
Just browse normally — open YouTube, make a call, load pages — everything
gets captured automatically.
Press Ctrl+C to stop. The CSV is saved automatically.

Step 3 — Run the live dashboard
Open a second PowerShell window (no need for Admin here) and run:
python dashboard_live.py
Then open your browser at:
http://127.0.0.1:8050
The dashboard refreshes every 5 seconds automatically.

What the dashboard shows
Section
KPI cards ->  Avg RTT, P95 RTT, Jitter, Packet Loss, Throughput ↓↑, BW Utilization, Retransmissions, Availability, Response Time
RTT chart -> Latency, P95 and Jitter over time
Loss chart -> Packet loss per window, colored by quality
Throughput -> Download vs Upload bandwidth
Traffic pie -> Distribution by type (DNS, HTTPS, VoIP, streaming...)
Quality timeline -> GOOD / DEGRADED / BAD per window
Live flows table -> Last 20 captured network flows with all metrics

What the CSV contains
Each row = one network flow captured during a 5-second window.
Column
timestamp -> When the flow was captured
traffic_type -> dns / https / voip_webrtc / streaming_udp / tcp_other...src_ip / dst_ip -> Source and destination IP addresses
protocol -> TCP or UDP
bandwidth_mbps ->Flow bandwidth in Mbps
passive_jitter_ms ->Jitter measured from packet inter-arrival times retrans_rate_pct -> TCP retransmission rate (%)
ping_google_latency_ms -> Active ping latency to Google
ping_google_jitter_ms -> Active ping jitter toGoogle
ping_google_loss_pct -> Active packet loss to Google
dns_time_ms -> DNS resolution time
quality_label -> good / degraded / bad (auto-labeled)

Quality labels — how they work
The agent automatically labels each window based on active ping results:
Label -> Condition
good -> Latency < 80ms AND Jitter < 15ms AND Loss < 1%
degraded -> Latency < 150ms AND Jitter < 30ms AND Loss < 5%
bad -> Latency > 150ms OR Jitter > 30ms OR Loss > 5%