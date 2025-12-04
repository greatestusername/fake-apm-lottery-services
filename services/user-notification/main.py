import asyncio
import os
import sys
import random
from contextlib import asynccontextmanager
from typing import Optional

if not os.getenv("PYTHONPATH"):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from shared import (
    RedisStreamClient, create_health_router, configure_logging, metrics,
    STREAM_EVENTS_CREATED, STREAM_WINNERS_SELECTED,
    setup_telemetry, instrument_fastapi, send_anomaly_event
)

logger = configure_logging("user-notification")
setup_telemetry("user-notification")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL", "http://localhost:8001")

redis_client = RedisStreamClient(REDIS_URL)
http_client: httpx.AsyncClient = None

background_tasks = set()


class SMSRequest(BaseModel):
    phone: str
    message: str
    notification_type: str
    event_id: Optional[str] = None
    user_id: Optional[str] = None


class BroadcastRequest(BaseModel):
    message: str
    notification_type: str
    event_id: str
    recipient_count: int = 1000


async def send_sms(phone: str, message: str, notification_type: str, 
                   event_id: str = None, user_id: str = None) -> dict:
    """Send SMS via gateway endpoint - creates HTTP trace spans."""
    try:
        response = await http_client.post(
            f"{SMS_GATEWAY_URL}/gateway/sms",
            json={
                "phone": phone,
                "message": message,
                "notification_type": notification_type,
                "event_id": event_id,
                "user_id": user_id
            },
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        logger.error(f"SMS gateway call failed: {e}")
        return {"status": "error", "error": str(e)}


async def send_broadcast(message: str, event_id: str, recipient_count: int = 1000) -> dict:
    """Send broadcast SMS via gateway - creates HTTP trace spans."""
    try:
        response = await http_client.post(
            f"{SMS_GATEWAY_URL}/gateway/broadcast",
            json={
                "message": message,
                "notification_type": "event_announce",
                "event_id": event_id,
                "recipient_count": recipient_count
            },
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        logger.error(f"Broadcast gateway call failed: {e}")
        return {"status": "error", "error": str(e)}


async def handle_event_created(payload: dict):
    """Handle new event creation - blast SMS to user base."""
    event_id = payload.get("event_id")
    event_name = payload.get("name")
    expires_at = payload.get("expires_at")
    
    if not event_id or not event_name:
        logger.warning("Received event created message with missing fields")
        return
    
    message = f"New lottery event '{event_name}' is now open! Sign up before {expires_at}"
    
    result = await send_broadcast(message, event_id, recipient_count=random.randint(500, 2000))
    
    logger.info(
        f"SMS BLAST: {message}",
        extra={
            "event_id": event_id,
            "notification_type": "event_announce",
            "gateway_status": result.get("status"),
            "recipient_count": result.get("recipient_count"),
            "campaign_id": result.get("campaign_id")
        }
    )
    
    metrics.NOTIFICATIONS_SENT.labels(type="event_announce").inc()


async def handle_winners_selected(payload: dict):
    """Handle winner selection - send SMS to each winner."""
    event_id = payload.get("event_id")
    event_name = payload.get("event_name", "lottery")
    winners = payload.get("winners", [])
    
    if not event_id:
        logger.warning("Received winners selected message with missing event_id")
        return
        
    logger.info(
        f"Processing winner notifications for event {event_id}",
        extra={"event_id": event_id, "winner_count": len(winners)}
    )
    
    success_count = 0
    fail_count = 0
    
    for winner in winners:
        phone = winner.get("phone", "unknown")
        username = winner.get("username", "Customer")
        user_id = winner.get("user_id")
        
        message = (
            f"Congratulations {username}! You won the {event_name} lottery. "
            f"Check your email for purchase instructions."
        )
        
        result = await send_sms(
            phone=phone,
            message=message,
            notification_type="winner_notify",
            event_id=event_id,
            user_id=user_id
        )
        
        if result.get("status") == "delivered":
            success_count += 1
        else:
            fail_count += 1
        
        logger.info(
            f"SMS SENT: {message}",
            extra={
                "event_id": event_id,
                "notification_type": "winner_notify",
                "user_id": user_id,
                "phone": phone[-4:] if phone else "unknown",
                "gateway_status": result.get("status"),
                "message_id": result.get("message_id")
            }
        )
        
        metrics.NOTIFICATIONS_SENT.labels(type="winner_notify").inc()
    
    logger.info(
        f"Completed winner notifications for event {event_id}",
        extra={
            "event_id": event_id,
            "total_sent": len(winners),
            "success_count": success_count,
            "fail_count": fail_count
        }
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    
    http_client = httpx.AsyncClient()
    await redis_client.connect()
    
    task1 = asyncio.create_task(
        redis_client.consume(
            STREAM_EVENTS_CREATED,
            "notification-group",
            "notification-1",
            handle_event_created
        )
    )
    
    task2 = asyncio.create_task(
        redis_client.consume(
            STREAM_WINNERS_SELECTED,
            "notification-group",
            "notification-1",
            handle_winners_selected
        )
    )
    
    background_tasks.update({task1, task2})
    
    logger.info("User notification service started")
    yield
    
    for task in background_tasks:
        task.cancel()
    await redis_client.close()
    await http_client.aclose()


app = FastAPI(title="User Notification Service", lifespan=lifespan)
instrument_fastapi(app)

app.include_router(create_health_router(service_name="user-notification"))


@app.get("/")
async def root():
    return {"service": "user-notification", "status": "running"}


@app.post("/gateway/sms")
async def sms_gateway(request: SMSRequest):
    """Simulated SMS gateway endpoint - called by this service to create HTTP spans."""
    delay = random.uniform(0.1, 2.0)
    await asyncio.sleep(delay)
    
    if random.random() < 0.02:
        logger.warning(
            f"SMS delivery failed (simulated)",
            extra={"phone": request.phone[-4:], "event_id": request.event_id}
        )
        await send_anomaly_event(
            event_type="anomalous_sms_delivery_failure",
            service="user-notification",
            dimensions={"anomaly_type": "sms_failure", "event_id": request.event_id or "unknown"},
            properties={"notification_type": request.notification_type}
        )
        return {"status": "failed", "latency_ms": int(delay * 1000)}
    
    metrics.NOTIFICATION_LATENCY.observe(delay)
    
    return {
        "status": "delivered",
        "latency_ms": int(delay * 1000),
        "message_id": f"msg_{random.randint(100000, 999999)}"
    }


@app.post("/gateway/broadcast")
async def broadcast_gateway(request: BroadcastRequest):
    """Simulated broadcast SMS gateway - called by this service to create HTTP spans."""
    delay = random.uniform(0.5, 3.0)
    await asyncio.sleep(delay)
    
    metrics.NOTIFICATION_LATENCY.observe(delay)
    
    return {
        "status": "queued",
        "recipient_count": request.recipient_count,
        "latency_ms": int(delay * 1000),
        "campaign_id": f"camp_{random.randint(100000, 999999)}"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
