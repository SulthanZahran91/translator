"""Glossary request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class GlossaryCreate(BaseModel):
    """Schema for creating a glossary."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    domain: str | None = None


class GlossaryUpdate(BaseModel):
    """Schema for updating a glossary."""
    name: str | None = None
    description: str | None = None
    domain: str | None = None


class GlossaryResponse(BaseModel):
    """Schema for glossary response."""
    id: str
    name: str
    description: str | None
    domain: str | None
    term_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class GlossaryListResponse(BaseModel):
    """Schema for glossary list response."""
    glossaries: list[GlossaryResponse]
    total: int


class TermCreate(BaseModel):
    """Schema for creating a term."""
    source_term: str = Field(..., min_length=1, max_length=500)
    target_term: str = Field(..., min_length=1, max_length=500)
    context: str | None = None
    domain: str | None = None
    definition: str | None = None


class TermUpdate(BaseModel):
    """Schema for updating a term."""
    target_term: str | None = None
    context: str | None = None
    domain: str | None = None
    definition: str | None = None


class TermResponse(BaseModel):
    """Schema for term response."""
    id: str
    source_term: str
    target_term: str
    context: str | None
    domain: str | None
    definition: str | None
    confidence: str
    occurrence_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class TermListResponse(BaseModel):
    """Schema for term list response."""
    terms: list[TermResponse]
    total: int


class BulkTermImport(BaseModel):
    """Schema for bulk term import."""
    terms: list[TermCreate]


class PromoteTermsRequest(BaseModel):
    """Schema for promoting job terms to user glossary."""
    term_sources: list[str] | None = None  # Specific terms, or None for all confirmed
    target_glossary_id: str

