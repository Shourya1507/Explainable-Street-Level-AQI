"""
/stations Lambda handler — returns station markers for the map.
In mock mode, returns hardcoded Delhi CPCB stations.
In live mode, reads from S3 or DynamoDB hot store.
"""
import json
import os
import boto3
from datetime import datetime, timezone

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
REGION = os.environ.get("AWS_REGION", "ap-south-1")
STATIONS_S3_BUCKET = os.environ.get("STATIONS_S3_BUCKET", "aqi-features-991166714312")
STATIONS_S3_KEY = os.environ.get("STATIONS_S3_KEY", "stations/delhi_latest.json")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}

# Mock Delhi CPCB stations — real coordinates, names match OpenAQ
MOCK_STATIONS = [
    {"id": "in-cpcb-igi",       "name": "IGI Airport",            "lat": 28.5562, "lon": 77.1000, "pm25": 142.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-anand",     "name": "Anand Vihar",            "lat": 28.6469, "lon": 77.3161, "pm25": 198.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-dwarka",    "name": "Dwarka Sec 8",           "lat": 28.5870, "lon": 77.0480, "pm25": 110.0, "category": "Poor",        "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-punjabi",   "name": "Punjabi Bagh",           "lat": 28.6714, "lon": 77.1313, "pm25": 175.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-rohini",    "name": "Rohini",                 "lat": 28.7395, "lon": 77.1194, "pm25": 160.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-ncit",      "name": "NSIT Dwarka",            "lat": 28.6127, "lon": 77.0265, "pm25": 125.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-okhla",     "name": "Okhla Phase 2",          "lat": 28.5356, "lon": 77.2706, "pm25": 168.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-r3g",       "name": "R K Puram",              "lat": 28.5644, "lon": 77.1749, "pm25": 155.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-sir",       "name": "Siri Fort",              "lat": 28.5498, "lon": 77.2173, "pm25": 143.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-mandir",    "name": "Mandir Marg",            "lat": 28.6358, "lon": 77.1978, "pm25": 132.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-lodhi",     "name": "Lodhi Road",             "lat": 28.5928, "lon": 77.2170, "pm25": 122.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-shadipur",  "name": "Shadipur",               "lat": 28.6507, "lon": 77.1518, "pm25": 188.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-wazirpur",  "name": "Wazirpur",               "lat": 28.6959, "lon": 77.1603, "pm25": 202.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-pusa",      "name": "IITD Pusa",              "lat": 28.6412, "lon": 77.1535, "pm25": 145.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
    {"id": "in-cpcb-vivek",     "name": "Vivek Vihar",            "lat": 28.6711, "lon": 77.3100, "pm25": 192.0, "category": "Very Poor",   "updated": "2026-10-10T17:00:00+05:30"},
]


def handler(event, context):
    print(f"Event: {json.dumps(event)}")

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    city = event.get("queryStringParameters", {}) or {}
    city = city.get("city", "delhi")

    if MOCK_MODE:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"stations": MOCK_STATIONS, "city": city, "source": "mock"})
        }

    # Live: read from S3
    try:
        s3 = boto3.client("s3", region_name=REGION)
        obj = s3.get_object(Bucket=STATIONS_S3_BUCKET, Key=f"stations/{city}_latest.json")
        stations = json.loads(obj["Body"].read())
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"stations": stations, "city": city, "source": "s3"})
        }
    except Exception as e:
        print(f"S3 read failed: {e}, falling back to mock")
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"stations": MOCK_STATIONS, "city": city, "source": "fallback"})
        }
