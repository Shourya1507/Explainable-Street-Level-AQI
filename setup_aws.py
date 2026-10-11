#!/usr/bin/env python3
"""
setup_aws.py — Run this once to complete Tier 0 AWS setup.

Does:
  1. Creates Amazon Location Service map resource
  2. Stores placeholder secrets in Secrets Manager
  3. Runs `sam build && sam deploy`
  4. Prints the API Gateway URL
  5. Uploads frontend to S3 and creates CloudFront distribution

Usage:
  python setup_aws.py [--openaq-key KEY] [--firms-key KEY]
"""
import argparse
import subprocess
import sys
import json
import os
import boto3

REGION = "ap-south-1"
PROFILE = "Shourya Sankrit"
ACCOUNT_ID = "991166714312"
STACK_NAME = "aqi-backend"
FRONTEND_BUCKET = f"aqi-frontend-{ACCOUNT_ID}"
MODELS_BUCKET = f"aqi-models-{ACCOUNT_ID}"

AWS = ["C:\\Users\\LENOVO\\AppData\\Local\\Programs\\Amazon\\AWSCLIV2\\aws.exe"]


def run(cmd, **kwargs):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"ERROR: exited {result.returncode}")
        sys.exit(result.returncode)
    return result


def boto_client(service):
    import boto3
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    return session.client(service)


def step1_location_service():
    """Create Amazon Location Service map resource."""
    print("\n=== Step 1: Amazon Location Service ===")
    client = boto_client("location")
    map_name = "aqi-delhi-map"
    try:
        client.create_map(
            MapName=map_name,
            Configuration={"Style": "VectorEsriNavigation"},
            Description="AQI Delhi light basemap",
            PricingPlan="RequestBasedUsage",
        )
        print(f"  Created map: {map_name}")
    except client.exceptions.ConflictException:
        print(f"  Map already exists: {map_name}")
    except Exception as e:
        print(f"  Map creation failed: {e} — skipping (MapLibre OSM fallback will be used)")

    # Get the map tile URL
    try:
        resp = client.describe_map(MapName=map_name)
        data_source = resp.get("DataSource", "")
        print(f"  Map data source: {data_source}")
        # The tile endpoint uses the Amplify Location SDK; we'll use the API key method
        # For now, store map name for the frontend
    except Exception as e:
        print(f"  Could not describe map: {e}")


def step2_secrets(openaq_key: str, firms_key: str):
    """Store API keys in Secrets Manager."""
    print("\n=== Step 2: Secrets Manager ===")
    client = boto_client("secretsmanager")

    secrets = {
        "aqi/openaq-api-key": openaq_key or "PLACEHOLDER_SET_THIS",
        "aqi/firms-map-key":  firms_key or "PLACEHOLDER_SET_THIS",
    }

    for name, value in secrets.items():
        try:
            client.create_secret(
                Name=name,
                SecretString=value,
                Description=f"AQI project — {name}",
            )
            print(f"  Created secret: {name}")
        except client.exceptions.ResourceExistsException:
            if value and "PLACEHOLDER" not in value:
                client.put_secret_value(SecretId=name, SecretString=value)
                print(f"  Updated secret: {name}")
            else:
                print(f"  Secret exists: {name} (not overwriting placeholder)")


