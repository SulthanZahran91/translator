"""Job log database model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base

if TYPE_CHECKING:
    from backend.models.job import TranslationJob


class JobLog(Base):
    """Log entry for a translation job."""

    __tablename__ = "job_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("translation_jobs.id", ondelete="CASCADE"),
        index=True,
    )

    level: Mapped[str] = mapped_column(String(10), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    phase: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
    )

    # Relationships
    job: Mapped["TranslationJob"] = relationship("TranslationJob", back_populates="logs")
