import asyncio
import os
import sys
import random
from contextlib import asynccontextmanager

if not os.getenv("PYTHONPATH"):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI

from shared import (
    RedisStreamClient, create_health_router, configure_logging, metrics,
    STREAM_EVENTS_CREATED, STREAM_WINNERS_SELECTED,
    setup_telemetry, instrument_fastapi
)

logger = configure_logging("user-notification")
setup_telemetry("user-notification")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = RedisStreamClient(REDIS_URL)

background_tasks = set()


async def simulate_sms_latency():
    """Simulate realistic SMS API latency (100ms - 2s)."""
    delay = random.uniform(0.1, 2.0)
    await asyncio.sleep(delay)
    metrics.NOTIFICATION_LATENCY.observe(delay)
    return delay


async def handle_event_created(payload: dict):
    """Handle new event creation - blast SMS to user base."""
    event_id = payload.get("event_id")
    event_name = payload.get("name")
    expires_at = payload.get("expires_at")
    
    if not event_id or not event_name:
        logger.warning("Received event created message with missing fields")
        return
    
    latency = await simulate_sms_latency()
    
    logger.info(
        f"SMS BLAST: New lottery event '{event_name}' is now open! Sign up before {expires_at}",
        extra={
            "event_id": event_id,
            "notification_type": "event_announce",
            "sms_latency_ms": int(latency * 1000),
            "recipient_type": "broadcast"
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
    
    for winner in winners:
        latency = await simulate_sms_latency()
        
        logger.info(
            f"SMS SENT: Congratulations {winner.get('username')}! You won the {event_name} lottery. "
            f"Check your email for purchase instructions.",
            extra={
                "event_id": event_id,
                "notification_type": "winner_notify",
                "user_id": winner.get("user_id"),
                "phone": winner.get("phone", "unknown")[-4:],
                "sms_latency_ms": int(latency * 1000)
            }
        )
        
        metrics.NOTIFICATIONS_SENT.labels(type="winner_notify").inc()
    
    logger.info(
        f"Completed sending {len(winners)} winner notifications for event {event_id}",
        extra={"event_id": event_id, "total_sent": len(winners)}
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
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


app = FastAPI(title="User Notification Service", lifespan=lifespan)
instrument_fastapi(app)

app.include_router(create_health_router(service_name="user-notification"))


@app.get("/")
async def root():
    return {"service": "user-notification", "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
