import math
import time
import logging
import os
import random
import requests
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider, Counter
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

# Create a counter metric
sine_metric = meter.create_counter(
    name="test.sine.metrics",
    description="A sine-like metric for different namespaces",
)

# Track previous Namespace4 state to detect anomaly transitions
previous_namespace4_anomaly = False
current_interval = 0
next_anomaly_interval = random.randint(1, 96)  # First anomaly within 8 hours (96 intervals @ 5min)
anomaly_end_interval = 0

def send_event_to_signalfx(namespace, value, is_anomaly, min_val, max_val):
    """
    Send an event to SignalFx when Namespace4 experiences an anomaly
    """
    event_type = "namespace_anomaly_detected" if is_anomaly else "namespace_anomaly_resolved"
    
    event_data = [{
        "category": "USER_DEFINED",
        "eventType": event_type,
        "dimensions": {
            "namespace": namespace,
            "anomaly_type": "range_shift"
        },
        "properties": {
            "value": str(value),
            "expected_max": str(max_val),
            "expected_min": str(min_val),
            "anomaly_state": "active" if is_anomaly else "resolved"
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
            logging.info(f"Event sent successfully for {namespace}: {event_type}")
        else:
            logging.error(f"Failed to send event: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Error sending event: {str(e)}")

def calculate_sine_value(min_val, max_val, phase, time_interval):
    amplitude = (max_val - min_val) / 2
    offset = min_val + amplitude
    value = amplitude * math.sin(time_interval + phase) + offset
    return value

def main():
    global previous_namespace4_anomaly, current_interval, next_anomaly_interval, anomaly_end_interval
    
    # Set initial phase for each namespace to ensure different cycles
    phases = [0, math.pi/4, math.pi/2, 3*math.pi/4, math.pi]
    is_namespace4_anomaly = False
    
    # Main loop to send metrics every 5 minutes (300 seconds)
    while True:
        current_time = time.time()
        current_interval += 1
        
        # Check if anomaly should start
        if not is_namespace4_anomaly and current_interval >= next_anomaly_interval:
            is_namespace4_anomaly = True
            anomaly_end_interval = current_interval + random.randint(2, 4)  # Lasts 10-20 min
        
        # Check if anomaly should end
        if is_namespace4_anomaly and current_interval >= anomaly_end_interval:
            is_namespace4_anomaly = False
            next_anomaly_interval = current_interval + random.randint(1, 96)  # Next within 8 hours
        
        # Calculate the sine values for each namespace and create "anomalies" with Namespace4
        namespace_values = {
            "Namespace1": calculate_sine_value(1, 500, phases[0], current_time),
            "Namespace2": calculate_sine_value(10, 300, phases[1], current_time),
            "Namespace3": calculate_sine_value(0, 5, phases[2], current_time),
            "Namespace4": calculate_sine_value(50, 500, phases[3], current_time) if is_namespace4_anomaly else calculate_sine_value(0, 2, phases[3], current_time),
            "Namespace5": calculate_sine_value(1, 30, phases[4], current_time),
        }
        
        # Check if Namespace4 anomaly state changed and send event
        if is_namespace4_anomaly != previous_namespace4_anomaly:
            if is_namespace4_anomaly:
                send_event_to_signalfx("Namespace4", namespace_values["Namespace4"], True, 50, 500)
                logging.info("ANOMALY DETECTED: Namespace4 shifted to range 50-500")
            else:
                send_event_to_signalfx("Namespace4", namespace_values["Namespace4"], False, 0, 2)
                logging.info("ANOMALY RESOLVED: Namespace4 returned to range 0-2")
            
            previous_namespace4_anomaly = is_namespace4_anomaly
        
        # Record the metrics and log the status
        for namespace, value in namespace_values.items():
            sine_metric.add(value, {"namespace": namespace})
            logging.info(f"Metric sent: namespace={namespace}, value={value:.2f}")
        
        # Wait for the next interval
        time.sleep(300)

if __name__ == "__main__":
    main()