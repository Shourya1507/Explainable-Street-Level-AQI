"""
XGBoost nowcast model — Explainable Street-Level AQI
Tier 1: leave-one-station-out cross-validation + training + SHAP

Usage:
  python train_nowcast.py --features-dir ./features --out-dir ./model_output
"""
import argparse
import json
import os
import sys
import math
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
    import numpy as np
    import xgboost as xgb
    import shap
    import boto3
except ImportError:
    print("Install: pip install pandas numpy xgboost shap boto3 pyarrow")
    sys.exit(1)

REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "aqi-models-991166714312")

# Feature columns for the model (must match build_features.py)
FEATURE_COLS = [
    "nearby_station_avg",
    "nearby_station_idw",
    "neighbor_spread",
    "nearest_station_km",
    "temperature",
    "humidity",
    "wind_speed",
    "wind_direction",
    "surface_pressure",
    "boundary_layer",
    "road_density",
    "hour_of_day",
    "day_of_week",
    "month",
    "is_weekend",
    "is_morning_peak",
    "is_evening_peak",
    # "fire_count", "aod",  # Tier 6 – not yet in production data pipeline
]

TARGET_COL = "pm25"

# XGBoost hyperparameters (reasonable defaults; tune in Tier 1+)
XGB_PARAMS = {
    "n_estimators": 500,
    "learning_rate": 0.05,
    "max_depth": 6,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
    "tree_method": "hist",
}


def rmse(y_true, y_pred) -> float:
    return math.sqrt(((np.array(y_true) - np.array(y_pred)) ** 2).mean())

def mae(y_true, y_pred) -> float:
    return abs(np.array(y_true) - np.array(y_pred)).mean()

def nearest_station_baseline(df: pd.DataFrame) -> np.ndarray:
    """Predict using the nearest station's reading (nearby_station_avg of k=1)."""
    return df["nearby_station_avg"].values

def idw_baseline(df: pd.DataFrame) -> np.ndarray:
    return df["nearby_station_idw"].values


def leave_one_station_out_cv(df: pd.DataFrame) -> dict:
    """
    Leave-one-station-out cross-validation.
    For each station, train on all others, predict on the held-out station.
    Reports RMSE and MAE for the model and both baselines.
    """
    stations = df["station_id"].unique()
    print(f"\nLeave-one-station-out CV: {len(stations)} stations")

    all_pred, all_true = [], []
    all_baseline_nn, all_baseline_idw = [], []
    station_results = {}

    for i, station in enumerate(stations):
        train_mask = df["station_id"] != station
        test_mask  = df["station_id"] == station

        train_df = df[train_mask].copy()
        test_df  = df[test_mask].copy()

        if len(test_df) < 10:
            print(f"  [{i+1}/{len(stations)}] {station}: skip (too few rows: {len(test_df)})")
            continue

        # Drop rows with NaN in required features
        train_df = train_df.dropna(subset=FEATURE_COLS + [TARGET_COL])
        test_df  = test_df.dropna(subset=FEATURE_COLS + [TARGET_COL])

        if len(train_df) < 50 or len(test_df) < 5:
            print(f"  [{i+1}/{len(stations)}] {station}: skip (insufficient data after NaN drop)")
            continue

        X_train = train_df[FEATURE_COLS]
        y_train = train_df[TARGET_COL]
        X_test  = test_df[FEATURE_COLS]
        y_test  = test_df[TARGET_COL]

        model = xgb.XGBRegressor(**XGB_PARAMS)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        y_pred = model.predict(X_test)
        y_pred = np.clip(y_pred, 0, 1500)

        station_rmse = rmse(y_test, y_pred)
        station_mae  = mae(y_test, y_pred)
        nn_rmse = rmse(y_test, nearest_station_baseline(test_df))
        idw_rmse = rmse(y_test, idw_baseline(test_df))
        nn_dist = test_df["nearest_station_km"].mean()

        station_results[station] = {
            "n_test": len(test_df),
            "model_rmse": round(station_rmse, 2),
            "model_mae": round(station_mae, 2),
            "nn_rmse": round(nn_rmse, 2),
            "idw_rmse": round(idw_rmse, 2),
            "mean_nearest_dist_km": round(float(nn_dist), 2),
        }

        print(f"  [{i+1}/{len(stations)}] {station}: RMSE={station_rmse:.1f} vs NN={nn_rmse:.1f} vs IDW={idw_rmse:.1f} (n={len(test_df)}, dist={nn_dist:.1f}km)")

        all_pred.extend(y_pred.tolist())
        all_true.extend(y_test.tolist())
        all_baseline_nn.extend(nearest_station_baseline(test_df).tolist())
        all_baseline_idw.extend(idw_baseline(test_df).tolist())

    overall = {
        "model_rmse":    round(rmse(all_true, all_pred), 2),
        "model_mae":     round(mae(all_true, all_pred), 2),
        "nn_rmse":       round(rmse(all_true, all_baseline_nn), 2),
        "nn_mae":        round(mae(all_true, all_baseline_nn), 2),
        "idw_rmse":      round(rmse(all_true, all_baseline_idw), 2),
        "idw_mae":       round(mae(all_true, all_baseline_idw), 2),
        "n_predictions": len(all_pred),
        "n_stations":    len(station_results),
    }

    print(f"\n=== Overall LOSO ===")
    print(f"Model RMSE: {overall['model_rmse']} µg/m³  (vs NN: {overall['nn_rmse']}, IDW: {overall['idw_rmse']})")
    print(f"Model MAE:  {overall['model_mae']} µg/m³  (vs NN: {overall['nn_mae']}, IDW: {overall['idw_mae']})")

    return {"overall": overall, "by_station": station_results}


