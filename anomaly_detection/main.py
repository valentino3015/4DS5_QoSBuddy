"""
main.py — QoSBuddy Anomaly Detection Pipeline
Trains on the real dataset using any_degradation / label_* columns.
"""

import sys, warnings, json, time
import numpy as np
import pandas as pd
from datetime import datetime
from collections import deque
from pathlib import Path
import logging

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.WARNING)

from stream_window import QoSStream, SlidingWindow
from feature_eng import QoSFeatureEngineer
from LSTMAECNNTRAN import MultiModalScorer, LABEL_COLS

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
CONFIG = {
    "csv_path":            "data_treatement/qosbuddy_dataset_enhanced.csv",
    "knowledge_base_path": "knowledge_base.json",
    "window_size":         10,
    "step":                2,
    "sequence_length":     5,
    "train_ratio":         0.7,
    "delay":               0.0,       # 0 = fast-forward; 2.0 = real-time feel
    "evaluation_mode":     True,
    "max_sequences":       None,      # None = run all
    "results_dir":         "anomaly_results",
    "train_epochs":        40,
    "decision_threshold":  0.5,
    "auto_tune_threshold": True,
    "threshold_min":       0.2,
    "threshold_max":       0.9,
    "threshold_step":      0.01,
}

# ─────────────────────────────────────────────────────────────
# GROUND TRUTH  — read directly from CSV labels, no heuristics
# ─────────────────────────────────────────────────────────────

def load_ground_truth_map_from_df(df: pd.DataFrame) -> dict:
    """
    Build a row-index → any_degradation map from the CSV so the
    streaming loop can look up the true label for each event.
    """
    df['any_degradation'] = (
        pd.to_numeric(df['any_degradation'], errors='coerce').fillna(0).astype(int))
    return df['any_degradation'].to_dict()   # {row_index: 0/1}

def window_ground_truth(window_data: list, gt_map: dict) -> bool:
    """Majority vote: anomalous if ≥30% of rows in the window are labelled anomalous."""
    hits = sum(1 for row in window_data
               if gt_map.get(row.get('_row_idx', -1), 0) == 1)
    return hits / len(window_data) >= 0.3

# ─────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────

