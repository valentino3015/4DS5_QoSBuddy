# anomaly_prediction/evaluator.py

from config import TARGET_LABELS
from sklearn.metrics import classification_report, roc_auc_score
import numpy as np

def print_performance_report(y_test, y_pred, y_proba):
    """
    Print performance metrics for multi-output classification.
    """
    print("\n=== Rapport de Performance ===")

    # Per target metrics
    print("\nMétriques par type d'anomalie:")
    for i, target in enumerate(TARGET_LABELS.keys()):
        y_true = y_test[target]
        y_pred_target = y_pred[:, i]
        y_proba_target = y_proba[i][:, 1] if len(y_proba[i][0]) > 1 else y_proba[i].flatten()

        auc = roc_auc_score(y_true, y_proba_target) if len(np.unique(y_true)) > 1 else 0
        print(f"{TARGET_LABELS[target]}: AUC = {auc:.3f}")

        # Classification report for this target
        if len(np.unique(y_true)) > 1:
            print(classification_report(y_true, y_pred_target, target_names=['Normal', 'Anomalie']))
        else:
            print(f"Only one class present: {np.unique(y_true)}")