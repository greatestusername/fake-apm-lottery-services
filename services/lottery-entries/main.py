import asyncio
import hashlib
import os
import sys
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

if not os.getenv("PYTHONPATH"):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, HTTPException, Header
from sqlalchemy import select, func, and_, delete

from shared import (
    RedisStreamClient, Database, create_health_router, configure_logging, metrics,
    STREAM_WINNERS_SELECTED, STREAM_EVENTS_CLEANUP,
    setup_telemetry, instrument_fastapi
)
from models import LotteryEntry, EntryStatus
from schemas import SubmitEntryRequest, EntryResponse, ValidEntriesResponse

logger = configure_logging("lottery-entries")
setup_telemetry("lottery-entries")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/entries")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

db = Database(DATABASE_URL)
redis_client = RedisStreamClient(REDIS_URL)

background_tasks = set()


def generate_idempotency_key(event_id: str, user_id: str, account_id: str) -> str:
    """Generate idempotency key from event_id + user_id + account_id."""
    raw = f"{event_id}:{user_id}:{account_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def check_fraud_patterns(
    session, 
    event_id: str, 
    user_id: str, 
    account_id: str, 
    phone: str
) -> tuple[bool, Optional[str]]:
    """Check for fraud patterns. Returns (is_valid, fraud_reason)."""
    
    result = await session.execute(
        select(func.count()).select_from(LotteryEntry).where(
            and_(LotteryEntry.event_id == event_id, LotteryEntry.user_id == user_id)
        )
    )
    if result.scalar() > 0:
        metrics.FRAUD_DETECTED.labels(reason="duplicate_user").inc()
        return False, "duplicate_user_id"
    
    result = await session.execute(
        select(func.count()).select_from(LotteryEntry).where(
            and_(LotteryEntry.event_id == event_id, LotteryEntry.account_id == account_id)
        )
    )
    if result.scalar() > 0:
        metrics.FRAUD_DETECTED.labels(reason="duplicate_account").inc()
        return False, "duplicate_account_id"
    
    result = await session.execute(
        select(func.count()).select_from(LotteryEntry).where(
            and_(LotteryEntry.event_id == event_id, LotteryEntry.phone == phone)
        )
    )
    if result.scalar() > 0:
        metrics.FRAUD_DETECTED.labels(reason="duplicate_phone").inc()
        return False, "duplicate_phone"
    
    return True, None


async def handle_winners_selected(payload: dict):
    """Update winner entries when lottery-draw selects winners."""
    event_id = payload.get("event_id")
    winners = payload.get("winners", [])
    
    if not event_id or not winners:
        return
    
    async with db.session() as session:
        winner_ids = [w.get("entry_id") for w in winners if w.get("entry_id")]
        
        if winner_ids:
            result = await session.execute(
                select(LotteryEntry).where(LotteryEntry.id.in_(winner_ids))
            )
            entries = result.scalars().all()
            
            for entry in entries:
                entry.status = EntryStatus.WINNER
                
            logger.info(
                f"Updated {len(entries)} entries to WINNER status",
                extra={"event_id": event_id, "winner_count": len(entries)}
            )


async def handle_cleanup(payload: dict):
    """Delete entries for cleaned up events."""
    event_id = payload.get("event_id")
    if not event_id:
        return
        
    async with db.session() as session:
        result = await session.execute(
            delete(LotteryEntry).where(LotteryEntry.event_id == event_id)
        )
        logger.info(
            f"Cleaned up entries for event",
            extra={"event_id": event_id, "deleted_count": result.rowcount}
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.create_tables()
    await redis_client.connect()
    
    task1 = asyncio.create_task(
        redis_client.consume(
            STREAM_WINNERS_SELECTED,
            "entries-group",
            "entries-1",
            handle_winners_selected
        )
    )
    
    task2 = asyncio.create_task(
        redis_client.consume(
            STREAM_EVENTS_CLEANUP,
            "entries-group",
            "entries-1",
            handle_cleanup
        )
    )
    
    background_tasks.update({task1, task2})
    
    logger.info("Lottery entries service started")
    yield
    
    for task in background_tasks:
        task.cancel()
    await redis_client.close()
    await db.close()


app = FastAPI(title="Lottery Entries Service", lifespan=lifespan)
instrument_fastapi(app)


async def check_ready():
    try:
        async with db.session():
            pass
        return True
    except Exception:
        return False

app.include_router(create_health_router(check_ready, "lottery-entries"))


@app.post("/entries", response_model=EntryResponse)
async def submit_entry(
    request: SubmitEntryRequest,
    x_idempotency_key: Optional[str] = Header(None)
):
    idempotency_key = x_idempotency_key or generate_idempotency_key(
        request.event_id, request.user_id, request.account_id
    )
    
    async with db.session() as session:
        result = await session.execute(
            select(LotteryEntry).where(LotteryEntry.idempotency_key == idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return EntryResponse.model_validate(existing)
        
        is_valid, fraud_reason = await check_fraud_patterns(
            session, request.event_id, request.user_id, request.account_id, request.phone
        )
        
        entry_id = str(uuid.uuid4())
        status = EntryStatus.VALID if is_valid else EntryStatus.INVALID
        
        entry = LotteryEntry(
            id=entry_id,
            event_id=request.event_id,
            user_id=request.user_id,
            username=request.username,
            account_id=request.account_id,
            phone=request.phone,
            status=status,
            fraud_reason=fraud_reason,
            created_at=datetime.utcnow(),
            idempotency_key=idempotency_key
        )
        
        session.add(entry)
        
        metrics.ENTRIES_SUBMITTED.labels(status=status.value).inc()
        
        if fraud_reason:
            logger.warning(
                f"Fraud detected for entry",
                extra={
                    "event_id": request.event_id,
                    "user_id": request.user_id,
                    "fraud_reason": fraud_reason
                }
            )
        else:
            logger.info(
                f"Entry submitted",
                extra={
                    "event_id": request.event_id,
                    "user_id": request.user_id,
                    "entry_id": entry_id
                }
            )
        
        return EntryResponse.model_validate(entry)


@app.get("/entries/event/{event_id}/valid", response_model=ValidEntriesResponse)
async def get_valid_entries(event_id: str):
    """Endpoint for lottery-draw to fetch all valid entries for an event."""
    async with db.session() as session:
        result = await session.execute(
            select(LotteryEntry).where(
                and_(
                    LotteryEntry.event_id == event_id,
                    LotteryEntry.status == EntryStatus.VALID
                )
            )
        )
        entries = result.scalars().all()
        
        return ValidEntriesResponse(
            event_id=event_id,
            entries=[EntryResponse.model_validate(e) for e in entries],
            total_count=len(entries)
        )


@app.get("/entries/event/{event_id}", response_model=list[EntryResponse])
async def get_all_entries(event_id: str, status: Optional[str] = None):
    """Get all entries for an event, optionally filtered by status."""
    async with db.session() as session:
        query = select(LotteryEntry).where(LotteryEntry.event_id == event_id)
        
        if status:
            try:
                status_enum = EntryStatus(status.upper())
                query = query.where(LotteryEntry.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        result = await session.execute(query.order_by(LotteryEntry.created_at))
        entries = result.scalars().all()
        
        return [EntryResponse.model_validate(e) for e in entries]


@app.get("/entries/{entry_id}", response_model=EntryResponse)
async def get_entry(entry_id: str):
    async with db.session() as session:
        result = await session.execute(
            select(LotteryEntry).where(LotteryEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
            
        return EntryResponse.model_validate(entry)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
