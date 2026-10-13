"""
/stations Lambda handler — returns station markers for the map.
In mock mode: returns hardcoded Delhi CPCB stations.
In live mode: reads from S3 (refreshed by the stations-refresher job or
              falls back to the latest local archive data).
"""
import json
import os
import math
import urllib.request
import urllib.parse
import boto3
from datetime import datetime, timezone

ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "")
MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
REGION = os.environ.get("AWS_REGION", "ap-south-1")
STATIONS_S3_BUCKET = os.environ.get("STATIONS_S3_BUCKET", f"aqi-features-{ACCOUNT_ID}" if ACCOUNT_ID else "aqi-features")
STATIONS_S3_KEY    = os.environ.get("STATIONS_S3_KEY",    "stations/delhi_latest.json")
OPENAQ_API_KEY     = os.environ.get("OPENAQ_API_KEY", "")
ALLOWED_ORIGIN     = os.environ.get("ALLOWED_ORIGIN", "*")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key,Authorization",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}

# Known Delhi OpenAQ location IDs → station metadata
STATION_META = {
    8188: {"id": "in-oaq-8188", "name": "Anand Vihar",   "lat": 28.6469, "lon": 77.3161},
    8189: {"id": "in-oaq-8189", "name": "IGI Airport",    "lat": 28.5562, "lon": 77.1000},
    8190: {"id": "in-oaq-8190", "name": "Punjabi Bagh",   "lat": 28.6714, "lon": 77.1313},
    8191: {"id": "in-oaq-8191", "name": "RK Puram",       "lat": 28.5644, "lon": 77.1749},
    8192: {"id": "in-oaq-8192", "name": "Siri Fort",      "lat": 28.5498, "lon": 77.2173},
    8193: {"id": "in-oaq-8193", "name": "Mandir Marg",    "lat": 28.6358, "lon": 77.1978},
    8194: {"id": "in-oaq-8194", "name": "Lodhi Road",     "lat": 28.5928, "lon": 77.2170},
    8195: {"id": "in-oaq-8195", "name": "Shadipur",       "lat": 28.6507, "lon": 77.1518},
    8196: {"id": "in-oaq-8196", "name": "Wazirpur",       "lat": 28.6959, "lon": 77.1603},
    8197: {"id": "in-oaq-8197", "name": "NSIT Dwarka",    "lat": 28.6127, "lon": 77.0265},
    8198: {"id": "in-oaq-8198", "name": "Okhla Phase 2",  "lat": 28.5356, "lon": 77.2706},
    8199: {"id": "in-oaq-8199", "name": "Rohini",         "lat": 28.7395, "lon": 77.1194},
    8200: {"id": "in-oaq-8200", "name": "Dwarka Sec 8",   "lat": 28.5870, "lon": 77.0480},
    8201: {"id": "in-oaq-8201", "name": "Vivek Vihar",    "lat": 28.6711, "lon": 77.3100},
    8202: {"id": "in-oaq-8202", "name": "IITD Pusa",      "lat": 28.6412, "lon": 77.1535},
}

