"""
wire_apigateway.py -- Creates /estimate (POST) and /stations (GET) in API Gateway
and deploys to the 'dev' stage. Run once after Lambda functions are deployed.
"""
import sys
import io
# Force UTF-8 output on Windows to avoid cp1252 UnicodeEncodeError
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import boto3
import json

REGION = "ap-south-1"
PROFILE = "Shourya Sankrit"
ACCOUNT_ID = "991166714312"
API_ID = "6diafyett2"
ROOT_RESOURCE_ID = "kvbxkt82d4"

ESTIMATE_LAMBDA_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:aqi-estimate"
STATIONS_LAMBDA_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:aqi-stations"


def get_clients():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    return session.client("apigateway"), session.client("lambda")


def create_resource(apigw, parent_id: str, path_part: str) -> str:
    resp = apigw.create_resource(
        restApiId=API_ID,
        parentId=parent_id,
        pathPart=path_part,
    )
    return resp["id"]


def add_method_lambda(apigw, resource_id: str, http_method: str, lambda_arn: str):
    # Create method
    apigw.put_method(
        restApiId=API_ID,
        resourceId=resource_id,
        httpMethod=http_method,
        authorizationType="NONE",
    )
    # Integration
    uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"
    apigw.put_integration(
        restApiId=API_ID,
        resourceId=resource_id,
        httpMethod=http_method,
        type="AWS_PROXY",
        integrationHttpMethod="POST",  # Always POST for Lambda proxy
        uri=uri,
    )
    print(f"  {http_method} -> Lambda (resource {resource_id})")


def add_cors_options(apigw, resource_id: str):
    """Add OPTIONS method for CORS preflight."""
    try:
        apigw.put_method(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            authorizationType="NONE",
        )
        apigw.put_integration(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            type="MOCK",
            requestTemplates={"application/json": '{"statusCode": 200}'},
        )
        apigw.put_method_response(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": False,
                "method.response.header.Access-Control-Allow-Methods": False,
                "method.response.header.Access-Control-Allow-Origin": False,
            },
        )
        apigw.put_integration_response(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": "'Content-Type,Authorization'",
                "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
                "method.response.header.Access-Control-Allow-Origin": "'*'",
            },
        )
    except Exception as e:
        print(f"  CORS OPTIONS warning: {e}")


def grant_lambda_permission(lam, function_name: str, api_id: str, stage: str, method: str, path: str):
    try:
        lam.add_permission(
            FunctionName=function_name,
            StatementId=f"apigw-{method.lower()}-{path.replace('/', '')}",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/{stage}/{method}/{path.lstrip('/')}",
        )
        print(f"  Granted invoke permission: {method} /{path}")
    except lam.exceptions.ResourceConflictException:
        print(f"  Permission already exists for {method} /{path}")


def main():
    print(f"=== Wiring API Gateway {API_ID} ===\n")
    apigw, lam = get_clients()

    # /estimate resource
    print("Creating /estimate resource...")
    est_id = create_resource(apigw, ROOT_RESOURCE_ID, "estimate")
    add_method_lambda(apigw, est_id, "POST", ESTIMATE_LAMBDA_ARN)
    add_cors_options(apigw, est_id)
    grant_lambda_permission(lam, "aqi-estimate", API_ID, "dev", "POST", "estimate")
    grant_lambda_permission(lam, "aqi-estimate", API_ID, "*", "POST", "estimate")

    # /stations resource
    print("\nCreating /stations resource...")
    sta_id = create_resource(apigw, ROOT_RESOURCE_ID, "stations")
    add_method_lambda(apigw, sta_id, "GET", STATIONS_LAMBDA_ARN)
    add_cors_options(apigw, sta_id)
    grant_lambda_permission(lam, "aqi-stations", API_ID, "dev", "GET", "stations")
    grant_lambda_permission(lam, "aqi-stations", API_ID, "*", "GET", "stations")

    # Deploy to 'dev' stage
    print("\nDeploying to 'dev' stage...")
    apigw.create_deployment(
        restApiId=API_ID,
        stageName="dev",
        stageDescription="Development stage — Tier 0 mock",
        description="Initial Tier 0 deployment",
    )

    api_url = f"https://{API_ID}.execute-api.{REGION}.amazonaws.com/dev"
    print(f"\n✅ API deployed!")
    print(f"   URL: {api_url}")
    print(f"   Test: curl -X POST {api_url}/estimate -H 'Content-Type: application/json' -d '{{\"lat\":28.6139,\"lon\":77.2090,\"timestamp\":\"2026-10-10T18:00:00+05:30\"}}'")

    return api_url


if __name__ == "__main__":
    main()
