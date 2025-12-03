#!/bin/bash
set -e

REGISTRY="quay.io"
NAMESPACE="jeremyh"
TAG="${1:-latest}"
PLATFORM="${PLATFORM:-linux/amd64,linux/arm64}"

SERVICES=(
    "lottery-orchestrator"
    "user-notification"
    "lottery-entries"
    "lottery-draw"
    "loadgenerator"
)

echo "Building and pushing multi-arch images to ${REGISTRY}/${NAMESPACE}"
echo "Tag: ${TAG}"
echo "Platforms: ${PLATFORM}"
echo ""

# Ensure buildx builder exists
docker buildx inspect multiarch >/dev/null 2>&1 || docker buildx create --name multiarch --use

for SERVICE in "${SERVICES[@]}"; do
    IMAGE="${REGISTRY}/${NAMESPACE}/${SERVICE}:${TAG}"
    echo "=== Building ${SERVICE} for ${PLATFORM} ==="
    
    docker buildx build \
        --platform "${PLATFORM}" \
        --push \
        -t "${IMAGE}" \
        -f "services/${SERVICE}/Dockerfile" \
        .
    
    echo ""
done

echo "All images built and pushed successfully!"
echo ""
echo "Images:"
for SERVICE in "${SERVICES[@]}"; do
    echo "  ${REGISTRY}/${NAMESPACE}/${SERVICE}:${TAG}"
done
