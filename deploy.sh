#!/bin/bash
set -e

INSTALL_OTEL="${INSTALL_OTEL:-false}"

echo "Deploying lottery system to Kubernetes..."

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/postgres.yaml

echo "Waiting for postgres to be ready..."
kubectl wait --for=condition=ready pod -l app=postgres -n lottery --timeout=120s

echo "Waiting for redis to be ready..."
kubectl wait --for=condition=ready pod -l app=redis -n lottery --timeout=60s

# Install Splunk OTel Collector if requested
if [ "$INSTALL_OTEL" = "true" ]; then
    # Check if collector already exists
    if kubectl get pods -n lottery -l app.kubernetes.io/name=splunk-otel-collector 2>/dev/null | grep -q Running; then
        echo "Splunk OTel Collector already running, skipping installation"
    elif [ -z "$SPLUNK_REALM" ] || [ -z "$SPLUNK_ACCESS_TOKEN" ]; then
        echo ""
        echo "WARNING: INSTALL_OTEL=true but SPLUNK_REALM or SPLUNK_ACCESS_TOKEN not set"
        echo "Skipping OTel collector installation"
        echo "To install later, run: ./helm/splunk-otel-collector/install.sh"
        echo ""
    else
        echo "Installing Splunk OTel Collector..."
        ./helm/splunk-otel-collector/install.sh
    fi
fi

kubectl apply -f k8s/lottery-orchestrator.yaml
kubectl apply -f k8s/lottery-entries.yaml

# Create/update Splunk secret from env vars (for anomaly event sending)
if [ -n "$SPLUNK_ACCESS_TOKEN" ]; then
    kubectl create secret generic splunk-observability -n lottery \
        --from-literal=realm="${SPLUNK_REALM:-us1}" \
        --from-literal=access-token="$SPLUNK_ACCESS_TOKEN" \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "Created/updated splunk-observability secret"
fi

kubectl apply -f k8s/user-notification.yaml
kubectl apply -f k8s/lottery-draw.yaml
kubectl apply -f k8s/loadgenerator.yaml

echo ""
echo "Deployment complete!"
echo ""
echo "Check status with:"
echo "  kubectl get pods -n lottery"
echo ""
echo "View logs with:"
echo "  kubectl logs -f deployment/lottery-orchestrator -n lottery"
echo "  kubectl logs -f deployment/loadgenerator -n lottery"
echo ""
if [ "$INSTALL_OTEL" != "true" ]; then
    echo "To enable Splunk Observability:"
    echo "  export SPLUNK_REALM=us0  # or your realm"
    echo "  export SPLUNK_ACCESS_TOKEN=your-token"
    echo "  ./helm/splunk-otel-collector/install.sh"
fi
