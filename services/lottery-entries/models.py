import os
import sys
from datetime import datetime
from enum import Enum

if not os.getenv("PYTHONPATH"):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import String, DateTime, Index, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class EntryStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    WINNER = "WINNER"


class LotteryEntry(Base):
    __tablename__ = "lottery_entries"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    account_id: Mapped[str] = mapped_column(String(8), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[EntryStatus] = mapped_column(
        SQLEnum(EntryStatus), default=EntryStatus.VALID, nullable=False
    )
    fraud_reason: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    
    __table_args__ = (
        Index("idx_event_user", "event_id", "user_id"),
        Index("idx_event_account", "event_id", "account_id"),
        Index("idx_event_phone", "event_id", "phone"),
        Index("idx_event_status", "event_id", "status"),
    )
