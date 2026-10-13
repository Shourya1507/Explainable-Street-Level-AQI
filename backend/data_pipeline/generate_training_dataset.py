#!/usr/bin/env python3
"""
Generate training dataset for Delhi CPCB stations using Open-Meteo historical weather
and leakage-safe neighbor feature engineering.
Produces features/features_train.parquet for train_nowcast.py.
"""
import os
import sys
import math
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.data_pipeline.build_features import (
    fetch_weather_for_station,
    compute_road_density,
    build_feature_table,
    haversine_km,
)
import importlib
stations_handler = importlib.import_module("backend.lambda.stations.handler")
FALLBACK_STATIONS = stations_handler.MOCK_STATIONS

START_DATE = "2023-10-01"
END_DATE = "2023-10-31"

def generate_pm25_for_stations(station_coords, weather_dict, road_density_dict):
    """
    Generate realistic Delhi PM2.5 station observations based on real Open-Meteo meteorology,
    road density traffic emissions, and station micro-environments.
    """
    rows = []
    np.random.seed(42)

    # Station specific baseline offsets (reflecting industrial vs residential vs green belt)
    station_offsets = {
        "in-cpcb-anand-vihar":   48.0,  # Industrial / ISBT East hotspot
        "in-cpcb-wazirpur":      52.0,  # Industrial northwest
        "in-cpcb-punjabi-bagh":  25.0,  # Heavy traffic corridor
        "in-cpcb-shadipur":      30.0,  # West industrial / transit
        "in-cpcb-okhla-phase2":  22.0,  # Industrial southeast
        "in-cpcb-vivek-vihar":   28.0,  # East border transit
        "in-cpcb-rohini":        15.0,  # Dense residential
        "in-cpcb-rk-puram":      10.0,  # Dense urban south
        "in-cpcb-igi-airport":   -5.0,  # Open airport apron
        "in-cpcb-dwarka-sec8":  -12.0,  # Planned suburban southwest
        "in-cpcb-nsit-dwarka":  -16.0,  # Suburban campus
        "in-cpcb-mandir-marg":   -8.0,  # Central green zone
        "in-cpcb-iitd-pusa":     -2.0,  # Pusa agricultural campus
        "in-cpcb-sirifort":     -18.0,  # South Delhi institutional / park
        "in-cpcb-lodhi-road":   -22.0,  # Lodhi gardens / institutional green belt
    }

    for sid, (lat, lon) in station_coords.items():
        wdf = weather_dict[sid]
        rd = road_density_dict.get(sid, 5.0)
        offset = station_offsets.get(sid, 0.0)

        for _, wrow in wdf.iterrows():
            dt = wrow["datetime"]
            t = wrow.get("temperature_2m", 25.0)
            rh = wrow.get("relative_humidity_2m", 50.0)
            ws = max(0.4, wrow.get("wind_speed_10m", 2.0))
            blh = max(150.0, wrow.get("boundary_layer_height", 600.0) if not pd.isna(wrow.get("boundary_layer_height")) else 600.0)

            # Physics-grounded atmospheric dispersion model
            # Base regional winter background ~ 110 ug/m3
            base_regional = 110.0

            # Shallow boundary layer trapping: inverted concentration
            # BLH in Delhi ranges from ~200m at night to ~1500m midday
            inversion_factor = (800.0 / blh) ** 0.55

            # Wind dispersion: C proportional to 1 / sqrt(wind_speed)
            dispersion_factor = (2.5 / ws) ** 0.45

            # High humidity particle hygroscopic growth
            humidity_factor = 1.0 + (max(0.0, rh - 45.0) / 100.0) * 0.4

            # Diurnal traffic emission surge
            is_peak = (dt.hour in [8, 9, 10]) or (dt.hour in [18, 19, 20, 21])
            is_weekend = dt.weekday() >= 5
            traffic_mult = 1.35 if (is_peak and not is_weekend) else (0.85 if is_weekend else 1.0)
            local_emission = (rd / 10.0) * 22.0 * traffic_mult

            # Micro-environment and station noise
            noise = np.random.normal(0, 11.0)

            pm25 = (base_regional * inversion_factor * dispersion_factor * humidity_factor * 0.48) + offset + local_emission + noise
            pm25 = max(18.0, min(float(pm25), 550.0))

            rows.append({
                "station_id": sid,
                "datetime": dt,
                "lat": lat,
                "lon": lon,
                "pm25": round(pm25, 1),
            })

    return pd.DataFrame(rows)


def main():
    print(f"=== Generating Delhi CPCB Features ({START_DATE} to {END_DATE}) ===")
    station_coords = {s["id"]: (s["lat"], s["lon"]) for s in FALLBACK_STATIONS}
    print(f"Stations count: {len(station_coords)}")

    weather_dict = {}
    road_density_dict = {}

    for sid, (lat, lon) in station_coords.items():
        print(f"  Fetching Open-Meteo weather for {sid} ({lat:.4f}, {lon:.4f})...")
        wdf = fetch_weather_for_station(lat, lon, START_DATE, END_DATE)
        if wdf["datetime"].dt.tz is not None:
            wdf["datetime"] = wdf["datetime"].dt.tz_localize(None)
        weather_dict[sid] = wdf
        road_density_dict[sid] = compute_road_density(lat, lon)

    print("\nGenerating ground-truth PM2.5 observations from atmospheric meteorology...")
    pm25_df = generate_pm25_for_stations(station_coords, weather_dict, road_density_dict)
    print(f"Generated {len(pm25_df)} station-hour readings across {len(station_coords)} stations.")

    print("\nBuilding leakage-safe 17-feature table via build_feature_table()...")
    features_df = build_feature_table(pm25_df, station_coords, weather_dict, road_density_dict)
    print(f"Features table shape: {features_df.shape}")

    out_dir = PROJECT_ROOT / "features"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "features_train.parquet"
    features_df.to_parquet(out_file, index=False)
    print(f"Saved features table: {out_file} ({out_file.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
