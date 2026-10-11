#!/usr/bin/env bash
# build_lambda_layer.sh
# Builds an AWS Lambda Layer (python3.12, linux/x86_64) containing:
#   xgboost-cpu, numpy
#
# xgboost's pred_contribs=True gives SHAP-equivalent contributions natively.
# Dropping shap, pandas and scipy keeps the layer well under the 250 MB limit.
#
# Usage:
#   cd /path/to/repo
#   bash infra/build_lambda_layer.sh
#
# Requires: Docker, AWS CLI (for upload step)
# Output: infra/lambda_layer.zip  (~60 MB zipped, ~130 MB unzipped)

set -euo pipefail

ACCOUNT_ID="${AWS_ACCOUNT_ID:-991166714312}"
REGION="${AWS_REGION:-ap-south-1}"
LAYER_NAME="aqi-ml-deps"
PYTHON_VERSION="3.12"

# Resolve absolute path to the infra/ directory regardless of CWD
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAYER_ZIP="${SCRIPT_DIR}/lambda_layer.zip"
STAGING_BUCKET="aqi-models-${ACCOUNT_ID}"

echo "=== Building Lambda Layer: ${LAYER_NAME} (python${PYTHON_VERSION} x86_64) ==="
echo "    Output: ${LAYER_ZIP}"

# Remove old zip if present
rm -f "${LAYER_ZIP}"

# Build inside official AWS Lambda python image (exact runtime match)
docker run --rm --platform linux/amd64 \
  --entrypoint bash \
  -v "${SCRIPT_DIR}:/out" \
  "public.ecr.aws/lambda/python:${PYTHON_VERSION}" -c "
    set -euo pipefail
    # Install zip (not present in the Lambda base image)
    yum install -y zip --quiet 2>/dev/null || apt-get install -y zip -qq 2>/dev/null || true

    pip install \
      'xgboost-cpu>=2.0.3' \
      'numpy>=1.26.0' \
      --target /tmp/python \
      --no-cache-dir \
      --upgrade \
      --quiet

    # Strip unnecessary files to save space
    find /tmp/python -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    find /tmp/python -name '*.dist-info' -type d -exec rm -rf {} + 2>/dev/null || true
    find /tmp/python -name '*.pyi' -delete 2>/dev/null || true

    cd /tmp
    zip -r9q /out/lambda_layer.zip python/
    echo 'Layer zipped successfully.'
  "

SIZE=$(du -sh "${LAYER_ZIP}" | cut -f1)
echo "Layer zip created: ${LAYER_ZIP} (${SIZE})"

# Lambda's direct --zip-file upload is capped at 50 MB.
# Always upload through S3 to avoid this limit.
echo ""
echo "=== Uploading layer via S3 (bypasses 50 MB direct-upload cap) ==="
LAYER_S3_KEY="lambda-layers/${LAYER_NAME}-$(date +%Y%m%d%H%M%S).zip"

aws s3 cp "${LAYER_ZIP}" "s3://${STAGING_BUCKET}/${LAYER_S3_KEY}" \
  --region "${REGION}"
echo "Uploaded to s3://${STAGING_BUCKET}/${LAYER_S3_KEY}"

echo ""
echo "=== Publishing layer version ==="
LAYER_VERSION_ARN=$(aws lambda publish-layer-version \
  --layer-name "${LAYER_NAME}" \
  --description "xgboost-cpu + numpy for AQI ML inference (python${PYTHON_VERSION} x86_64)" \
  --compatible-runtimes "python${PYTHON_VERSION}" \
  --compatible-architectures "x86_64" \
  --content "S3Bucket=${STAGING_BUCKET},S3Key=${LAYER_S3_KEY}" \
  --region "${REGION}" \
  --query "LayerVersionArn" \
  --output text)

echo "Published: ${LAYER_VERSION_ARN}"
echo ""
echo "=== Next steps ==="
echo "1. Update infra/samconfig.toml parameter_overrides with:"
echo "   MlLayerArn=${LAYER_VERSION_ARN}"
echo ""
echo "2. Or deploy directly with:"
echo "   cd infra && sam build && sam deploy --parameter-overrides MockMode=false MlLayerArn=${LAYER_VERSION_ARN}"
echo ""
echo "3. Retrain the model (feature set changed to 17 features):"
echo "   cd backend/ml && python train_nowcast.py --upload"
