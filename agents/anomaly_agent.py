"""
QoSBuddy — AnomalyDetectorAgent
================================
Agent 1: Detects and predicts network degradations from 5G KPI data.

Pipeline:
  1. BATCH TRAINING   — trains Isolation Forest + LSTM on historical CSV
  2. LIVE INFERENCE   — streams CSV row-by-row (simulating real-time feed),
                        runs rule engine + ML models on every window,
                        emits structured JSON events to output feed

Output feed: data/output/anomaly_feed.jsonl  (one JSON object per line)
             — consumed by downstream agents (RCA, Remediation, etc.)

Usage:
    python agents/anomaly_agent.py --mode train   # batch train only
    python agents/anomaly_agent.py --mode stream  # stream inference (loads saved models)
    python agents/anomaly_agent.py --mode all     # train then stream (default)
"""

import os, sys, json, time, logging, argparse, warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
import joblib

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings("ignore")

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
DATA_DIR    = ROOT / "data"
MODEL_DIR   = ROOT / "models"
OUTPUT_DIR  = DATA_DIR / "output"
LOG_DIR     = ROOT / "logs"

for d in [MODEL_DIR, OUTPUT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

TS_KPI_PATH  = DATA_DIR / "time_series_kpi.csv"
FEED_PATH    = OUTPUT_DIR / "anomaly_feed.jsonl"
IF_PATH      = MODEL_DIR / "isolation_forest.joblib"
SCALER_PATH  = MODEL_DIR / "scaler.joblib"
LSTM_PATH    = MODEL_DIR / "lstm_predictor.pt"

# ─── Logging ──────────────────────────────────────────────────────────────────
# Force UTF-8 on stdout so Windows CP1252 doesn't choke on special characters.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_stream_handler = logging.StreamHandler(sys.stdout)
_file_handler   = logging.FileHandler(LOG_DIR / "anomaly_agent.log", encoding="utf-8")
_formatter      = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
_stream_handler.setFormatter(_formatter)
_file_handler.setFormatter(_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _file_handler])
log = logging.getLogger("AnomalyDetectorAgent")

# ─── KPI feature columns (numeric inputs to models) ───────────────────────────
KPI_FEATURES = [
    "RSRP_dBm", "SINR_dB", "PRB_util_DL_pct", "PRB_util_UL_pct",
    "CQI", "BLER_DL_pct", "BLER_UL_pct",
    "throughput_DL_Mbps", "throughput_UL_Mbps", "latency_ms",
    "call_drop_rate_pct", "HO_success_rate_pct", "MOS", "MIMO_rank",
    "active_users",
]

# ─── Rule-based thresholds (domain knowledge from radio issue document) ────────
THRESHOLDS = {
    "RSRP_dBm":            {"min": -110, "label": "Poor coverage"},
    "SINR_dB":             {"min": 0,    "label": "High interference"},
    "PRB_util_DL_pct":     {"max": 85,   "label": "DL capacity saturation"},
    "PRB_util_UL_pct":     {"max": 80,   "label": "UL capacity saturation"},
    "CQI":                 {"min": 4,    "label": "Poor channel quality"},
    "BLER_DL_pct":         {"max": 10,   "label": "Excessive DL block errors"},
    "BLER_UL_pct":         {"max": 10,   "label": "Excessive UL block errors"},
    "latency_ms":          {"max": 80,   "label": "High latency"},
    "call_drop_rate_pct":  {"max": 3,    "label": "Excessive call drops"},
    "HO_success_rate_pct": {"min": 80,   "label": "Handover degradation"},
    "MOS":                 {"min": 2.5,  "label": "Poor voice quality"},
    "throughput_DL_Mbps":  {"min": 10,   "label": "Very low DL throughput"},
}

SEVERITY_MAP = {
    0: "normal",
    1: "low",
    2: "medium",
    3: "high",
}

