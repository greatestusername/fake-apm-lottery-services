import os
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SPLUNK_REALM = os.getenv("SPLUNK_REALM", "us1")
SPLUNK_ACCESS_TOKEN = os.getenv("SPLUNK_ACCESS_TOKEN", "")


async def send_anomaly_event(
    event_type: str,
    service: str,
    dimensions: Optional[dict] = None,
    properties: Optional[dict] = None,
) -> bool:
    """Send an anomaly event to Splunk Observability."""
    if not SPLUNK_ACCESS_TOKEN:
        logger.warning(f"SPLUNK_ACCESS_TOKEN not set, skipping event: {event_type}")
        return False

    url = f"https://ingest.{SPLUNK_REALM}.signalfx.com/v2/event"
    
    payload = [{
        "category": "USER_DEFINED",
        "eventType": event_type,
        "dimensions": {
            "service": service,
            "environment": os.getenv("DEPLOYMENT_ENV", "apm-anomaly-detection"),
            **(dimensions or {}),
        },
        "properties": properties or {},
        "timestamp": int(time.time() * 1000),
    }]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json", "X-SF-Token": SPLUNK_ACCESS_TOKEN},
            )
        
        if response.status_code in (200, 202):
            logger.info(f"Sent Splunk event: {event_type}", extra={"event_type": event_type, "service": service})
            return True
        
        logger.warning(f"Failed to send Splunk event: {response.status_code}", extra={"event_type": event_type})
        return False
        
    except Exception as e:
        logger.error(f"Error sending Splunk event: {e}", extra={"event_type": event_type})
        return False