def compute_metrics(preds, truths, scores):
    from sklearn.metrics import (precision_score, recall_score,
                                 f1_score, accuracy_score, roc_auc_score)
    yt = np.array(truths, dtype=int)
    yp = np.array(preds,  dtype=int)
    ys = np.array(scores)
    m = {
        'accuracy':  round(float(accuracy_score(yt, yp)),                          4),
        'precision': round(float(precision_score(yt, yp, zero_division=0)),        4),
        'recall':    round(float(recall_score(yt, yp, zero_division=0)),           4),
        'f1':        round(float(f1_score(yt, yp, zero_division=0)),               4),
    }
    if len(np.unique(yt)) > 1:
        m['roc_auc'] = round(float(roc_auc_score(yt, ys)), 4)
    tp = int(((yt == 1) & (yp == 1)).sum())
    fp = int(((yt == 0) & (yp == 1)).sum())
    fn = int(((yt == 1) & (yp == 0)).sum())
    tn = int(((yt == 0) & (yp == 0)).sum())
    m.update({'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn})
    return m


def find_best_threshold(truths, scores, thr_min=0.2, thr_max=0.9, thr_step=0.01):
    """
    Brute-force threshold search maximizing F1 on the evaluation split.
    Returns best threshold and associated metrics.
    """
    best_thr = 0.5
    best_m = None
    best_f1 = -1.0
    thr = thr_min

    while thr <= thr_max + 1e-12:
        preds = [1 if s > thr else 0 for s in scores]
        m = compute_metrics(preds, truths, scores)
        if m['f1'] > best_f1:
            best_f1 = m['f1']
            best_thr = float(round(thr, 4))
            best_m = m
        thr += thr_step

    return best_thr, best_m

def severity_icon(sev):
    return {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(sev, '⚪')

# ─────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────

def run():
    csv_path  = CONFIG["csv_path"]
    kb_path   = CONFIG["knowledge_base_path"]
    seq_len   = CONFIG["sequence_length"]
    w_size    = CONFIG["window_size"]
    step      = CONFIG["step"]
    train_ratio = CONFIG["train_ratio"]
    decision_thr = CONFIG["decision_threshold"]
    results_d = CONFIG["results_dir"]
    Path(results_d).mkdir(exist_ok=True)

    engineer = QoSFeatureEngineer()
    df_all = pd.read_csv(csv_path)
    split_idx = int(len(df_all) * train_ratio)
    min_test_rows = max(w_size + step * seq_len, w_size + seq_len)
    if len(df_all) - split_idx < min_test_rows:
        split_idx = max(1, len(df_all) - min_test_rows)
    if split_idx <= 0 or split_idx >= len(df_all):
        raise ValueError("Invalid temporal split; adjust train_ratio/window/sequence settings.")

    df_train = df_all.iloc[:split_idx].copy().reset_index(drop=True)
    df_test  = df_all.iloc[split_idx:].copy().reset_index(drop=True)

    # Detect feature dimension
    sample_df = df_train.head(w_size)
    sample_f  = engineer.transform(sample_df.to_dict('records'))
    input_dim = len(sample_f)

    print("=" * 60)
    print("  QoSBuddy — Anomaly Detection Pipeline")
    print("=" * 60)
    print(f"  Dataset  : {csv_path}")
    print(f"  Split    : train={len(df_train)} rows ({train_ratio*100:.0f}%) | "
          f"test={len(df_test)} rows ({(1-train_ratio)*100:.0f}%)")
    print(f"  Features : {input_dim}  |  Window: {w_size}  |  Seq: {seq_len}")
    print(f"  Threshold: {decision_thr:.2f}")
    print("=" * 60)

    # ── [1/3] Train on real data ──────────────────────────────
    scorer = MultiModalScorer(kb_path, input_dim=input_dim,
                              seq_length=seq_len, device='cpu')
    print("\n[1/3] Training …")
    scorer.train_from_df(
        df_train, engineer,
        window_size=w_size, step=step,
        epochs=CONFIG["train_epochs"],
    )

    # ── [2/3] Load ground-truth map ───────────────────────────
    print("[2/3] Loading ground-truth labels …")
    gt_map = load_ground_truth_map_from_df(df_test)
    total_true = sum(gt_map.values())
    print(f"      {len(gt_map)} rows  |  {total_true} anomalous ({total_true/len(gt_map)*100:.1f}%)\n")

    # ── [3/3] Stream inference ────────────────────────────────
    print("[3/3] Running inference …\n")
    print(f"  {'#':>6}  {'Score':>6}  {'Decision':<16}  {'Type':<22}  {'GT'}")
    print("  " + "─" * 62)

    # Stream starts from the first row of the TEST split (temporal holdout)
    df_test['any_degradation'] = (
        pd.to_numeric(df_test['any_degradation'], errors='coerce').fillna(0).astype(int))

    buf      = deque(maxlen=w_size)
    feat_buf = deque(maxlen=seq_len)
    anomalies = []
    preds, truths, scores_list, inf_times = [], [], [], []
    seq_n   = 0
    max_seq = CONFIG["max_sequences"]

    for row_idx, row in df_test.iterrows():
        event = row.to_dict()
        event['_row_idx'] = row_idx
        buf.append(event)

        if len(buf) < w_size or (row_idx + 1) % step != 0:
            continue

        window_data = list(buf)
        feats    = engineer.transform(window_data)
        feat_vec = np.array([feats[k] for k in sorted(feats.keys())], dtype=np.float32)
        feat_buf.append(feat_vec)

        if len(feat_buf) < seq_len:
            continue

        seq_n += 1
        seq = np.array(feat_buf, dtype=np.float32)
        gt  = window_ground_truth(window_data, gt_map)

        t0     = time.perf_counter()
        result = scorer.score(seq)
        inf_ms = (time.perf_counter() - t0) * 1000

        pred_now = int(result.final_score > decision_thr)
        preds.append(pred_now)
        truths.append(int(gt))
        scores_list.append(result.final_score)
        inf_times.append(inf_ms)

        gt_tag = "ANOM" if gt else "norm"
        if pred_now:
            icon    = severity_icon(result.severity)
            dec_str = f"{icon} {result.severity}"
        else:
            dec_str = "  ok"
        deg_str = (result.degradation_type or '')[:20]
        print(f"  {seq_n:>6}  {result.final_score:>6.3f}  {dec_str:<16}  {deg_str:<22}  {gt_tag}")

        if pred_now:
            anomalies.append({
                "seq":       seq_n,
                "score":     result.final_score,
                "severity":  result.severity,
                "type":      result.degradation_type,
                "causes":    result.causes,
                "solutions": result.solutions,
                "metrics": {
                    "sinr":       round(feats.get("mean_sinr", 0), 2),
                    "rsrp":       round(feats.get("mean_rsrp", 0), 2),
                    "throughput": round(feats.get("mean_throughput_dl", 0), 2),
                    "latency":    round(feats.get("mean_latency", 0), 2),
                    "mos":        round(feats.get("mean_mos", 0), 2),
                },
                "timestamp": datetime.now().isoformat(),
            })

        if max_seq and seq_n >= max_seq:
            break

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"  Sequences   : {seq_n}")
    print(f"  Anomalies   : {len(anomalies)}  ({len(anomalies)/max(seq_n,1)*100:.1f}%)")
    print(f"  Avg latency : {np.mean(inf_times):.1f} ms")

    if CONFIG["evaluation_mode"] and len(truths) > 0:
        m = compute_metrics(preds, truths, scores_list)
        print(f"\n  vs. ground truth (any_degradation label):")
        print(f"    Accuracy  {m['accuracy']:.4f}   F1       {m['f1']:.4f}")
        print(f"    Precision {m['precision']:.4f}   Recall   {m['recall']:.4f}")
        if 'roc_auc' in m:
            print(f"    ROC-AUC   {m['roc_auc']:.4f}")
        print(f"    TP={m['tp']}  FP={m['fp']}  FN={m['fn']}  TN={m['tn']}")

        if CONFIG.get("auto_tune_threshold", False):
            best_thr, best_m = find_best_threshold(
                truths, scores_list,
                thr_min=CONFIG.get("threshold_min", 0.2),
                thr_max=CONFIG.get("threshold_max", 0.9),
                thr_step=CONFIG.get("threshold_step", 0.01),
            )
            print("\n  Threshold tuning (test split, objective=F1):")
            print(f"    Current threshold : {decision_thr:.2f}   F1={m['f1']:.4f}")
            print(f"    Best threshold    : {best_thr:.2f}   F1={best_m['f1']:.4f}")
            print(f"    Precision={best_m['precision']:.4f}  Recall={best_m['recall']:.4f}  "
                  f"TP={best_m['tp']} FP={best_m['fp']} FN={best_m['fn']} TN={best_m['tn']}")

        grade = ("✅ Excellent" if m['f1'] >= 0.85
                 else "👍 Good"    if m['f1'] >= 0.70
                 else "⚠️  Needs tuning")
        print(f"\n  Assessment : {grade}")

    # ── Save ──────────────────────────────────────────────────
    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_file = f"{results_d}/anomalies_{ts}.json"
    with open(out_file, 'w') as f:
        json.dump(anomalies, f, indent=2)
    print(f"\n  Saved → {out_file}")
    print("=" * 60)

    if anomalies:
        last = anomalies[-1]
        print(f"\n  Last anomaly  seq #{last['seq']}  score={last['score']}")
        print(f"    {last['type']}  [{last['severity']}]")
        print(f"    Cause : {last['causes'][0] if last['causes'] else '-'}")
        print(f"    Fix   : {last['solutions'][0] if last['solutions'] else '-'}")
        print(f"    SINR={last['metrics']['sinr']} dB  "
              f"RSRP={last['metrics']['rsrp']} dBm  "
              f"Tput={last['metrics']['throughput']} Mbps  "
              f"Lat={last['metrics']['latency']} ms")
    print()


if __name__ == "__main__":
    run()