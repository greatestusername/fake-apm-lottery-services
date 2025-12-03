# Lottery Services

**THIS IS 100% AN EXERCISE IN CHATGIBBITYGENERATION OF CODE. HOOMONS DID NOT WROTE THIS CODE ORIGINALLY.**

Event-driven microservices system for testing APM aperiodic/anomaly detection. Services communicate via Redis Streams.

## Services

| Service | Port | Description |
|---------|------|-------------|
| lottery-orchestrator | 8000 | Event lifecycle management, expiry detection |
| lottery-entries | 8002 | Entry submission, fraud detection |
| lottery-draw | 8003 | **Aperiodic** winner selection (triggers on event expiry) |
| user-notification | 8001 | Fake SMS logging |
| loadgenerator | 8080 | Traffic generation (events every 30-120 min) |

## Quick Start

### Build Images

```bash
# Build and push to quay.io/jeremyh
./build.sh latest

# Build locally only
./build-local.sh latest
```

### Deploy to Kubernetes

```bash
# Basic deployment
./deploy.sh

# With Splunk Observability
export SPLUNK_REALM=us1
export SPLUNK_ACCESS_TOKEN=your-token
INSTALL_OTEL=true ./deploy.sh
```

### Install Splunk OTel Collector Separately

```bash
export SPLUNK_REALM=us1
export SPLUNK_ACCESS_TOKEN=your-token
./helm/splunk-otel-collector/install.sh

# Or with custom values
VALUES_FILE=./my-values.yaml ./helm/splunk-otel-collector/install.sh
```

## Configuration

### Environment Variables (all services)

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://splunk-otel-collector:4317` | OTel collector endpoint |
| `OTEL_ENABLED` | `true` | Set to `false` to disable tracing |
| `DEPLOYMENT_ENV` | `production` | Environment name |

### Load Generator

| Variable | Default | Description |
|----------|---------|-------------|
| `MIN_EVENT_INTERVAL_MINUTES` | `30` | Min time between events |
| `MAX_EVENT_INTERVAL_MINUTES` | `120` | Max time between events |
| `CHEATER_PERCENTAGE` | `0.10` | Fraction of fraudulent entries |

## Endpoints

All services expose:
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe  
- `GET /metrics` - Prometheus metrics

### Key API Endpoints

```bash
# Create event
POST /events (lottery-orchestrator)

# Submit entry
POST /entries (lottery-entries)

# Manually trigger load generator
POST /trigger (loadgenerator)
```

## Architecture

```
loadgenerator
     │
     ▼
lottery-orchestrator ──► Redis Stream: events:created ──► user-notification
     │
     │ (30s expiry check)
     ▼
Redis Stream: events:expired
     │
     ▼
lottery-draw ──► lottery-entries (GET valid entries)
     │
     ├──► Redis Stream: winners:selected ──► lottery-entries, user-notification
     └──► Redis Stream: draw:completed ──► lottery-orchestrator
```

## Local Development

```bash
# Set PYTHONPATH for imports
export PYTHONPATH=$(pwd)

# Install dependencies
pip install -r requirements.txt

# Run a service
cd services/lottery-orchestrator
python main.py
```

## Monitoring

Check pod status:
```bash
kubectl get pods -n lottery
```

View logs:
```bash
kubectl logs -f deployment/lottery-orchestrator -n lottery
kubectl logs -f deployment/lottery-draw -n lottery
```

Trigger manual event (for testing):
```bash
kubectl exec -n lottery deployment/loadgenerator -- curl -X POST http://localhost:8080/trigger
```

