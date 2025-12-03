import asyncio
import sys
import os
from datetime import datetime

# Add the current directory to sys.path so backend module can be found
sys.path.append(os.getcwd())

from sqlalchemy import select
from backend.core.database import async_session_factory
from backend.models.job import TranslationJob, JobStatus
from backend.models.user import User
from backend.translation.runner import JobRunner

async def verify_job_flow():
    print("Starting verification script...")
    
    async with async_session_factory() as db:
        # 1. Create a dummy user if not exists
        result = await db.execute(select(User).where(User.email == "test@example.com"))
        user = result.scalar_one_or_none()
        if not user:
            user = User(email="test@example.com", password_hash="hashed_password", name="Test User")
            db.add(user)
            await db.commit()
            await db.refresh(user)
        
        # 2. Create a dummy job
        job = TranslationJob(
            user_id=user.id,
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
        await db.refresh(job)
        print(f"Job created with ID: {job.id}")
        
        # Create a dummy file for the runner to find
        with open("/tmp/test.docx", "w") as f:
            f.write("Dummy content")

        # 3. Run the job runner (mocking the actual processing steps if needed, 
        # but here we want to see if it runs and updates status)
        # Note: The runner will fail at ingestion because it's not a real docx, 
        # but it should update status to PROCESSING and then FAILED.
        # This confirms the runner is executing and updating DB.
        
        runner = JobRunner(job.id)
        await runner.run()
        
        # 4. Check final status
        await db.refresh(job)
        print(f"Final Job Status: {job.status}")
        print(f"Current Phase: {job.current_phase}")
        print(f"Last Error: {job.last_error}")
        
        if job.status != JobStatus.PENDING.value:
            print("SUCCESS: Job status updated from PENDING")
        else:
            print("FAILURE: Job status remained PENDING")

if __name__ == "__main__":
    asyncio.run(verify_job_flow())