def train_final_model(df: pd.DataFrame) -> xgb.XGBRegressor:
    """Train on all stations (final model for serving)."""
    df_clean = df.dropna(subset=FEATURE_COLS + [TARGET_COL])
    X = df_clean[FEATURE_COLS]
    y = df_clean[TARGET_COL]
    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(X, y, verbose=False)
    print(f"\nFinal model trained on {len(df_clean)} rows across {df['station_id'].nunique()} stations")
    return model


def compute_shap_for_sample(model: xgb.XGBRegressor, X_sample: pd.DataFrame) -> pd.DataFrame:
    """Compute SHAP values for a sample of rows."""
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)
    return pd.DataFrame(shap_values, columns=FEATURE_COLS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features-dir", default="./features")
    parser.add_argument("--out-dir", default="./model_output")
    parser.add_argument("--skip-cv", action="store_true", help="Skip LOSO CV, train final only")
    parser.add_argument("--upload", action="store_true", help="Upload model to S3")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    feat_dir = Path(args.features_dir)
    parquet_files = list(feat_dir.glob("*.parquet"))
    if not parquet_files:
        print(f"No parquet files found in {feat_dir}. Run build_features.py first.")
        sys.exit(1)

    print(f"Loading {len(parquet_files)} feature files...")
    df = pd.concat([pd.read_parquet(f) for f in parquet_files], ignore_index=True)
    print(f"Loaded {len(df)} rows, {df['station_id'].nunique()} stations")

    # Record data window (rules.md §5.5)
    data_window = {
        "start": str(df["datetime"].min()),
        "end":   str(df["datetime"].max()),
        "station_count": int(df["station_id"].nunique()),
        "stations": df["station_id"].unique().tolist(),
        "total_rows": len(df),
    }
    with open(out / "data_window.json", "w") as f:
        json.dump(data_window, f, indent=2, default=str)

    # Leave-one-station-out CV
    eval_results = {}
    if not args.skip_cv:
        eval_results = leave_one_station_out_cv(df)
        # Fallback: time-split eval when only 1 station (LOSO produces no results)
        if not eval_results.get("overall") or eval_results["overall"].get("n_predictions", 0) == 0:
            print("\nOnly 1 station — using 80/20 time-split evaluation instead of LOSO.")
            df_sorted = df.dropna(subset=FEATURE_COLS + [TARGET_COL]).sort_values("datetime")
            split = int(len(df_sorted) * 0.8)
            train_ts = df_sorted.iloc[:split]
            test_ts  = df_sorted.iloc[split:]
            ts_model = xgb.XGBRegressor(**XGB_PARAMS)
            ts_model.fit(train_ts[FEATURE_COLS], train_ts[TARGET_COL], verbose=False)
            y_pred_ts = np.clip(ts_model.predict(test_ts[FEATURE_COLS]), 0, 1500)
            y_true_ts = test_ts[TARGET_COL].values
            # Persistence baseline: last known value
            persist_pred = test_ts[TARGET_COL].shift(1).bfill().values
            ts_rmse   = rmse(y_true_ts, y_pred_ts)
            ts_mae    = mae(y_true_ts, y_pred_ts)
            pers_rmse = rmse(y_true_ts, persist_pred)
            pers_mae  = mae(y_true_ts, persist_pred)
            eval_results = {
                "method": "time_split_80_20",
                "overall": {
                    "model_rmse":    round(ts_rmse,   2),
                    "model_mae":     round(ts_mae,    2),
                    "nn_rmse":       round(pers_rmse, 2),  # persistence baseline
                    "nn_mae":        round(pers_mae,  2),
                    "idw_rmse":      round(pers_rmse, 2),
                    "idw_mae":       round(pers_mae,  2),
                    "n_predictions": len(y_true_ts),
                    "n_stations":    1,
                    "note": "Single-station dataset; evaluated via 80/20 time split. Persistence baseline used instead of nearest-station.",
                },
            }
            print(f"  Time-split RMSE: {ts_rmse:.1f}  Persistence baseline: {pers_rmse:.1f}")
        with open(out / "eval_results.json", "w") as f:
            json.dump(eval_results, f, indent=2)

    # Train final model
    model = train_final_model(df)
    model_path = out / "nowcast_model.ubj"
    model.save_model(str(model_path))
    print(f"Model saved: {model_path}")

    # SHAP on a random sample
    df_clean = df.dropna(subset=FEATURE_COLS)
    sample = df_clean.sample(min(200, len(df_clean)), random_state=42)
    shap_df = compute_shap_for_sample(model, sample[FEATURE_COLS])
    shap_path = out / "shap_sample.parquet"
    shap_df.to_parquet(shap_path)
    print(f"SHAP sample saved: {shap_path}")

    # Feature importance summary
    importance = dict(zip(FEATURE_COLS, model.feature_importances_.tolist()))
    with open(out / "feature_importance.json", "w") as f:
        json.dump(importance, f, indent=2)

    # Upload to S3
    if args.upload:
        s3 = boto3.client("s3", region_name=REGION)
        for p in [model_path, out / "eval_results.json", out / "data_window.json",
                  out / "feature_importance.json", shap_path]:
            if p.exists():
                key = f"nowcast/{p.name}"
                print(f"Uploading {p.name} to s3://{MODELS_BUCKET}/{key}")
                s3.upload_file(str(p), MODELS_BUCKET, key)

    print("\nDone. Evaluation results:")
    if eval_results.get("overall"):
        o = eval_results["overall"]
        print(f"  Model RMSE: {o['model_rmse']} µg/m³")
        print(f"  NN baseline RMSE: {o['nn_rmse']} µg/m³")
        print(f"  IDW baseline RMSE: {o['idw_rmse']} µg/m³")


if __name__ == "__main__":
    main()
