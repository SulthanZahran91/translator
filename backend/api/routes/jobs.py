"""Jobs API routes."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import DbSessionDep, SettingsDep, StorageDep
from backend.api.routes.auth import CurrentUserDep
from backend.api.schemas.job import (
    JobCreate,
    JobGlossaryResponse,
    JobListResponse,
    JobProgressResponse,
    JobResponse,
    ResolveConflictRequest,
    GlossaryTermResponse,
    GlossaryConflictResponse,
)
from backend.models.job import TranslationJob, JobStatus
from backend.models.glossary import JobGlossary


router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    current_user: CurrentUserDep,
    db: DbSessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    source_language: str = Form(default="ko"),
    target_language: str = Form(default="en"),
    output_format: str = Form(default="docx"),
) -> TranslationJob:
    """Create a new translation job with file upload."""
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )
    
    # Check file extension
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".docx")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and DOCX files are supported",
        )
    
    # Read file content
    content = await file.read()
    
    # Check file size
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB",
        )
    
    # Create job record first to get ID
    source_format = "pdf" if filename_lower.endswith(".pdf") else "docx"
    
    job = TranslationJob(
        user_id=current_user.id,
        source_file_name=file.filename,
        source_file_size_bytes=len(content),
        source_format=source_format,
        source_language=source_language,
        target_language=target_language,
        output_format=output_format,
        source_file_path="",  # Will be updated after save
    )
    db.add(job)
    await db.flush()
    
    # Save file to storage
    file_path = await storage.save_upload(content, file.filename, job.id)
    job.source_file_path = str(file_path)
    
    await db.flush()
    
    return job


@router.get("", response_model=JobListResponse)
async def list_jobs(
    current_user: CurrentUserDep,
    db: DbSessionDep,
    page: int = 1,
    per_page: int = 20,
) -> JobListResponse:
    """List user's translation jobs."""
    offset = (page - 1) * per_page
    
    # Get jobs
    query = (
        select(TranslationJob)
        .where(TranslationJob.user_id == current_user.id)
        .order_by(TranslationJob.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(query)
    jobs = list(result.scalars().all())
    
    # Get total count
    count_query = (
        select(TranslationJob)
        .where(TranslationJob.user_id == current_user.id)
    )
    count_result = await db.execute(count_query)
    total = len(list(count_result.scalars().all()))
    
    return JobListResponse(
        jobs=[JobResponse.model_validate(job) for job in jobs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> TranslationJob:
    """Get a specific job."""
    result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.id == job_id,
            TranslationJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    
    return job


@router.get("/{job_id}/download")
async def download_job(
    job_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
    storage: StorageDep,
):
    """Download the translated document."""
    result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.id == job_id,
            TranslationJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    
    if job.status != JobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not completed yet",
        )
    
    if not job.output_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found",
        )
    
    from pathlib import Path
    output_path = Path(job.output_file_path)
    
    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found",
        )
    
    # Generate download filename
    original_name = Path(job.source_file_name).stem
    extension = job.output_format or "docx"
    download_name = f"{original_name}_translated.{extension}"
    
    return FileResponse(
        path=output_path,
        filename=download_name,
        media_type="application/octet-stream",
    )


@router.post("/{job_id}/pause", response_model=JobProgressResponse)
async def pause_job(
    job_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> TranslationJob:
    """Pause a running job."""
    result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.id == job_id,
            TranslationJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    
    if job.status != JobStatus.PROCESSING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause jobs that are processing",
        )
    
    job.status = JobStatus.PAUSED.value
    await db.flush()
    
    return job


@router.post("/{job_id}/resume", response_model=JobProgressResponse)
async def resume_job(
    job_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> TranslationJob:
    """Resume a paused job."""
    result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.id == job_id,
            TranslationJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    
    if job.status != JobStatus.PAUSED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resume paused jobs",
        )
    
    job.status = JobStatus.PENDING.value  # Will be picked up by worker
    await db.flush()
    
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
    storage: StorageDep,
):
    """Cancel a job."""
    result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.id == job_id,
            TranslationJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    
    # Mark as cancelled
    job.status = JobStatus.CANCELLED.value
    
    # Clean up storage
    await storage.cleanup_job(job_id)
    
    await db.flush()


@router.get("/{job_id}/glossary", response_model=JobGlossaryResponse)
async def get_job_glossary(
    job_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> JobGlossaryResponse:
    """Get extracted glossary terms and conflicts for a job."""
    result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.id == job_id,
            TranslationJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    
    # Get job glossary
    glossary_result = await db.execute(
        select(JobGlossary).where(JobGlossary.job_id == job_id)
    )
    job_glossary = glossary_result.scalar_one_or_none()
    
    terms = []
    conflicts = []
    
    if job_glossary:
        if job_glossary.terms_json:
            for term_data in job_glossary.terms_json.get("terms", {}).values():
                terms.append(GlossaryTermResponse(
                    source_term=term_data.get("source_term", ""),
                    target_term=term_data.get("target_term", ""),
                    confidence=term_data.get("confidence", "low"),
                    occurrence_count=term_data.get("occurrence_count", 1),
                ))
        
        if job_glossary.conflicts_json:
            for conflict_data in job_glossary.conflicts_json.values():
                conflicts.append(GlossaryConflictResponse(
                    source_term=conflict_data.get("source_term", ""),
                    translations=conflict_data.get("translations", []),
                    resolved=conflict_data.get("resolved", False),
                    resolved_translation=conflict_data.get("resolved_translation"),
                ))
    
    return JobGlossaryResponse(terms=terms, conflicts=conflicts)


@router.post("/{job_id}/glossary/resolve")
async def resolve_glossary_conflict(
    job_id: str,
    request: ResolveConflictRequest,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    """Resolve a glossary conflict."""
    result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.id == job_id,
            TranslationJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    
    # Get job glossary
    glossary_result = await db.execute(
        select(JobGlossary).where(JobGlossary.job_id == job_id)
    )
    job_glossary = glossary_result.scalar_one_or_none()
    
    if not job_glossary or not job_glossary.conflicts_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No conflicts found",
        )
    
    if request.source_term not in job_glossary.conflicts_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict not found",
        )
    
    # Update conflict
    job_glossary.conflicts_json[request.source_term]["resolved"] = True
    job_glossary.conflicts_json[request.source_term]["resolved_translation"] = request.chosen_translation
    
    # Also update terms
    if job_glossary.terms_json and request.source_term in job_glossary.terms_json.get("terms", {}):
        job_glossary.terms_json["terms"][request.source_term]["target_term"] = request.chosen_translation
        job_glossary.terms_json["terms"][request.source_term]["source"] = "confirmed"
        job_glossary.terms_json["terms"][request.source_term]["confidence"] = "high"
    
    await db.flush()
    
    return {"message": "Conflict resolved"}

