"""
Feature engineering — Explainable Street-Level AQI
Tier 1: builds the feature table for XGBoost training and serving.

Input: OpenAQ PM2.5 readings + Open-Meteo weather
Output: Parquet feature tables in S3 (aqi-features-<account>/features/delhi/)

CRITICAL leakage rule (rules.md §5.1):
  A station's own reading is NEVER part of its own neighbor features.
  This is enforced in build_neighbor_features() by station_id exclusion.
"""
import argparse
import json
import math
import os
import sys
import gzip
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import boto3

try:
    import pandas as pd
    import numpy as np
    import requests
except ImportError:
    print("Install: pip install pandas numpy requests pyarrow")
    sys.exit(1)

REGION = os.environ.get("AWS_REGION", "ap-south-1")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "")
FEATURES_BUCKET = os.environ.get("FEATURES_BUCKET", f"aqi-features-{ACCOUNT_ID}" if ACCOUNT_ID else "aqi-features")
RAW_BUCKET = os.environ.get("RAW_BUCKET", f"aqi-raw-{ACCOUNT_ID}" if ACCOUNT_ID else "aqi-raw")


# ── Weather fetch (Open-Meteo — no key needed) ────────────────────────────────
def fetch_weather_for_station(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """
    Fetch hourly weather from Open-Meteo historical API.
    Variables: temperature_2m, relative_humidity_2m, wind_speed_10m, wind_direction_10m,
               surface_pressure, boundary_layer_height (if available)
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "surface_pressure",
            "boundary_layer_height",
        ]),
        "timezone": "Asia/Kolkata",
        "wind_speed_unit": "ms",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()["hourly"]
    df = pd.DataFrame(data)
    df["datetime"] = pd.to_datetime(df["time"])
    df = df.drop(columns=["time"])
    df["lat"] = lat
    df["lon"] = lon
    return df


# ── Road density model (calibrated from OpenStreetMap nodes matching inference) ──
ROAD_DENSITY_NODES = [
    (28.6304, 77.2177, 16.5),  # Connaught Place
    (28.6289, 77.2407, 17.2),  # ITO / Ring Road / Delhi Gate
    (28.6506, 77.2303, 15.0),  # Chandni Chowk / Old Delhi
    (28.6514, 77.1907, 14.2),  # Karol Bagh / Pusa Road
    (28.5677, 77.2433, 13.8),  # Lajpat Nagar / Ring Road South
    (28.5494, 77.2528, 14.5),  # Nehru Place / Outer Ring Road
    (28.6469, 77.3160, 15.5),  # Anand Vihar / ISBT East
    (28.7159, 77.1147, 7.8),   # Rohini Sector 1-16
    (28.5921, 77.0460, 8.2),   # Dwarka Sector 6-10
    (28.5562, 77.1000, 9.5),   # IGI Airport / Aerocity
    (28.5355, 77.2732, 11.2),  # Okhla Industrial Area
    (28.8530, 77.0930, 3.8),   # Narela / Outer North
    (28.6092, 76.9798, 3.2),   # Najafgarh / Rural West
    (28.4680, 77.2450, 2.1),   # Asola Bhatti / Southern Ridge
    (28.6600, 77.2600, 3.5),   # Yamuna Floodplains
]

def compute_road_density(lat: float, lon: float, radius_m: float = 1000) -> float:
    """
    Interpolate road density in km/km² using Inverse Distance Weighting (IDW)
    across verified Delhi OSM road network nodes.
    Matches backend/lambda/estimate/handler.py road_density_for exactly.
    """
    weights = []
    values = []
    for n_lat, n_lon, dens in ROAD_DENSITY_NODES:
        d = haversine_km(lat, lon, n_lat, n_lon)
        if d < 0.2:
            return round(dens, 2)
        w = 1.0 / (d ** 2)
        weights.append(w)
        values.append(dens)
    total_w = sum(weights)
    if total_w == 0:
        return 5.2
    est = sum(w * v for w, v in zip(weights, values)) / total_w
    return round(max(1.5, min(est, 20.0)), 2)


# ── Haversine distance ─────────────────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# ── Neighbor features (no leakage) ───────────────────────────────────────────
def build_neighbor_features(
    station_id: str,
    hour_dt: datetime,
    all_stations_pm25: Dict[str, float],  # {station_id: pm25}
    all_stations_coords: Dict[str, Tuple[float, float]],  # {station_id: (lat, lon)}
    target_lat: float,
    target_lon: float,
    max_neighbors: int = 5,
) -> Dict:
    """
    Compute neighbor-based features EXCLUDING the target station.
    LEAKAGE CHECK: station_id is always excluded from its own neighbors.
    """
    neighbors = []
    for s_id, pm25 in all_stations_pm25.items():
        if s_id == station_id:
            continue  # ← CRITICAL: no leakage
        if s_id not in all_stations_coords:
            continue
        s_lat, s_lon = all_stations_coords[s_id]
        dist = haversine_km(target_lat, target_lon, s_lat, s_lon)
        neighbors.append({"id": s_id, "pm25": pm25, "dist_km": dist})

    neighbors.sort(key=lambda x: x["dist_km"])
    nearest = neighbors[:max_neighbors]

    if not nearest:
        return {
            "nearest_station_km": 999.0,
            "nearby_station_avg": float("nan"),
            "nearby_station_idw": float("nan"),
            "neighbor_spread": float("nan"),
        }

    nearest_km = nearest[0]["dist_km"]
    # Simple average of nearest N
    avg = float(np.mean([n["pm25"] for n in nearest]))
    # Inverse-distance-weighted average
    weights = [1.0 / max(n["dist_km"], 0.1) for n in nearest]
    idw = float(np.average([n["pm25"] for n in nearest], weights=weights))
    spread = float(np.std([n["pm25"] for n in nearest]))

    return {
        "nearest_station_km": round(nearest_km, 2),
        "nearby_station_avg": round(avg, 2),
        "nearby_station_idw": round(idw, 2),
        "neighbor_spread": round(spread, 2),
    }


# ── Time features ─────────────────────────────────────────────────────────────
def time_features(dt: datetime) -> Dict:
    return {
        "hour_of_day": dt.hour,
        "day_of_week": dt.weekday(),  # 0=Mon, 6=Sun
        "month": dt.month,
        "is_weekend": int(dt.weekday() >= 5),
        "is_morning_peak": int(dt.hour in [7, 8, 9, 10]),
        "is_evening_peak": int(dt.hour in [17, 18, 19, 20]),
    }


# ── Build full feature table ──────────────────────────────────────────────────
def build_feature_table(
    pm25_df: pd.DataFrame,
    station_coords: Dict[str, Tuple[float, float]],
    weather_df: Dict[str, pd.DataFrame],  # {station_id: weather_df}
    road_density: Dict[str, float],       # {station_id: density}
) -> pd.DataFrame:
    """
    Build the station × hour feature table for training.
    pm25_df columns: station_id, datetime (hour), pm25, lat, lon
    """
    rows = []
    pm25_df["datetime_h"] = pd.to_datetime(pm25_df["datetime"]).dt.floor("h")

    # Group by hour — we need all stations' readings per hour for neighbor features
    for hour, hour_group in pm25_df.groupby("datetime_h"):
        all_pm25 = dict(zip(hour_group["station_id"], hour_group["pm25"]))

        for _, row in hour_group.iterrows():
            sid = row["station_id"]
            lat, lon = row["lat"], row["lon"]
            pm25_val = row["pm25"]

            # Skip impossible values
            if pd.isna(pm25_val) or pm25_val < 0 or pm25_val > 1500:
                continue

            # Neighbor features (leakage-safe)
            neighbor_feats = build_neighbor_features(
                sid, hour, all_pm25, station_coords, lat, lon
            )

            # Time features
            t_feats = time_features(hour)

            # Weather features
            wx = {}
            if sid in weather_df:
                wdf = weather_df[sid]
                hour_wx = wdf[wdf["datetime"].dt.floor("h") == hour]
                if not hour_wx.empty:
                    r = hour_wx.iloc[0]
                    wx = {
                        "temperature":       r.get("temperature_2m", float("nan")),
                        "humidity":          r.get("relative_humidity_2m", float("nan")),
                        "wind_speed":        r.get("wind_speed_10m", float("nan")),
                        "wind_direction":    r.get("wind_direction_10m", float("nan")),
                        "surface_pressure":  r.get("surface_pressure", float("nan")),
                        "boundary_layer":    r.get("boundary_layer_height", float("nan")),
                    }

            feature_row = {
                "station_id": sid,
                "datetime": hour,
                "lat": lat,
                "lon": lon,
                "pm25": pm25_val,
                "road_density": road_density.get(sid, 0.0),
                **neighbor_feats,
                **t_feats,
                **wx,
                # Fire count and AOD — added in Tier 6
                "fire_count":  float("nan"),
                "aod":         float("nan"),
            }
            rows.append(feature_row)

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Build AQI feature table")
    parser.add_argument("--city", default="delhi")
    parser.add_argument("--input-dir", default="./data_pull")
    parser.add_argument("--out-dir", default="./features")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    input_path = Path(args.input_dir)
    
    print("Parsing downloaded OpenAQ files...")
    df_list = []
    station_coords = {}
    
    # Read all csv.gz files in the data_pull directory
    files = list(input_path.glob("*.csv.gz"))
    if not files:
        print(f"No files found in {args.input_dir}. Did you run pull_openaq.py?")
        sys.exit(1)
        
    for f in files:
        try:
            # We assume the CSV has columns: location_id, datetime, value, lat, lon
            # Actually, OpenAQ S3 archive format has specific columns:
            # locationId, location, parameter, value, date.utc, coordinates.latitude, coordinates.longitude
            df = pd.read_csv(f, compression='gzip')
            if df.empty: continue
            
            # Filter to pm25 only if needed (assuming file contains only pm2.5 based on pull_openaq.py)
            if 'parameter' in df.columns:
                df = df[df['parameter'] == 'pm25']
            
            # Rename columns to match what build_feature_table expects
            col_map = {
                'locationId': 'station_id',
                'location_id': 'station_id',
                'date.utc': 'datetime',
                'coordinates.latitude': 'lat',
                'coordinates.longitude': 'lon'
            }
            # Handle if columns are named differently
            for old, new in col_map.items():
                if old in df.columns:
                    df.rename(columns={old: new}, inplace=True)
            
            if 'station_id' not in df.columns:
                # Infer station id from filename if missing
                # e.g. locationid=8188
                sid = f.name.split('locationid=')[1].split('_')[0]
                df['station_id'] = sid
                
            if 'datetime' not in df.columns and 'date_utc' in df.columns:
                df['datetime'] = df['date_utc']
                
            df = df[['station_id', 'datetime', 'value', 'lat', 'lon']].dropna(subset=['value'])
            if df.empty: continue
            
            df.rename(columns={'value': 'pm25'}, inplace=True)
            df['station_id'] = df['station_id'].astype(str)
            df_list.append(df)
            
            # Store coords
            sid = str(df['station_id'].iloc[0])
            lat, lon = df['lat'].iloc[0], df['lon'].iloc[0]
            if sid not in station_coords and not pd.isna(lat) and not pd.isna(lon):
                station_coords[sid] = (lat, lon)
                
        except Exception as e:
            print(f"Error reading {f.name}: {e}")
            
    pm25_df = pd.concat(df_list, ignore_index=True)
    dt_series = pd.to_datetime(pm25_df['datetime'], utc=True)
    pm25_df['datetime'] = dt_series.dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
    
    print(f"Loaded {len(pm25_df)} PM2.5 readings for {len(station_coords)} stations (converted to IST).")
    
    # Compute road density and fetch weather for each station
    weather_df = {}
    road_density = {}
    
    # Get overall start/end dates
    start_date = pm25_df['datetime'].min().strftime('%Y-%m-%d')
    end_date = pm25_df['datetime'].max().strftime('%Y-%m-%d')
    
    for sid, (lat, lon) in station_coords.items():
        print(f"Fetching Open-Meteo weather for station {sid} ({lat}, {lon})")
        try:
            wdf = fetch_weather_for_station(lat, lon, start_date, end_date)
            # Open-Meteo was requested in Asia/Kolkata; ensure timezone-naive for join
            if wdf['datetime'].dt.tz is not None:
                wdf['datetime'] = wdf['datetime'].dt.tz_localize(None)
            weather_df[sid] = wdf
        except Exception as e:
            print(f"Weather fetch failed for {sid}: {e}")
            
        print(f"Estimating road density for {sid}")
        road_density[sid] = compute_road_density(lat, lon)
        
    print("Building full feature table (this takes a moment)...")
    feature_table = build_feature_table(pm25_df, station_coords, weather_df, road_density)
    
    print(f"Built feature table with {len(feature_table)} rows.")
    
    out_file = out / "features_train.parquet"
    feature_table.to_parquet(out_file, index=False)
    print(f"Saved to {out_file}")
    
    if args.upload:
        s3 = boto3.client("s3")
        s3_key = f"features/{args.city}/features_train.parquet"
        print(f"Uploading to s3://{FEATURES_BUCKET}/{s3_key} ...")
        s3.upload_file(str(out_file), FEATURES_BUCKET, s3_key)
        print("Upload complete!")

if __name__ == "__main__":
    main()
