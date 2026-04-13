# anomaly_prediction/data_loader.py

import pandas as pd
from pathlib import Path
from config import FEATURE_COLS, TARGET_COLS

DATA_PATH = Path(__file__).parent.parent / "data_treatement" / "qosbuddy_dataset_final.csv"

def load_data(path=DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])

    # Vérification des colonnes requises
    missing_feat = [c for c in FEATURE_COLS if c not in df.columns]
    missing_tgt  = [c for c in TARGET_COLS  if c not in df.columns]
    if missing_feat:
        raise ValueError(f"Features manquantes dans le CSV : {missing_feat}")
    if missing_tgt:
        raise ValueError(f"Labels manquants dans le CSV : {missing_tgt}")

    # Supprime les lignes avec NaN sur les features
    df = df.dropna(subset=FEATURE_COLS + TARGET_COLS)
    print(f"[data_loader] {len(df)} lignes chargées depuis {path.name}")
    return df