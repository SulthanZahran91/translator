import asyncio
import sys
import os

# Add the current directory to sys.path so backend module can be found
sys.path.append(os.getcwd())

from backend.translation.llm_client import UpstreamLLMClient
from backend.models.user import User

async def main():
    print("Starting reproduction script...")
    # Mock user
    user = User(email="test@example.com", upstream_password="password")
    client = UpstreamLLMClient(user=user)
    
    try:
        print("Authenticating...")
        auth_response = await client.authenticate("test@example.com", "password")
        print(f"Auth response: {auth_response}")
        
        token = auth_response["token"]
        user.upstream_token = token
        
        print("Sending completion request...")
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="test-model"
        )
        print(f"Completion response: {response}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
