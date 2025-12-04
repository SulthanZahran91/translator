import asyncio
import logging
from uuid import uuid4

from sqlalchemy import select

from backend.core.database import async_session_factory, init_db
from backend.models.job import JobStatus, TranslationJob
from backend.models.log import JobLog
from backend.models.user import User
from backend.translation.runner import JobRunner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reproduce():
    # Initialize DB
    await init_db()

    async with async_session_factory() as db:
        # Create a test user
        user_id = str(uuid4())
        user = User(
            id=user_id,
            email=f"test_{user_id}@example.com",
            password_hash="hashed_password",
            name="Test User"
        )
        db.add(user)
        await db.commit()

        # Create a test job
        job_id = str(uuid4())
        job = TranslationJob(
            id=job_id,
            user_id=user_id,
            source_file_name="test.docx",
            source_file_size_bytes=100,
            source_format="docx",
            source_language="ko",
            target_language="en",
            output_format="docx",
            source_file_path="/tmp/test.docx", # Dummy path
            status=JobStatus.PENDING.value
        )
        db.add(job)
        await db.commit()

        print(f"Created job {job_id}")

        # Run JobRunner
        runner = JobRunner(job_id)

        # We expect this to fail because the file doesn't exist, but it should log the failure
        print("Running JobRunner...")
        await runner.run()
        print("JobRunner finished.")

        # Check logs
        result = await db.execute(
            select(JobLog).where(JobLog.job_id == job_id).order_by(JobLog.created_at)
        )
        logs = result.scalars().all()

        print(f"Found {len(logs)} logs:")
        for log in logs:
            print(f"[{log.created_at}] {log.level}: {log.message}")

if __name__ == "__main__":
    asyncio.run(reproduce())
