#!/bin/bash
set -e

REGISTRY="quay.io"
NAMESPACE="jeremyh"
TAG="${1:-latest}"

SERVICES=(
    "lottery-orchestrator"
    "user-notification"
    "lottery-entries"
    "lottery-draw"
    "loadgenerator"
)

echo "Building images locally (no push)"
echo "Tag: ${TAG}"
echo ""

for SERVICE in "${SERVICES[@]}"; do
    IMAGE="${REGISTRY}/${NAMESPACE}/${SERVICE}:${TAG}"
    echo "=== Building ${SERVICE} ==="
    
    docker build \
        -t "${IMAGE}" \
        -f "services/${SERVICE}/Dockerfile" \
        .
    
    echo ""
done

echo "All images built successfully!"

