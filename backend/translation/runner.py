"""Job runner for executing translation jobs."""

import asyncio
import logging
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import async_session_factory
from backend.models.job import JobStatus, TranslationJob
from backend.models.log import JobLog
from backend.translation.chunking.chunker import chunk_document
from backend.translation.export.docx_writer import write_docx
from backend.translation.ingestion.docx_parser import parse_docx
from backend.translation.ingestion.txt_parser import parse_txt
from backend.translation.orchestrator import (
    TranslationOrchestrator,
    TranslationPhase,
    TranslationProgress,
)
from backend.translation.reconstruction.reconstructor import reconstruct_document

logger = logging.getLogger(__name__)


class JobRunner:
    """Executes a translation job."""

    def __init__(self, job_id: str):
        self.job_id = job_id

    def _create_progress_callback(self, db: AsyncSession, job: TranslationJob):
        """Create an async progress callback."""
        async def callback(progress: TranslationProgress):
            await self._on_progress(db, job, progress)
        return callback

    async def run(self):
        """Run the translation job."""

        async with async_session_factory() as db:
            try:
                # Load job
                job = await self._get_job(db)

                if not job:
                    logger.error(f"Job {self.job_id} not found")
                    return

                # Start processing
                await self._update_status(db, job, JobStatus.PROCESSING, "Starting translation job")

                # 1. Ingestion
                await self._log(db, "Starting document ingestion", phase="Ingestion")
                job.current_phase = "Ingestion"
                await db.commit()

                if not job.source_file_path:
                    raise ValueError("Source file path not set")

                # Select parser based on source format
                if job.source_format == "txt":
                    document = await asyncio.to_thread(parse_txt, job.source_file_path)
                else:
                    document = await asyncio.to_thread(parse_docx, job.source_file_path)
                await self._log(db, f"Parsed document: {len(document.sections)} sections", phase="Ingestion")

                # 2. Chunking
                await self._log(db, "Starting document chunking", phase="Chunking")
                job.current_phase = "Chunking"
                await db.commit()

                units = await asyncio.to_thread(chunk_document, document)
                job.total_units = len(units)
                await self._log(db, f"Created {len(units)} translation units", phase="Chunking")
                await db.commit()

                # 3. Translation
                await self._log(db, "Starting translation", phase="Translation")
                job.current_phase = "Translation"
                await db.commit()

                orchestrator = TranslationOrchestrator(
                    user=job.user,
                    db_session=db,
                    progress_callback=self._create_progress_callback(db, job)
                )



                translated_units = await orchestrator.translate_units(units)

                await self._log(db, "Translation completed", phase="Translation")

                # 4. Reconstruction
                await self._log(db, "Starting document reconstruction", phase="Reconstruction")
                job.current_phase = "Reconstruction"
                await db.commit()

                reconstructed_doc = await asyncio.to_thread(reconstruct_document, document, translated_units)
                await self._log(db, "Document reconstructed", phase="Reconstruction")

                # 5. Export
                await self._log(db, "Starting document export", phase="Export")
                job.current_phase = "Export"
                await db.commit()

                output_filename = f"translated_{Path(job.source_file_name).stem}.docx"
                output_dir = Path(job.source_file_path).parent
                output_path = output_dir / output_filename

                await asyncio.to_thread(write_docx, reconstructed_doc.document, output_path)

                job.output_file_path = str(output_path)
                job.output_format = "docx"
                await self._log(db, f"Document exported to {output_path}", phase="Export")

                # Complete
                await self._update_status(db, job, JobStatus.COMPLETED, "Job completed successfully")
                job.completed_at = datetime.utcnow()
                job.current_phase = "Completed"
                await db.commit()

            except Exception as e:
                logger.error(f"Job failed: {e}")
                traceback.print_exc()

                await self._log(db, f"Job failed: {str(e)}", level="ERROR", phase="Failed")

                # Re-fetch job to ensure attached to session
                job = await self._get_job(db)
                if job:
                    job.status = JobStatus.FAILED.value
                    job.last_error = str(e)
                    job.current_phase = "Failed"
                    await db.commit()

    async def _get_job(self, db: AsyncSession) -> TranslationJob | None:
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(TranslationJob)
            .where(TranslationJob.id == self.job_id)
            .options(selectinload(TranslationJob.user))
        )
        return result.scalar_one_or_none()

    async def _update_status(self, db: AsyncSession, job: TranslationJob, status: JobStatus, message: str):
        job.status = status.value
        if status == JobStatus.PROCESSING:
            job.started_at = datetime.utcnow()
        await self._log(db, message, phase=status.value)
        await db.commit()

    async def _log(self, db: AsyncSession, message: str, level: str = "INFO", phase: str = None):
        log_entry = JobLog(
            job_id=self.job_id,
            message=message,
            level=level,
            phase=phase
        )
        db.add(log_entry)
        # We commit logs immediately so they appear in the UI
        await db.commit()

    async def _on_progress(self, db: AsyncSession, job: TranslationJob, progress: TranslationProgress):
        """Handle progress updates from orchestrator."""
        # Update job progress
        job.total_units = progress.total_units
        job.processed_units = progress.completed_units
        job.current_phase = progress.phase.value

        # Log errors if any
        if progress.errors:
            # Only log the last error to avoid spamming
            last_error = progress.errors[-1]
            if job.last_error != last_error:
                job.last_error = last_error
                await self._log(db, f"Error in unit {progress.current_unit}: {last_error}", level="ERROR", phase="Translation")

        # Log phase changes
        if job.status != progress.phase.value and progress.phase != TranslationPhase.TRANSLATING:
             await self._log(db, f"Translation phase changed to {progress.phase.value}", phase="Translation")

        # Commit updates
        await db.commit()


