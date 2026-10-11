#!/usr/bin/env bash
# build_lambda_layer.sh
# Builds an AWS Lambda Layer (python3.12, linux/amd64) containing:
#   xgboost, shap, pandas, numpy
#
# Usage:
#   cd infra/
#   chmod +x build_lambda_layer.sh
#   ./build_lambda_layer.sh
#
# Requires: Docker (to match Lambda's linux/amd64 environment)
# Output: infra/lambda_layer.zip  — ready to upload to S3 or deploy directly

set -euo pipefail

ACCOUNT_ID="${AWS_ACCOUNT_ID:-991166714312}"
REGION="${AWS_REGION:-ap-south-1}"
LAYER_NAME="aqi-ml-deps"
PYTHON_VERSION="3.12"
OUT_DIR="$(dirname "$0")"
LAYER_ZIP="${OUT_DIR}/lambda_layer.zip"

echo "=== Building Lambda Layer for ${LAYER_NAME} (python${PYTHON_VERSION}) ==="

# Build inside an Amazon Linux 2023 container (matches Lambda runtime)
docker run --rm --platform linux/amd64 \
  -v "${OUT_DIR}:/out" \
  "public.ecr.aws/lambda/python:${PYTHON_VERSION}" \
  bash -c "
    pip install \
      'xgboost>=2.0.3' \
      'shap>=0.45.0' \
      'pandas>=2.1.0' \
      'numpy>=1.26.0' \
      --target /tmp/python \
      --no-cache-dir \
      --upgrade \
      --quiet && \
    cd /tmp && \
    zip -r9 /out/lambda_layer.zip python/ -x '*.pyc' -x '__pycache__/*' -x '*.dist-info/*' && \
    echo 'Layer zipped.'
  "

SIZE=$(du -sh "${LAYER_ZIP}" | cut -f1)
echo "Layer zip: ${LAYER_ZIP} (${SIZE})"

echo ""
echo "=== Uploading layer to AWS Lambda ==="
LAYER_VERSION=$(aws lambda publish-layer-version \
  --layer-name "${LAYER_NAME}" \
  --description "xgboost+shap+pandas+numpy for AQI ML inference (python${PYTHON_VERSION})" \
  --compatible-runtimes "python${PYTHON_VERSION}" \
  --compatible-architectures "x86_64" \
  --zip-file "fileb://${LAYER_ZIP}" \
  --region "${REGION}" \
  --query "LayerVersionArn" \
  --output text)

echo "Published: ${LAYER_VERSION}"
echo ""
echo "Add to template.yaml EstimateFunction:"
echo "  Layers:"
echo "    - ${LAYER_VERSION}"
echo ""
echo "Or run: python backend/deploy_real_mode.py --layer-arn ${LAYER_VERSION}"
