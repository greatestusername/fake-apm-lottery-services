#!/bin/bash
set -e

# Splunk OTel Collector Installation Script
# 
# Required environment variables:
#   SPLUNK_REALM       - Splunk Observability realm (us0, us1, eu0, etc.)
#   SPLUNK_ACCESS_TOKEN - Splunk Observability access token
#
# Optional:
#   CLUSTER_NAME       - Kubernetes cluster name (default: lottery-cluster)
#   NAMESPACE          - Kubernetes namespace (default: lottery)
#   VALUES_FILE        - Path to custom values.yaml (default: ./values.yaml)

NAMESPACE="${NAMESPACE:-lottery}"
CLUSTER_NAME="${CLUSTER_NAME:-lottery-cluster}"
VALUES_FILE="${VALUES_FILE:-$(dirname $0)/values.yaml}"

if [ -z "$SPLUNK_REALM" ]; then
    echo "ERROR: SPLUNK_REALM environment variable is required"
    echo "Example: export SPLUNK_REALM=us0"
    exit 1
fi

if [ -z "$SPLUNK_ACCESS_TOKEN" ]; then
    echo "ERROR: SPLUNK_ACCESS_TOKEN environment variable is required"
    exit 1
fi

echo "Installing Splunk OTel Collector..."
echo "  Realm: $SPLUNK_REALM"
echo "  Namespace: $NAMESPACE"
echo "  Cluster: $CLUSTER_NAME"
echo "  Values: $VALUES_FILE"
echo ""

# Add Helm repo
helm repo add splunk-otel-collector-chart https://signalfx.github.io/splunk-otel-collector-chart
helm repo update

# Create namespace if needed
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Install or upgrade the collector
helm upgrade --install splunk-otel-collector \
    splunk-otel-collector-chart/splunk-otel-collector \
    --namespace "$NAMESPACE" \
    --values "$VALUES_FILE" \
    --set clusterName="$CLUSTER_NAME" \
    --set splunkObservability.realm="$SPLUNK_REALM" \
    --set splunkObservability.accessToken="$SPLUNK_ACCESS_TOKEN"

echo ""
echo "Splunk OTel Collector installed successfully!"
echo ""
echo "Verify with:"
echo "  kubectl get pods -n $NAMESPACE -l app=splunk-otel-collector"
echo ""
echo "Applications should send OTLP data to:"
echo "  gRPC: otel-collector:4317"
echo "  HTTP: otel-collector:4318"

