"""
/estimate Lambda handler — Explainable Street-Level AQI
Fetches live weather from Open-Meteo (no key needed), runs XGBoost inference
from S3-stored model, produces SHAP drivers, and optionally calls Bedrock
for natural-language explanation.

MOCK_MODE env var:
  "true"  → return canned response (Tier 0)
  "false" → full pipeline (Tier 1+)
"""
import json
import os
import math
import urllib.request
import urllib.parse
import boto3
from datetime import datetime, timezone, timedelta

IST_OFFSET = timedelta(hours=5, minutes=30)

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
REGION = os.environ.get("AWS_REGION", "ap-south-1")
DYNAMODB_CACHE_TABLE = os.environ.get("DYNAMODB_CACHE_TABLE", "aqi-cache")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
SAGEMAKER_ENDPOINT = os.environ.get("SAGEMAKER_ENDPOINT", "")

# ── AQI category bands (CPCB) ─────────────────────────────────────────────────
def pm25_to_category(pm25: float) -> str:
    if pm25 <= 30:    return "Good"
    if pm25 <= 60:    return "Satisfactory"
    if pm25 <= 90:    return "Moderate"
    if pm25 <= 120:   return "Poor"
    if pm25 <= 250:   return "Very Poor"
    return "Severe"

ADVICE = {
    "Good":         "Air quality is acceptable for most outdoor activity.",
    "Satisfactory": "Air quality is acceptable for most outdoor activity.",
    "Moderate":     "Sensitive groups may want to limit long outdoor exertion.",
    "Poor":         "Limit prolonged outdoor activity, especially for children and older adults.",
    "Very Poor":    "Avoid outdoor exercise. Sensitive groups should stay indoors.",
    "Severe":       "Stay indoors where possible and avoid outdoor activity.",
}

# ── driver lookup: feature name → human-readable note ─────────────────────────
DRIVER_NOTES = {
    "wind_speed":          "low wind trapping pollutants",
    "nearby_station_avg":  "surrounding stations reading high",
    "hour_of_day":         "evening traffic peak",
    "humidity":            "high humidity amplifying particle concentration",
    "temperature":         "temperature inversion limiting dispersion",
    "road_density":        "high road density from nearby traffic",
    "fire_count":          "active fire detections upwind",
    "aod":                 "elevated aerosol optical depth",
    "boundary_layer":      "shallow boundary layer trapping pollutants",
    "day_of_week":         "weekday traffic pattern",
    "surface_pressure":    "surface pressure affecting dispersion",
    "wind_direction":      "wind direction from pollution sources",
    "is_morning_peak":     "morning traffic peak",
    "is_evening_peak":     "evening traffic peak",
    "is_weekend":          "weekend traffic reduction",
    "month":               "seasonal pollution pattern",
}

# ── mock response (Tier 0) ─────────────────────────────────────────────────────
MOCK_RESPONSE = {
    "pm25": 184.2,
    "category": "Very Poor",
    "confidence": "medium",
    "nearest_station_km": 3.1,
    "drivers": [
        {"feature": "wind_speed",        "shap": 32.0, "note": "low wind trapping pollutants"},
        {"feature": "nearby_station_avg","shap": 28.0, "note": "surrounding stations reading high"},
        {"feature": "hour_of_day",       "shap": 11.0, "note": "evening traffic peak"},
    ],
    "explanation": "Low wind and high readings at nearby stations are associated with elevated PM2.5 at this location.",
    "advice": "Avoid outdoor exercise. Sensitive groups should stay indoors.",
    "explanation_source": "mock",
}

# ── CORS headers ───────────────────────────────────────────────────────────────
CORS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}

# ── cache helpers ──────────────────────────────────────────────────────────────
def cache_key(lat: float, lon: float, hour: str, lang: str) -> str:
    rlat = round(lat * 100) / 100
    rlon = round(lon * 100) / 100
    return f"{rlat}#{rlon}#{hour}#{lang}"

def get_cache(key: str):
    try:
        ddb = boto3.resource("dynamodb", region_name=REGION)
        table = ddb.Table(DYNAMODB_CACHE_TABLE)
        resp = table.get_item(Key={"pk": key})
        item = resp.get("Item")
        if item:
            return json.loads(item["payload"])
    except Exception:
        pass
    return None

def put_cache(key: str, payload: dict, ttl_seconds: int = 3600):
    try:
        ddb = boto3.resource("dynamodb", region_name=REGION)
        table = ddb.Table(DYNAMODB_CACHE_TABLE)
        expires = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
        table.put_item(Item={"pk": key, "payload": json.dumps(payload), "ttl": expires})
    except Exception:
        pass

