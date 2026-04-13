# anomaly_prediction/predictor.py

from config import FEATURE_COLS, TARGET_COLS, TARGET_LABELS
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.metrics import classification_report, roc_auc_score
import joblib
import os

def build_and_train_model(df):
    """
    Build and train a multi-output classifier for QoS anomaly prediction.
    """
    X = df[FEATURE_COLS]
    y = df[TARGET_COLS]

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Multi-output classifier
    base_classifier = RandomForestClassifier(n_estimators=100, random_state=42)
    pipeline = MultiOutputClassifier(base_classifier)
    pipeline.fit(X_train, y_train)

    # Predictions
    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)

    # Save model
    os.makedirs('models', exist_ok=True)
    joblib.dump(pipeline, 'models/qos_predictor.pkl')

    return pipeline, X_test, y_test, y_pred, y_proba

def predict_single_cell(pipeline, sample):
    """
    Predict anomalies for a single cell sample.
    """
    sample_df = pd.DataFrame([sample])
    pred = pipeline.predict(sample_df)[0]
    proba = pipeline.predict_proba(sample_df)

    results = {}
    for i, col in enumerate(TARGET_COLS):
        results[col] = {
            'prediction': int(pred[i]),
            'probability': proba[i][0][1] if len(proba[i][0]) > 1 else proba[i][0][0]
        }
    return results

def print_cell_report(cell_id, results):
    """
    Print prediction report for a single cell.
    """
    print(f"\n=== Prédiction pour la cellule {cell_id} ===")
    for label, res in results.items():
        status = "ANOMALIE" if res['prediction'] == 1 else "NORMAL"
        prob = res['probability'] * 100
        print(f"{TARGET_LABELS[label]}: {status} ({prob:.1f}%)")