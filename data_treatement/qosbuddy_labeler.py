"""
QoSBuddy — Générateur de labels de dégradation réseau
======================================================
Auteur : QoSBuddy — généré pour projet étudiant
"""

import pandas as pd
import numpy as np
import os
import sys
import csv
import re
import io

# ─────────────────────────────────────────────
# 1. MAPPING DES COLONNES
# ─────────────────────────────────────────────

COLUMN_MAP = {
    # ── RSRP (serving cell en priorité) ──
    "Serving RSRP_4G":  "rsrp",
    "RSRP(dBm)":        "rsrp",
    "RSRP":             "rsrp",
    "LTE_RSRP":         "rsrp",

    # ── RSRP voisins ──
    "1st RSRP in Neighboring Cells_4G": "rsrp_neighbor1",
    "2nd RSRP in Neighboring Cells_4G": "rsrp_neighbor2",
    "3rd RSRP in Neighboring Cells_4G": "rsrp_neighbor3",

    # ── SINR ──
    "Serving PCC SINR_4G":  "sinr",
    "Serving SCC1 SINR_4G": "sinr_scc1",
    "SINR(dB)":             "sinr",
    "SINR":                 "sinr",
    "LTE_SINR":             "sinr",
    "SNR":                  "sinr",

    # ── RSRQ ──
    "Serving RSRQ_4G":  "rsrq",
    "RSRQ(dB)":         "rsrq",
    "RSRQ":             "rsrq",
    "LTE_RSRQ":         "rsrq",

    # ── RSRQ voisins ──
    "1st RSRQ in Neighboring Cells_4G": "rsrq_neighbor1",
    "2nd RSRQ in Neighboring Cells_4G": "rsrq_neighbor2",
    "3rd RSRQ in Neighboring Cells_4G": "rsrq_neighbor3",

    # ── CQI ──
    "CQI":      "cqi",
    "LTE_CQI":  "cqi",
    "CQI_CW0":  "cqi",

    # ── Débit / Throughput ──
    "DL_bitrate":               "throughput_dl",
    "DL Throughput":            "throughput_dl",
    "Throughput(Mbps)":         "throughput_dl",
    "DL_tput_Mbps":             "throughput_dl",
    "PDCP Throughput DL_4G":    "throughput_dl",
    "LTE RLC Throughput DL_4G": "throughput_dl",
    "Downlink(Mbps)":           "throughput_dl",

    "UL_bitrate":       "throughput_ul",
    "UL Throughput":    "throughput_ul",
    "Uplink(Mbps)":     "throughput_ul",

    # ── Timestamp ──
    "Timestamp":    "timestamp",
    "Time":         "timestamp",
    "DATE_TIME":    "timestamp",
    "DateTime":     "timestamp",

    # ── Latitude / Longitude ──
    "Latitude":  "lat",
    "Longitude": "lon",
    "LAT":       "lat",
    "LON":       "lon",
    "lat":       "lat",
    "lon":       "lon",
}

# ─────────────────────────────────────────────
# 2. SEUILS
# ─────────────────────────────────────────────
THRESHOLDS = {
    "rsrp_critical":        -110,
    "rsrp_poor":            -100,
    "sinr_critical":           0,
    "sinr_poor":               5,
    "rsrq_poor":             -15,
    "cqi_poor":                7,
    "throughput_low_dl":       2,
    "throughput_critical_dl":  0.5,
    "consecutive_window":      3,
    "prb_congestion":         85,
}

# ─────────────────────────────────────────────
# 3. PARSERS SPÉCIALISÉS
# ─────────────────────────────────────────────