# ── Live weather from Open-Meteo (no API key needed) ──────────────────────────
def fetch_live_weather(lat: float, lon: float) -> dict:
    """
    Fetch the most recent hourly weather from Open-Meteo forecast API.
    Returns a feature dict with temperature, humidity, wind_speed, etc.
    """
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "surface_pressure",
            "boundary_layer_height",
        ]),
        "forecast_days": 1,
        "timezone": "Asia/Kolkata",
        "wind_speed_unit": "ms",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return {}
        # Open-Meteo returns times in Asia/Kolkata when timezone=Asia/Kolkata
        # Compare with current IST time (UTC+5:30)
        now_ist = datetime.now(timezone.utc) + IST_OFFSET
        now_str = now_ist.strftime("%Y-%m-%dT%H:00")
        # Find closest past time index
        idx = 0
        for i, t in enumerate(times):
            if t <= now_str:
                idx = i
        return {
            "temperature":      _safe(hourly.get("temperature_2m", []), idx),
            "humidity":         _safe(hourly.get("relative_humidity_2m", []), idx),
            "wind_speed":       _safe(hourly.get("wind_speed_10m", []), idx),
            "wind_direction":   _safe(hourly.get("wind_direction_10m", []), idx),
            "surface_pressure": _safe(hourly.get("surface_pressure", []), idx),
            "boundary_layer":   _safe(hourly.get("boundary_layer_height", []), idx),
        }
    except Exception as e:
        print(f"Open-Meteo fetch failed: {e}")
        return {}

def _safe(lst, idx):
    try:
        v = lst[idx]
        return float(v) if v is not None else float("nan")
    except Exception:
        return float("nan")

# ── Nearest stations from S3 ───────────────────────────────────────────────────
_STATIONS_CACHE = None
_STATIONS_BUCKET = os.environ.get("STATIONS_S3_BUCKET", "aqi-features-991166714312")
_STATIONS_KEY    = os.environ.get("STATIONS_S3_KEY",    "stations/delhi_latest.json")

def load_stations() -> list:
    global _STATIONS_CACHE
    if _STATIONS_CACHE is not None:
        return _STATIONS_CACHE
    try:
        s3 = boto3.client("s3", region_name=REGION)
        obj = s3.get_object(Bucket=_STATIONS_BUCKET, Key=_STATIONS_KEY)
        _STATIONS_CACHE = json.loads(obj["Body"].read())
        print(f"Loaded {len(_STATIONS_CACHE)} stations from S3")
    except Exception as e:
        print(f"Could not load stations from S3: {e}")
        _STATIONS_CACHE = []
    return _STATIONS_CACHE

def nearest_station_features(lat: float, lon: float) -> dict:
    """
    Compute IDW and neighbor features from live station readings.
    Returns nearest_station_km, nearby_station_avg, nearby_station_idw.
    """
    stations = load_stations()
    if not stations:
        return {"nearest_station_km": 999.0, "nearby_station_avg": float("nan"),
                "nearby_station_idw": float("nan"), "neighbor_spread": float("nan")}

    dists = []
    for st in stations:
        if st.get("pm25") is None:
            continue
        d = haversine_km(lat, lon, st["lat"], st["lon"])
        dists.append((d, st["pm25"]))

    dists.sort(key=lambda x: x[0])
    nearest = dists[:5]

    if not nearest:
        return {"nearest_station_km": 999.0, "nearby_station_avg": float("nan"),
                "nearby_station_idw": float("nan"), "neighbor_spread": float("nan")}

    nearest_km = nearest[0][0]
    vals = [x[1] for x in nearest]
    avg = sum(vals) / len(vals)
    weights = [1.0 / max(x[0], 0.1) for x in nearest]
    idw = sum(v * w for v, w in zip(vals, weights)) / sum(weights)
    spread = (sum((v - avg) ** 2 for v in vals) / len(vals)) ** 0.5

    return {
        "nearest_station_km": round(nearest_km, 2),
        "nearby_station_avg": round(avg, 2),
        "nearby_station_idw": round(idw, 2),
        "neighbor_spread":    round(spread, 2),
    }

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(max(0, a)))

