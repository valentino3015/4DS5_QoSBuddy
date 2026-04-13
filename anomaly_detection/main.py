"""
main.py — QoSBuddy Anomaly Detection Pipeline
Clean, concise terminal output. Models trained before inference.
"""

import sys, warnings, json, time
import numpy as np
import pandas as pd
from datetime import datetime
from collections import deque
from pathlib import Path
import logging

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.WARNING)   # suppress INFO spam
logger = logging.getLogger(__name__)

from stream_window import QoSStream, SlidingWindow
from feature_eng import QoSFeatureEngineer
from LSTMAECNNTRAN import MultiModalScorer, TemporalCNN

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
CONFIG = {
    "csv_path":             "data_treatement/qosbuddy_dataset_enhanced.csv",
    "knowledge_base_path":  "knowledge_base.json",
    "window_size":          10,
    "step":                 2,
    "sequence_length":      5,
    "delay":                0.0,          # 0 = fast / set to 2.0 for real-time feel
    "evaluation_mode":      True,
    "max_sequences":        None,         # None = run all
    "results_dir":          "anomaly_results",
    "train_epochs":         40,
}

# ─────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────

def build_training_data(csv_path: str, window_size: int, step: int,
                        seq_len: int, engineer: QoSFeatureEngineer):
    """Build (sequences, labels) from the full CSV for model training."""
    df = pd.read_csv(csv_path)
    records = df.to_dict('records')

    windows, labels = [], []
    buf = deque(maxlen=window_size)
    feat_buf = deque(maxlen=seq_len)

    for i, row in enumerate(records):
        row['timestamp'] = str(row.get('timestamp', i))
        buf.append(row)
        if len(buf) == window_size and (i + 1) % step == 0:
            window = list(buf)
            feats  = engineer.transform(window)
            feat_vec = [feats[k] for k in sorted(feats.keys())]
            feat_buf.append(feat_vec)
            if len(feat_buf) == seq_len:
                seq = np.array(feat_buf)
                win_df = pd.DataFrame(window)
                # Ground truth: any of the critical thresholds exceeded
                is_anom = int(
                    win_df['sinr'].mean() < -5 or
                    win_df['rsrp'].mean() < -115 or
                    win_df['throughput_dl'].mean() < 5 or
                    win_df['latency_ms'].mean() > 300
                )
                windows.append(seq)
                labels.append(is_anom)

    return np.array(windows, dtype=np.float32), np.array(labels, dtype=np.float32)


def get_ground_truth(window_data):
    df = pd.DataFrame(window_data)
    return (
        df['sinr'].mean() < -5 or
        df['rsrp'].mean() < -115 or
        df['throughput_dl'].mean() < 5 or
        df['latency_ms'].mean() > 300
    )


