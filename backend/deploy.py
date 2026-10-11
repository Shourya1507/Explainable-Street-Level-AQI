#!/usr/bin/env python3
"""
SAM (Serverless Application Model) deploy script for AQI backend
Tier 0: deploys mocked /estimate and /stations behind API Gateway + Lambda

Usage:
  python deploy.py

Requires: AWS SAM CLI installed, AWS credentials configured.
"""
import subprocess
import sys
import os
import json

STACK_NAME = os.environ.get("STACK_NAME", "aqi-backend")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
PROFILE = os.environ.get("AWS_PROFILE", "Shourya Sankrit")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "991166714312")
FRONTEND_BUCKET = f"aqi-frontend-{ACCOUNT_ID}"
MODELS_BUCKET = f"aqi-models-{ACCOUNT_ID}"


def run(cmd: list, cwd: str = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=False, text=True)
    if check and result.returncode != 0:
        print(f"ERROR: command failed with code {result.returncode}")
        sys.exit(result.returncode)
    return result


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    infra_dir = os.path.join(base, "..", "infra")

    print("=== AQI Backend Deploy ===")
    print(f"Stack: {STACK_NAME}")
    print(f"Region: {REGION}")
    print(f"Account: {ACCOUNT_ID}")

    SAM_CMD = r"C:\Program Files\Amazon\AWSSAMCLI\bin\sam.cmd"
    # Package SAM template
    run([
        SAM_CMD, "package",
        "--template-file", os.path.join(infra_dir, "template.yaml"),
        "--s3-bucket", MODELS_BUCKET,
        "--s3-prefix", "sam-packages",
        "--output-template-file", os.path.join(infra_dir, "packaged.yaml"),
        "--region", REGION,
        "--profile", PROFILE,
    ])

    # Deploy SAM stack
    run([
        SAM_CMD, "deploy",
        "--template-file", os.path.join(infra_dir, "packaged.yaml"),
        "--stack-name", STACK_NAME,
        "--region", REGION,
        "--profile", PROFILE,
        "--capabilities", "CAPABILITY_IAM", "CAPABILITY_NAMED_IAM",
        "--no-fail-on-empty-changeset",
        "--parameter-overrides",
        f"AccountId={ACCOUNT_ID}",
        f"MockMode=false",
    ])

    # Get the API Gateway URL from stack outputs
    cmd = [
        "aws", "cloudformation", "describe-stacks",
        "--stack-name", STACK_NAME,
        "--region", REGION,
        "--profile", PROFILE,
        "--query", "Stacks[0].Outputs",
        "--output", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        outputs = json.loads(result.stdout)
        for out in outputs:
            print(f"  {out['OutputKey']}: {out['OutputValue']}")

    print("\n=== Deploy complete ===")


if __name__ == "__main__":
    main()