# ── Time features (caller must pass an IST datetime) ──────────────────────────
def time_features(dt_ist: datetime) -> dict:
    """dt_ist must already be in IST (UTC+5:30) so peak-hour flags are correct."""
    return {
        "hour_of_day":    dt_ist.hour,
        "day_of_week":    dt_ist.weekday(),
        "month":          dt_ist.month,
        "is_weekend":     int(dt_ist.weekday() >= 5),
        "is_morning_peak":int(dt_ist.hour in [7, 8, 9, 10]),
        "is_evening_peak":int(dt_ist.hour in [17, 18, 19, 20]),
    }

# ── Road density (static lookup — expand as needed) ───────────────────────────
ROAD_DENSITY_LOOKUP = {
    # Approximate km of road within 1km radius for known areas of Delhi
    # Generated once from OSM Overpass; static for Lambda cold path
    "default": 5.2,
}
def road_density_for(lat: float, lon: float) -> float:
    return ROAD_DENSITY_LOOKUP.get("default", 5.2)

# ── Bedrock explanation ────────────────────────────────────────────────────────
def bedrock_explain(drivers: list, category: str, confidence: str):
    try:
        client = boto3.client("bedrock-runtime", region_name=REGION)
        driver_text = "; ".join([f"{d['note']} (SHAP {d['shap']:.1f})" for d in drivers])
        prompt = f"""You are an AQI explainer. Given SHAP drivers for a PM2.5 estimate,
write a short explanation and advice. Return JSON only with keys: explanation, advice.

Rules:
- Use "associated with", never "causes"
- Explanation: max 2 sentences
- Advice: 1 sentence matching the category
- Do not invent causes not in the drivers

Category: {category}
Confidence: {confidence}
Top drivers: {driver_text}"""
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        })
        resp = client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=body.encode("utf-8"),
            contentType="application/json",
            accept="application/json"
        )
        result = json.loads(resp["body"].read())
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        return parsed["explanation"], parsed["advice"], "bedrock"
    except Exception as e:
        print(f"Bedrock failed: {e} — using template fallback")
        return _template_explain(drivers, category), ADVICE.get(category, ""), "fallback"

def _template_explain(drivers: list, category: str) -> str:
    if not drivers:
        return f"Current environmental factors contribute to {category.lower()} air quality across the vicinity."
    notes = [d.get("note", d.get("feature", "")) for d in drivers]
    if len(notes) == 1:
        return f"{notes[0].capitalize()} is the predominant factor associated with {category.lower()} air quality here."
    elif len(notes) == 2:
        return f"{notes[0].capitalize()}, combined with {notes[1]}, is associated with {category.lower()} air quality at this location."
    else:
        return f"{notes[0].capitalize()}, along with {notes[1]} and {notes[2]}, drives the {category.lower()} air quality recorded here."

