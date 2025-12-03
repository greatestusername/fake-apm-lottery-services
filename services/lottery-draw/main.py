import asyncio
import os
import sys
import random
import time
from contextlib import asynccontextmanager

if not os.getenv("PYTHONPATH"):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx
from fastapi import FastAPI

from shared import (
    RedisStreamClient, create_health_router, configure_logging, metrics,
    STREAM_EVENTS_EXPIRED, STREAM_WINNERS_SELECTED, STREAM_DRAW_COMPLETED,
    setup_telemetry, instrument_fastapi
)

logger = configure_logging("lottery-draw")
setup_telemetry("lottery-draw")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
ENTRIES_SERVICE_URL = os.getenv("ENTRIES_SERVICE_URL", "http://localhost:8002")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")

redis_client = RedisStreamClient(REDIS_URL)
http_client: httpx.AsyncClient = None

background_tasks = set()


async def fetch_valid_entries(event_id: str) -> list[dict]:
    """Fetch all valid entries for an event from lottery-entries service."""
    try:
        response = await http_client.get(
            f"{ENTRIES_SERVICE_URL}/entries/event/{event_id}/valid",
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        return data.get("entries", [])
    except Exception as e:
        logger.error(f"Failed to fetch entries for event {event_id}: {e}")
        return []


async def execute_draw(event_id: str, event_name: str, total_items: int):
    """
    Execute the lottery draw for an event.
    
    This is the core aperiodic operation - it only runs when events expire,
    which can be anywhere from 30 minutes to 4 hours after creation.
    """
    start_time = time.time()
    
    logger.info(
        f"Starting draw for event: {event_name}",
        extra={"event_id": event_id, "total_items": total_items}
    )
    
    entries = await fetch_valid_entries(event_id)
    
    if not entries:
        logger.warning(
            f"No valid entries for event {event_id}, skipping draw",
            extra={"event_id": event_id}
        )
        await redis_client.publish(STREAM_DRAW_COMPLETED, {
            "event_id": event_id,
            "winner_count": 0,
            "status": "no_entries"
        })
        return
    
    winner_count = min(total_items, len(entries))
    winners = random.sample(entries, winner_count)
    
    winner_payload = [
        {
            "entry_id": w["id"],
            "user_id": w["user_id"],
            "username": w["username"],
            "phone": w["phone"]
        }
        for w in winners
    ]
    
    logger.info(
        f"Draw complete: {winner_count} winners selected from {len(entries)} entries",
        extra={
            "event_id": event_id,
            "winner_count": winner_count,
            "entry_count": len(entries),
            "selection_ratio": f"{winner_count}/{len(entries)}"
        }
    )
    
    await redis_client.publish(STREAM_WINNERS_SELECTED, {
        "event_id": event_id,
        "event_name": event_name,
        "winners": winner_payload
    })
    
    await redis_client.publish(STREAM_DRAW_COMPLETED, {
        "event_id": event_id,
        "winner_count": winner_count,
        "entry_count": len(entries),
        "status": "completed"
    })
    
    duration = time.time() - start_time
    metrics.DRAWS_EXECUTED.inc()
    metrics.WINNERS_SELECTED.inc(winner_count)
    metrics.DRAW_DURATION.observe(duration)
    
    logger.info(
        f"Draw execution completed",
        extra={
            "event_id": event_id,
            "duration_seconds": round(duration, 3),
            "winners_selected": winner_count
        }
    )


async def handle_event_expired(payload: dict):
    """
    Handle expired event notification from orchestrator.
    
    This handler is the key aperiodic behavior - it only fires when events
    expire, which happens at unpredictable intervals.
    """
    event_id = payload.get("event_id")
    event_name = payload.get("name", "unknown")
    total_items = payload.get("total_items", 0)
    
    if not event_id:
        logger.warning("Received expired event with no event_id")
        return
    
    logger.info(
        f"Received expired event notification",
        extra={"event_id": event_id, "name": event_name}
    )
    
    await execute_draw(event_id, event_name, total_items)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    
    http_client = httpx.AsyncClient()
    await redis_client.connect()
    
    task = asyncio.create_task(
        redis_client.consume(
            STREAM_EVENTS_EXPIRED,
            "draw-group",
            "draw-1",
            handle_event_expired
        )
    )
    background_tasks.add(task)
    
    logger.info("Lottery draw service started - waiting for expired events")
    yield
    
    for task in background_tasks:
        task.cancel()
    await redis_client.close()
    await http_client.aclose()


app = FastAPI(title="Lottery Draw Service", lifespan=lifespan)
instrument_fastapi(app)

app.include_router(create_health_router(service_name="lottery-draw"))


@app.get("/")
async def root():
    return {
        "service": "lottery-draw",
        "status": "idle",
        "description": "Waiting for event expirations to trigger draws"
    }


@app.get("/stats")
async def get_stats():
    return {
        "draws_executed": metrics.DRAWS_EXECUTED._value.get(),
        "winners_selected": metrics.WINNERS_SELECTED._value.get()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