# ══════════════════════════════════════════════════════════════════════════════
# LSTM MODEL DEFINITION
# ══════════════════════════════════════════════════════════════════════════════
class LSTMPredictor(nn.Module):
    """
    Predicts anomaly score N steps ahead from a sliding window of KPI values.
    Input:  (batch, seq_len, n_features)
    Output: (batch, 1)  — predicted anomaly score [0–10]
    """
    def __init__(self, n_features: int, hidden: int = 64, layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features, hidden_size=hidden,
            num_layers=layers, batch_first=True,
            dropout=dropout if layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
            nn.Sigmoid(),          # output in [0,1], scaled to [0,10] at inference
        )

    def forward(self, x):
        _, (h, _) = self.lstm(x)   # take last hidden state
        return self.head(h[-1])


# ══════════════════════════════════════════════════════════════════════════════
# RULE ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def rule_engine(row: pd.Series) -> dict:
    """
    Evaluates domain-knowledge thresholds against a single KPI row.
    Returns a dict with triggered rules, breach counts, and severity.
    """
    triggered = []
    score = 0

    for kpi, cond in THRESHOLDS.items():
        val = row[kpi] if kpi in row.index and pd.notna(row[kpi]) else np.nan
        if pd.isna(val):
            continue
        breached = False
        if "min" in cond and val < cond["min"]:
            breached = True
        if "max" in cond and val > cond["max"]:
            breached = True
        if breached:
            triggered.append({"kpi": kpi, "value": round(float(val), 3), "reason": cond["label"]})
            # Weight critical KPIs more
            weight = 2 if kpi in ("RSRP_dBm", "SINR_dB", "call_drop_rate_pct", "HO_success_rate_pct") else 1
            score += weight

    severity_level = min(4, score // 2)
    return {
        "rule_triggered":  len(triggered) > 0,
        "rule_score":      score,
        "rule_severity":   SEVERITY_MAP[severity_level],
        "breached_kpis":   triggered,
    }


# ══════════════════════════════════════════════════════════════════════════════
# BATCH TRAINER
# ══════════════════════════════════════════════════════════════════════════════
class BatchTrainer:
    def __init__(self, seq_len: int = 16, sample_frac: float = 0.15):
        self.seq_len     = seq_len
        self.sample_frac = sample_frac
        self.scaler      = StandardScaler()
        self.iso_forest  = IsolationForest(
            n_estimators=200, contamination=0.08, random_state=42, n_jobs=-1
        )
        self.lstm        = None
        self.device      = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ── Load & preprocess ──────────────────────────────────────────────────────
    def load_data(self) -> pd.DataFrame:
        log.info(f"Loading KPI data from {TS_KPI_PATH} ...")
        df = pd.read_csv(TS_KPI_PATH, parse_dates=["timestamp"])
        df = df.dropna(subset=KPI_FEATURES)
        df = df.sample(frac=self.sample_frac, random_state=42).sort_values("timestamp")
        log.info(f"  Loaded {len(df):,} rows after {self.sample_frac*100:.0f}% sample")
        return df

    # ── Train Isolation Forest ─────────────────────────────────────────────────
    def train_isolation_forest(self, df: pd.DataFrame):
        log.info("Training Isolation Forest ...")
        X = self.scaler.fit_transform(df[KPI_FEATURES].values)
        self.iso_forest.fit(X)

        # Evaluate against ground-truth labels
        y_true = (df["label"] == "anomaly").astype(int).values
        raw_scores = self.iso_forest.decision_function(X)  # higher = more normal
        y_pred = (self.iso_forest.predict(X) == -1).astype(int)

        log.info("Isolation Forest evaluation:\n" +
                 classification_report(y_true, y_pred, target_names=["normal","anomaly"], zero_division=0))

        joblib.dump(self.iso_forest, IF_PATH)
        joblib.dump(self.scaler, SCALER_PATH)
        log.info(f"  Saved -> {IF_PATH}")
        log.info(f"  Saved -> {SCALER_PATH}")

    # ── Build LSTM sequences ───────────────────────────────────────────────────
    def build_sequences(self, X_scaled: np.ndarray, y: np.ndarray):
        Xs, ys = [], []
        for i in range(len(X_scaled) - self.seq_len):
            Xs.append(X_scaled[i : i + self.seq_len])
            ys.append(y[i + self.seq_len])
        return np.array(Xs, dtype=np.float32), np.array(ys, dtype=np.float32)

    # ── Train LSTM ─────────────────────────────────────────────────────────────
    def train_lstm(self, df: pd.DataFrame):
        log.info("Training LSTM predictor ...")
        X_scaled = self.scaler.transform(df[KPI_FEATURES].values)

        # Target: normalised anomaly_score_0_10
        y = (df["anomaly_score_0_10"].values / 10.0).astype(np.float32)

        Xs, ys = self.build_sequences(X_scaled, y)
        split   = int(0.85 * len(Xs))
        X_tr, X_val = Xs[:split], Xs[split:]
        y_tr, y_val = ys[:split], ys[split:]

        tr_loader  = DataLoader(TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr)),
                                batch_size=256, shuffle=True)
        val_loader = DataLoader(TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val)),
                                batch_size=256)

        self.lstm = LSTMPredictor(n_features=len(KPI_FEATURES)).to(self.device)
        optim     = torch.optim.Adam(self.lstm.parameters(), lr=1e-3)
        criterion = nn.MSELoss()

        best_val, patience, patience_max = float("inf"), 0, 5

        for epoch in range(1, 31):
            # — train —
            self.lstm.train()
            tr_loss = 0
            for xb, yb in tr_loader:
                xb, yb = xb.to(self.device), yb.to(self.device)
                optim.zero_grad()
                pred = self.lstm(xb).squeeze()
                loss = criterion(pred, yb)
                loss.backward()
                optim.step()
                tr_loss += loss.item() * len(xb)
            tr_loss /= len(X_tr)

            # — validate —
            self.lstm.eval()
            val_loss = 0
            with torch.no_grad():
                for xb, yb in val_loader:
                    xb, yb = xb.to(self.device), yb.to(self.device)
                    pred = self.lstm(xb).squeeze()
                    val_loss += criterion(pred, yb).item() * len(xb)
            val_loss /= max(len(X_val), 1)

            log.info(f"  Epoch {epoch:02d} — train_loss={tr_loss:.5f}  val_loss={val_loss:.5f}")

            if val_loss < best_val - 1e-5:
                best_val = val_loss
                torch.save(self.lstm.state_dict(), LSTM_PATH)
                patience = 0
            else:
                patience += 1
                if patience >= patience_max:
                    log.info(f"  Early stopping at epoch {epoch}")
                    break

        log.info(f"  Best val_loss={best_val:.5f} - saved -> {LSTM_PATH}")

    # ── Run full training ──────────────────────────────────────────────────────
    def run(self):
        log.info("=" * 60)
        log.info("BATCH TRAINING - AnomalyDetectorAgent")
        log.info("=" * 60)
        df = self.load_data()
        self.train_isolation_forest(df)
        self.train_lstm(df)
        log.info("Batch training complete [OK]")


