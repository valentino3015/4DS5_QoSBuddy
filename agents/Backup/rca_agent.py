"""
QoSBuddy -- RCAAgent (Agent 2)
================================
Consumes anomaly events from Agent 1's anomaly_feed.jsonl and performs
Root Cause Analysis on each one.

Pipeline:
  1. BATCH TRAINING   -- trains an RF classifier + similarity index on labeled_incidents.csv
  2. BATCH CATCH-UP   -- processes all existing events in anomaly_feed.jsonl
  3. LIVE TAIL        -- watches anomaly_feed.jsonl for new lines, diagnoses in real-time

Per event output:
  - Primary root cause + confidence score
  - Ranked list of all likely causes with individual probabilities
  - Recommended solution mapped to the top cause
  - Top-3 similar past incidents (k-NN on KPI snapshot)

Output feed: data/output/rca_feed.jsonl  (consumed by Agent 3 -- Remediation)

Usage:
    python agents/rca_agent.py --mode train          # batch train only
    python agents/rca_agent.py --mode run            # catch-up + live tail (loads saved models)
    python agents/rca_agent.py --mode all            # train then catch-up + live tail (default)
    python agents/rca_agent.py --mode all --tail-interval 2.0   # poll every 2 seconds
"""

import os, sys, json, time, logging, argparse, warnings
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report
from sklearn.neighbors import NearestNeighbors
import joblib

warnings.filterwarnings("ignore")

# ─── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent
DATA_DIR   = ROOT / "data"
MODEL_DIR  = ROOT / "models"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR    = ROOT / "logs"

for d in [MODEL_DIR, OUTPUT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

INCIDENTS_PATH = DATA_DIR / "labeled_incidents.csv"
ANOMALY_FEED   = OUTPUT_DIR / "anomaly_feed.jsonl"
RCA_FEED       = OUTPUT_DIR / "rca_feed.jsonl"

RF_PATH        = MODEL_DIR / "rca_rf_classifier.joblib"
RCA_SCALER_PATH= MODEL_DIR / "rca_scaler.joblib"
LABEL_ENC_PATH = MODEL_DIR / "rca_label_encoder.joblib"
KNN_PATH       = MODEL_DIR / "rca_knn_index.joblib"
INCIDENT_DB_PATH = MODEL_DIR / "rca_incident_db.joblib"

# ─── Logging ───────────────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_stream_handler = logging.StreamHandler(sys.stdout)
_file_handler   = logging.FileHandler(LOG_DIR / "rca_agent.log", encoding="utf-8")
_formatter      = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
_stream_handler.setFormatter(_formatter)
_file_handler.setFormatter(_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _file_handler])
log = logging.getLogger("RCAAgent")

# ─── KPI features ─────────────────────────────────────────────────────────────
# KPI_FEATURES_INCIDENTS: columns actually present in labeled_incidents.csv
# (DL-only snapshot — UL cols and active_users were not written to that file).
# KPI_FEATURES_ALL: full set from Agent 1's time-series stream (used at inference
# time when the kpi_snapshot in the anomaly event may have more columns).
# The agent always intersects against whatever columns are available at runtime.
KPI_FEATURES_INCIDENTS = [
    "RSRP_dBm", "SINR_dB", "PRB_util_DL_pct",
    "CQI", "BLER_DL_pct",
    "throughput_DL_Mbps", "latency_ms",
    "call_drop_rate_pct", "HO_success_rate_pct", "MOS", "MIMO_rank",
]

KPI_FEATURES_ALL = [
    "RSRP_dBm", "SINR_dB", "PRB_util_DL_pct", "PRB_util_UL_pct",
    "CQI", "BLER_DL_pct", "BLER_UL_pct",
    "throughput_DL_Mbps", "throughput_UL_Mbps", "latency_ms",
    "call_drop_rate_pct", "HO_success_rate_pct", "MOS", "MIMO_rank",
    "active_users",
]

# Runtime feature list — overwritten in RCATrainer.load_incidents()
KPI_FEATURES = KPI_FEATURES_INCIDENTS

