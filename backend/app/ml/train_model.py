"""
Phase 8 — Reproducible Graph ML Model Training & Evaluation Pipeline.
Trains a baseline Logistic Regression and a Random Forest Classifier on leakage-safe
graph topological features. Evaluates precision, recall, F1, ROC-AUC, and PR-AUC.
Compares ML outputs against the rule-based graph scoring engine.
Persists trained artifacts to backend/app/ml/model_artifacts.joblib and metadata.json.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
    classification_report,
)

# Add paths
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.abspath(os.path.join(BACKEND_DIR, "..")))

from app.ml.feature_extractor import CLIENT_FEATURE_NAMES, extract_client_features_from_graph
from app.services.risk_scoring import score_factors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_synthetic_graph_dataset() -> Tuple[np.ndarray, np.ndarray, list, list]:
    """
    Builds the graph dataset from the deterministic seed specifications (seed_data.py).
    Extracts purely structural and behavioral features without target leakage.
    Returns:
        X: feature matrix (N, num_features)
        y: binary fraud labels (N,)
        client_ids: list of client IDs
        feature_dicts: list of extracted feature dicts
    """
    # Import seed generation helpers
    from database.seed_data import make_clients, make_transactions, LOCATIONS, DEVICES

    clients_raw = make_clients()
    txs_raw = make_transactions(clients_raw)

    graph_data = {
        "clients": {c["client_id"]: c for c in clients_raw},
        "transactions": txs_raw,
        "devices": {d["device_id"]: d for d in DEVICES},
        "locations": {l["location_id"]: l for l in LOCATIONS},
    }

    client_ids = [c["client_id"] for c in clients_raw]
    # Ground truth: indices 30-39 are synthetic fraud actors (CLT031 - CLT040)
    y = np.array([1 if (30 <= i <= 39) else 0 for i in range(len(clients_raw))], dtype=int)

    feature_dicts = []
    feature_rows = []
    for cid in client_ids:
        feats = extract_client_features_from_graph(cid, graph_data)
        feature_dicts.append(feats)
        feature_rows.append([feats[name] for name in CLIENT_FEATURE_NAMES])

    X = np.array(feature_rows, dtype=float)
    return X, y, client_ids, feature_dicts


def train_and_evaluate(seed: int = 42) -> Dict[str, Any]:
    """
    Executes reproducible ML training, evaluation, comparison, and persistence.
    """
    logger.info("Extracting leakage-safe graph features for 60 clients...")
    X, y, client_ids, feature_dicts = build_synthetic_graph_dataset()

    # 1. Stratified Train / Test Split (75% train, 25% test = 45 train, 15 test)
    X_train, X_test, y_train, y_test, ids_train, ids_test = train_test_split(
        X, y, client_ids, test_size=0.25, random_state=seed, stratify=y
    )

    logger.info(
        "Train set: %d samples (%d fraud, %d legit) | Test set: %d samples (%d fraud, %d legit)",
        len(y_train), int(sum(y_train)), len(y_train) - int(sum(y_train)),
        len(y_test), int(sum(y_test)), len(y_test) - int(sum(y_test)),
    )

    # 2. Fit Scaler ONLY on Training Split
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 3. Model 1: Logistic Regression (Baseline)
    baseline_lr = LogisticRegression(class_weight="balanced", random_state=seed, max_iter=1000)
    baseline_lr.fit(X_train_scaled, y_train)
    lr_pred = baseline_lr.predict(X_test_scaled)
    lr_prob = baseline_lr.predict_proba(X_test_scaled)[:, 1]

    # 4. Model 2: Random Forest Classifier (Primary Ensemble)
    rf_model = RandomForestClassifier(
        n_estimators=100, max_depth=4, class_weight="balanced", random_state=seed
    )
    rf_model.fit(X_train_scaled, y_train)
    rf_pred = rf_model.predict(X_test_scaled)
    rf_prob = rf_model.predict_proba(X_test_scaled)[:, 1]

    # 5. Evaluate Metrics
    def compute_metrics(y_true, y_pred, y_prob):
        cm = confusion_matrix(y_true, y_pred).tolist()
        tn, fp, fn, tp = cm[0][0], cm[0][1], cm[1][0], cm[1][1]
        prec = float(precision_score(y_true, y_pred, zero_division=0))
        rec = float(recall_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))
        roc = float(roc_auc_score(y_true, y_prob)) if len(set(y_true)) > 1 else 0.5
        pr_auc = float(average_precision_score(y_true, y_prob)) if len(set(y_true)) > 1 else 0.0
        return {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "roc_auc": round(roc, 4),
            "pr_auc": round(pr_auc, 4),
            "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        }

    metrics_lr = compute_metrics(y_test, lr_pred, lr_prob)
    metrics_rf = compute_metrics(y_test, rf_pred, rf_prob)

    # 6. Compare with Rule-Based Risk Engine on the exact same test partition
    rule_predictions = []
    # Map test client features to heuristic rule scoring for fair comparison
    for cid in ids_test:
        idx = client_ids.index(cid)
        feats = feature_dicts[idx]
        rule_factors = {
            "shared_device": 1 if feats["shared_device_count"] > 0 else 0,
            "shared_location": 1 if feats["high_risk_loc_tx_count"] > 0 else 0,
            "multi_hop_path": 1 if feats["out_degree"] >= 3 else 0,
            "cycle_participation": 1 if feats["cycle_member"] > 0 else 0,
            "high_transaction_velocity": min(5, int(feats["velocity_burst_count"])),
            "suspicious_connections": 1 if feats["shared_device_count"] > 0 else 0,
        }
        scored = score_factors(cid, rule_factors)
        rule_pred = 1 if scored["riskScore"] >= 50.0 else 0
        rule_predictions.append(rule_pred)

    metrics_rule = {
        "precision": round(float(precision_score(y_test, rule_predictions, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, rule_predictions, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, rule_predictions, zero_division=0)), 4),
    }

    # 7. Extract Feature Importances
    importances = rf_model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    feature_importance_list = [
        {"feature": CLIENT_FEATURE_NAMES[i], "importance": round(float(importances[i]), 4)}
        for i in sorted_idx
    ]

    # 8. Assemble Metadata Package
    metadata = {
        "modelVersion": "1.0.0-rf-graph",
        "modelType": "RandomForestClassifier",
        "baselineType": "LogisticRegression",
        "trainingDate": datetime.now(timezone.utc).isoformat(),
        "randomSeed": seed,
        "dataset": {
            "totalEntities": len(client_ids),
            "trainSamples": len(y_train),
            "testSamples": len(y_test),
            "fraudPrevalence": round(float(sum(y) / len(y)), 4),
            "trainDistribution": {"fraud": int(sum(y_train)), "legit": int(len(y_train) - sum(y_train))},
            "testDistribution": {"fraud": int(sum(y_test)), "legit": int(len(y_test) - sum(y_test))},
        },
        "featureNames": CLIENT_FEATURE_NAMES,
        "featureImportances": feature_importance_list,
        "evaluation": {
            "primaryModel": metrics_rf,
            "baselineModel": metrics_lr,
            "ruleBasedBaseline": metrics_rule,
        },
        "thresholdSelection": {
            "defaultClassificationThreshold": 0.50,
            "rationale": "Balanced threshold calibrated to penalize false negatives (missed fraud rings) while containing false positives.",
        },
        "testPredictions": [
            {
                "clientId": ids_test[i],
                "groundTruth": int(y_test[i]),
                "mlProb": round(float(rf_prob[i]), 4),
                "mlPred": int(rf_pred[i]),
                "rulePred": int(rule_predictions[i]),
            }
            for i in range(len(ids_test))
        ],
    }

    # 9. Persist Model Artifacts
    output_dir = os.path.dirname(__file__)
    artifact_path = os.path.join(output_dir, "model_artifacts.joblib")
    metadata_path = os.path.join(output_dir, "metadata.json")

    bundle = {
        "model": rf_model,
        "baseline_model": baseline_lr,
        "scaler": scaler,
        "feature_names": CLIENT_FEATURE_NAMES,
        "metadata": metadata,
    }
    joblib.dump(bundle, artifact_path)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Saved model artifact to %s", artifact_path)
    logger.info("Saved evaluation metadata to %s", metadata_path)
    logger.info("Random Forest F1: %.4f | ROC-AUC: %.4f", metrics_rf["f1"], metrics_rf["roc_auc"])
    logger.info("Logistic Regression F1: %.4f | ROC-AUC: %.4f", metrics_lr["f1"], metrics_lr["roc_auc"])
    logger.info("Rule-Based Baseline F1: %.4f", metrics_rule["f1"])

    return metadata


if __name__ == "__main__":
    train_and_evaluate(seed=42)