# Mock Delhi CPCB stations — real coordinates, names match OpenAQ
MOCK_STATIONS = [
    {"id": "in-cpcb-igi",      "name": "IGI Airport",   "lat": 28.5562, "lon": 77.1000, "pm25": 142.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-anand",    "name": "Anand Vihar",   "lat": 28.6469, "lon": 77.3161, "pm25": 198.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-dwarka",   "name": "Dwarka Sec 8",  "lat": 28.5870, "lon": 77.0480, "pm25": 110.0, "category": "Poor",       "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-punjabi",  "name": "Punjabi Bagh",  "lat": 28.6714, "lon": 77.1313, "pm25": 175.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-rohini",   "name": "Rohini",        "lat": 28.7395, "lon": 77.1194, "pm25": 160.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-ncit",     "name": "NSIT Dwarka",   "lat": 28.6127, "lon": 77.0265, "pm25": 125.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-okhla",    "name": "Okhla Phase 2", "lat": 28.5356, "lon": 77.2706, "pm25": 168.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-r3g",      "name": "R K Puram",     "lat": 28.5644, "lon": 77.1749, "pm25": 155.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-sir",      "name": "Siri Fort",     "lat": 28.5498, "lon": 77.2173, "pm25": 143.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-mandir",   "name": "Mandir Marg",   "lat": 28.6358, "lon": 77.1978, "pm25": 132.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-lodhi",    "name": "Lodhi Road",    "lat": 28.5928, "lon": 77.2170, "pm25": 122.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-shadipur", "name": "Shadipur",      "lat": 28.6507, "lon": 77.1518, "pm25": 188.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-wazirpur", "name": "Wazirpur",      "lat": 28.6959, "lon": 77.1603, "pm25": 202.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-pusa",     "name": "IITD Pusa",     "lat": 28.6412, "lon": 77.1535, "pm25": 145.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-vivek",    "name": "Vivek Vihar",   "lat": 28.6711, "lon": 77.3100, "pm25": 192.0, "category": "Very Poor",  "updated": "2026-10-10T17:00:00+05:30"},
]


def pm25_to_category(pm25: float) -> str:
    if pm25 <= 30:    return "Good"
    if pm25 <= 60:    return "Satisfactory"
    if pm25 <= 90:    return "Moderate"
    if pm25 <= 120:   return "Poor"
    if pm25 <= 250:   return "Very Poor"
    return "Severe"


def fetch_openaq_latest(loc_id: int, api_key: str) -> tuple:
    """Returns (pm25, updated_iso) or (None, None) on failure."""
    url = f"https://api.openaq.org/v3/locations/{loc_id}/latest"
    headers_pairs = []
    if api_key:
        headers_pairs.append(("X-API-Key", api_key))
    try:
        req = urllib.request.Request(url, headers=dict(headers_pairs))
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        for r in results:
            param = r.get("parameter", {})
            pname = param.get("name", "") if isinstance(param, dict) else str(param)
            if pname in ("pm25", "pm2.5"):
                val = r.get("value")
                ts = r.get("lastUpdated") or r.get("datetime", {})
                if isinstance(ts, dict):
                    updated = ts.get("local", ts.get("utc", ""))
                else:
                    updated = str(ts)
                if val is not None and val >= 0:
                    return float(val), updated
    except Exception as e:
        print(f"OpenAQ fetch failed for loc {loc_id}: {e}")
    return None, None


def fetch_live_stations(api_key: str) -> list:
    """Fetch current readings from OpenAQ v3 and write to S3."""
    now_iso = datetime.now(timezone.utc).isoformat()
    stations = []
    for loc_id, meta in STATION_META.items():
        pm25, updated = fetch_openaq_latest(loc_id, api_key)
        if pm25 is None:
            continue
        stations.append({
            **meta,
            "pm25": round(pm25, 1),
            "category": pm25_to_category(pm25),
            "updated": updated or now_iso,
            "source": "openaq_v3_live",
        })
        print(f"  Live: {meta['name']} = {pm25:.1f} µg/m³")

    if stations:
        # Write fresh data to S3 for caching
        try:
            s3 = boto3.client("s3", region_name=REGION)
            s3.put_object(
                Bucket=STATIONS_S3_BUCKET,
                Key=STATIONS_S3_KEY,
                Body=json.dumps(stations).encode("utf-8"),
                ContentType="application/json",
            )
            print(f"Cached {len(stations)} stations to S3")
        except Exception as e:
            print(f"S3 write failed: {e}")

    return stations


def read_stations_from_s3() -> list:
    """Read the cached stations JSON from S3."""
    try:
        s3 = boto3.client("s3", region_name=REGION)
        obj = s3.get_object(Bucket=STATIONS_S3_BUCKET, Key=STATIONS_S3_KEY)
        return json.loads(obj["Body"].read())
    except Exception as e:
        print(f"S3 read failed: {e}")
        return []


def handler(event, context):
    print(f"Event: {json.dumps(event)}")

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    qsp = event.get("queryStringParameters") or {}
    city = qsp.get("city", "delhi")
    force_refresh = qsp.get("refresh", "false").lower() == "true"

    # ── Mock mode ─────────────────────────────────────────────────────────────
    if MOCK_MODE:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"stations": MOCK_STATIONS, "city": city, "source": "mock"})
        }

    # ── Live mode ─────────────────────────────────────────────────────────────
    stations = []

    # Try reading from S3 first (fast path)
    if not force_refresh:
        stations = read_stations_from_s3()
        if stations:
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"stations": stations, "city": city, "source": "s3_cache"})
            }

    # Fetch live from OpenAQ if S3 is empty / stale or refresh forced
    if OPENAQ_API_KEY:
        stations = fetch_live_stations(OPENAQ_API_KEY)

    # Hard fallback: mock data
    if not stations:
        print("No live data available — returning mock fallback")
        stations = MOCK_STATIONS

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "stations": stations,
            "city": city,
            "source": "live" if stations and stations[0].get("source") == "openaq_v3_live" else "fallback",
        })
    }