# ─── Domain knowledge: cause -> solution mapping ───────────────────────────────
CAUSE_TO_SOLUTION = {
    "Poor RSRP coverage":              "Mechanical/electrical tilt optimization + coverage gap analysis",
    "High interference (SINR<0)":      "Interference matrix audit + power control optimization",
    "HO failure":                      "A3 offset tuning + TTT adjustment + neighbor list cleanup",
    "Overshooting cell":               "Increase electrical downtilt + reduce Tx power",
    "Missing neighbor":                "ANR (Automatic Neighbor Relation) audit + manual neighbor add",
    "Bad tilt/azimuth":                "Physical antenna survey + mechanical tilt correction",
    "SRVCC failure":                   "VoNR/SRVCC parameter audit + IMS configuration check",
    "UL/DL interference":              "UL power control optimization + interference cancellation",
    "High BLER":                       "HARQ parameter tuning + modulation scheme review",
    "Wrong codec":                     "Force adaptive AMR-WB + codec negotiation fix",
    "PRB congestion":                  "Load balancing + carrier aggregation activation",
    "Poor indoor RSRP":                "Deploy indoor small cell / IBS + 700 MHz layer add",
    "Low SINR":                        "Antenna tilt optimization + frequency reuse plan review",
    "PRB saturation":                  "Sector split 3->6 + Massive MIMO upgrade",
    "Poor CQI":                        "CQI reporting parameter tuning + beamforming optimization",
    "Low MIMO rank":                   "Antenna correlation check + 4x4 MIMO reconfiguration",
    "Insufficient bandwidth":          "Bandwidth upgrade to 100 MHz NR + CA activation",
    "Transport congestion":            "Transport link upgrade + QoS remarking",
    "Bad IP routing":                  "BGP/OSPF route optimization + MTU audit",
    "Bufferbloat":                     "AQM (Active Queue Management) + buffer size tuning",
    "UPF/AMF issue":                   "UPF instance restart + AMF load balancing",
    "RLC retransmissions":             "RLC window size tuning + ARQ parameter review",
    "PDU session drop":                "PDU session timer tuning + UPF path check",
    "Inter-freq HO failure":           "Inter-frequency HO threshold tuning + B2 event optimization",
    "Coverage hole":                   "Drive test + small cell / repeater deployment",
    "Missing neighbor relation":       "ANR audit + X2/Xn interface check",
    "PCI collision":                   "PCI planning audit + collision/confusion resolution",
    "X2/Xn failure":                   "X2/Xn interface reset + transport path check",
    "PRB utilization >85%":            "Load balancing + CA activation + sector split",
    "CSSR drop in busy hour":          "Admission control tuning + capacity expansion",
    "Throughput collapse busy hour":   "Massive MIMO + additional carrier deployment",
    "Massive MIMO config issue":       "Beam management parameter audit + codebook reconfiguration",
}

# ─── RCA tag groupings for secondary classification ────────────────────────────
CAUSE_TO_TAG = {
    "Poor RSRP coverage":              ["coverage", "signal"],
    "High interference (SINR<0)":      ["interference", "signal"],
    "HO failure":                      ["mobility", "handover"],
    "Overshooting cell":               ["coverage", "interference"],
    "Missing neighbor":                ["mobility", "configuration"],
    "Bad tilt/azimuth":                ["coverage", "configuration"],
    "SRVCC failure":                   ["voice", "core"],
    "UL/DL interference":              ["interference", "signal"],
    "High BLER":                       ["signal", "configuration"],
    "Wrong codec":                     ["voice", "configuration"],
    "PRB congestion":                  ["capacity", "traffic"],
    "Poor indoor RSRP":                ["coverage", "signal"],
    "Low SINR":                        ["interference", "signal"],
    "PRB saturation":                  ["capacity", "traffic"],
    "Poor CQI":                        ["signal", "configuration"],
    "Low MIMO rank":                   ["configuration", "signal"],
    "Insufficient bandwidth":          ["capacity", "configuration"],
    "Transport congestion":            ["transport", "capacity"],
    "Bad IP routing":                  ["transport", "core"],
    "Bufferbloat":                     ["transport", "configuration"],
    "UPF/AMF issue":                   ["core", "configuration"],
    "RLC retransmissions":             ["signal", "transport"],
    "PDU session drop":                ["core", "mobility"],
    "Inter-freq HO failure":           ["mobility", "handover"],
    "Coverage hole":                   ["coverage", "signal"],
    "Missing neighbor relation":       ["mobility", "configuration"],
    "PCI collision":                   ["configuration", "interference"],
    "X2/Xn failure":                   ["transport", "core"],
    "PRB utilization >85%":            ["capacity", "traffic"],
    "CSSR drop in busy hour":          ["capacity", "traffic"],
    "Throughput collapse busy hour":   ["capacity", "traffic"],
    "Massive MIMO config issue":       ["configuration", "signal"],
}