def step3_sam_deploy():
    """Build and deploy the SAM stack."""
    print("\n=== Step 3: SAM deploy ===")
    infra_dir = os.path.join(os.path.dirname(__file__), "infra")

    run(["sam", "build", "--template-file", "template.yaml"], cwd=infra_dir)
    run(["sam", "deploy"], cwd=infra_dir)

    # Get outputs
    result = subprocess.run(
        AWS + ["cloudformation", "describe-stacks",
               "--stack-name", STACK_NAME,
               "--region", REGION,
               "--profile", PROFILE,
               "--query", "Stacks[0].Outputs",
               "--output", "json"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        outputs = json.loads(result.stdout)
        for o in outputs:
            print(f"  {o['OutputKey']}: {o['OutputValue']}")
        api_url = next((o["OutputValue"] for o in outputs if o["OutputKey"] == "ApiUrl"), None)
        return api_url
    return None


def step4_frontend(api_url: str):
    """Patch app.js with real API URL, upload frontend to S3, create CloudFront."""
    print("\n=== Step 4: Frontend deploy ===")
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend", "src")
    app_js = os.path.join(frontend_dir, "app.js")

    if api_url:
        with open(app_js, "r") as f:
            content = f.read()
        patched = content.replace(
            'API_BASE: window.AQI_API_BASE || "https://REPLACE_WITH_API_GW_URL"',
            f'API_BASE: window.AQI_API_BASE || "{api_url}"'
        )
        with open(app_js, "w") as f:
            f.write(patched)
        print(f"  Patched app.js with API URL: {api_url}")

    # Upload to S3
    run(AWS + ["s3", "sync", frontend_dir, f"s3://{FRONTEND_BUCKET}/",
               "--profile", PROFILE, "--region", REGION,
               "--cache-control", "public,max-age=300"])

    # Enable static website hosting
    boto3_s3 = boto_client("s3")
    boto3_s3.put_bucket_website(
        Bucket=FRONTEND_BUCKET,
        WebsiteConfiguration={
            "IndexDocument": {"Suffix": "index.html"},
            "ErrorDocument": {"Key": "index.html"},
        }
    )

    # Create CloudFront distribution
    try:
        cf = boto_client("cloudfront")
        resp = cf.create_distribution(
            DistributionConfig={
                "CallerReference": f"aqi-frontend-{ACCOUNT_ID}",
                "Comment": "AQI Delhi frontend",
                "DefaultCacheBehavior": {
                    "TargetOriginId": "s3-frontend",
                    "ViewerProtocolPolicy": "redirect-to-https",
                    "ForwardedValues": {"QueryString": False, "Cookies": {"Forward": "none"}},
                    "MinTTL": 0, "DefaultTTL": 300, "MaxTTL": 3600,
                },
                "Origins": {
                    "Quantity": 1,
                    "Items": [{
                        "Id": "s3-frontend",
                        "DomainName": f"{FRONTEND_BUCKET}.s3-website.ap-south-1.amazonaws.com",
                        "CustomOriginConfig": {
                            "HTTPPort": 80, "HTTPSPort": 443,
                            "OriginProtocolPolicy": "http-only",
                        },
                    }],
                },
                "DefaultRootObject": "index.html",
                "Enabled": True,
                "PriceClass": "PriceClass_200",  # US, EU, Asia
            }
        )
        domain = resp["Distribution"]["DomainName"]
        dist_id = resp["Distribution"]["Id"]
        print(f"\n  ✅ CloudFront domain: https://{domain}")
        print(f"  Distribution ID: {dist_id}")
        print(f"  NOTE: CloudFront propagation takes ~5-10 minutes")
        return f"https://{domain}"
    except Exception as e:
        print(f"  CloudFront creation failed: {e}")
        s3_url = f"http://{FRONTEND_BUCKET}.s3-website.ap-south-1.amazonaws.com"
        print(f"  Fallback: {s3_url}")
        return s3_url


def main():
    parser = argparse.ArgumentParser(description="Complete Tier 0 AWS setup")
    parser.add_argument("--openaq-key", default="", help="OpenAQ API key")
    parser.add_argument("--firms-key", default="", help="NASA FIRMS MAP_KEY")
    parser.add_argument("--skip-sam", action="store_true", help="Skip SAM deploy")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend deploy")
    args = parser.parse_args()

    print("=== AQI Delhi — Tier 0 Setup ===")
    print(f"Account: {ACCOUNT_ID} | Region: {REGION}\n")

    step1_location_service()
    step2_secrets(args.openaq_key, args.firms_key)

    api_url = None
    if not args.skip_sam:
        api_url = step3_sam_deploy()

    frontend_url = None
    if not args.skip_frontend:
        frontend_url = step4_frontend(api_url)

    print("\n=== Setup complete ===")
    if api_url:
        print(f"  API Gateway: {api_url}")
    if frontend_url:
        print(f"  Frontend:    {frontend_url}")
    print(f"\nNext steps:")
    print(f"  1. Open {frontend_url or 'the frontend URL'} in a browser")
    print(f"  2. Click on Delhi map — you should get a mocked estimate")
    print(f"  3. Register keys: openaq.org + firms.modaps.eosdis.nasa.gov")
    print(f"  4. Re-run: python setup_aws.py --openaq-key KEY --firms-key KEY")


if __name__ == "__main__":
    main()
