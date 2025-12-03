# Scripts for Creating Anomalous Metrics

These scripts generate synthetic metrics with **known anomalies** enabling validation of anomaly detection algorithms. Each script also emits events when anomalies occur, providing ground truth for detection accuracy testing.

## Scripts

### `sine_metrics.py`
Generates predictable sine-wave metrics across 5 namespaces with different ranges. **Namespace4** randomly spikes from a low baseline (0-2) to a high range (50-500) at most once per ~8 hours, lasting 10-20 minutes each. Useful for testing detectors that catch rare, unpredictable spikes in otherwise stable periodic data.

### `aperiodic_queue_metrics.py`
Simulates message queue depth for 10 queues. Most queues produce random values within their ranges. Two queues (`queue_09_aperiodic`, `queue_10_aperiodic`) emit 0 most of the time but **spike randomly** every 100-300 intervals. Useful for testing detectors that catch rare, unpredictable bursts in otherwise quiet signals.

## Usage

```bash
export REALM=<your-signalfx-realm>
export ACCESS_TOKEN=<your-signalfx-token>
pip install -r requirements.txt
python sine_metrics.py      # or aperiodic_queue_metrics.py
```
