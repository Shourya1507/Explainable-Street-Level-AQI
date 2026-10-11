#!/usr/bin/env python3
"""
setup_github_oidc.py
Sets up AWS IAM OpenID Connect (OIDC) provider and a deployment role for GitHub Actions.
Allows Shourya1507/Explainable-Street-Level-AQI repository to deploy automatically
to S3 and AWS Lambda on git push WITHOUT any permanent access keys.
"""
import json
import boto3
from botocore.exceptions import ClientError

PROFILE = "Shourya Sankrit"
REGION = "ap-south-1"
ACCOUNT_ID = "991166714312"
REPO = "Shourya1507/Explainable-Street-Level-AQI"
ROLE_NAME = "github-actions-aqi-deploy-role"
OIDC_URL = "https://token.actions.githubusercontent.com"
AUDIENCE = "sts.amazonaws.com"
# GitHub standard OIDC root CA thumbprints
THUMBPRINTS = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58786977157a9e31b15eee97299a8634a664f3",
]

def main():
    try:
        sess = boto3.Session(profile_name=PROFILE, region_name=REGION)
    except Exception:
        sess = boto3.Session(region_name=REGION)
    iam = sess.client("iam")

    provider_arn = f"arn:aws:iam::{ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

    # 1. Ensure OIDC Provider exists
    try:
        iam.get_open_id_connect_provider(OpenIDConnectProviderArn=provider_arn)
        print(f"[OK] OIDC Provider exists: {provider_arn}")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchEntity", "ResourceNotFoundException"):
            print("Creating OIDC Provider for GitHub Actions...")
            resp = iam.create_open_id_connect_provider(
                Url=OIDC_URL,
                ClientIDList=[AUDIENCE],
                ThumbprintList=THUMBPRINTS
            )
            provider_arn = resp["OpenIDConnectProviderArn"]
            print(f"[OK] Created OIDC Provider: {provider_arn}")
        else:
            raise

    # 2. Create or Update IAM Role for GitHub Actions
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Federated": provider_arn
                },
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": AUDIENCE
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": [
                            f"repo:{REPO}:*",
                            f"repo:{REPO.lower()}:*"
                        ]
                    }
                }
            }
        ]
    }

    try:
        iam.get_role(RoleName=ROLE_NAME)
        iam.update_assume_role_policy(
            RoleName=ROLE_NAME,
            PolicyDocument=json.dumps(trust_policy)
        )
        print(f"[OK] Role exists and trust policy updated: {ROLE_NAME}")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchEntity", "ResourceNotFoundException"):
            print(f"Creating IAM Role: {ROLE_NAME}...")
            iam.create_role(
                RoleName=ROLE_NAME,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="Automated deployment role for GitHub Actions CI/CD"
            )
            print(f"[OK] Created IAM Role: {ROLE_NAME}")
        else:
            raise

    # 3. Attach inline least-privilege policy for S3 sync and Lambda update
    deploy_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "S3FrontendDeploy",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                    "s3:DeleteObject"
                ],
                "Resource": [
                    f"arn:aws:s3:::aqi-frontend-{ACCOUNT_ID}",
                    f"arn:aws:s3:::aqi-frontend-{ACCOUNT_ID}/*"
                ]
            },
            {
                "Sid": "LambdaDeploy",
                "Effect": "Allow",
                "Action": [
                    "lambda:UpdateFunctionCode",
                    "lambda:UpdateFunctionConfiguration",
                    "lambda:GetFunctionConfiguration"
                ],
                "Resource": [
                    f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:aqi-estimate",
                    f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:aqi-stations"
                ]
            }
        ]
    }

    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="GitHubActionsDeployPolicy",
        PolicyDocument=json.dumps(deploy_policy)
    )
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
    print(f"[OK] Attached deploy policy to role: {role_arn}")
    print("\n=== SUCCESS ===")
    print(f"Role ARN for GitHub Actions: {role_arn}")

if __name__ == "__main__":
    main()
