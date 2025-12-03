import os
import random
import time
import logging
import requests
import json
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# Set up logging
logging.basicConfig(level=logging.INFO)

# Get environment variables
REALM = os.getenv('REALM') or os.getenv('SPLUNK_REALM')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN') or os.getenv('SPLUNK_ACCESS_TOKEN')

# Validate environment variables
if not REALM or not ACCESS_TOKEN:
    raise ValueError("REALM and ACCESS_TOKEN/SPLUNK_ACCESS_TOKEN environment variables must be set")

# Set up the OTLP HTTP exporter for SignalFx
otlp_endpoint = f"https://ingest.{REALM}.signalfx.com/v2/datapoint/otlp"
event_endpoint = f"https://ingest.{REALM}.signalfx.com/v2/event"
logging.info(f"Configuring OTLP exporter with endpoint: {otlp_endpoint}")
logging.info(f"Event endpoint: {event_endpoint}")

otlp_exporter = OTLPMetricExporter(
    endpoint=otlp_endpoint,
    headers={"X-SF-Token": ACCESS_TOKEN}
)

reader = PeriodicExportingMetricReader(otlp_exporter, export_interval_millis=60000)
provider = MeterProvider(metric_readers=[reader])
metrics.set_meter_provider(provider)

# Get a meter
meter = metrics.get_meter(__name__)

# Create a counter metric for message queues
message_queue_metric = meter.create_counter(
    name="message.queue.depth",
    description="Message queue depth for various queues",
)

# Define message queue configurations
QUEUE_CONFIGS = {
    "queue_01": {"min": 1, "max": 10},
    "queue_02": {"min": 4, "max": 200},
    "queue_03": {"min": 0, "max": 244},
    "queue_04": {"min": 0, "max": 14},
    "queue_05": {"min": 5, "max": 150},
    "queue_06": {"min": 0, "max": 75},
    "queue_07": {"min": 10, "max": 300},
    "queue_08": {"min": 0, "max": 50},
    "queue_09_aperiodic": {"min": 0, "max": 500, "aperiodic": True},
    "queue_10_aperiodic": {"min": 0, "max": 350, "aperiodic": True},
}

# Track aperiodic queue state
# Aperiodic queues return 0 most of the time, then spike randomly every 100-300 intervals
aperiodic_state = {}
for queue_name, config in QUEUE_CONFIGS.items():
    if config.get("aperiodic", False):
        aperiodic_state[queue_name] = {
            "next_spike_interval": random.randint(100, 300),
            "last_spike_interval": 0
        }
        logging.info(f"{queue_name}: first spike scheduled at interval {aperiodic_state[queue_name]['next_spike_interval']}")

def send_event_to_signalfx(queue_name, spike_value, interval_count):
    """
    Send an event to SignalFx when an anomalous spike occurs
    """
    event_data = [{
        "category": "USER_DEFINED",
        "eventType": "queue_anomaly_spike",
        "dimensions": {
            "queue_name": queue_name,
            "spike_type": "aperiodic"
        },
        "properties": {
            "spike_value": str(spike_value),
            "interval_count": str(interval_count),
            "max_value": str(QUEUE_CONFIGS[queue_name]["max"]),
            "min_value": str(QUEUE_CONFIGS[queue_name]["min"])
        },
        "timestamp": int(time.time() * 1000)
    }]
    
    headers = {
        "Content-Type": "application/json",
        "X-SF-Token": ACCESS_TOKEN
    }
    
    try:
        response = requests.post(event_endpoint, headers=headers, json=event_data)
        if response.status_code == 200:
            logging.info(f"Event sent successfully for {queue_name} spike")
        else:
            logging.error(f"Failed to send event: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Error sending event: {str(e)}")

def calculate_random_value(min_val, max_val):
    """Generate a random value within the given range"""
    return random.uniform(min_val, max_val)

def calculate_aperiodic_value(min_val, max_val, interval_count, queue_name):
    """
    Returns None most of the time, then generates a spike at random intervals.
    After each spike, schedules the next one randomly between 100-300 intervals.
    Sends an event to SignalFx when a spike occurs.
    """
    state = aperiodic_state[queue_name]
    
    # Check if it's time for a spike
    if interval_count == state["next_spike_interval"]:
        # Generate spike (70-100% of max value)
        spike_value = random.uniform(max_val * 0.7, max_val)
        
        # Schedule next spike
        intervals_until_next = random.randint(100, 300)
        state["next_spike_interval"] = interval_count + intervals_until_next
        state["last_spike_interval"] = interval_count
        
        logging.info(
            f"SPIKE: {queue_name} at interval {interval_count}, "
            f"value={spike_value:.2f}, next at {state['next_spike_interval']}"
        )
        
        # Send event to SignalFx
        send_event_to_signalfx(queue_name, spike_value, interval_count)
        
        return spike_value
    else:
        return None

def main():
    interval_count = 0
    
    logging.info("Starting message queue metric generator...")
    logging.info(f"Configured {len(QUEUE_CONFIGS)} message queues")
    
    # Main loop to send metrics every 10 minutes (600 seconds)
    while True:
        interval_count += 1
        
        metrics_sent = 0
        metrics_skipped = 0
        
        # Calculate and send metrics for each queue
        for queue_name, config in QUEUE_CONFIGS.items():
            # Handle aperiodic queues differently
            if config.get("aperiodic", False):
                value = calculate_aperiodic_value(
                    config["min"], 
                    config["max"], 
                    interval_count,
                    queue_name
                )
            else:
                # Regular queues generate random values within their range
                value = calculate_random_value(config["min"], config["max"])
            
            # Only send metric if value exists (aperiodic queues return None when not spiking)
            if value is not None:
                message_queue_metric.add(value, {"queue_name": queue_name})
                logging.info(f"Metric sent: queue={queue_name}, value={value:.2f}")
                metrics_sent += 1
            else:
                logging.debug(f"Skipped: queue={queue_name} (no value)")
                metrics_skipped += 1
        
        logging.info(f"Interval {interval_count}: sent={metrics_sent}, skipped={metrics_skipped}")
        
        # Wait for the next interval (10 minutes = 600 seconds)
        time.sleep(600)

if __name__ == "__main__":
    main()