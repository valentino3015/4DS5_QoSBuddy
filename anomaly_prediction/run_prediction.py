# anomaly_prediction/run_prediction.py

from data_loader  import load_data
from predictor    import build_and_train_model, predict_single_cell, print_cell_report
from evaluator    import print_performance_report
from dashboard    import plot_dashboard, export_predictions
from config       import FEATURE_COLS, TARGET_COLS

def main():
    print("=" * 60)
    print("  QoSBuddy — BO Prediction (données réelles)")
    print("=" * 60)

    # 1. Charger les données réelles
    df = load_data()

    # 2. Entraîner le modèle
    pipeline, X_test, y_test, y_pred, y_proba = build_and_train_model(df)

    # 3. Évaluation
    print_performance_report(y_test, y_pred, y_proba)

    # 4. Prédiction sur une cellule exemple (prendre la dernière ligne du CSV)
    sample = df[FEATURE_COLS].iloc[-1].to_dict()
    results = predict_single_cell(pipeline, sample)
    print_cell_report(str(df["source_file"].iloc[-1]), results)

    # 5. Export
    export_predictions(df, pipeline)
    plot_dashboard(df, y_test, y_proba)

if __name__ == "__main__":
    main()