# ── Main handler ───────────────────────────────────────────────────────────────
def handler(event, context):
    # Log request metadata only — never the full event body (may contain PII / query params)
    http_method = event.get("httpMethod", "UNKNOWN")
    source_ip = (event.get("requestContext") or {}).get("identity", {}).get("sourceIp", "?")
    print(f"Request: {http_method} /estimate from {source_ip}")

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS, "body": ""}

    # Parse body
    try:
        body = json.loads(event.get("body") or "{}")
        lat = float(body["lat"])
        lon = float(body["lon"])
        timestamp = body.get("timestamp", datetime.now(timezone.utc).isoformat())
        lang = body.get("lang", "en")
        audio = body.get("audio", False)
    except (KeyError, ValueError, TypeError) as e:
        return {"statusCode": 400, "headers": CORS,
                "body": json.dumps({"error": "INVALID_REQUEST", "message": str(e)})}

    # Cache lookup
    hour = timestamp[:13]  # e.g. "2026-10-11T14"
    ck = cache_key(lat, lon, hour, lang)
    cached = get_cache(ck)
    if cached:
        cached["cache_hit"] = True
        return {"statusCode": 200, "headers": CORS, "body": json.dumps(cached)}

    # ── Mock mode (Tier 0) ────────────────────────────────────────────────────
    if MOCK_MODE:
        resp_body = dict(MOCK_RESPONSE)
        resp_body["lat"] = lat
        resp_body["lon"] = lon
        resp_body["timestamp"] = timestamp
        put_cache(ck, resp_body)
        return {"statusCode": 200, "headers": CORS, "body": json.dumps(resp_body)}

    # ── Real mode (Tier 1+) ───────────────────────────────────────────────────
    inference_mode = "unknown"  # set in try or except block below
    try:
        # Parse the request timestamp for time features
        try:
            req_dt_utc = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except Exception:
            req_dt_utc = datetime.now(timezone.utc)
        # Convert to IST so hour-of-day and peak flags are Delhi local
        req_dt_ist = req_dt_utc.astimezone(timezone(IST_OFFSET))

        # Build feature vector
        weather = fetch_live_weather(lat, lon)
        station_feats = nearest_station_features(lat, lon)
        t_feats = time_features(req_dt_ist)

        features = {
            **weather,
            **station_feats,
            **t_feats,
            "road_density": road_density_for(lat, lon),
            "fire_count": float("nan"),
            "aod": float("nan"),
            "lat": lat,
            "lon": lon,
            "timestamp": timestamp,
        }

        # Inference
        if SAGEMAKER_ENDPOINT:
            import lambda_inference as li
            pm25, drivers, confidence, nearest_km = li.predict(features)
        else:
            import lambda_inference as li
            pm25, drivers, confidence, nearest_km = li.predict(features)
        inference_mode = "xgboost"

    except Exception as e:
        import traceback
        print(f"Prediction pipeline failed: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        # Graceful fallback — use IDW from stations if available
        if "station_feats" not in locals():
            station_feats = nearest_station_features(lat, lon)
        if "weather" not in locals():
            weather = fetch_live_weather(lat, lon)
        if "req_dt_ist" not in locals():
            req_dt_ist = datetime.now(timezone(IST_OFFSET))
        if "t_feats" not in locals():
            t_feats = time_features(req_dt_ist)

        idw = station_feats.get("nearby_station_idw", MOCK_RESPONSE["pm25"])
        pm25 = idw if (idw and not math.isnan(idw)) else MOCK_RESPONSE["pm25"]
        nearest_km = station_feats.get("nearest_station_km", 999.0)
        confidence = "high" if nearest_km <= 3.0 else ("medium" if nearest_km <= 8.0 else "low")

        drivers = []
        avg = station_feats.get("nearby_station_avg", pm25)
        drivers.append({
            "feature": "nearby_station_avg",
            "shap": round(pm25 * 0.45, 1),
            "note": f"surrounding stations averaging {round(avg)} µg/m³"
        })

        wind = weather.get("wind_speed", float("nan"))
        if not math.isnan(wind):
            if wind < 2.5:
                drivers.append({
                    "feature": "wind_speed",
                    "shap": round(pm25 * 0.22, 1),
                    "note": f"stagnant wind ({round(wind, 1)} m/s) trapping particulates"
                })
            else:
                drivers.append({
                    "feature": "wind_speed",
                    "shap": round(-pm25 * 0.15, 1),
                    "note": f"active breeze ({round(wind, 1)} m/s) aiding dispersion"
                })

        hum = weather.get("humidity", float("nan"))
        if not math.isnan(hum):
            if hum > 65:
                drivers.append({
                    "feature": "humidity",
                    "shap": round(pm25 * 0.18, 1),
                    "note": f"high humidity ({round(hum)}%) condensing airborne particles"
                })
            elif hum < 35:
                drivers.append({
                    "feature": "humidity",
                    "shap": round(-pm25 * 0.10, 1),
                    "note": f"dry air ({round(hum)}%) facilitating dispersal"
                })

        if t_feats.get("is_evening_peak"):
            drivers.append({
                "feature": "is_evening_peak",
                "shap": round(pm25 * 0.15, 1),
                "note": "evening commute vehicular emissions peak"
            })
        elif t_feats.get("is_morning_peak"):
            drivers.append({
                "feature": "is_morning_peak",
                "shap": round(pm25 * 0.15, 1),
                "note": "morning rush hour traffic peak"
            })
        else:
            drivers.append({
                "feature": "road_density",
                "shap": round(pm25 * 0.10, 1),
                "note": "urban road network and local activity"
            })

        drivers.sort(key=lambda d: abs(d["shap"]), reverse=True)
        drivers = drivers[:3]
        inference_mode = "idw_fallback"

    category = pm25_to_category(pm25)
    explanation, advice, source = bedrock_explain(drivers, category, confidence)

    resp_body = {
        "pm25":              round(float(pm25), 1),
        "category":          category,
        "confidence":        confidence,
        "nearest_station_km":nearest_km,
        "drivers":           drivers,
        "explanation":       explanation,
        "advice":            advice,
        "explanation_source":source,
        "inference_mode":    inference_mode,
        "lat":               lat,
        "lon":               lon,
        "timestamp":         timestamp,
    }

    put_cache(ck, resp_body)
    return {"statusCode": 200, "headers": CORS, "body": json.dumps(resp_body)}
