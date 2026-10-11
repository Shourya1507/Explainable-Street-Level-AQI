"""
/estimate Lambda handler — Explainable Street-Level AQI
Tier 0: returns a mocked response so the front end can build against a real API contract.
Tier 1+: switch MOCK_MODE = False after the real ML endpoint is deployed.
"""
import json
import os
import math
import boto3
from datetime import datetime, timezone

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
REGION = os.environ.get("AWS_REGION", "ap-south-1")
DYNAMODB_CACHE_TABLE = os.environ.get("DYNAMODB_CACHE_TABLE", "aqi-cache")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
SAGEMAKER_ENDPOINT = os.environ.get("SAGEMAKER_ENDPOINT", "")

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
}

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

# ── mock response ─────────────────────────────────────────────────────────────
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

# ── cache helpers ─────────────────────────────────────────────────────────────
def cache_key(lat: float, lon: float, hour: str, lang: str) -> str:
    """Round to ~1km grid for cache efficiency."""
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

# ── Bedrock explanation ───────────────────────────────────────────────────────
def bedrock_explain(drivers: list, category: str, confidence: str) -> tuple[str, str, str]:
    """Returns (explanation, advice, source). Falls back to template on any error."""
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
        return _template_explain(drivers, category), ADVICE[category], "fallback"

def _template_explain(drivers: list, category: str) -> str:
    notes = [d["note"] for d in drivers[:2]]
    return f"{' and '.join(notes).capitalize()} are associated with the {category.lower()} air quality at this location."

# ── SageMaker inference ───────────────────────────────────────────────────────
def sagemaker_predict(features: dict) -> tuple[float, list]:
    """Returns (pm25, drivers). Falls back to mock on error."""
    if not SAGEMAKER_ENDPOINT:
        raise ValueError("No SageMaker endpoint configured")
    client = boto3.client("sagemaker-runtime", region_name=REGION)
    resp = client.invoke_endpoint(
        EndpointName=SAGEMAKER_ENDPOINT,
        ContentType="application/json",
        Body=json.dumps(features)
    )
    result = json.loads(resp["Body"].read())
    return result["pm25"], result["drivers"]

# ── main handler ─────────────────────────────────────────────────────────────
def handler(event, context):
    print(f"Event: {json.dumps(event)}")

    # CORS headers
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
    }

    # Pre-flight
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": ""}

    # Parse body
    try:
        body = json.loads(event.get("body") or "{}")
        lat = float(body["lat"])
        lon = float(body["lon"])
        timestamp = body.get("timestamp", datetime.now(timezone.utc).isoformat())
        lang = body.get("lang", "en")
        audio = body.get("audio", False)
    except (KeyError, ValueError, TypeError) as e:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "INVALID_REQUEST", "message": str(e)})
        }

    # Cache lookup
    hour = timestamp[:13]  # "2026-10-10T18"
    ck = cache_key(lat, lon, hour, lang)
    cached = get_cache(ck)
    if cached:
        cached["cache_hit"] = True
        return {"statusCode": 200, "headers": headers, "body": json.dumps(cached)}

    # ── Mock mode (Tier 0) ────────────────────────────────────────────────────
    if MOCK_MODE:
        resp_body = dict(MOCK_RESPONSE)
        resp_body["lat"] = lat
        resp_body["lon"] = lon
        resp_body["timestamp"] = timestamp
        put_cache(ck, resp_body)
        return {"statusCode": 200, "headers": headers, "body": json.dumps(resp_body)}

    # ── Real mode (Tier 1+) ───────────────────────────────────────────────────
    try:
        # Build feature vector for inference
        features = {"lat": lat, "lon": lon, "timestamp": timestamp}
        if SAGEMAKER_ENDPOINT:
            pm25, drivers = sagemaker_predict(features)
            nearest_km = 999.0 # or some logic to get nearest_km
            confidence = "medium"
        else:
            import lambda_inference
            pm25, drivers, confidence, nearest_km = lambda_inference.predict(features)
    except Exception as e:
        print(f"Prediction failed: {e}")
        # Fallback: mock values until model is ready
        pm25 = MOCK_RESPONSE["pm25"]
        drivers = MOCK_RESPONSE["drivers"]
        nearest_km = MOCK_RESPONSE["nearest_station_km"]
        confidence = MOCK_RESPONSE["confidence"]

    category = pm25_to_category(pm25)
    explanation, advice, source = bedrock_explain(drivers, category, confidence)

    resp_body = {
        "pm25": round(pm25, 1),
        "category": category,
        "confidence": confidence,
        "nearest_station_km": nearest_km,
        "drivers": drivers,
        "explanation": explanation,
        "advice": advice,
        "explanation_source": source,
        "lat": lat,
        "lon": lon,
        "timestamp": timestamp,
    }

    put_cache(ck, resp_body)
    return {"statusCode": 200, "headers": headers, "body": json.dumps(resp_body)}
