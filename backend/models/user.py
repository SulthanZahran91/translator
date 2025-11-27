"""User database model."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class User(Base):
    """User account model."""
    
    __tablename__ = "users"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    
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
    jobs: Mapped[list["TranslationJob"]] = relationship(
        "TranslationJob",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    glossaries: Mapped[list["UserGlossary"]] = relationship(
        "UserGlossary",
        back_populates="user",
        cascade="all, delete-orphan",
    )


# Import at bottom to avoid circular imports
from backend.models.job import TranslationJob
from backend.models.glossary import UserGlossary

