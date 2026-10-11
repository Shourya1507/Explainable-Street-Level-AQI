"""
Lambda inference fallback — loads XGBoost model from S3 and predicts locally.
Used when SageMaker endpoint is unavailable (quota delay, cost, cold start).
Included inside the estimate Lambda when SAGEMAKER_ENDPOINT is empty.

This module is imported by handler.py automatically if no endpoint is set.
"""
import io
import os
import json
import boto3
import math
import logging

logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "aqi-models-991166714312")
MODEL_KEY = os.environ.get("MODEL_KEY", "nowcast/nowcast_model.ubj")

# Driver lookup: feature → human note (must match build_features.py)
DRIVER_NOTES = {
    "nearby_station_avg":  "surrounding stations reading high",
    "nearby_station_idw":  "surrounding stations (IDW) reading high",
    "neighbor_spread":     "high variability in nearby readings",
    "nearest_station_km":  "distance to nearest monitoring station",
    "temperature":         "temperature conditions",
    "humidity":            "high humidity amplifying particle concentration",
    "wind_speed":          "low wind trapping pollutants",
    "wind_direction":      "wind direction from pollution sources",
    "surface_pressure":    "surface pressure affecting dispersion",
    "boundary_layer":      "shallow boundary layer trapping pollutants",
    "road_density":        "high road density from nearby traffic",
    "hour_of_day":         "evening traffic peak",
    "day_of_week":         "weekday traffic pattern",
    "month":               "seasonal pollution pattern",
    "is_weekend":          "weekend traffic reduction",
    "is_morning_peak":     "morning traffic peak",
    "is_evening_peak":     "evening traffic peak",
    "fire_count":          "active fire detections upwind",
    "aod":                 "elevated aerosol optical depth",
}

_model_cache = None  # module-level cache — survives warm Lambda invocations


def _load_model():
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    try:
        import xgboost as xgb
    except ImportError:
        logger.error("xgboost not installed in Lambda layer")
        raise

    logger.info(f"Loading model from s3://{MODELS_BUCKET}/{MODEL_KEY}")
    s3 = boto3.client("s3", region_name=REGION)
    model_path = "/tmp/nowcast_model.ubj"
    s3.download_file(MODELS_BUCKET, MODEL_KEY, model_path)

    model = xgb.XGBRegressor()
    model.load_model(model_path)
    _model_cache = model
    logger.info("Model loaded and cached")
    return model


def predict(features: dict) -> tuple:
    """
    Predict PM2.5 from a feature dict.
    Returns (pm25_value, drivers_list, confidence_level, nearest_km)

    features dict keys must match FEATURE_COLS in train_nowcast.py
    """
    try:
        import pandas as pd
        import numpy as np
        import shap
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        raise

    FEATURE_COLS = [
        # "nearby_station_avg", "nearby_station_idw", "neighbor_spread",
        # "nearest_station_km", 
        "temperature", "humidity", "wind_speed",
        "wind_direction", "surface_pressure", "boundary_layer",
        "road_density", "hour_of_day", "day_of_week", "month",
        "is_weekend", "is_morning_peak", "is_evening_peak",
        # "fire_count", "aod",
    ]

    model = _load_model()

    # Build feature vector — fill missing with NaN
    row = {col: features.get(col, float("nan")) for col in FEATURE_COLS}
    X = pd.DataFrame([row])

    # Predict
    pm25 = float(model.predict(X)[0])
    pm25 = max(0.0, min(pm25, 1500.0))

    # SHAP top 3 drivers
    try:
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X)[0]
        driver_indices = sorted(range(len(shap_vals)), key=lambda i: abs(shap_vals[i]), reverse=True)[:3]
        drivers = []
        for idx in driver_indices:
            feat = FEATURE_COLS[idx]
            sv = float(shap_vals[idx])
            if abs(sv) < 0.1:
                continue
            drivers.append({
                "feature": feat,
                "shap": round(sv, 2),
                "note": DRIVER_NOTES.get(feat, feat.replace("_", " ")),
            })
    except Exception as e:
        logger.warning(f"SHAP failed: {e} — returning empty drivers")
        drivers = []

    # Confidence: distance-based
    nearest_km = features.get("nearest_station_km", 999.0)
    if nearest_km is None or math.isnan(nearest_km):
        nearest_km = 999.0
    if nearest_km <= 3.0:
        confidence = "high"
    elif nearest_km <= 8.0:
        confidence = "medium"
    else:
        confidence = "low"

    return pm25, drivers, confidence, nearest_km
