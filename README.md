# Lottery Services

**THIS IS 100% AN EXERCISE IN CHATGIBBITYGENERATION OF CODE. HOOMONS DID NOT WROTE THIS CODE ORIGINALLY.**

Event-driven "Lottery Drop" for rare merch. Microservices (APM) for testing APM aperiodic/anomaly detection. Services communicate via Redis Streams.
- Repo also includes some anomalous metrics scripts in `./
other-metric-anomaly-scripts`

## Anomalous & Aperiodic Behaviors

Designed to test APM anomaly detection. The following behaviors are injected:

### Aperiodic Timing

| Behavior | Frequency | Description |
|----------|-----------|-------------|
| Event creation | 20-55 min (configurable) | New lottery events are created at random intervals |
| Event entrance expiry | 30-240 min after creation | Each event has a randomized lifespan before the draw triggers |
| Draws | Only on event entrance expiry | `lottery-draw` only executes when entrance to the event is closed (fully event-driven) |

### Simulated Anomalies

| Anomaly | Service | Frequency | Splunk Event |
|---------|---------|-----------|--------------|
| Low participation | `loadgenerator` | 10% of events get only 1 entry | `anomalous_low_participation` |
| Traffic burst | `loadgenerator` | 5% of events get 10-25 entry/sec bursts | `anomalous_traffic_burst` |
| Fraudulent entries | `loadgenerator` → `lottery-entries` | ~10% of entries use duplicate user/account/phone | — |
| Stats endpoint 506s | `lottery-draw` | Every 1.5-3 hours, 1-4 consecutive 506s | `anomalous_stats_endpoint_506` |
| SMS delivery failure | `user-notification` | 2% of individual SMS messages fail | `anomalous_sms_delivery_failure` |

### Variable Latency

| Operation | Latency Range | Service |
|-----------|---------------|---------|
| Individual SMS | 100-2000ms | `user-notification` |
| Broadcast SMS | 500-3000ms | `user-notification` |

### Configuration

Anomaly-related environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MIN_EVENT_INTERVAL_MINUTES` | `20` | Min time between event creation |
| `MAX_EVENT_INTERVAL_MINUTES` | `55` | Max time between event creation |
| `CHEATER_PERCENTAGE` | `0.10` | Fraction of entries that trigger fraud detection |

## Services

| Service | Port | Description |
|---------|------|-------------|
| lottery-orchestrator | 8000 | Event lifecycle management, expiry detection |
| lottery-entries | 8002 | Entry submission, fraud detection |
| lottery-draw | 8003 | **Aperiodic** winner selection (triggers when entry period closes) |
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
| `DEPLOYMENT_ENV` | `apm-anomaly-detection` | Environment name |

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
Redis Stream: events:expired (entrance closed)
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

