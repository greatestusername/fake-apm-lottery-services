import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional

# Handle imports for both container (PYTHONPATH set) and local dev
if os.getenv("PYTHONPATH"):
    pass
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, HTTPException, Header
from sqlalchemy import select, and_

from shared import (
    RedisStreamClient, Database, create_health_router, configure_logging, metrics,
    STREAM_EVENTS_CREATED, STREAM_EVENTS_EXPIRED, STREAM_EVENTS_CLEANUP, STREAM_DRAW_COMPLETED,
    setup_telemetry, instrument_fastapi
)
from models import LotteryEvent, EventStatus
from schemas import CreateEventRequest, EventResponse, ValidateEventResponse

logger = configure_logging("lottery-orchestrator")
setup_telemetry("lottery-orchestrator")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/orchestrator")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

db = Database(DATABASE_URL)
redis_client = RedisStreamClient(REDIS_URL)

background_tasks = set()


async def check_expired_events():
    """Background job that runs every 30s to find and expire events."""
    while True:
        try:
            async with db.session() as session:
                now = datetime.utcnow()
                result = await session.execute(
                    select(LotteryEvent).where(
                        and_(
                            LotteryEvent.status == EventStatus.ACTIVE,
                            LotteryEvent.expires_at <= now
                        )
                    )
                )
                expired_events = result.scalars().all()
                
                for event in expired_events:
                    event.status = EventStatus.EXPIRED
                    logger.info(
                        f"Event expired: {event.name}",
                        extra={"event_id": event.id, "event_name": event.name}
                    )
                    await redis_client.publish(STREAM_EVENTS_EXPIRED, {
                        "event_id": event.id,
                        "name": event.name,
                        "total_items": event.total_items
                    })
                    metrics.EVENTS_EXPIRED.inc()
                    
                if expired_events:
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"Error checking expired events: {e}")
            
        await asyncio.sleep(30)


async def cleanup_old_events():
    """Background job that cleans up events older than 48 hours."""
    while True:
        await asyncio.sleep(3600)
        try:
            async with db.session() as session:
                cutoff = datetime.utcnow() - timedelta(hours=48)
                result = await session.execute(
                    select(LotteryEvent).where(
                        and_(
                            LotteryEvent.status == EventStatus.COMPLETED,
                            LotteryEvent.completed_at <= cutoff
                        )
                    )
                )
                old_events = result.scalars().all()
                
                for event in old_events:
                    await redis_client.publish(STREAM_EVENTS_CLEANUP, {
                        "event_id": event.id
                    })
                    await session.delete(event)
                    logger.info(f"Cleaned up old event", extra={"event_id": event.id})
                    
        except Exception as e:
            logger.error(f"Error cleaning up old events: {e}")


async def handle_draw_completed(payload: dict):
    """Handle draw completion events from lottery-draw service."""
    event_id = payload.get("event_id")
    if not event_id:
        return
        
    async with db.session() as session:
        result = await session.execute(
            select(LotteryEvent).where(LotteryEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        
        if event and event.status in (EventStatus.EXPIRED, EventStatus.DRAWING):
            event.status = EventStatus.COMPLETED
            event.completed_at = datetime.utcnow()
            logger.info(
                f"Event completed: {event.name}",
                extra={"event_id": event.id, "winner_count": payload.get("winner_count", 0)}
            )
            metrics.EVENTS_COMPLETED.inc()


async def update_active_events_gauge():
    """Periodically update the active events gauge."""
    while True:
        try:
            async with db.session() as session:
                result = await session.execute(
                    select(LotteryEvent).where(LotteryEvent.status == EventStatus.ACTIVE)
                )
                count = len(result.scalars().all())
                metrics.ACTIVE_EVENTS.set(count)
        except Exception:
            pass
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.create_tables()
    await redis_client.connect()
    
    task1 = asyncio.create_task(check_expired_events())
    task2 = asyncio.create_task(cleanup_old_events())
    task3 = asyncio.create_task(update_active_events_gauge())
    task4 = asyncio.create_task(
        redis_client.consume(
            STREAM_DRAW_COMPLETED, 
            "orchestrator-group", 
            "orchestrator-1",
            handle_draw_completed
        )
    )
    background_tasks.update({task1, task2, task3, task4})
    
    logger.info("Lottery orchestrator started")
    yield
    
    for task in background_tasks:
        task.cancel()
    await redis_client.close()
    await db.close()


app = FastAPI(title="Lottery Orchestrator", lifespan=lifespan)
instrument_fastapi(app)


async def check_ready():
    try:
        async with db.session():
            pass
        return True
    except Exception:
        return False

app.include_router(create_health_router(check_ready, "lottery-orchestrator"))


@app.post("/events", response_model=EventResponse)
async def create_event(
    request: CreateEventRequest,
    x_idempotency_key: Optional[str] = Header(None)
):
    idempotency_key = x_idempotency_key or request.idempotency_key
    
    async with db.session() as session:
        if idempotency_key:
            result = await session.execute(
                select(LotteryEvent).where(LotteryEvent.idempotency_key == idempotency_key)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return EventResponse.model_validate(existing)
        
        event_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=request.expires_in_minutes)
        
        event = LotteryEvent(
            id=event_id,
            name=request.name,
            total_items=request.total_items,
            created_at=now,
            expires_at=expires_at,
            status=EventStatus.ACTIVE,
            idempotency_key=idempotency_key
        )
        
        session.add(event)
        await session.flush()
        
        logger.info(
            f"Event created: {event.name}",
            extra={
                "event_id": event_id,
                "event_name": event.name,
                "total_items": event.total_items,
                "expires_at": expires_at.isoformat()
            }
        )
        
        await redis_client.publish(STREAM_EVENTS_CREATED, {
            "event_id": event_id,
            "name": event.name,
            "total_items": event.total_items,
            "expires_at": expires_at.isoformat()
        })
        
        metrics.EVENTS_CREATED.inc()
        
        return EventResponse.model_validate(event)


@app.get("/events/{event_id}", response_model=EventResponse)
async def get_event(event_id: str):
    async with db.session() as session:
        result = await session.execute(
            select(LotteryEvent).where(LotteryEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
            
        return EventResponse.model_validate(event)


@app.get("/events/{event_id}/validate", response_model=ValidateEventResponse)
async def validate_event(event_id: str):
    """Endpoint for other services to validate event status."""
    async with db.session() as session:
        result = await session.execute(
            select(LotteryEvent).where(LotteryEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        
        if not event:
            return ValidateEventResponse(
                valid=False,
                event_id=event_id,
                status="NOT_FOUND",
                expired=True,
                total_items=0,
                message="Event does not exist"
            )
        
        now = datetime.utcnow()
        is_expired = event.expires_at <= now or event.status != EventStatus.ACTIVE
        
        return ValidateEventResponse(
            valid=event.status == EventStatus.ACTIVE and not is_expired,
            event_id=event_id,
            status=event.status.value,
            expired=is_expired,
            total_items=event.total_items,
            message=None if event.status == EventStatus.ACTIVE else f"Event is {event.status.value}"
        )


@app.get("/events", response_model=list[EventResponse])
async def list_events(status: Optional[str] = None):
    async with db.session() as session:
        query = select(LotteryEvent)
        if status:
            try:
                status_enum = EventStatus(status.upper())
                query = query.where(LotteryEvent.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
                
        result = await session.execute(query.order_by(LotteryEvent.created_at.desc()))
        events = result.scalars().all()
        
        return [EventResponse.model_validate(e) for e in events]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
