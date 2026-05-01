"""
QoSBuddy — Fusion multi-datasets
=================================
Charge plusieurs CSV hétérogènes, les labellise via qosbuddy_labeler,
équilibre les classes, et exporte un dataset ML prêt à l'emploi.

Usage :
  python qosbuddy_merger.py fichier1.csv fichier2.csv
  python qosbuddy_merger.py --folder ./mes_datasets/
"""

import pandas as pd
import numpy as np
import os
import sys
import glob
import argparse

from other.data_treatement.qosbuddy_labeler import (
    load_dataset, check_required_columns, clean_data,
    apply_labels, COLUMN_MAP
)

STANDARD_COLS = [
    "rsrp", "sinr", "rsrq", "cqi",
    "throughput_dl", "throughput_ul",
    "prb_utilization", "timestamp", "lat", "lon",
    "source_file",
    "label_call_drop_risk",
    "label_low_throughput",
    "label_handover_risk",
    "label_coverage_hole",
    "label_interference",
    "label_voice_quality_risk",
    "label_prb_congestion",
    "any_degradation",
    "severity",
    "recommendation",
]


# ─────────────────────────────────────────────
# UTILITAIRE
# ─────────────────────────────────────────────

def safe_pct(count, total):
    """Division sécurisée — retourne 0.0 si total == 0."""
    return 100 * count / total if total > 0 else 0.0


# ─────────────────────────────────────────────
# 1. TRAITEMENT D'UN FICHIER UNIQUE
# ─────────────────────────────────────────────

def process_one_file(filepath):
    print(f"\n  ┌─ {os.path.basename(filepath)}")
    try:
        df = load_dataset(filepath)
        check_required_columns(df)
        df = clean_data(df)

        if len(df) == 0:
            print(f"  └─ IGNORÉ (0 lignes valides après nettoyage)")
            return None

        df = apply_labels(df)
        df["source_file"] = os.path.basename(filepath)

        cols_to_keep = [c for c in STANDARD_COLS if c in df.columns]
        df = df[cols_to_keep]

        deg = int(df["any_degradation"].sum())
        pct = safe_pct(deg, len(df))
        print(f"  └─ OK : {len(df)} lignes · "
              f"{deg} dégradations ({pct:.1f}%)")
        return df

    except SystemExit:
        print(f"  └─ IGNORÉ (colonnes requises absentes)")
        return None
    except Exception as e:
        print(f"  └─ ERREUR : {e}")
        import traceback
        traceback.print_exc()
        return None


# ─────────────────────────────────────────────
# 2. STATISTIQUES PAR SOURCE
# ─────────────────────────────────────────────

def print_source_stats(df):
    if len(df) == 0:
        print("\n  ⚠  Dataset fusionné vide — rien à afficher.")
        return

    print("\n  ─── Contributions par source ───")
    label_cols = [c for c in df.columns if c.startswith("label_")]

    for src, grp in df.groupby("source_file"):
        total    = len(grp)
        degraded = int(grp["any_degradation"].sum())
        print(f"  {src[:45]:<45} {total:>7} lignes  "
              f"dégradées: {degraded:>5} ({safe_pct(degraded, total):.1f}%)")

    total_all    = len(df)
    degraded_all = int(df["any_degradation"].sum())
    print(f"\n  {'TOTAL':<45} {total_all:>7} lignes  "
          f"dégradées: {degraded_all:>5} "
          f"({safe_pct(degraded_all, total_all):.1f}%)")

    print("\n  ─── Labels actifs (total dataset) ───")
    for col in label_cols:
        count   = int(df[col].sum())
        pct     = safe_pct(count, total_all)
        bar_len = max(0, min(20, int(pct)))
        bar     = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {col.replace('label_',''):<25} {bar} {pct:4.1f}%  ({count})")


# ─────────────────────────────────────────────
# 3. ÉQUILIBRAGE DES CLASSES
# ─────────────────────────────────────────────

