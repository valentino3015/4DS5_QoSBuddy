# QoSBuddy
## AI-Driven Predictive Quality of Service Monitoring and Optimization System

---

## Introduction

QoSBuddy is an AI-driven network operations project designed to help operators observe, understand, and improve Quality of Service in near real time.

QoSBuddy aims to:

- Monitor network performance in real time
- Detect anomalies automatically
- Predict potential degradations
- Recommend corrective actions
- Provide clear and actionable reports

---

## Project Information

**Project Duration:** 12 Weeks  
**Status:** In Preparation  

---

## Team Members

- Mariem Gharbi  
- Hadyle Zribi  
- Donia Hali  
- Mariam Ben Abdallah  
- Omar Zallila  
- Ahmed Abid  

## 1) Folder Roles

### `agents/`
Contains the runtime intelligence of the system:

- `detection_agent.py`
  - Trains anomaly + RCA models (batch mode).
  - Replays KPI time series (stream mode).
  - Detects anomalies using:
    - rule engine
    - LSTM autoencoder
    - Temporal CNN
    - neighbor-cell correlation
  - Runs inline RCA and writes events to `data/output/rca_feed.jsonl`.

- `remediation_agent.py`
  - Reads RCA feed (`data/output/rca_feed.jsonl`).
  - Recommends remediation actions from a remediation knowledge base.
  - Writes enriched events to `data/output/remediation_feed.jsonl`.
  - Hosts:
    - WebSocket server for live updates
    - HTTP server for the dashboard UI (`dashboard/index.html`)

### `data/`
Contains mapping/config data and runtime outputs:

- `rca_mapping.json`
  - Mapping between root causes and:
    - suggested solutions
    - cause tags
  - Used by `detection_agent.py` RCA stage.

- `output/` (created at runtime)
  - `rca_feed.jsonl`: anomaly + RCA events from DetectionAgent
  - `remediation_feed.jsonl`: RCA + remediation actions from RemediationAgent

Other expected input files used by agents (typically placed under `data/`):

- `time_series_kpi.csv` (stream + anomaly model training input)
- `labeled_incidents.csv` (RCA classifier training input)
- `cell_topology.csv` (neighbor relationships and topology for correlation/dashboard)

### `dashboard/`
Contains the live UI:

- `index.html`
  - Real-time operations dashboard.
  - Receives WebSocket events from `remediation_agent.py`.
  - Shows:
    - severity counters
    - KPI trend charts
    - live feed cards
    - remediation details
    - topology and analytics views

---

## 2) End-to-End Data Flow

1. DetectionAgent trains models from historical data (`--mode train`).
2. DetectionAgent streams KPI rows and emits anomaly+RCA JSON lines to `data/output/rca_feed.jsonl`.
3. RemediationAgent tails this feed and enriches each event with action plans.
4. RemediationAgent pushes live events to the dashboard via WebSocket.
5. Dashboard renders operations view (overview, topology, analytics) in real time.

---

## 3) How to Run

From repository root:

```bash
python agents/detection_agent.py --mode all
```

This performs training + streaming and produces `data/output/rca_feed.jsonl`.

Then start remediation + dashboard:

```bash
python agents/remediation_agent.py
```

Default endpoints:

- Dashboard: `http://localhost:8080`
- WebSocket: `ws://localhost:8765`

Optional arguments:

```bash
python agents/detection_agent.py --mode train --sample-frac 0.15 --seq-len 16
python agents/detection_agent.py --mode stream --chunk-size 500 --stream-delay 0.0
python agents/remediation_agent.py --ws-port 9000 --http-port 9001 --tail-interval 0.5
```

---

## 4) Key Outputs

- `data/output/rca_feed.jsonl`
  - Source of truth for anomaly and RCA events from DetectionAgent.
- `data/output/remediation_feed.jsonl`
  - Enriched remediation event stream used by dashboard and post-analysis.
- `logs/detection_agent.log`
- `logs/remediation_agent.log`

---

## 5) Notes and Operational Tips

- If dashboard shows no events:
  - confirm DetectionAgent is producing `rca_feed.jsonl`
  - confirm RemediationAgent is running and WebSocket is connected
- If RCA quality is poor:
  - improve `data/labeled_incidents.csv`
  - enrich `data/rca_mapping.json`
- If neighbor escalation is missing:
  - verify `data/cell_topology.csv` exists and has valid `neighbor_cells`

