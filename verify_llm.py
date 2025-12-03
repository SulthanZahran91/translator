import asyncio
import httpx
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from backend.translation.llm_client import UpstreamLLMClient
from backend.models.user import User

async def test_integration():
    print("Testing Upstream Integration...")
    
    # 1. Test Auth directly against dummy service
    print("\n1. Testing Direct Upstream Auth...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "http://localhost:8001/auth",
                json={"email": "test@example.com", "password": "password123"}
            )
            print(f"Auth Response: {resp.status_code}")
            data = resp.json()
            token = data.get("token")
            print(f"Token received: {token}")
            assert token is not None
        except Exception as e:
            print(f"Direct Auth Failed: {e}")
            return

    # 2. Test LLM Client Wrapper
    print("\n2. Testing LLM Client Wrapper...")
    user = User(
        email="test@example.com",
        upstream_token=token,
        upstream_password="password123"
    )
    
    llm_client = UpstreamLLMClient(user=user)
    
    try:
        resp = await llm_client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-3.5-turbo"
        )
        print("Chat Completion Success!")
        print(resp)
    except Exception as e:
        print(f"LLM Client Failed: {e}")
        return

    # 3. Test Re-authentication
    print("\n3. Testing Re-authentication...")
    # Manually expire token (client side simulation)
    user.upstream_token = "expired_token"
    
    try:
        resp = await llm_client.chat_completion(
            messages=[{"role": "user", "content": "Hello again"}],
            model="gpt-3.5-turbo"
        )
        print("Re-auth & Completion Success!")
        print(f"New Token: {user.upstream_token}")
        assert user.upstream_token != "expired_token"
    except Exception as e:
        print(f"Re-auth Failed: {e}")
        return

    print("\nALL TESTS PASSED")

if __name__ == "__main__":
    asyncio.run(test_integration())
