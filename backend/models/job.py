"""Translation job database model."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class JobStatus(str, Enum):
    """Translation job status."""
    PENDING = "pending"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranslationJob(Base):
    """Translation job model."""
    
    __tablename__ = "translation_jobs"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    
    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default=JobStatus.PENDING.value,
        index=True,
    )
    
    # Source file info
    source_file_path: Mapped[str] = mapped_column(String(500))
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    source_format: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "pdf", "docx"
    
    # Output file info
    output_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_format: Mapped[str | None] = mapped_column(String(10), nullable=True)
    
    # Translation direction
    source_language: Mapped[str] = mapped_column(String(10), default="ko")  # Korean
    target_language: Mapped[str] = mapped_column(String(10), default="en")  # English
    
    # Progress tracking
    total_units: Mapped[int] = mapped_column(Integer, default=0)
    completed_units: Mapped[int] = mapped_column(Integer, default=0)
    current_phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Token usage
    total_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    
    # Error handling
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="jobs")
    job_glossary: Mapped["JobGlossary | None"] = relationship(
        "JobGlossary",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )
    
    logs: Mapped[list["JobLog"]] = relationship(
        "JobLog",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobLog.created_at",
    )
    
    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.total_units == 0:
            return 0.0
        return (self.completed_units / self.total_units) * 100
    
    @property
    def is_active(self) -> bool:
        """Check if job is actively being processed."""
        return self.status in (JobStatus.PENDING.value, JobStatus.PROCESSING.value)
    
    @property
    def is_completed(self) -> bool:
        """Check if job has finished (successfully or not)."""
        return self.status in (
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        )


# Import at bottom to avoid circular imports
from backend.models.user import User
from backend.models.glossary import JobGlossary
from backend.models.log import JobLog