def balance_dataset(df, strategy="oversample", ratio=0.3):
    if len(df) == 0:
        print("\n  ⚠  Dataset vide — équilibrage ignoré.")
        return df

    normal        = df[df["any_degradation"] == 0]
    degraded      = df[df["any_degradation"] == 1]
    current_ratio = safe_pct(len(degraded), len(df)) / 100

    print(f"\n  ─── Équilibrage des classes ───")
    print(f"  Avant : normal={len(normal)} · dégradé={len(degraded)} "
          f"· ratio={current_ratio:.1%}")

    if strategy == "none" or current_ratio >= ratio:
        print(f"  → Aucun équilibrage nécessaire")
        return df

    if strategy == "oversample" and len(degraded) > 0:
        target_degraded = int(len(normal) * ratio / (1 - ratio))
        n_to_add        = target_degraded - len(degraded)
        if n_to_add > 0:
            extras = degraded.sample(n=n_to_add, replace=True,
                                     random_state=42).copy()
            for col in ["rsrp", "sinr", "rsrq", "cqi"]:
                if col in extras.columns:
                    noise       = np.random.normal(0, 0.5, len(extras))
                    extras[col] = (extras[col] + noise).round(1)
            df = pd.concat([df, extras], ignore_index=True)

    elif strategy == "undersample" and len(degraded) > 0:
        target_normal = int(len(degraded) * (1 - ratio) / ratio)
        normal        = normal.sample(n=min(target_normal, len(normal)),
                                      random_state=42)
        df = pd.concat([normal, degraded], ignore_index=True)

    new_ratio = safe_pct(int(df["any_degradation"].sum()), len(df)) / 100
    print(f"  Après : {len(df)} lignes · ratio={new_ratio:.1%}")
    return df.sample(frac=1, random_state=42).reset_index(drop=True)


# ─────────────────────────────────────────────
# 4. EXPORT FINAL
# ─────────────────────────────────────────────

def export_final(df, output_path="qosbuddy_dataset_final.csv"):
    if len(df) == 0:
        print("\n  ⚠  Dataset vide — aucun export.")
        return

    df.to_csv(output_path, index=False)
    print(f"\n  ─── Dataset final exporté ───")
    print(f"  Fichier  : {output_path}")
    print(f"  Lignes   : {len(df)}")
    print(f"  Colonnes : {len(df.columns)}")
    print(f"  Taille   : {os.path.getsize(output_path) / 1024:.0f} KB")

    feature_cols = [c for c in ["rsrp", "sinr", "rsrq", "cqi",
                                  "throughput_dl", "throughput_ul",
                                  "prb_utilization"] if c in df.columns]
    label_cols   = [c for c in df.columns if c.startswith("label_")]
    print(f"\n  Features ML : {feature_cols}")
    print(f"  Labels ML   : {label_cols}")
    print(f"  Label binaire principal : any_degradation")
    print(f"\n  Prêt pour : sklearn, xgboost, pytorch, etc.")


# ─────────────────────────────────────────────
# 5. PIPELINE PRINCIPALE
# ─────────────────────────────────────────────

def run(filepaths, output="qosbuddy_dataset_final.csv",
        balance="oversample", balance_ratio=0.3):

    print("=" * 60)
    print("  QoSBuddy — Fusion multi-datasets")
    print("=" * 60)
    print(f"\n  {len(filepaths)} fichier(s) à traiter...")

    dfs = []
    for fp in filepaths:
        result = process_one_file(fp)
        if result is not None:
            dfs.append(result)

    if not dfs:
        print("\n[ERREUR] Aucun fichier traité avec succès.")
        print("  → Consultez les diagnostics ci-dessus.")
        return None

    print(f"\n  Fusion de {len(dfs)} dataset(s)...")
    merged = pd.concat(dfs, ignore_index=True)

    print_source_stats(merged)
    merged = balance_dataset(merged, strategy=balance, ratio=balance_ratio)
    export_final(merged, output)

    print("\n" + "=" * 60)
    return merged


# ─────────────────────────────────────────────
# 6. POINT D'ENTRÉE CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="QoSBuddy — Fusion et labellisation multi-datasets LTE"
    )
    parser.add_argument("files", nargs="*", help="Fichiers CSV à traiter")
    parser.add_argument("--folder", "-f",
                        help="Dossier contenant les CSV à traiter")
    parser.add_argument("--output", "-o",
                        default="qosbuddy_dataset_final.csv",
                        help="Fichier de sortie")
    parser.add_argument("--balance",
                        choices=["oversample", "undersample", "none"],
                        default="oversample")
    parser.add_argument("--ratio", type=float, default=0.3)
    args = parser.parse_args()

    filepaths = list(args.files)
    if args.folder:
        filepaths += glob.glob(os.path.join(args.folder, "*.csv"))

    if not filepaths:
        print("Usage :")
        print("  python qosbuddy_merger.py fichier1.csv fichier2.csv")
        print("  python qosbuddy_merger.py --folder ./datasets/")
        sys.exit(0)

    run(filepaths, output=args.output,
        balance=args.balance, balance_ratio=args.ratio)