def severity_icon(sev):
    return {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(sev, '⚪')


def compute_metrics(preds, truths, scores):
    from sklearn.metrics import precision_score, recall_score, f1_score, accuracy_score, roc_auc_score
    y_t = np.array(truths, dtype=int)
    y_p = np.array(preds,  dtype=int)
    y_s = np.array(scores)
    m = {
        'accuracy':  round(float(accuracy_score(y_t, y_p)), 4),
        'precision': round(float(precision_score(y_t, y_p, zero_division=0)), 4),
        'recall':    round(float(recall_score(y_t, y_p, zero_division=0)), 4),
        'f1':        round(float(f1_score(y_t, y_p, zero_division=0)), 4),
    }
    if len(np.unique(y_t)) > 1:
        m['roc_auc'] = round(float(roc_auc_score(y_t, y_s)), 4)
    tp = int(((y_t == 1) & (y_p == 1)).sum())
    fp = int(((y_t == 0) & (y_p == 1)).sum())
    fn = int(((y_t == 1) & (y_p == 0)).sum())
    tn = int(((y_t == 0) & (y_p == 0)).sum())
    m.update({'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn})
    return m


# ─────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────

def run():
    csv_path  = CONFIG["csv_path"]
    kb_path   = CONFIG["knowledge_base_path"]
    seq_len   = CONFIG["sequence_length"]
    w_size    = CONFIG["window_size"]
    step      = CONFIG["step"]
    results_d = CONFIG["results_dir"]
    Path(results_d).mkdir(exist_ok=True)

    engineer = QoSFeatureEngineer()

    # ── detect feature dim ──
    sample_df  = pd.read_csv(csv_path).head(w_size)
    sample_f   = engineer.transform(sample_df.to_dict('records'))
    input_dim  = len(sample_f)

    print("=" * 60)
    print("  QoSBuddy — Anomaly Detection Pipeline")
    print("=" * 60)
    print(f"  Dataset  : {csv_path}")
    print(f"  Features : {input_dim}  |  Window: {w_size}  |  Seq: {seq_len}")
    print("=" * 60)

    # ── train ──
    print("\n[1/3] Building training sequences …")
    X_train, y_train = build_training_data(csv_path, w_size, step, seq_len, engineer)
    n_anom = int(y_train.sum())
    print(f"      {len(X_train)} sequences  ({n_anom} anomalies / {len(X_train)-n_anom} normal)")

    scorer = MultiModalScorer(kb_path, input_dim=input_dim, seq_length=seq_len, device='cpu')

    print("\n[2/3] Training models …")
    scorer.train_models(X_train, y_train, epochs=CONFIG["train_epochs"], verbose=True)

    # ── inference ──
    print("[3/3] Running inference on stream …\n")
    print(f"  {'#':>5}  {'Score':>6}  {'Sev':<8}  {'Type':<22}  {'GT'}")
    print("  " + "─" * 55)

    stream  = QoSStream(csv_path, delay=CONFIG["delay"])
    window  = SlidingWindow(w_size, step)
    feat_buf = deque(maxlen=seq_len)

    results, anomalies = [], []
    preds, truths, scores_list, inf_times = [], [], [], []
    seq_n = 0
    max_seq = CONFIG["max_sequences"]

    for event in stream.stream():
        window.add(event)
        if not window.is_ready():
            continue

        window_data = window.get_window()
        feats = engineer.transform(window_data)
        feat_vec = [feats[k] for k in sorted(feats.keys())]
        feat_buf.append(feat_vec)

        if len(feat_buf) < seq_len:
            continue

        seq_n += 1
        seq = np.array(feat_buf, dtype=np.float32)
        gt  = get_ground_truth(window_data)

        t0 = time.perf_counter()
        result = scorer.score(seq)
        inf_ms = (time.perf_counter() - t0) * 1000

        preds.append(int(result.is_anomaly))
        truths.append(int(gt))
        scores_list.append(result.final_score)
        inf_times.append(inf_ms)

        gt_tag = "ANOM" if gt else "norm"
        if result.is_anomaly:
            sev_str = f"{severity_icon(result.severity)} {result.severity}"
        else:
            sev_str = "  ok"
        deg_str = (result.degradation_type or '')[:20]
        print(f"  {seq_n:>5}  {result.final_score:>6.3f}  {sev_str:<14}  {deg_str:<22}  {gt_tag}")

        if result.is_anomaly:
            entry = {
                "seq": seq_n,
                "score": result.final_score,
                "severity": result.severity,
                "type": result.degradation_type,
                "causes": result.causes,
                "solutions": result.solutions,
                "metrics": {k: round(v, 2) for k, v in {
                    "sinr": feats.get("mean_sinr"),
                    "rsrp": feats.get("mean_rsrp"),
                    "throughput": feats.get("mean_throughput_dl"),
                    "latency": feats.get("mean_latency"),
                    "mos": feats.get("mean_mos"),
                }.items()},
                "timestamp": datetime.now().isoformat(),
            }
            anomalies.append(entry)

        if max_seq and seq_n >= max_seq:
            break

    # ── results ──
    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"  Sequences processed : {seq_n}")
    print(f"  Anomalies detected  : {len(anomalies)}  ({len(anomalies)/seq_n*100:.1f}%)")
    print(f"  Avg inference time  : {np.mean(inf_times):.1f} ms")

    if CONFIG["evaluation_mode"] and len(truths) > 0:
        m = compute_metrics(preds, truths, scores_list)
        print(f"\n  Evaluation (vs ground truth):")
        print(f"    Accuracy  {m['accuracy']:.4f}   F1       {m['f1']:.4f}")
        print(f"    Precision {m['precision']:.4f}   Recall   {m['recall']:.4f}")
        if 'roc_auc' in m:
            print(f"    ROC-AUC   {m['roc_auc']:.4f}")
        print(f"    TP={m['tp']}  FP={m['fp']}  FN={m['fn']}  TN={m['tn']}")

        grade = ("✅ Excellent" if m['f1'] >= 0.85
                 else "👍 Good" if m['f1'] >= 0.70
                 else "⚠️  Needs tuning")
        print(f"\n  Assessment: {grade}")

    # ── save ──
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_file = f"{results_d}/anomalies_{ts}.json"
    with open(out_file, 'w') as f:
        json.dump(anomalies, f, indent=2)

    print(f"\n  Results saved → {out_file}")
    print("=" * 60)

    # ── print last anomaly detail ──
    if anomalies:
        last = anomalies[-1]
        print(f"\n  Last anomaly  (seq #{last['seq']}, score={last['score']})")
        print(f"    Type    : {last['type']}  [{last['severity']}]")
        print(f"    Causes  : {' | '.join(last['causes'][:2])}")
        print(f"    Fix     : {last['solutions'][0]}")
        print(f"    SINR={last['metrics']['sinr']} dB  RSRP={last['metrics']['rsrp']} dBm  "
              f"Tput={last['metrics']['throughput']} Mbps  Lat={last['metrics']['latency']} ms")
    print()


if __name__ == "__main__":
    run()