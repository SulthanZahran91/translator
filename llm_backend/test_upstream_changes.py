import subprocess
import time
import requests
import sys
import os
import signal

def run_test():
    print("Starting services...")
    
    # Start dummy upstream
    upstream_process = subprocess.Popen(
        [sys.executable, "llm_backend/dummy_upstream.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Start llm backend
    backend_process = subprocess.Popen(
        [sys.executable, "llm_backend/llm_backend.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for services to start
    time.sleep(10)
    
    try:
        print("\n--- Test 1: Direct Upstream Auth (Query Params) ---")
        # Test auth with query params
        resp = requests.post(
            "http://localhost:8001/auth",
            params={"email": "test@example.com", "password": "pass"}
        )
        if resp.status_code == 200 and "token" in resp.json():
            print("✅ Direct Upstream Auth (Query Params) Passed")
            upstream_token = resp.json()["token"]
        else:
            print(f"❌ Direct Upstream Auth (Query Params) Failed: {resp.status_code} {resp.text}")
            return

        print("\n--- Test 2: Direct Upstream Completion (No Recommend Header) ---")
        # Test completion without recommend header
        headers = {
            "Authorization": f"Bearer {upstream_token}",
            "Content-Type": "application/json",
            "email": "test@example.com",
            "product": "API",
            "version": "1.0.0"
        }
        data = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False
        }
        resp = requests.post(
            "http://localhost:8001/v1/chat/completions",
            headers=headers,
            json=data
        )
        if resp.status_code == 200:
            print("✅ Direct Upstream Completion (No Recommend Header) Passed")
        else:
            print(f"❌ Direct Upstream Completion (No Recommend Header) Failed: {resp.status_code} {resp.text}")
            return

        print("\n--- Test 3: Proxy Auth ---")
        print("⚠️  Skipping Proxy /auth test as endpoint is not implemented in current llm_backend.py")

        print("\n--- Test 4: Proxy Completion ---")
        # Test proxy completion
        headers = {
            "Authorization": "Bearer test", # Proxy API Key
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello via Proxy"}],
            "stream": False
        }
        resp = requests.post(
            "http://localhost:8000/v1/chat/completions",
            headers=headers,
            json=data
        )
        if resp.status_code == 200:
             print("✅ Proxy Completion Passed")
             print("Response:", resp.json())
        else:
             print(f"❌ Proxy Completion Failed: {resp.status_code} {resp.text}")

    except Exception as e:
        print(f"❌ Test Failed with Exception: {e}")
        print("--- Upstream Output ---")
        print(upstream_process.stdout.read().decode())
        print(upstream_process.stderr.read().decode())
        print("--- Backend Output ---")
        print(backend_process.stdout.read().decode())
        print(backend_process.stderr.read().decode())
    finally:
        print("\nStopping services...")
        if upstream_process.poll() is None:
            os.kill(upstream_process.pid, signal.SIGTERM)
        if backend_process.poll() is None:
            os.kill(backend_process.pid, signal.SIGTERM)

if __name__ == "__main__":
    run_test()
