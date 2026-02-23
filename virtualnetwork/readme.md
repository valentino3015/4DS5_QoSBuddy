# QoSBuddy — Virtual Network Dataset (Mininet)

Dataset collected from a simulated SDN network with controlled traffic scenarios.
Used for training and validating QoS machine learning models.

---

## Files

| File | Description |
|------|-------------|
| `qos_dataset.csv` | Labeled dataset — 20 rows, 5 scenarios × 4 host pairs |
| `topology.py` | Mininet topology script (virtual network definition) |
| `collect_data.py` | Scenario orchestrator — generates traffic and collects metrics |
| `dashboard.py` | Dash dashboard to visualize the dataset |

---

## How the data was collected

A virtual network was created using **Mininet** running inside a Ubuntu VM.

**Network topology:**
```
Zone A          Core         Zone B
  h1 ─┐                    ┌─ h3
      ├─ s1 ── s3 (bottleneck) ── s2 ─┤
  h2 ─┘                    └─ h4
```

- 4 virtual hosts (h1, h2 in Zone A — h3, h4 in Zone B)
- 3 Open vSwitch switches (s1, s2 = edge, s3 = core bottleneck)
- 1 OpenFlow SDN controller (c0)
- Links use TC (Traffic Control) to emulate real network conditions

For each scenario, the script:
1. Starts the network with specific link parameters
2. Runs `ping` between all host pairs → measures latency, jitter, packet loss
3. Runs `iperf3 UDP` between all host pairs → measures throughput
4. Saves results to CSV with the scenario label
5. Tears down the network and moves to the next scenario

---

## Scenarios

5 network conditions were simulated, each representing a different QoS state:

| Scenario | Bandwidth | Delay | Packet Loss | Jitter | What it represents |
|----------|-----------|-------|-------------|--------|--------------------|
| `normal` | 10 Mbps | 5ms | 0% | 1ms | Healthy network, no issues |
| `congested` | 1 Mbps | 20ms | 2% | 5ms | Network under heavy load |
| `high_loss` | 5 Mbps | 10ms | 15% | 2ms | Poor link quality, packet drops |
| `high_jitter` | 8 Mbps | 8ms | 0% | 20ms | Unstable network, variable delay |
| `critical` | 0.5 Mbps | 50ms | 20% | 15ms | Severe degradation, near failure |

---

## Dataset structure

**20 rows total** — 5 scenarios × 4 host pairs (h1→h3, h1→h4, h2→h3, h2→h4)

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime | When the measurement was taken |
| `scenario` | string | Network condition label (ground truth) |
| `src` | string | Source host (h1 or h2) |
| `dst` | string | Destination host (h3 or h4) |
| `latency_ms` | float | Average RTT measured by ping (ms) |
| `jitter_ms` | float | Latency standard deviation — ping variation (ms) |
| `packet_loss_pct` | float | Percentage of lost packets (%) |
| `throughput_mbps` | float | UDP throughput measured by iperf3 (Mbps) |

---

## Key properties

**Ground-truth labels** — the `scenario` column is a reliable label because
the network conditions were injected programmatically. There is no ambiguity
about what caused each measurement.

**Controlled variability** — each scenario has distinct and intentional
differences across all 4 metrics, making the dataset well-suited for
classification tasks.

**Cross-zone traffic only** — all measurements are between Zone A and Zone B,
passing through the bottleneck switch s3. This is where QoS degradation is
injected and observed.

---

## Visualize the dataset — Dashboard

A Dash dashboard is included to explore the dataset visually.

**Requirements:**
```
pip install dash plotly pandas
```

**Run:**
```
python dashboard.py
```

Then open your browser at:
```
http://127.0.0.1:8050
```

**What the dashboard shows:**

| Section | Description |
|---------|-------------|
| **KPI cards** | Average latency, jitter, packet loss, throughput across all scenarios |
| **Network topology** | Visual map of the virtual network (hosts, switches, zones) |
| **Radar chart** | Multi-metric comparison of all 5 scenarios on a single chart |
| **Latency boxplot** | Distribution of latency values per scenario |
| **Jitter boxplot** | Distribution of jitter values per scenario |
| **Packet loss bar chart** | Average loss per scenario |
| **Latency heatmap** | Latency per source host per scenario |
| **Raw data table** | Full dataset, filterable and sortable |

The dashboard reads `qos_dataset.csv` from the same folder — make sure both
files are in the same directory before running.

---

## Intended use

This dataset is the first building block for the QoSBuddy ML pipeline:

```
qos_dataset.csv  (this file)
        ↓
  Feature engineering
        ↓
  Model training
  (anomaly detection / traffic classification / QoS prediction)
        ↓
  Deployment in QoSBuddy dashboard
```

Suggested next steps:
- Use `scenario` as the classification target
- Features: `latency_ms`, `jitter_ms`, `packet_loss_pct`, `throughput_mbps`
- Suggested models to try: Random Forest, KNN, SVM, Isolation Forest (anomaly)
- Combine with `qos_realtraffic.csv` (real traffic) for fine-tuning

---

## How to reproduce

Requirements: Ubuntu VM with Mininet 2.3 installed (or the official Mininet VM image).

```bash
# Run the topology test
sudo python3 topology.py

# Run the full data collection (takes ~10 minutes)
sudo python3 collect_data.py
```

Output: `qos_dataset.csv` in the same directory.