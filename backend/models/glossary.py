"""Glossary database models."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class UserGlossary(Base):
    """User's personal glossary."""
    
    __tablename__ = "user_glossaries"
    
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
    
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="glossaries")
    terms: Mapped[list["GlossaryTerm"]] = relationship(
        "GlossaryTerm",
        back_populates="glossary",
        cascade="all, delete-orphan",
    )


class GlossaryTerm(Base):
    """Individual glossary term."""
    
    __tablename__ = "glossary_terms"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    glossary_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("user_glossaries.id", ondelete="CASCADE"),
        index=True,
    )
    
    source_term: Mapped[str] = mapped_column(String(500), index=True)
    target_term: Mapped[str] = mapped_column(String(500))
    
    context: Mapped[str | None] = mapped_column(String(100), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    source: Mapped[str] = mapped_column(String(50), default="user_provided")
    confidence: Mapped[str] = mapped_column(String(20), default="high")
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    
    # Relationships
    glossary: Mapped["UserGlossary"] = relationship(
        "UserGlossary",
        back_populates="terms",
    )


class JobGlossary(Base):
    """Job-specific glossary with extracted terms and conflicts."""
    
    __tablename__ = "job_glossaries"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("translation_jobs.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    
    # Store terms and conflicts as JSON for flexibility
    terms_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    conflicts_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    
    # Relationships
    job: Mapped["TranslationJob"] = relationship(
        "TranslationJob",
        back_populates="job_glossary",
    )


class SystemGlossary(Base):
    """System-level predefined glossary."""
    
    __tablename__ = "system_glossaries"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Store terms as JSON
    terms_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# Import at bottom to avoid circular imports
from backend.models.user import User
from backend.models.job import TranslationJob