def _strip_unit(val):
    """
    Supprime les unités textuelles collées aux valeurs numériques.
    '-99 dBm' → -99.0 | '29 Mbps' → 29.0 | '0 dB' → 0.0
    Retourne np.nan si conversion impossible.
    """
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    # Garde uniquement le préfixe numérique (chiffres, signe, point)
    m = re.match(r"^([+-]?\d+\.?\d*)", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return np.nan
    return np.nan


def _detect_format(filepath):
    """
    Détecte le format du CSV.
    Retourne : 'tabquoted' | 'unitvalues' | 'standard'
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        f.readline()           # skip header
        first = f.readline()

    # mendeley : ligne entre guillemets avec tabulations à l'intérieur
    if first.strip().startswith('"') and "\t" in first:
        return "tabquoted"

    # network_logs : valeurs numériques suivies d'une unité
    if re.search(r"-?\d+\s+(dBm|dB|Mbps|km/h)", first):
        return "unitvalues"

    return "standard"


def _read_tabquoted(filepath):
    """
    Lecteur pour le format mendeley :
    Chaque ligne de données est une chaîne entre guillemets doubles
    contenant des valeurs séparées par des tabulations (et virgules).

    Ligne brute exemple :
      "1\\t,3.502\\t,6.437\\t,2021-...\\t,-62.50,-5.88,..."
    """
    print(f"      → Format détecté : tabquoted (mendeley-style)")
    rows         = []
    header_cols  = None

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_header  = f.readline().strip()
        header_cols = [c.strip() for c in raw_header.split(",")]

        for line in f:
            line = line.strip().strip('"')
            if not line:
                continue
            # Normaliser : "valeur\t," ou "valeur\t" → "valeur,"
            line = line.replace("\t,", ",").replace("\t", ",")
            for parts in csv.reader(io.StringIO(line)):
                parts = [p.strip() for p in parts]
                # Ajuster la longueur au nombre de colonnes de l'en-tête
                if len(parts) < len(header_cols):
                    parts += [""] * (len(header_cols) - len(parts))
                rows.append(parts[:len(header_cols)])

    df = pd.DataFrame(rows, columns=header_cols)
    print(f"      → Lignes parsées : {len(df)}")
    return df


def _read_unitvalues(filepath):
    """
    Lecteur standard pour les fichiers avec unités dans les valeurs.
    Le nettoyage des unités est fait dans clean_data() via _strip_unit().
    """
    print(f"      → Format détecté : unitvalues (network_logs-style)")
    return pd.read_csv(filepath, low_memory=False)


# ─────────────────────────────────────────────
# 4. FONCTIONS DE LABELLISATION
# ─────────────────────────────────────────────

def label_call_drop_risk(df):
    rsrp_bad = df["rsrp"] < THRESHOLDS["rsrp_critical"]
    sinr_bad = df["sinr"] < THRESHOLDS["sinr_critical"]
    combined = rsrp_bad & sinr_bad
    w        = THRESHOLDS["consecutive_window"]
    rolling  = combined.rolling(window=w, min_periods=w).sum()
    return (rolling >= w).fillna(False)


def label_low_throughput(df):
    conditions = []
    if "sinr" in df.columns:
        conditions.append(df["sinr"].reset_index(drop=True) < THRESHOLDS["sinr_poor"])
    if "cqi" in df.columns:
        conditions.append(df["cqi"].reset_index(drop=True) < THRESHOLDS["cqi_poor"])
    if "throughput_dl" in df.columns:
        conditions.append(df["throughput_dl"].reset_index(drop=True) < THRESHOLDS["throughput_low_dl"])
    if not conditions:
        return pd.Series(False, index=df.index)
    combined = pd.concat(conditions, axis=1).sum(axis=1)
    return (combined >= 2).fillna(False)


def label_handover_risk(df):
    rsrp_edge = (df["rsrp"] < THRESHOLDS["rsrp_poor"]) & \
                (df["rsrp"] >= THRESHOLDS["rsrp_critical"])
    if "rsrq" in df.columns:
        rsrq_bad = df["rsrq"] < THRESHOLDS["rsrq_poor"]
        return (rsrp_edge & rsrq_bad).fillna(False)
    return rsrp_edge.fillna(False)


def label_coverage_hole(df):
    rsrp_critical = df["rsrp"] < THRESHOLDS["rsrp_critical"]
    w             = THRESHOLDS["consecutive_window"]
    rolling       = rsrp_critical.rolling(window=w, min_periods=w).sum()
    return (rolling >= w).fillna(False)


def label_interference(df):
    sinr_bad = df["sinr"] < THRESHOLDS["sinr_critical"]
    rsrp_ok  = df["rsrp"] >= THRESHOLDS["rsrp_poor"]
    return (sinr_bad & rsrp_ok).fillna(False)


def label_voice_quality_risk(df):
    conditions = []
    if "sinr" in df.columns:
        conditions.append(df["sinr"].reset_index(drop=True) < THRESHOLDS["sinr_poor"])
    if "rsrq" in df.columns:
        conditions.append(df["rsrq"].reset_index(drop=True) < THRESHOLDS["rsrq_poor"])
    if not conditions:
        return pd.Series(False, index=df.index)
    combined = pd.concat(conditions, axis=1).sum(axis=1)
    return (combined >= 2).fillna(False)


def label_prb_congestion(df):
    if "prb_utilization" in df.columns:
        return (df["prb_utilization"] > THRESHOLDS["prb_congestion"]).fillna(False)
    if "throughput_dl" in df.columns and "sinr" in df.columns:
        low_tput  = df["throughput_dl"] < THRESHOLDS["throughput_low_dl"]
        good_sinr = df["sinr"] >= THRESHOLDS["sinr_poor"]
        return (low_tput & good_sinr).fillna(False)
    return pd.Series(False, index=df.index)


# ─────────────────────────────────────────────
# 5. MOTEUR DE RECOMMANDATIONS
# ─────────────────────────────────────────────

def generate_recommendation(row):
    if row.get("label_call_drop_risk"):
        return "Optimisation tilt + ajustement puissance cellule + vérification liste voisins"
    if row.get("label_coverage_hole"):
        return "Analyse zone trou de couverture → ajout site ou small cell 800 MHz"
    if row.get("label_interference"):
        return "Nettoyage PCI + optimisation A3 offset + ajustement TTT"
    if row.get("label_handover_risk"):
        return "Optimisation HO thresholds + ajuster timer T310 + vérification voisinage"
    if row.get("label_prb_congestion"):
        return "Ajout carrier + activation Carrier Aggregation + activation Massive MIMO"
    if row.get("label_low_throughput"):
        return "Optimisation CQI + activation 4x4 MIMO + augmenter bandwidth 10→20 MHz"
    if row.get("label_voice_quality_risk"):
        return "Activer AMR adaptatif + optimiser puissance UL + ajuster scheduler VoLTE"
    return "Aucune dégradation détectée"


def get_severity(row):
    label_cols = [c for c in row.index if c.startswith("label_")]
    active     = sum(1 for c in label_cols if row.get(c))
    if active == 0: return "OK"
    if active == 1: return "WARNING"
    return "CRITICAL"


# ─────────────────────────────────────────────
# 6. PIPELINE PRINCIPALE
# ─────────────────────────────────────────────

def load_dataset(filepath):
    """
    Charge le CSV avec détection automatique du format,
    puis renomme les colonnes (sans doublons de cible).
    """
    print(f"[1/4] Chargement du dataset : {filepath}")
    fmt = _detect_format(filepath)

    if fmt == "tabquoted":
        df = _read_tabquoted(filepath)
    elif fmt == "unitvalues":
        df = _read_unitvalues(filepath)
    else:
        print(f"      → Format détecté : standard")
        df = pd.read_csv(filepath, low_memory=False)

    print(f"      → {len(df)} lignes, {len(df.columns)} colonnes")
    print(f"      → Colonnes originales : {list(df.columns[:8])}...")

    # Renommage sans doublon sur les cibles
    rename       = {}
    used_targets = set()
    for src_col, target_col in COLUMN_MAP.items():
        if src_col in df.columns:
            if target_col not in used_targets:
                rename[src_col] = target_col
                used_targets.add(target_col)
            else:
                df = df.drop(columns=[src_col])

    df = df.rename(columns=rename)
    print(f"      → Colonnes mappées    : {list(rename.values())}")
    return df


def check_required_columns(df):
    required = ["rsrp", "sinr"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        print(f"\n[ERREUR] Colonnes requises manquantes : {missing}")
        print(f"  → Colonnes disponibles : {list(df.columns)}")
        sys.exit(1)
    print(f"[2/4] Colonnes essentielles OK ✓ (rsrp, sinr présents)")


def clean_data(df):
    """
    Nettoyage : strip des unités textuelles, conversion numérique,
    filtrage des outliers physiques LTE.
    """
    numeric_cols = ["rsrp", "sinr", "rsrq", "cqi",
                    "throughput_dl", "throughput_ul",
                    "rsrp_neighbor1", "rsrp_neighbor2", "rsrp_neighbor3",
                    "rsrq_neighbor1", "rsrq_neighbor2", "rsrq_neighbor3"]

    for col in numeric_cols:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(_strip_unit)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Diagnostic NaN sur colonnes clés
    for col in ["rsrp", "sinr"]:
        if col not in df.columns:
            continue
        n_nan = int(df[col].isna().sum())
        if n_nan > 0:
            pct = 100 * n_nan / len(df)
            print(f"      ⚠  {col} : {n_nan} valeurs invalides ({pct:.1f}%) → NaN")
            samples = df[col].dropna().head(3).tolist()
            print(f"         Exemples valides après nettoyage : {samples}")

    # Filtrage outliers physiques LTE
    n_before = len(df)
    if "rsrp" in df.columns:
        df = df[df["rsrp"].between(-140, -40) | df["rsrp"].isna()]
    if "sinr" in df.columns:
        df = df[df["sinr"].between(-20, 40)   | df["sinr"].isna()]
    if "cqi" in df.columns:
        df = df[df["cqi"].between(0, 15)      | df["cqi"].isna()]

    df        = df.dropna(subset=["rsrp", "sinr"])
    n_dropped = n_before - len(df)
    print(f"[2/4] Nettoyage : {n_dropped} lignes supprimées (NaN/outliers)")

    if len(df) == 0:
        print(f"      ✗ Dataset vide après nettoyage.")
    else:
        print(f"      → Dataset propre : {len(df)} lignes")
        print(f"         rsrp  min/mean/max : "
              f"{df['rsrp'].min():.1f} / {df['rsrp'].mean():.1f} / {df['rsrp'].max():.1f}")
        print(f"         sinr  min/mean/max : "
              f"{df['sinr'].min():.1f} / {df['sinr'].mean():.1f} / {df['sinr'].max():.1f}")

    return df.reset_index(drop=True)


def apply_labels(df):
    if len(df) == 0:
        for col in ["label_call_drop_risk", "label_low_throughput",
                    "label_handover_risk", "label_coverage_hole",
                    "label_interference", "label_voice_quality_risk",
                    "label_prb_congestion", "any_degradation",
                    "recommendation", "severity"]:
            df[col] = pd.Series(dtype=bool if col.startswith("label_") else object)
        return df

    print("[3/4] Application des règles métier...")
    df["label_call_drop_risk"]     = label_call_drop_risk(df)
    df["label_low_throughput"]     = label_low_throughput(df)
    df["label_handover_risk"]      = label_handover_risk(df)
    df["label_coverage_hole"]      = label_coverage_hole(df)
    df["label_interference"]       = label_interference(df)
    df["label_voice_quality_risk"] = label_voice_quality_risk(df)
    df["label_prb_congestion"]     = label_prb_congestion(df)

    label_cols        = [c for c in df.columns if c.startswith("label_")]
    df["any_degradation"] = df[label_cols].any(axis=1).astype(int)
    df["recommendation"]  = df.apply(generate_recommendation, axis=1)
    df["severity"]        = df.apply(get_severity, axis=1)

    print(f"\n      ─── Statistiques des labels ───")
    total = len(df)
    for col in label_cols:
        count = int(df[col].sum())
        pct   = 100 * count / total if total > 0 else 0.0
        print(f"      {col:<30} : {count:>6} ({pct:4.1f}%)")
    deg     = int(df["any_degradation"].sum())
    pct_deg = 100 * deg / total if total > 0 else 0.0
    print(f"      {'any_degradation':<30} : {deg:>6} ({pct_deg:.1f}%)")
    return df


def export_results(df, input_path):
    base = os.path.splitext(input_path)[0]
    out  = base + "_qosbuddy_labeled.csv"
    df.to_csv(out, index=False)
    print(f"\n[4/4] Export terminé → {out}")
    critical = df[df["severity"] == "CRITICAL"] if "severity" in df.columns else pd.DataFrame()
    if len(critical) > 0:
        print(f"\n      ─── Aperçu CRITICAL ({len(critical)} lignes) ───")
        cols_show = ["rsrp", "sinr"] + \
                    [c for c in ["cqi", "throughput_dl"] if c in df.columns] + \
                    ["severity", "recommendation"]
        print(critical[cols_show].head(5).to_string(index=False))
    return out


# ─────────────────────────────────────────────
# 7. POINT D'ENTRÉE
# ─────────────────────────────────────────────

def run(filepath):
    print("=" * 60)
    print("  QoSBuddy — Labellisation des dégradations réseau LTE")
    print("=" * 60 + "\n")
    df  = load_dataset(filepath)
    check_required_columns(df)
    df  = clean_data(df)
    df  = apply_labels(df)
    out = export_results(df, filepath)
    print("\n  Terminé. Dataset prêt pour l'entraînement ML.")
    print(f"  Fichier de sortie : {out}")
    print("=" * 60)
    return df


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python qosbuddy_labeler.py <chemin_vers_dataset.csv>")
        sys.exit(0)
    run(sys.argv[1])