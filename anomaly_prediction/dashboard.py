# anomaly_prediction/dashboard.py

import pandas as pd
import os
from config import TARGET_COLS, FEATURE_COLS

def plot_dashboard(df, y_test, y_proba):
    """
    Generate dashboard plots (placeholder - implement with matplotlib/seaborn).
    """
    print("\n=== Dashboard ===")
    print("Génération des graphiques... (à implémenter avec matplotlib)")

    # Placeholder: print anomaly distribution
    anomaly_counts = df[TARGET_COLS].sum()
    print("Distribution des anomalies:")
    for col, count in anomaly_counts.items():
        print(f"{col}: {count} cas")

def export_predictions(df, pipeline):
    """
    Export predictions to CSV.
    """
    print("\n=== Export des Prédictions ===")
    os.makedirs('outputs', exist_ok=True)

    # Predict on full dataset
    X = df[FEATURE_COLS]
    predictions = pipeline.predict(X)
    probas = pipeline.predict_proba(X)

    # Create results DataFrame
    results_df = df.copy()
    for i, col in enumerate(TARGET_COLS):
        results_df[f'pred_{col}'] = predictions[:, i]
        results_df[f'proba_{col}'] = probas[i][:, 1] if len(probas[i][0]) > 1 else probas[i].flatten()

    results_df.to_csv('outputs/predictions.csv', index=False)
    print("Prédictions exportées vers outputs/predictions.csv")