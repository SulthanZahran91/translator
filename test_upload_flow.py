#!/usr/bin/env python3
"""
Test script to verify the document upload flow end-to-end.
This script:
1. Creates/fetches a test user
2. Uploads a document via the API endpoint
3. Monitors job progress
4. Reports the results
"""
import asyncio
import httpx
import sys
import os
import time

# Add the current directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Backend API URL (via the external API)
BACKEND_URL = "http://localhost:8002"
API_PREFIX = "/api/v1"

async def register_or_login(client: httpx.AsyncClient, email: str, password: str):
    """Register a new user or login if exists."""
    print(f"[1/5] Registering/logging in user: {email}")
    
    # Try to register first
    register_response = await client.post(
        f"{BACKEND_URL}{API_PREFIX}/auth/register",
        json={"email": email, "password": password, "name": "Test User"}
    )
    
    if register_response.status_code == 201:
        print("   ✓ User registered successfully")
    elif register_response.status_code == 400:  # User exists
        print("   → User already exists, logging in...")
    else:
        print(f"   ! Registration failed: {register_response.status_code} - {register_response.text}")
    
    # Login uses OAuth2PasswordRequestForm - requires form data with 'username' field
    login_response = await client.post(
        f"{BACKEND_URL}{API_PREFIX}/auth/login",
        data={"username": email, "password": password}  # Form data with username field
    )
    
    if login_response.status_code != 200:
        print(f"   ✗ Login failed: {login_response.status_code} - {login_response.text}")
        return None
    
    data = login_response.json()
    token = data.get("access_token")
    print(f"   ✓ Login successful, got access token")
    return token


async def upload_document(client: httpx.AsyncClient, token: str, file_path: str):
    """Upload a document for translation."""
    print(f"[2/5] Uploading document: {file_path}")
    
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "text/plain")}
        data = {
            "source_language": "ko",
            "target_language": "en",
            "output_format": "docx"
        }
        
        response = await client.post(
            f"{BACKEND_URL}{API_PREFIX}/jobs",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            data=data
        )
    
    if response.status_code != 201:
        print(f"   ✗ Upload failed: {response.status_code} - {response.text}")
        return None
    
    job = response.json()
    print(f"   ✓ Job created: ID={job['id']}")
    print(f"     Status: {job['status']}")
    print(f"     Source: {job['source_file_name']}")
    return job


async def monitor_job(client: httpx.AsyncClient, token: str, job_id: str, max_wait: int = 60):
    """Monitor job progress until completion or timeout."""
    print(f"[3/5] Monitoring job progress (max {max_wait}s)...")
    
    start_time = time.time()
    last_status = None
    last_phase = None
    
    while time.time() - start_time < max_wait:
        response = await client.get(
            f"{BACKEND_URL}{API_PREFIX}/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code != 200:
            print(f"   ✗ Failed to get job status: {response.status_code}")
            return None
        
        job = response.json()
        status = job.get("status")
        phase = job.get("current_phase")
        
        if status != last_status or phase != last_phase:
            print(f"   → Status: {status}, Phase: {phase}")
            last_status = status
            last_phase = phase
        
        if status in ["completed", "failed", "cancelled"]:
            return job
        
        await asyncio.sleep(2)
    
    print(f"   ! Timeout waiting for job completion")
    return await client.get(
        f"{BACKEND_URL}{API_PREFIX}/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"}
    ).json()


async def get_job_logs(client: httpx.AsyncClient, token: str, job_id: str):
    """Get job logs."""
    print(f"[4/5] Fetching job logs...")
    
    response = await client.get(
        f"{BACKEND_URL}{API_PREFIX}/jobs/{job_id}/logs",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code != 200:
        print(f"   ✗ Failed to get logs: {response.status_code}")
        return []
    
    logs = response.json()
    print(f"   ✓ Got {len(logs)} log entries")
    return logs


async def print_summary(job: dict, logs: list):
    """Print final summary."""
    print("\n" + "=" * 60)
    print("[5/5] SUMMARY")
    print("=" * 60)
    print(f"Job ID:       {job.get('id')}")
    print(f"Status:       {job.get('status')}")
    print(f"Phase:        {job.get('current_phase')}")
    print(f"Source:       {job.get('source_file_name')}")
    print(f"Output:       {job.get('output_file_path') or 'N/A'}")
    print(f"Total Units:  {job.get('total_units') or 0}")
    print(f"Processed:    {job.get('processed_units') or 0}")
    
    if job.get("last_error"):
        print(f"\nLast Error:")
        print(f"  {job.get('last_error')}")
    
    if logs:
        print(f"\nRecent Logs:")
        for log in logs[-10:]:  # Last 10 logs
            level = log.get("level", "INFO")
            msg = log.get("message", "")
            phase = log.get("phase", "")
            print(f"  [{level}] {phase}: {msg}")
    
    print("=" * 60)
    
    if job.get("status") == "completed":
        print("✅ UPLOAD FLOW TEST PASSED")
    elif job.get("status") == "processing":
        print("⏳ Job still processing (test incomplete)")
    else:
        print(f"❌ UPLOAD FLOW TEST FAILED (status: {job.get('status')})")


async def main():
    """Main test function."""
    print("\n" + "=" * 60)
    print("DOCUMENT UPLOAD FLOW TEST")
    print("=" * 60 + "\n")
    
    # Check if test file exists
    test_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "large_test_document.txt")
    if not os.path.exists(test_file):
        print(f"Error: Test file not found: {test_file}")
        return
    
    print(f"Using test file: {test_file}")
    print(f"Backend URL: {BACKEND_URL}")
    print()
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Auth
        token = await register_or_login(client, "test@example.com", "testpass123")
        if not token:
            print("\nFailed to authenticate. Is the backend running?")
            return
        
        # 2. Upload
        job = await upload_document(client, token, test_file)
        if not job:
            print("\nFailed to upload document.")
            return
        
        # 3. Monitor
        final_job = await monitor_job(client, token, job["id"])
        if not final_job:
            final_job = job
        
        # 4. Logs
        logs = await get_job_logs(client, token, job["id"])
        
        # 5. Summary
        await print_summary(final_job, logs)


if __name__ == "__main__":
    asyncio.run(main())