# ══════════════════════════════════════════════════════════════════════════════
# BATCH TRAINER
# ══════════════════════════════════════════════════════════════════════════════
class RCATrainer:
    """
    Trains:
      1. RandomForestClassifier  -- predicts root_cause from KPI snapshot
      2. NearestNeighbors index  -- finds similar past incidents by KPI distance
    Both trained on labeled_incidents.csv produced by the data generator.
    """
    def __init__(self):
        self.scaler   = StandardScaler()
        self.le       = LabelEncoder()
        self.rf       = RandomForestClassifier(
            n_estimators=300, max_depth=20, min_samples_leaf=2,
            class_weight="balanced", random_state=42, n_jobs=-1,
        )
        self.knn      = NearestNeighbors(n_neighbors=5, metric="euclidean", n_jobs=-1)
        self.incident_db: list[dict] = []

    # ── Load labeled incidents ─────────────────────────────────────────────────
    def load_incidents(self) -> pd.DataFrame:
        global KPI_FEATURES
        log.info(f"Loading labeled incidents from {INCIDENTS_PATH} ...")
        df = pd.read_csv(INCIDENTS_PATH)

        # Auto-detect which KPI columns are actually present in this file
        available = [c for c in KPI_FEATURES_ALL if c in df.columns]
        KPI_FEATURES = available
        log.info(f"  Using {len(KPI_FEATURES)} KPI features: {KPI_FEATURES}")

        df = df.dropna(subset=KPI_FEATURES + ["root_cause"])
        log.info(f"  {len(df):,} incidents loaded | {df['root_cause'].nunique()} unique causes")
        return df

    # ── Train RF classifier ────────────────────────────────────────────────────
    def train_classifier(self, df: pd.DataFrame):
        log.info("Training RandomForest RCA classifier ...")
        X = self.scaler.fit_transform(df[KPI_FEATURES].values)
        y = self.le.fit_transform(df["root_cause"].values)

        # Simple train/val split (80/20)
        split = int(0.8 * len(X))
        X_tr, X_val = X[:split], X[split:]
        y_tr, y_val = y[:split], y[split:]

        self.rf.fit(X_tr, y_tr)
        y_pred = self.rf.predict(X_val)

        report = classification_report(
            y_val, y_pred,
            target_names=self.le.classes_,
            zero_division=0,
        )
        log.info("RF classifier evaluation:\n" + report)

        # Feature importance summary
        importances = sorted(
            zip(KPI_FEATURES, self.rf.feature_importances_),
            key=lambda x: x[1], reverse=True,
        )
        log.info("Top-5 most important KPIs for RCA:")
        for feat, imp in importances[:5]:
            log.info(f"  {feat:<30s} {imp:.4f}")

        joblib.dump(self.rf,     RF_PATH)
        joblib.dump(self.scaler, RCA_SCALER_PATH)
        joblib.dump(self.le,     LABEL_ENC_PATH)
        joblib.dump(KPI_FEATURES, MODEL_DIR / "rca_kpi_features.joblib")
        log.info(f"  Classifier saved -> {RF_PATH}")

    # ── Build k-NN similarity index ────────────────────────────────────────────
    def build_knn_index(self, df: pd.DataFrame):
        log.info("Building k-NN similarity index ...")
        X = self.scaler.transform(df[KPI_FEATURES].values)
        self.knn.fit(X)

        # Build lightweight incident DB for retrieval
        self.incident_db = []
        for _, row in df.iterrows():
            self.incident_db.append({
                "incident_id":    str(row.get("incident_id", "")),
                "root_cause":     str(row.get("root_cause", "")),
                "issue_type":     str(row.get("issue_type", "")),
                "severity":       str(row.get("severity", "")),
                "resolution_hours": row.get("resolution_hours", None),
                "recommended_solution": str(row.get("recommended_solution", "")),
                "kpi_snapshot": {
                    k: round(float(row[k]), 3)
                    for k in KPI_FEATURES if pd.notna(row.get(k, np.nan))
                },
            })

        joblib.dump(self.knn,          KNN_PATH)
        joblib.dump(self.incident_db,  INCIDENT_DB_PATH)
        log.info(f"  k-NN index built on {len(self.incident_db):,} incidents -> {KNN_PATH}")

    # ── Run full training ──────────────────────────────────────────────────────
    def run(self):
        log.info("=" * 60)
        log.info("BATCH TRAINING - RCAAgent")
        log.info("=" * 60)
        df = self.load_incidents()
        self.train_classifier(df)
        self.build_knn_index(df)
        log.info("RCA batch training complete [OK]")


