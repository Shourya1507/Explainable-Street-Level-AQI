"""
complete_apigateway.py -- Finishes API Gateway setup using existing resource IDs,
adds /stations, grants Lambda invoke permissions, and deploys to 'dev' stage.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import boto3, json

REGION     = os.environ.get("AWS_REGION", "ap-south-1")
PROFILE    = os.environ.get("AWS_PROFILE", "Shourya Sankrit")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "991166714312")
API_ID     = os.environ.get("API_ID", "6diafyett2")
ROOT_ID    = os.environ.get("ROOT_ID", "kvbxkt82d4")
EST_ID     = os.environ.get("EST_ID", "mad1vd")   # /estimate resource already exists with POST

ESTIMATE_LAMBDA_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:aqi-estimate"
STATIONS_LAMBDA_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:aqi-stations"

def session():
    try:
        return boto3.Session(profile_name=PROFILE, region_name=REGION)
    except Exception:
        return boto3.Session(region_name=REGION)

def grant(lam_client, fn_name, method, path_segment, sid_suffix):
    try:
        lam_client.add_permission(
            FunctionName=fn_name,
            StatementId=f"apigw-{sid_suffix}",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{API_ID}/*/{method}/{path_segment}",
        )
        print(f"  Granted invoke: {method} /{path_segment}")
    except lam_client.exceptions.ResourceConflictException:
        print(f"  Permission already exists: {method} /{path_segment}")

def add_cors(apigw, resource_id):
    try:
        apigw.put_method(
            restApiId=API_ID, resourceId=resource_id,
            httpMethod="OPTIONS", authorizationType="NONE",
        )
    except apigw.exceptions.ConflictException:
        pass
    try:
        apigw.put_integration(
            restApiId=API_ID, resourceId=resource_id, httpMethod="OPTIONS",
            type="MOCK", requestTemplates={"application/json": '{"statusCode": 200}'},
        )
        apigw.put_method_response(
            restApiId=API_ID, resourceId=resource_id, httpMethod="OPTIONS",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": False,
                "method.response.header.Access-Control-Allow-Methods": False,
                "method.response.header.Access-Control-Allow-Origin":  False,
            },
        )
        apigw.put_integration_response(
            restApiId=API_ID, resourceId=resource_id, httpMethod="OPTIONS",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": "'Content-Type,Authorization'",
                "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
                "method.response.header.Access-Control-Allow-Origin":  "'*'",
            },
        )
        print(f"  CORS OPTIONS added to resource {resource_id}")
    except Exception as e:
        print(f"  CORS warning: {e}")

def main():
    s = session()
    apigw = s.client("apigateway")
    lam   = s.client("lambda")

    print(f"=== Completing API Gateway {API_ID} ===")

    # 1. /estimate -- already has POST integration; add CORS + permissions
    print("\n/estimate (existing resource, id=mad1vd)")
    add_cors(apigw, EST_ID)
    grant(lam, "aqi-estimate", "POST", "estimate", "post-estimate")

    # 2. /stations -- create fresh
    print("\n/stations (creating new resource)")
    try:
        r = apigw.create_resource(restApiId=API_ID, parentId=ROOT_ID, pathPart="stations")
        sta_id = r["id"]
        print(f"  Created /stations resource id={sta_id}")
    except apigw.exceptions.ConflictException:
        # Already exists, fetch its id
        resources = apigw.get_resources(restApiId=API_ID)["items"]
        sta_id = next(x["id"] for x in resources if x.get("pathPart") == "stations")
        print(f"  /stations already exists, id={sta_id}")

    # Add GET method + Lambda proxy integration
    uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{STATIONS_LAMBDA_ARN}/invocations"
    try:
        apigw.put_method(
            restApiId=API_ID, resourceId=sta_id,
            httpMethod="GET", authorizationType="NONE",
        )
    except apigw.exceptions.ConflictException:
        print("  GET method already exists on /stations")
    try:
        apigw.put_integration(
            restApiId=API_ID, resourceId=sta_id, httpMethod="GET",
            type="AWS_PROXY", integrationHttpMethod="POST", uri=uri,
        )
        print("  GET -> aqi-stations Lambda integrated")
    except Exception as e:
        print(f"  Integration note: {e}")

    add_cors(apigw, sta_id)
    grant(lam, "aqi-stations", "GET", "stations", "get-stations")

    # 3. Deploy to 'dev' stage
    print("\nDeploying to 'dev' stage...")
    apigw.create_deployment(
        restApiId=API_ID,
        stageName="dev",
        description="Tier 0: mocked estimate + stations",
    )

    # 4. Enable throttling on the stage
    try:
        apigw.update_stage(
            restApiId=API_ID,
            stageName="dev",
            patchOperations=[
                {"op": "replace", "path": "/*/*/throttling/rateLimit",  "value": "20"},
                {"op": "replace", "path": "/*/*/throttling/burstLimit", "value": "50"},
            ]
        )
        print("  Throttling applied: 20 rps, burst 50")
    except Exception as e:
        print(f"  Throttling note: {e}")

    api_url = f"https://{API_ID}.execute-api.{REGION}.amazonaws.com/dev"
    print(f"\n=== API LIVE ===")
    print(f"  Base URL : {api_url}")
    print(f"  /estimate: POST {api_url}/estimate")
    print(f"  /stations: GET  {api_url}/stations")
    print(f"\nTest command (run in any terminal):")
    print(f'  curl -s -X POST {api_url}/estimate -H "Content-Type: application/json" -d "{{\\"lat\\":28.6139,\\"lon\\":77.2090,\\"timestamp\\":\\"2026-10-10T18:00:00+05:30\\"}}" | python -m json.tool')

    return api_url

if __name__ == "__main__":
    main()
