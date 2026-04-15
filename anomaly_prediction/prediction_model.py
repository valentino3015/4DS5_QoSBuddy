from __future__ import annotations

from typing import Dict, List, Tuple, Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except Exception:
    XGBOOST_AVAILABLE = False


def train_random_forest_baseline(
    X_train: np.ndarray,
    y_train: np.ndarray,
    random_state: int = 42,
) -> Pipeline:
    """
    Train a RandomForest baseline for anomaly prediction.
    """
    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=10,
                    min_samples_split=10,
                    min_samples_leaf=4,
                    class_weight="balanced",
                    random_state=random_state,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)
    return model


def train_xgboost_baseline(
    X_train: np.ndarray,
    y_train: np.ndarray,
    random_state: int = 42,
) -> Pipeline:
    """
    Train an XGBoost baseline if xgboost is installed.
    """
    if not XGBOOST_AVAILABLE:
        raise ImportError(
            "xgboost is not installed. Install it first or use RandomForest baseline."
        )

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "classifier",
                XGBClassifier(
                    n_estimators=300,
                    max_depth=6,
                    learning_rate=0.05,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    objective="binary:logistic",
                    eval_metric="logloss",
                    random_state=random_state,
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)
    return model


def evaluate_classifier(
    model: Pipeline,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> Dict[str, Any]:
    """
    Evaluate a trained classifier and return a metrics dictionary.
    """
    y_pred = model.predict(X_test)

    results = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1_score": f1_score(y_test, y_pred, zero_division=0),
        "confusion_matrix": confusion_matrix(y_test, y_pred),
        "classification_report": classification_report(
            y_test, y_pred, zero_division=0
        ),
        "y_pred": y_pred,
    }
    return results


def print_evaluation_results(results: Dict[str, Any], model_name: str = "Model") -> None:
    """
    Pretty-print evaluation results.
    """
    print("\n" + "=" * 70)
    print(f"{model_name.upper()} - EVALUATION RESULTS")
    print("=" * 70)
    print(f"Accuracy : {results['accuracy']:.4f}")
    print(f"Precision: {results['precision']:.4f}")
    print(f"Recall   : {results['recall']:.4f}")
    print(f"F1-score : {results['f1_score']:.4f}")

    print("\n" + "=" * 70)
    print("CONFUSION MATRIX")
    print("=" * 70)
    print(results["confusion_matrix"])

    print("\n" + "=" * 70)
    print("CLASSIFICATION REPORT")
    print("=" * 70)
    print(results["classification_report"])


def get_feature_importance(
    model: Pipeline,
    feature_names: List[str],
) -> List[Tuple[str, float]]:
    """
    Return sorted feature importances for tree-based models.
    """
    clf = model.named_steps["classifier"]

    if not hasattr(clf, "feature_importances_"):
        raise ValueError("This model does not expose feature_importances_.")

    importances = clf.feature_importances_
    pairs = list(zip(feature_names, importances))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs


def print_feature_importance(
    model: Pipeline,
    feature_names: List[str],
    top_k: int = 15,
) -> None:
    """
    Print top-k flattened feature importances.
    """
    pairs = get_feature_importance(model, feature_names)

    print("\n" + "=" * 70)
    print(f"TOP {top_k} FEATURE IMPORTANCE")
    print("=" * 70)
    for name, score in pairs[:top_k]:
        print(f"{name:<35} {score:.6f}")


def aggregate_feature_importance(
    model: Pipeline,
    flattened_feature_names: List[str],
) -> List[Tuple[str, float]]:
    """
    Aggregate importances of flattened temporal features like sinr_t-1, sinr_t-2...
    into base feature importance like sinr.
    """
    pairs = get_feature_importance(model, flattened_feature_names)

    aggregated: Dict[str, float] = {}
    for name, score in pairs:
        base_feature = name.rsplit("_t-", 1)[0] if "_t-" in name else name
        aggregated[base_feature] = aggregated.get(base_feature, 0.0) + float(score)

    agg_sorted = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
    return agg_sorted


def print_aggregated_feature_importance(
    model: Pipeline,
    flattened_feature_names: List[str],
) -> None:
    """
    Print aggregated feature importance by original feature.
    """
    agg_sorted = aggregate_feature_importance(model, flattened_feature_names)

    print("\n" + "=" * 70)
    print("AGGREGATED FEATURE IMPORTANCE")
    print("=" * 70)
    for name, score in agg_sorted:
        print(f"{name:<25} {score:.6f}")