# ══════════════════════════════════════════════════════════════════════════════
# RCA ENGINE  (stateless, used by the inferencer)
# ══════════════════════════════════════════════════════════════════════════════
class RCAEngine:
    """
    Loads trained models and performs RCA on a single anomaly event dict.
    Returns a structured diagnosis dict ready to be serialised to JSON.
    """
    def __init__(self):
        global KPI_FEATURES
        log.info("Loading RCA models ...")
        required = [RF_PATH, RCA_SCALER_PATH, LABEL_ENC_PATH, KNN_PATH, INCIDENT_DB_PATH]
        if not all(p.exists() for p in required):
            raise FileNotFoundError("RCA models not found. Run with --mode train first.")

        self.rf           = joblib.load(RF_PATH)
        self.scaler       = joblib.load(RCA_SCALER_PATH)
        self.le           = joblib.load(LABEL_ENC_PATH)
        self.knn          = joblib.load(KNN_PATH)
        self.incident_db  = joblib.load(INCIDENT_DB_PATH)

        # Restore the exact feature list used during training
        feat_path = MODEL_DIR / "rca_kpi_features.joblib"
        if feat_path.exists():
            KPI_FEATURES = joblib.load(feat_path)
            log.info(f"  Restored {len(KPI_FEATURES)} training features from saved model")
        log.info("  RCA models loaded [OK]")

    # ── Extract KPI vector from anomaly event ─────────────────────────────────
    def _extract_kpi_vector(self, event: dict) -> np.ndarray | None:
        snap = event.get("kpi_snapshot", {})
        # Use only the features the model was trained on (saved alongside models)
        vec = []
        for feat in KPI_FEATURES:
            v = snap.get(feat, None)
            vec.append(float(v) if v is not None else np.nan)
        arr = np.array(vec, dtype=np.float64)
        if np.isnan(arr).all():
            return None
        # Impute remaining NaNs with 0 (scaler was fit on complete rows)
        arr = np.where(np.isnan(arr), 0.0, arr)
        return arr

    # ── RF: ranked cause probabilities ────────────────────────────────────────
    def _classify(self, x_raw: np.ndarray) -> list[dict]:
        x_scaled = self.scaler.transform(x_raw.reshape(1, -1))
        proba    = self.rf.predict_proba(x_scaled)[0]
        classes  = self.le.classes_

        ranked = sorted(
            [{"cause": str(c), "probability": round(float(p), 4)} for c, p in zip(classes, proba)],
            key=lambda d: d["probability"],
            reverse=True,
        )
        return ranked   # full ranked list

    # ── k-NN: similar past incidents ─────────────────────────────────────────
    def _find_similar(self, x_raw: np.ndarray, top_k: int = 3) -> list[dict]:
        x_scaled  = self.scaler.transform(x_raw.reshape(1, -1))
        distances, indices = self.knn.kneighbors(x_scaled, n_neighbors=top_k)

        # Compute a reference scale from the retrieved distances so the similarity
        # percentages spread nicely.  Using exponential decay: sim = exp(-d / scale).
        dists = distances[0]
        ref_scale = max(float(np.mean(dists)), 0.5)  # avoid div-by-zero

        similar = []
        for dist, idx in zip(dists, indices[0]):
            inc = self.incident_db[idx]
            sim_pct = round(float(np.clip(np.exp(-dist / ref_scale) * 100, 1, 99)), 1)
            similar.append({
                "incident_id":        inc["incident_id"],
                "root_cause":         inc["root_cause"],
                "issue_type":         inc["issue_type"],
                "severity":           inc["severity"],
                "resolution_hours":   inc["resolution_hours"],
                "recommended_solution": inc["recommended_solution"],
                "kpi_distance":       round(float(dist), 4),
                "similarity_pct":     sim_pct,
            })
        return similar

    # ── Rule-based cause override (high-confidence heuristics) ────────────────
    def _rule_override(self, event: dict) -> str | None:
        """
        If a single KPI is catastrophically out of range, override the RF
        prediction with a near-certain cause. Mirrors domain knowledge from
        the radio issue document.
        """
        snap = event.get("kpi_snapshot", {})
        rule_breaches = event.get("rule_engine", {}).get("breached_kpis", [])
        breached_kpis = {b["kpi"] for b in rule_breaches}

        rsrp  = snap.get("RSRP_dBm", 0)
        sinr  = snap.get("SINR_dB",  99)
        prb   = snap.get("PRB_util_DL_pct", 0)
        lat   = snap.get("latency_ms", 0)
        ho_sr = snap.get("HO_success_rate_pct", 100)
        cdr   = snap.get("call_drop_rate_pct", 0)

        # Prioritised override rules (most specific first)
        if rsrp < -115 and sinr < 0:
            return "Poor RSRP coverage"
        if sinr < -3 and "SINR_dB" in breached_kpis and prb < 70:
            return "High interference (SINR<0)"
        if ho_sr < 70 and cdr > 4:
            return "HO failure"
        if prb > 90 and lat > 60:
            return "PRB saturation"
        if lat > 100 and prb < 70:
            return "Transport congestion"
        if ho_sr < 75 and sinr > 5:
            return "Missing neighbor relation"
        return None   # no override, trust RF

    # ── Main diagnosis method ─────────────────────────────────────────────────
    def diagnose(self, event: dict) -> dict:
        x_raw = self._extract_kpi_vector(event)

        if x_raw is None:
            return {
                "status": "error",
                "reason": "No KPI data in event",
            }

        # 1 — RF ranked causes
        ranked_causes = self._classify(x_raw)
        top_cause     = ranked_causes[0]["cause"]
        top_prob      = ranked_causes[0]["probability"]

        # 2 — Rule override
        override = self._rule_override(event)
        if override and override != top_cause:
            # Inject override at position 0, boost confidence
            override_entry = {"cause": override, "probability": round(min(1.0, top_prob + 0.15), 4)}
            ranked_causes  = [override_entry] + [r for r in ranked_causes if r["cause"] != override]
            top_cause      = override
            top_prob       = override_entry["probability"]
            used_override  = True
        else:
            used_override  = False

        # 3 — Solution + tags
        solution = CAUSE_TO_SOLUTION.get(top_cause, "Manual investigation required")
        tags     = CAUSE_TO_TAG.get(top_cause, ["unknown"])

        # 4 — Similar incidents
        similar = self._find_similar(x_raw, top_k=3)

        # 5 — Overall RCA confidence
        confidence = round(top_prob * 100, 1)

        # 6 — Neighbour escalation bonus
        # If Agent 1 flagged this as a cluster event (neighbour_escalated=True),
        # it narrows the cause space to network-wide issues (coverage, interference,
        # transport) and boosts our confidence since isolated config errors are
        # unlikely to affect multiple cells simultaneously.
        neighbour_escalated = event.get("neighbour_escalated", False)
        cluster_tags = []
        if neighbour_escalated:
            confidence = round(min(99.0, confidence + 12.0), 1)
            cluster_tags = ["cluster_event", "multi_cell"]
            # If the top cause is a single-cell config issue, demote it
            single_cell_causes = {"PCI collision", "Bad tilt/azimuth", "SRVCC failure",
                                   "Wrong codec", "Massive MIMO config issue"}
            if top_cause in single_cell_causes and len(ranked_causes) > 1:
                # Swap in the next most likely non-single-cell cause
                for alt in ranked_causes[1:]:
                    if alt["cause"] not in single_cell_causes:
                        top_cause = alt["cause"]
                        tags      = CAUSE_TO_TAG.get(top_cause, tags)
                        solution  = CAUSE_TO_SOLUTION.get(top_cause, solution)
                        break

        return {
            "status":              "ok",
            "primary_cause":       top_cause,
            "confidence_pct":      confidence,
            "rca_tags":            tags + cluster_tags,
            "used_rule_override":  used_override,
            "neighbour_escalated": neighbour_escalated,
            "ranked_causes":       ranked_causes[:8],
            "recommended_solution": solution,
            "similar_incidents":   similar,
        }