# ══════════════════════════════════════════════════════════════════════════════
# LIVE STREAM INFERENCER
# ══════════════════════════════════════════════════════════════════════════════
class StreamInferencer:
    """
    Simulates a real-time KPI feed by replaying the CSV row-by-row.
    For each incoming row:
      1. Rule engine fires immediately
      2. Isolation Forest scores the point
      3. LSTM predicts future anomaly score from a rolling window
      4. Fuses all signals into a final alert event → JSON feed
    """
    def __init__(self, seq_len: int = 16, stream_delay: float = 0.0,
                 cell_filter: str = None, chunk_size: int = 500):
        self.seq_len      = seq_len
        self.stream_delay = stream_delay   # seconds between rows (0 = as fast as possible)
        self.cell_filter  = cell_filter
        self.chunk_size   = chunk_size
        self.device       = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Rolling windows per cell for LSTM
        self.cell_windows: dict[str, list] = {}

        # Signal 4: neighbour correlation
        # key=timestamp, value=set of cell_ids flagged anomalous at that timestamp
        self.ts_anomaly_cells: dict[str, set] = {}
        # cell -> list of neighbour cell_ids (from cell_topology.csv)
        self.neighbour_map: dict[str, list] = self._load_neighbour_map()

        # Stats
        self.stats = {"processed": 0, "anomalies": 0, "alerts_emitted": 0, "critical_escalations": 0}

        self._load_models()

    def _load_models(self):
        log.info("Loading trained models ...")
        if not IF_PATH.exists() or not SCALER_PATH.exists() or not LSTM_PATH.exists():
            raise FileNotFoundError(
                "Models not found. Run with --mode train first."
            )
        self.scaler     = joblib.load(SCALER_PATH)
        self.iso_forest = joblib.load(IF_PATH)

        self.lstm = LSTMPredictor(n_features=len(KPI_FEATURES)).to(self.device)
        self.lstm.load_state_dict(torch.load(LSTM_PATH, map_location=self.device))
        self.lstm.eval()
        log.info("  Models loaded [OK]")

    # ── Load cell topology neighbour map ─────────────────────────────────────
    def _load_neighbour_map(self) -> dict[str, list]:
        topo_path = DATA_DIR / "cell_topology.csv"
        if not topo_path.exists():
            log.warning("cell_topology.csv not found - neighbour correlation disabled")
            return {}
        try:
            df = pd.read_csv(topo_path)
            nb_map = {}
            for _, r in df.iterrows():
                cell = str(r.get("cell_id", ""))
                raw  = str(r.get("neighbor_cells", ""))
                nb_map[cell] = [n.strip() for n in raw.split(";") if n.strip()]
            log.info(f"  Neighbour map loaded: {len(nb_map)} cells")
            return nb_map
        except Exception as e:
            log.warning(f"Could not load neighbour map: {e}")
            return {}

    # ── Signal 4: neighbour correlation ───────────────────────────────────────
    def _neighbour_vote(self, cell_id: str, timestamp: str, is_anomaly: bool) -> bool:
        # Register anomaly state for this cell+timestamp
        bucket = self.ts_anomaly_cells.setdefault(timestamp, set())
        if is_anomaly:
            bucket.add(cell_id)
        # Keep only last 5 timestamp buckets to handle minor out-of-order rows
        if len(self.ts_anomaly_cells) > 5:
            oldest = sorted(self.ts_anomaly_cells.keys())[0]
            del self.ts_anomaly_cells[oldest]
        if not is_anomaly:
            return False
        neighbours = self.neighbour_map.get(cell_id, [])
        if not neighbours:
            return False
        anomalous_neighbours = sum(1 for nb in neighbours if nb in bucket)
        return anomalous_neighbours >= 2

    # ── Isolation Forest score for a single row ────────────────────────────────
    def _if_score(self, row: pd.Series) -> tuple[bool, float]:
        x = self.scaler.transform(row[KPI_FEATURES].values.reshape(1, -1))
        is_anomaly = self.iso_forest.predict(x)[0] == -1
        # decision_function: more negative = more anomalous → invert & normalise
        raw = self.iso_forest.decision_function(x)[0]
        score = float(np.clip((0.1 - raw) * 50, 0, 10))
        return bool(is_anomaly), round(score, 3)

    # ── LSTM: predict future anomaly score ────────────────────────────────────
    def _lstm_predict(self, cell_id: str, x_scaled: np.ndarray) -> float | None:
        window = self.cell_windows.setdefault(cell_id, [])
        window.append(x_scaled.flatten())
        if len(window) > self.seq_len:
            window.pop(0)
        if len(window) < self.seq_len:
            return None   # not enough history yet

        seq = torch.tensor(np.array(window, dtype=np.float32)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            pred = self.lstm(seq).item()
        return round(pred * 10, 3)   # back to [0, 10]

    # ── Fuse rule + IF + LSTM + neighbour into final alert ───────────────────
    def _fuse_signals(self, rule: dict, if_anomaly: bool, if_score: float,
                      lstm_score: float | None, neighbour_escalate: bool = False) -> dict:
        # 3 model votes → 3 anomaly levels
        votes = 0
        if rule["rule_triggered"]:                       votes += 1
        if if_anomaly:                                   votes += 1
        if lstm_score is not None and lstm_score > 5.0: votes += 1

        combined_score = round(
            (rule["rule_score"] * 0.35) +
            (if_score           * 0.40) +
            ((lstm_score or 0)  * 0.25), 3
        )

        # Honest vote-to-label mapping: 3 voters -> 3 anomaly levels
        if votes == 0:
            final_label = "normal"
        elif votes == 1:
            final_label = "low"
        elif votes == 2:
            final_label = "medium"
        else:  # votes == 3, all models agree
            final_label = "high"

        # 4th signal (neighbour correlation) is the ONLY path to critical.
        # Requires: all 3 models agree (high) AND cluster event confirmed.
        if final_label == "high" and neighbour_escalate:
            final_label = "critical"

        return {
            "votes":               votes,
            "combined_score":      combined_score,
            "final_label":         final_label,
            "is_anomaly":          final_label != "normal",
            "neighbour_escalated": final_label == "critical",
        }

    # ── Emit one JSON event to feed file and console ───────────────────────────
    def _emit(self, event: dict):
        line = json.dumps(event, default=str)
        with open(FEED_PATH, "a") as f:
            f.write(line + "\n")

        sev = event["fusion"]["final_label"]
        if sev in ("high", "critical"):
            icon = "[!!]"
        elif sev == "medium":
            icon = "[! ]"
        elif sev == "low":
            icon = "[~ ]"
        else:
            icon = "[OK]"

        log.info(
            f"{icon} [{sev.upper():8s}] {event['cell_id']} | "
            f"score={event['fusion']['combined_score']:.2f} | "
            f"votes={event['fusion']['votes']}/3 nb={event['fusion'].get('neighbour_escalated',False)} | "
            f"breaches={len(event['rule_engine']['breached_kpis'])}"
        )
        self.stats["alerts_emitted"] += 1

    # ── Main stream loop ───────────────────────────────────────────────────────
    def run(self):
        log.info("=" * 60)
        log.info("LIVE STREAM INFERENCE - AnomalyDetectorAgent")
        log.info(f"  Feed output -> {FEED_PATH}")
        log.info("=" * 60)

        # Clear previous feed
        FEED_PATH.write_text("")

        # Stream CSV in chunks
        reader = pd.read_csv(
            TS_KPI_PATH,
            parse_dates=["timestamp"],
            chunksize=self.chunk_size,
        )

        for chunk in reader:
            chunk = chunk.dropna(subset=KPI_FEATURES)
            if self.cell_filter:
                chunk = chunk[chunk["cell_id"] == self.cell_filter]
            if chunk.empty:
                continue

            for _, row in chunk.iterrows():
                self.stats["processed"] += 1

                # 1 — Rule engine
                rule_result = rule_engine(row)

                # 2 — Isolation Forest
                x_scaled = self.scaler.transform(row[KPI_FEATURES].values.reshape(1, -1))
                if_anomaly, if_score = self._if_score(row)

                # 3 — LSTM prediction
                lstm_score = self._lstm_predict(row["cell_id"], x_scaled)

                # 4 — Neighbour correlation (4th signal)
                # A cell is "pre-anomalous" if at least 1 model flagged it
                pre_anomaly = (
                    rule_result["rule_triggered"] or if_anomaly or
                    (lstm_score is not None and lstm_score > 5.0)
                )
                neighbour_escalate = self._neighbour_vote(
                    row["cell_id"], str(row["timestamp"]), pre_anomaly
                )

                # 5 — Fuse all 4 signals
                fusion = self._fuse_signals(
                    rule_result, if_anomaly, if_score, lstm_score, neighbour_escalate
                )

                if fusion["is_anomaly"]:
                    self.stats["anomalies"] += 1
                if fusion.get("neighbour_escalated"):
                    self.stats["critical_escalations"] += 1

                # 5 — Build event (always emit; downstream agents filter by label)
                def _safe(col, default=""):
                    return row[col] if col in row.index and pd.notna(row[col]) else default

                event = {
                    "event_id":   f"EVT-{self.stats['processed']:07d}",
                    "agent":      "AnomalyDetectorAgent",
                    "emitted_at": datetime.utcnow().isoformat() + "Z",
                    "timestamp":  str(row["timestamp"]),
                    "cell_id":    row["cell_id"],
                    "site_id":    _safe("site_id"),
                    "region":     _safe("region"),
                    "vendor":     _safe("vendor"),
                    "nr_band":    _safe("nr_band"),
                    "network_slice": _safe("network_slice"),
                    "kpi_snapshot": {
                        k: round(float(row[k]), 3)
                        for k in KPI_FEATURES
                        if k in row.index and pd.notna(row[k])
                    },
                    "rule_engine":  rule_result,
                    "isolation_forest": {
                        "is_anomaly": if_anomaly,
                        "score_0_10": if_score,
                    },
                    "lstm_predictor": {
                        "predicted_score_0_10": lstm_score,
                        "horizon":              "next_15min",
                        "ready":                lstm_score is not None,
                    },
                    "fusion":              fusion,
                    "neighbour_escalated": fusion.get("neighbour_escalated", False),
                    "ground_truth":        _safe("label", "unknown"),
                }

                # Only emit anomalies (or everything in debug mode)
                if fusion["is_anomaly"]:
                    self._emit(event)

                if self.stream_delay > 0:
                    time.sleep(self.stream_delay)

        log.info("-" * 60)
        log.info(f"Stream complete. Stats: {self.stats}")
        log.info(f"Feed written -> {FEED_PATH}  ({self.stats['alerts_emitted']:,} events)")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(description="QoSBuddy - AnomalyDetectorAgent")
    p.add_argument("--mode",        choices=["train","stream","all"], default="all",
                   help="train: batch training only | stream: inference only | all: both")
    p.add_argument("--sample-frac", type=float, default=0.15,
                   help="Fraction of KPI CSV to use for training (default 0.15)")
    p.add_argument("--seq-len",     type=int,   default=16,
                   help="LSTM sequence length in timesteps (default 16 = 4h @ 15min)")
    p.add_argument("--stream-delay",type=float, default=0.0,
                   help="Seconds to wait between streamed rows (default 0 = max speed)")
    p.add_argument("--cell",        type=str,   default=None,
                   help="Filter stream to a specific cell_id (optional)")
    p.add_argument("--chunk-size",  type=int,   default=500,
                   help="CSV chunk size for streaming (default 500)")
    return p.parse_args()


def main():
    args = parse_args()
    log.info("QoSBuddy AnomalyDetectorAgent starting")
    log.info(f"  mode={args.mode} | seq_len={args.seq_len} | sample_frac={args.sample_frac}")

    if args.mode in ("train", "all"):
        trainer = BatchTrainer(seq_len=args.seq_len, sample_frac=args.sample_frac)
        trainer.run()

    if args.mode in ("stream", "all"):
        inferencer = StreamInferencer(
            seq_len=args.seq_len,
            stream_delay=args.stream_delay,
            cell_filter=args.cell,
            chunk_size=args.chunk_size,
        )
        inferencer.run()


if __name__ == "__main__":
    main()