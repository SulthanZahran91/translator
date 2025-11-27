"""Job request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    """Schema for creating a job (file uploaded separately)."""
    source_language: str = "ko"
    target_language: str = "en"
    output_format: Literal["docx", "pdf"] = "docx"


class JobResponse(BaseModel):
    """Schema for job response."""
    id: str
    status: str
    source_file_name: str
    source_file_size_bytes: int
    source_format: str | None
    output_format: str | None
    source_language: str
    target_language: str
    
    total_units: int
    completed_units: int
    progress_percent: float
    current_phase: str | None
    
    total_input_tokens: int
    total_output_tokens: int
    
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    
    last_error: str | None
    
    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    """Schema for job list response."""
    jobs: list[JobResponse]
    total: int
    page: int
    per_page: int


class JobProgressResponse(BaseModel):
    """Schema for job progress update."""
    id: str
    status: str
    completed_units: int
    total_units: int
    progress_percent: float
    current_phase: str | None


class GlossaryTermResponse(BaseModel):
    """Schema for glossary term in job context."""
    source_term: str
    target_term: str
    confidence: str
    occurrence_count: int


class GlossaryConflictResponse(BaseModel):
    """Schema for glossary conflict."""
    source_term: str
    translations: list[str]
    resolved: bool
    resolved_translation: str | None


class JobGlossaryResponse(BaseModel):
    """Schema for job glossary response."""
    terms: list[GlossaryTermResponse]
    conflicts: list[GlossaryConflictResponse]


class ResolveConflictRequest(BaseModel):
    """Schema for resolving a glossary conflict."""
    source_term: str
    chosen_translation: str