# ══════════════════════════════════════════════════════════════════════════════
# STREAM INFERENCER  (batch catch-up + live tail)
# ══════════════════════════════════════════════════════════════════════════════
class RCAInferencer:
    """
    Reads anomaly_feed.jsonl in two phases:
      Phase 1 -- CATCH-UP: reads all lines already in the file.
      Phase 2 -- LIVE TAIL: polls for new lines appended by Agent 1,
                            processes them as they arrive.
    """
    def __init__(self, tail_interval: float = 1.0, max_tail_idle: int = 0):
        self.tail_interval  = tail_interval   # seconds between polls
        self.max_tail_idle  = max_tail_idle   # 0 = run forever; N = stop after N idle polls
        self.engine         = RCAEngine()
        self.stats          = {"processed": 0, "diagnosed": 0, "errors": 0}

    # ── Process one anomaly event line ────────────────────────────────────────
    def _process_line(self, line: str, phase: str):
        line = line.strip()
        if not line:
            return

        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            log.warning(f"  Skipping malformed JSON line: {e}")
            self.stats["errors"] += 1
            return

        self.stats["processed"] += 1

        # Run RCA
        diagnosis = self.engine.diagnose(event)

        # Build output event
        rca_event = {
            "rca_event_id":   f"RCA-{self.stats['processed']:07d}",
            "agent":          "RCAAgent",
            "phase":          phase,
            "processed_at":   datetime.utcnow().isoformat() + "Z",
            # Pass-through context from Agent 1
            "source_event_id":   event.get("event_id", ""),
            "timestamp":         event.get("timestamp", ""),
            "cell_id":           event.get("cell_id", ""),
            "site_id":           event.get("site_id", ""),
            "region":            event.get("region", ""),
            "vendor":            event.get("vendor", ""),
            "nr_band":           event.get("nr_band", ""),
            "network_slice":     event.get("network_slice", ""),
            "anomaly_severity":  event.get("fusion", {}).get("final_label", ""),
            "anomaly_score":     event.get("fusion", {}).get("combined_score", None),
            "kpi_snapshot":      event.get("kpi_snapshot", {}),
            "rule_engine":       event.get("rule_engine", {}),
            # RCA output
            "rca":               diagnosis,
            # Ground truth (for evaluation, from Agent 1 label)
            "ground_truth_label": event.get("ground_truth", ""),
        }

        # Write to feed
        with open(RCA_FEED, "a", encoding="utf-8") as f:
            f.write(json.dumps(rca_event, default=str) + "\n")

        self.stats["diagnosed"] += 1

        # Console log
        sev = rca_event["anomaly_severity"].upper()
        if diagnosis["status"] == "ok":
            conf   = diagnosis["confidence_pct"]
            cause  = diagnosis["primary_cause"]
            n_sim  = len(diagnosis["similar_incidents"])
            tag    = "[!!]" if sev in ("HIGH","CRITICAL") else "[~ ]"
            log.info(
                f"{tag} [{sev:<8s}] {rca_event['cell_id']:<14s} | "
                f"cause='{cause}' | conf={conf:.1f}% | "
                f"similar={n_sim} past incidents"
            )
        else:
            log.warning(f"  [ERR] RCA failed for {rca_event['cell_id']}: {diagnosis.get('reason')}")

    # ── Phase 1: batch catch-up ───────────────────────────────────────────────
    def _catch_up(self) -> int:
        """Reads all existing lines in anomaly_feed.jsonl. Returns file position."""
        if not ANOMALY_FEED.exists():
            log.warning(f"Anomaly feed not found at {ANOMALY_FEED}. Waiting for Agent 1 ...")
            return 0

        log.info("=" * 60)
        log.info("PHASE 1 - CATCH-UP: processing existing anomaly events ...")
        log.info("=" * 60)

        with open(ANOMALY_FEED, "r", encoding="utf-8") as f:
            lines = f.readlines()
            pos   = f.tell()

        log.info(f"  Found {len(lines):,} existing events to process ...")
        for line in lines:
            self._process_line(line, phase="catch-up")

        log.info(f"  Catch-up complete. Diagnosed {self.stats['diagnosed']:,} events.")
        return pos

    # ── Phase 2: live tail ────────────────────────────────────────────────────
    def _live_tail(self, start_pos: int):
        log.info("=" * 60)
        log.info("PHASE 2 - LIVE TAIL: watching for new anomaly events ...")
        log.info(f"  Polling every {self.tail_interval}s | Ctrl+C to stop")
        log.info("=" * 60)

        pos       = start_pos
        idle_count = 0

        while True:
            try:
                if not ANOMALY_FEED.exists():
                    time.sleep(self.tail_interval)
                    continue

                with open(ANOMALY_FEED, "r", encoding="utf-8") as f:
                    f.seek(pos)
                    new_lines = f.readlines()
                    pos = f.tell()

                if new_lines:
                    idle_count = 0
                    for line in new_lines:
                        self._process_line(line, phase="live")
                else:
                    idle_count += 1
                    if self.max_tail_idle > 0 and idle_count >= self.max_tail_idle:
                        log.info(f"  No new events for {idle_count} polls. Stopping tail.")
                        break

                time.sleep(self.tail_interval)

            except KeyboardInterrupt:
                log.info("  Tail interrupted by user.")
                break

    # ── Main run ──────────────────────────────────────────────────────────────
    def run(self):
        # Clear previous feed
        RCA_FEED.write_text("", encoding="utf-8")
        log.info(f"RCA feed -> {RCA_FEED}")

        pos = self._catch_up()
        self._live_tail(start_pos=pos)

        log.info("-" * 60)
        log.info(f"RCAAgent finished. Stats: {self.stats}")
        log.info(f"RCA feed written -> {RCA_FEED}  ({self.stats['diagnosed']:,} events)")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(description="QoSBuddy - RCAAgent (Agent 2)")
    p.add_argument("--mode", choices=["train", "run", "all"], default="all",
                   help="train: batch train only | run: catch-up + tail | all: both (default)")
    p.add_argument("--tail-interval", type=float, default=1.0,
                   help="Seconds between live tail polls (default 1.0)")
    p.add_argument("--max-tail-idle", type=int, default=0,
                   help="Stop tail after N consecutive idle polls (0 = run forever, default 0)")
    return p.parse_args()


def main():
    args = parse_args()
    log.info("QoSBuddy RCAAgent starting")
    log.info(f"  mode={args.mode} | tail_interval={args.tail_interval}s")

    if args.mode in ("train", "all"):
        trainer = RCATrainer()
        trainer.run()

    if args.mode in ("run", "all"):
        inferencer = RCAInferencer(
            tail_interval=args.tail_interval,
            max_tail_idle=args.max_tail_idle,
        )
        inferencer.run()


if __name__ == "__main__":
    main()