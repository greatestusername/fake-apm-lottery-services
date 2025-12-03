from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


class SubmitEntryRequest(BaseModel):
    event_id: str
    user_id: str = Field(..., min_length=1, max_length=64)
    username: str = Field(..., min_length=1, max_length=128)
    account_id: str = Field(..., min_length=8, max_length=8)
    phone: str = Field(..., min_length=10, max_length=20)
    
    @field_validator("account_id")
    @classmethod
    def validate_account_id(cls, v):
        if not v.isdigit() or len(v) != 8:
            raise ValueError("account_id must be exactly 8 digits")
        return v
    
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        cleaned = re.sub(r"[^\d]", "", v)
        if len(cleaned) < 10:
            raise ValueError("phone must have at least 10 digits")
        return v


class EntryResponse(BaseModel):
    id: str
    event_id: str
    user_id: str
    username: str
    account_id: str
    phone: str
    status: str
    fraud_reason: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ValidEntriesResponse(BaseModel):
    event_id: str
    entries: list[EntryResponse]
    total_count: int

