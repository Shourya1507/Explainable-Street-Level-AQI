#!/usr/bin/env python3
"""
deploy_real_mode.py
Packages and redeploys both Lambda functions with MOCK_MODE=false.
Also optionally sets OPENAQ_API_KEY as an environment variable.

Usage:
  python deploy_real_mode.py
  python deploy_real_mode.py --openaq-key YOUR_KEY
"""
import argparse
import io
import os
import sys
import zipfile
import tempfile
from pathlib import Path
import boto3

PROFILE    = "Shourya Sankrit"
REGION     = "ap-south-1"
ACCOUNT_ID = "991166714312"
MODELS_BUCKET   = f"aqi-models-{ACCOUNT_ID}"
FEATURES_BUCKET = f"aqi-features-{ACCOUNT_ID}"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Lambda function names
ESTIMATE_FUNCTION = "aqi-estimate"
STATIONS_FUNCTION = "aqi-stations"

# Lambda source directories
ESTIMATE_DIR = PROJECT_ROOT / "backend" / "lambda" / "estimate"
STATIONS_DIR = PROJECT_ROOT / "backend" / "lambda" / "stations"


def make_zip(source_dir: Path) -> bytes:
    """Create a zip of all .py files in source_dir, returning raw bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in source_dir.glob("*.py"):
            zf.write(f, f.name)
            print(f"    + {f.name}")
    buf.seek(0)
    return buf.read()


def update_function_code(lam, function_name: str, zip_bytes: bytes):
    resp = lam.update_function_code(
        FunctionName=function_name,
        ZipFile=zip_bytes,
    )
    print(f"  Code updated: {resp['CodeSize']} bytes, SHA256: {resp['CodeSha256'][:12]}...")
    # Wait for update to complete before updating config
    waiter = lam.get_waiter("function_updated")
    waiter.wait(FunctionName=function_name)
    print(f"  Code update propagated")


def update_env_vars(lam, function_name: str, env_updates: dict):
    """Merge env_updates into existing env vars for the function."""
    current = lam.get_function_configuration(FunctionName=function_name)
    existing_env = current.get("Environment", {}).get("Variables", {})
    merged = {**existing_env, **env_updates}
    lam.update_function_configuration(
        FunctionName=function_name,
        Environment={"Variables": merged},
    )
    # Wait for config update
    waiter = lam.get_waiter("function_updated")
    waiter.wait(FunctionName=function_name)
    print(f"  Env vars updated: {list(env_updates.keys())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--openaq-key", default=os.environ.get("OPENAQ_API_KEY", ""),
                        help="OpenAQ API key to inject into Lambda env vars")
    args = parser.parse_args()

    try:
        sess = boto3.Session(profile_name=PROFILE, region_name=REGION)
    except Exception:
        sess = boto3.Session(region_name=REGION)
    lam = sess.client("lambda")

    # ── Deploy aqi-estimate ───────────────────────────────────────────────────
    print(f"\n=== Deploying {ESTIMATE_FUNCTION} ===")
    print(f"  Zipping {ESTIMATE_DIR} ...")
    estimate_zip = make_zip(ESTIMATE_DIR)
    update_function_code(lam, ESTIMATE_FUNCTION, estimate_zip)

    estimate_env = {
        "MOCK_MODE":           "false",
        "DYNAMODB_CACHE_TABLE":"aqi-cache",
        "MODELS_BUCKET":       MODELS_BUCKET,
        "MODEL_KEY":           "nowcast/nowcast_model.ubj",
        "STATIONS_S3_BUCKET":  FEATURES_BUCKET,
        "STATIONS_S3_KEY":     "stations/delhi_latest.json",
    }
    if args.openaq_key:
        estimate_env["OPENAQ_API_KEY"] = args.openaq_key
    update_env_vars(lam, ESTIMATE_FUNCTION, estimate_env)

    # ── Deploy aqi-stations ───────────────────────────────────────────────────
    print(f"\n=== Deploying {STATIONS_FUNCTION} ===")
    print(f"  Zipping {STATIONS_DIR} ...")
    stations_zip = make_zip(STATIONS_DIR)
    update_function_code(lam, STATIONS_FUNCTION, stations_zip)

    stations_env = {
        "MOCK_MODE":          "false",
        "STATIONS_S3_BUCKET": FEATURES_BUCKET,
        "STATIONS_S3_KEY":    "stations/delhi_latest.json",
    }
    if args.openaq_key:
        stations_env["OPENAQ_API_KEY"] = args.openaq_key
    update_env_vars(lam, STATIONS_FUNCTION, stations_env)

    print("\n=== Deployment complete! ===")
    api_url = f"https://6diafyett2.execute-api.{REGION}.amazonaws.com/dev"
    print(f"  API Base: {api_url}")
    print(f"  Stations: GET  {api_url}/stations")
    print(f"  Estimate: POST {api_url}/estimate")
    print()
    print("Test:")
    print(f'  curl -s "{api_url}/stations" | python -m json.tool | head -30')
    print(f'  curl -s -X POST "{api_url}/estimate" -H "Content-Type: application/json" \\')
    print(f'       -d \'{{"lat":28.6139,"lon":77.2090}}\' | python -m json.tool')


if __name__ == "__main__":
    main()
