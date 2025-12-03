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

echo "Building and pushing images to ${REGISTRY}/${NAMESPACE}"
echo "Tag: ${TAG}"
echo ""

for SERVICE in "${SERVICES[@]}"; do
    IMAGE="${REGISTRY}/${NAMESPACE}/${SERVICE}:${TAG}"
    echo "=== Building ${SERVICE} ==="
    
    docker build \
        --platform linux/amd64 \
        -t "${IMAGE}" \
        -f "services/${SERVICE}/Dockerfile" \
        .
    
    echo "=== Pushing ${IMAGE} ==="
    docker push "${IMAGE}"
    
    echo ""
done

echo "All images built and pushed successfully!"
echo ""
echo "Images:"
for SERVICE in "${SERVICES[@]}"; do
    echo "  ${REGISTRY}/${NAMESPACE}/${SERVICE}:${TAG}"
done

