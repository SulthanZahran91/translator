import httpx
from typing import Any, Dict, List, Optional
from backend.core.config import get_settings
from backend.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

class UpstreamLLMClient:
    def __init__(self, user: Optional[User] = None, db_session: Optional[AsyncSession] = None):
        self.settings = get_settings()
        self.user = user
        self.db_session = db_session

    async def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate against the upstream service.
        Returns the full response data (containing token).
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.settings.upstream_auth_url,
                json={"email": email, "password": password},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

    async def chat_completion(self, messages: List[Dict[str, Any]], model: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a chat completion request to the upstream service.
        Handles re-authentication if 401 is received.
        """
        if not self.user or not self.user.upstream_token:
            raise ValueError("User not authenticated with upstream service")

        model = model or self.settings.llm_model
        payload = {
            "model": model,
            "messages": messages,
            "stream": False 
        }

        headers = {
            "Authorization": f"Bearer {self.user.upstream_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.settings.upstream_completion_url,
                    json=payload,
                    headers=headers,
                    timeout=self.settings.timeout_seconds if hasattr(self.settings, 'timeout_seconds') else 120
                )
                
                if response.status_code == 401:
                    # Token expired, attempt re-auth
                    await self._reauthenticate()
                    # Update headers with new token
                    headers["Authorization"] = f"Bearer {self.user.upstream_token}"
                    # Retry request
                    response = await client.post(
                        self.settings.upstream_completion_url,
                        json=payload,
                        headers=headers,
                        timeout=self.settings.timeout_seconds if hasattr(self.settings, 'timeout_seconds') else 120
                    )

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Upstream API error: {e.response.text}") from e
            except Exception as e:
                raise RuntimeError(f"LLM request failed: {str(e)}") from e

    async def _reauthenticate(self):
        """
        Re-authenticate using stored credentials and update the user record.
        """
        if not self.user.email or not self.user.upstream_password:
            raise ValueError("Missing credentials for re-authentication")

        try:
            auth_data = await self.authenticate(self.user.email, self.user.upstream_password)
            new_token = auth_data.get("token")
            
            if not new_token:
                raise ValueError("No token in re-auth response")

            # Update in-memory user object
            self.user.upstream_token = new_token
            
            # Update database if session is available
            if self.db_session:
                stmt = (
                    update(User)
                    .where(User.id == self.user.id)
                    .values(upstream_token=new_token)
                )
                await self.db_session.execute(stmt)
                await self.db_session.commit()
                
        except Exception as e:
            raise RuntimeError(f"Re-authentication failed: {str(e)}") from e
