from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CreateEventRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    event_date: datetime
    total_items: int = Field(..., ge=10, le=200)
    expires_in_minutes: int = Field(..., ge=30, le=240)
    idempotency_key: Optional[str] = None


class EventResponse(BaseModel):
    id: str
    name: str
    total_items: int
    created_at: datetime
    expires_at: datetime
    status: str
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ValidateEventResponse(BaseModel):
    valid: bool
    event_id: str
    status: str
    expired: bool
    total_items: int
    message: Optional[str] = None

