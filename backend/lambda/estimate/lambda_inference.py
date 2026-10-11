"""
Lambda inference — loads XGBoost model from S3 and predicts locally.
Used when SAGEMAKER_ENDPOINT is empty (default path).

Dependencies (must be in Lambda Layer):
  xgboost-cpu >= 2.0.3
  numpy >= 1.26.0

NOTE: shap and pandas are NOT used here.
  - SHAP contributions come from xgboost's native pred_contribs=True
    (identical math to shap.TreeExplainer, no extra dependency).
  - Feature vectors are plain Python dicts / numpy arrays (no DataFrame).
"""
import io
import os
import math
import logging
import numpy as np

logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "aqi-models-991166714312")
MODEL_KEY = os.environ.get("MODEL_KEY", "nowcast/nowcast_model.ubj")

# ── Feature columns — MUST match train_nowcast.py exactly ─────────────────────
FEATURE_COLS = [
    "nearby_station_avg", "nearby_station_idw", "neighbor_spread",
    "nearest_station_km",
    "temperature", "humidity", "wind_speed",
    "wind_direction", "surface_pressure", "boundary_layer",
    "road_density", "hour_of_day", "day_of_week", "month",
    "is_weekend", "is_morning_peak", "is_evening_peak",
    # "fire_count", "aod",  # Tier 6 — not yet in production data pipeline
]

# ── Human-readable driver notes ────────────────────────────────────────────────
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
    "hour_of_day":         "time-of-day traffic pattern",
    "day_of_week":         "weekday traffic pattern",
    "month":               "seasonal pollution pattern",
    "is_weekend":          "weekend traffic reduction",
    "is_morning_peak":     "morning traffic peak",
    "is_evening_peak":     "evening traffic peak",
    "fire_count":          "active fire detections upwind",
    "aod":                 "elevated aerosol optical depth",
}

_model_cache = None   # module-level — survives warm Lambda invocations
_booster_cache = None


def _load_model():
    global _model_cache, _booster_cache
    if _model_cache is not None:
        return _model_cache, _booster_cache

    try:
        import xgboost as xgb
    except ImportError:
        logger.error("xgboost not installed — Lambda Layer missing")
        raise

    import boto3
    logger.info(f"Loading model from s3://{MODELS_BUCKET}/{MODEL_KEY}")
    s3 = boto3.client("s3", region_name=REGION)
    model_path = "/tmp/nowcast_model.ubj"
    s3.download_file(MODELS_BUCKET, MODEL_KEY, model_path)

    # XGBRegressor wrapper — used for predict()
    model = xgb.XGBRegressor()
    model.load_model(model_path)

    # Underlying Booster — used for pred_contribs (native SHAP)
    booster = model.get_booster()

    _model_cache = model
    _booster_cache = booster
    logger.info("Model loaded and cached")
    return model, booster


def predict(features: dict) -> tuple:
    """
    Predict PM2.5 from a feature dict and compute SHAP contributions.

    Args:
        features: dict with keys matching FEATURE_COLS

    Returns:
        (pm25_value, drivers_list, confidence_level, nearest_km)

    drivers_list elements: {"feature", "shap", "note"}
    SHAP contributions come from booster.predict(pred_contribs=True),
    which gives the same values as shap.TreeExplainer without the
    shap/pandas/scipy dependency chain.
    """
    import xgboost as xgb

    model, booster = _load_model()

    # Build feature array — fill missing with NaN
    row = np.array(
        [features.get(col, float("nan")) for col in FEATURE_COLS],
        dtype=np.float32,
    ).reshape(1, -1)

    dmatrix = xgb.DMatrix(row, feature_names=FEATURE_COLS)

    # Predict PM2.5
    pm25 = float(booster.predict(dmatrix)[0])
    pm25 = max(0.0, min(pm25, 1500.0))

    # Native SHAP contributions — shape (1, n_features + 1); last col is bias
    try:
        contribs = booster.predict(dmatrix, pred_contribs=True)[0]
        # contribs[-1] is the bias term — exclude it
        feat_contribs = contribs[:-1]

        # Top 3 by absolute contribution; skip tiny values
        ranked = sorted(enumerate(feat_contribs), key=lambda x: abs(x[1]), reverse=True)
        drivers = []
        for idx, sv in ranked[:3]:
            if abs(sv) < 0.1:
                continue
            feat = FEATURE_COLS[idx]
            drivers.append({
                "feature": feat,
                "shap":    round(float(sv), 2),
                "note":    DRIVER_NOTES.get(feat, feat.replace("_", " ")),
            })
    except Exception as e:
        logger.warning(f"pred_contribs failed: {e} — returning empty drivers")
        drivers = []

    # Confidence: distance-based
    nearest_km = features.get("nearest_station_km", 999.0)
    if nearest_km is None or (isinstance(nearest_km, float) and math.isnan(nearest_km)):
        nearest_km = 999.0
    nearest_km = float(nearest_km)

    if nearest_km <= 3.0:
        confidence = "high"
    elif nearest_km <= 8.0:
        confidence = "medium"
    else:
        confidence = "low"

    return pm25, drivers, confidence, nearest_km
