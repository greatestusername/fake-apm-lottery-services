import os
import sys
from datetime import datetime
from enum import Enum

if not os.getenv("PYTHONPATH"):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import String, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class EventStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DRAWING = "DRAWING"
    COMPLETED = "COMPLETED"


class LotteryEvent(Base):
    __tablename__ = "lottery_events"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[EventStatus] = mapped_column(
        SQLEnum(EventStatus), default=EventStatus.ACTIVE, nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=True)
