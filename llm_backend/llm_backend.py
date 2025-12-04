import json
import time
import os
import uuid
import re
import httpx
import uvicorn
import asyncio
import logging
import secrets
from datetime import datetime
from typing import Optional, Dict, List, Union, Any
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel

# --- 1. CONFIGURATION & LOGGING SETUP ---
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Set up standard file logging
logging.basicConfig(
    filename=str(BASE_DIR / 'proxy.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)


class Settings(BaseModel):
    upstream_auth_url: str
    upstream_completion_url: str
    token_json_key: str = "token"
    timeout_seconds: int = 120
    master_api_key: Optional[str] = None  # Optional master key for admin

    @classmethod
    def from_env(cls):
        return cls(
            upstream_auth_url=os.getenv("UPSTREAM_AUTH_URL", "http://localhost:8001/auth"),
            upstream_completion_url=os.getenv("UPSTREAM_COMPLETION_URL", "http://localhost:8001/v1/chat/completions"),
            master_api_key=os.getenv("MASTER_API_KEY", None)
        )

try:
    settings = Settings.from_env()
except Exception as e:
    logger.error(f"Failed to load settings: {e}")
    settings = None


# --- 2. USER/TOKEN STORE ---
# Maps proxy_api_key -> user session data
user_sessions: Dict[str, Dict] = {}

# Structure of each session:
# {
#     "email": str,
#     "password": str,
#     "upstream_token": str,
#     "token_expiry": float (timestamp),
#     "created_at": float (timestamp)
# }


def generate_proxy_api_key() -> str:
    """Generate a secure random API key for the proxy."""
    return f"pk_{secrets.token_urlsafe(32)}"


def get_user_session(proxy_api_key: str) -> Optional[Dict]:
    """Get user session by proxy API key."""
    return user_sessions.get(proxy_api_key)


def save_user_session(proxy_api_key: str, email: str, password: str, upstream_token: str, expires_in: int = 3300):
    """Save or update a user session."""
    user_sessions[proxy_api_key] = {
        "email": email,
        "password": password,
        "upstream_token": upstream_token,
        "token_expiry": time.time() + expires_in,
        "created_at": time.time()
    }


def update_upstream_token(proxy_api_key: str, upstream_token: str, expires_in: int = 3300):
    """Update just the upstream token for an existing session."""
    if proxy_api_key in user_sessions:
        user_sessions[proxy_api_key]["upstream_token"] = upstream_token
        user_sessions[proxy_api_key]["token_expiry"] = time.time() + expires_in


def is_token_expired(proxy_api_key: str) -> bool:
    """Check if the upstream token is expired."""
    session = user_sessions.get(proxy_api_key)
    if not session:
        return True
    return session["token_expiry"] <= time.time()


def delete_user_session(proxy_api_key: str):
    """Delete a user session."""
    if proxy_api_key in user_sessions:
        del user_sessions[proxy_api_key]


async def refresh_upstream_token(proxy_api_key: str) -> str:
    """Refresh the upstream token for a user session."""
    session = user_sessions.get(proxy_api_key)
    if not session:
        raise HTTPException(status_code=401, detail="Session not found. Please authenticate again.")
    
    email = session["email"]
    password = session["password"]
    
    logger.info(f"[TOKEN REFRESH] Refreshing token for {email}")
    
    async with httpx.AsyncClient() as client:
        try:
            auth_payload = {"email": email, "password": password}
            
            response = await client.post(
                settings.upstream_auth_url,
                params=auth_payload,
                json=auth_payload,
                timeout=10.0
            )
            
            logger.info(f"[TOKEN REFRESH] Response Status: {response.status_code}")
            
            if response.status_code != 200:
                delete_user_session(proxy_api_key)
                raise HTTPException(status_code=401, detail="Token refresh failed. Please authenticate again.")
            
            data = response.json()
            token = (
                data.get(settings.token_json_key) or
                data.get("access_token") or
                data.get("data", {}).get("token")
            )
            
            if not token:
                raise HTTPException(status_code=401, detail="Token not found in refresh response")
            
            update_upstream_token(proxy_api_key, token)
            logger.info(f"[TOKEN REFRESH] Success for {email}")
            return token
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[TOKEN REFRESH] Error: {e}")
            raise HTTPException(status_code=500, detail=f"Token refresh error: {str(e)}")


# --- 3. APP SETUP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings:
        logger.info("Adapter Configured Successfully")
        logger.info(f"Upstream Auth URL: {settings.upstream_auth_url}")
        logger.info(f"Upstream Completion URL: {settings.upstream_completion_url}")
    yield

app = FastAPI(title="OpenAI-Compatible Bridge", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


# --- 4. SCHEMAS ---
class AuthRequest(BaseModel):
    email: str
    password: str

class OpenAIMessage(BaseModel):
    role: str
    content: Optional[Union[str, List[Dict]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    model_config = {"extra": "ignore"}

class OpenAIRequest(BaseModel):
    model: str = "gpt-3.5-turbo"
    messages: List[OpenAIMessage]
    temperature: Optional[float] = 0.7
    stream: bool = False
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[Union[str, Dict]] = None
    model_config = {"extra": "ignore"}


# --- 5. STREAM GENERATOR ---
async def generate_fake_stream(response_data: dict):
    chunk_id = response_data.get("id", f"chatcmpl-{uuid.uuid4()}")
    created = response_data.get("created", int(time.time()))
    model = response_data.get("model", "unknown")
    
    choices = response_data.get("choices", [])
    if not choices:
        yield "data: [DONE]\n\n"
        return

    choice = choices[0]
    message = choice.get("message", {})
    
    delta = {
        "role": message.get("role", "assistant"),
        "content": message.get("content", "")
    }
    
    if "tool_calls" in message:
        delta["tool_calls"] = message["tool_calls"]

    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": choice.get("finish_reason", "stop")
            }
        ]
    }

    yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"


# --- 6. AUTH ENDPOINT ---
@app.post("/auth")
async def proxy_auth(
    request: Request,
    auth_body: Optional[AuthRequest] = None
):
    """
    Authenticate and get a proxy API key.
    Accepts email/password via JSON body or query params.
    Returns a unique proxy API key to use for subsequent requests.
    """
    # Get credentials from body or query params
    if auth_body:
        email = auth_body.email
        password = auth_body.password
    else:
        email = request.query_params.get("email")
        password = request.query_params.get("password")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    logger.info("=" * 60)
    logger.info(f"[AUTH] Proxy auth attempt for: {email}")
    
    # Try to authenticate against upstream
    async with httpx.AsyncClient() as client:
        try:
            auth_payload = {"email": email, "password": password}
            
            logger.info(f"[AUTH] URL: {settings.upstream_auth_url}")
            logger.info(f"[AUTH] Payload: {json.dumps(auth_payload, indent=2)}")
            
            response = await client.post(
                settings.upstream_auth_url,
                params=auth_payload,
                json=auth_payload,
                timeout=10.0
            )
            
            logger.info(f"[AUTH] Response Status: {response.status_code}")
            logger.info(f"[AUTH] Response Body: {response.text}")
            
            if response.status_code != 200:
                logger.warning(f"[AUTH] Failed for {email}: {response.status_code}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Upstream auth failed: {response.text}"
                )
            
            data = response.json()
            upstream_token = (
                data.get(settings.token_json_key) or
                data.get("access_token") or
                data.get("data", {}).get("token")
            )
            
            if not upstream_token:
                raise HTTPException(status_code=401, detail="Token not found in response")
            
            # Generate a unique proxy API key for this user
            proxy_api_key = generate_proxy_api_key()
            
            # Save the session
            save_user_session(proxy_api_key, email, password, upstream_token)
            
            logger.info(f"[AUTH] Success! New session created for: {email}")
            logger.info(f"[AUTH] Proxy API Key: {proxy_api_key[:20]}...")
            logger.info("=" * 60)
            
            return JSONResponse(content={
                "status": "success",
                "message": f"Authenticated as {email}",
                "api_key": proxy_api_key,
                "token_type": "Bearer",
                "expires_in": 3300
            })
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[AUTH] Error: {e}")
            raise HTTPException(status_code=500, detail=f"Auth error: {str(e)}")


# --- 7. LOGOUT ENDPOINT ---
@app.post("/logout")
async def proxy_logout(
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    """Invalidate a proxy API key."""
    if not auth:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    proxy_api_key = auth.credentials
    session = get_user_session(proxy_api_key)
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    email = session["email"]
    delete_user_session(proxy_api_key)
    
    logger.info(f"[LOGOUT] Session deleted for: {email}")
    
    return JSONResponse(content={
        "status": "success",
        "message": "Logged out successfully"
    })


# --- 8. SESSION INFO ENDPOINT ---
@app.get("/me")
async def get_session_info(
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    """Get current session info."""
    if not auth:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    proxy_api_key = auth.credentials
    session = get_user_session(proxy_api_key)
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    return JSONResponse(content={
        "email": session["email"],
        "created_at": datetime.fromtimestamp(session["created_at"]).isoformat(),
        "token_expires_at": datetime.fromtimestamp(session["token_expiry"]).isoformat(),
        "token_expired": is_token_expired(proxy_api_key)
    })


# --- 9. MAIN COMPLETION ENDPOINT ---
@app.post("/v1/chat/completions")
async def chat_completions(
    raw_request: Request,
    request: OpenAIRequest,
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    start_time = time.time()
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    response_data = None
    status_code = 500
    
    try:
        # --- AUTHENTICATION ---
        if not auth:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        proxy_api_key = auth.credentials
        session = get_user_session(proxy_api_key)
        
        if not session:
            raise HTTPException(status_code=401, detail="Invalid API key. Please authenticate via /auth first.")
        
        email = session["email"]
        logger.info(f"[{req_id}] Request from user: {email}")
        
        # Check if upstream token needs refresh
        if is_token_expired(proxy_api_key):
            logger.info(f"[{req_id}] Token expired, refreshing...")
            await refresh_upstream_token(proxy_api_key)
            session = get_user_session(proxy_api_key)  # Get updated session
        
        upstream_token = session["upstream_token"]

        # --- Prepare Payload ---
        messages_payload = []
        for m in request.messages:
            msg_dict = {"role": m.role}
            msg_dict["content"] = m.content if m.content is not None else ""
            if m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            messages_payload.append(msg_dict)
        
        payload = {
            "model": request.model,
            "messages": messages_payload,
            "stream": False  # FORCE FALSE UPSTREAM
        }
        
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        # --- RETRY LOOP ---
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                headers = {
                    "Authorization": f"Bearer {upstream_token}",
                    "Content-Type": "application/json",
                    "email": email,
                    "product": "API",
                    "version": "1.0.0",
                }

                # LOG REQUEST
                logger.info("=" * 60)
                logger.info(f"[{req_id}] UPSTREAM REQUEST")
                logger.info(f"[{req_id}] User: {email}")
                logger.info(f"[{req_id}] URL: {settings.upstream_completion_url}")
                logger.info(f"[{req_id}] Headers: {json.dumps({k: ('***' if k == 'Authorization' else v) for k, v in headers.items()}, indent=2)}")
                logger.info(f"[{req_id}] Payload: {json.dumps(payload, indent=2)}")

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        settings.upstream_completion_url,
                        json=payload,
                        headers=headers,
                        timeout=settings.timeout_seconds
                    )
                    
                    # LOG RESPONSE
                    logger.info(f"[{req_id}] UPSTREAM RESPONSE")
                    logger.info(f"[{req_id}] Status: {resp.status_code}")
                    logger.info(f"[{req_id}] Response Body: {resp.text}")
                    logger.info("=" * 60)
                    
                    if resp.status_code == 401:
                        logger.warning(f"[{req_id}] Got 401 Unauthorized. Attempt {attempt}")
                        if attempt < max_retries:
                            # Try to refresh token
                            upstream_token = await refresh_upstream_token(proxy_api_key)
                            continue
                        status_code = 401
                        raise HTTPException(status_code=401, detail="Token rejected. Please re-authenticate.")

                    resp.raise_for_status()
                    data = resp.json()
                    
                    # --- RESPONSE PROCESSING ---
                    final_choices = []
                    raw_choices = data.get("choices", [])
                    
                    if not raw_choices and "response" in data:
                        raw_choices = [{"message": {"role": "assistant", "content": data["response"]}}]

                    for i, choice in enumerate(raw_choices):
                        msg = choice.get("message", {})
                        content = msg.get("content") or ""
                        
                        # CLEANUP TOOLS
                        clean_tool_calls = []
                        existing_tools = msg.get("tool_calls", [])
                        if existing_tools and isinstance(existing_tools, list):
                            for tc in existing_tools:
                                if "type" not in tc:
                                    tc["type"] = "function"
                                if "function" not in tc:
                                    tc["function"] = {"name": "unknown", "arguments": "{}"}
                                clean_tool_calls.append(tc)
                        
                        clean_msg = {"role": msg.get("role", "assistant"), "content": content}
                        finish_reason = choice.get("finish_reason", "stop")

                        if clean_tool_calls:
                            clean_msg["tool_calls"] = clean_tool_calls
                            finish_reason = "tool_calls"

                        final_choices.append({
                            "index": i,
                            "message": clean_msg,
                            "finish_reason": finish_reason
                        })

                    response_data = {
                        "id": data.get("id", f"chatcmpl-{uuid.uuid4()}"),
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": request.model,
                        "choices": final_choices,
                        "usage": data.get("usage", {})
                    }
                    
                    if response_data["usage"]:
                        response_data["usage"] = {k: v for k, v in response_data["usage"].items() if v is not None}
                    
                    status_code = 200
                    elapsed = time.time() - start_time
                    logger.info(f"[{req_id}] Request completed in {elapsed:.2f}s for user: {email}")
                    
                    # --- CHECK STREAM REQUEST ---
                    if request.stream:
                        return StreamingResponse(
                            generate_fake_stream(response_data),
                            media_type="text/event-stream"
                        )
                    else:
                        return JSONResponse(content=response_data)

            except HTTPException:
                raise
            except Exception as e:
                if attempt < max_retries and "401" in str(e):
                    upstream_token = await refresh_upstream_token(proxy_api_key)
                    continue
                logger.error(f"[{req_id}] Error: {e}")
                status_code = 500
                response_data = {"error": str(e)}
                raise HTTPException(status_code=500, detail=str(e))
    
    except HTTPException:
        raise
    except Exception as e:
        status_code = 500 if status_code == 200 else status_code
        response_data = {"error": str(e)}
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/completions")
async def chat_completions_alias(
    raw_request: Request,
    req: OpenAIRequest,
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    return await chat_completions(raw_request, req, auth)


# --- 10. HEALTH & INFO ENDPOINTS ---
@app.get("/health")
async def health_check():
    return {"status": "healthy", "active_sessions": len(user_sessions)}


@app.get("/")
async def root():
    return HTMLResponse(content="""
    <html>
        <head><title>OpenAI-Compatible Bridge</title></head>
        <body>
            <h1>🔋 OpenAI-Compatible Bridge</h1>
            <h2>Endpoints:</h2>
            <ul>
                <li><code>POST /auth</code> - Authenticate and get API key</li>
                <li><code>POST /logout</code> - Invalidate API key</li>
                <li><code>GET /me</code> - Get session info</li>
                <li><code>POST /v1/chat/completions</code> - Chat completions (OpenAI compatible)</li>
                <li><code>POST /chat/completions</code> - Chat completions (alias)</li>
                <li><code>GET /health</code> - Health check</li>
            </ul>
            <h2>Usage:</h2>
            <ol>
                <li>Call <code>POST /auth</code> with email/password to get an API key</li>
                <li>Use the returned API key in the <code>Authorization: Bearer &lt;api_key&gt;</code> header</li>
                <li>Call <code>/v1/chat/completions</code> with your requests</li>
            </ol>
        </body>
    </html>
    """)


if __name__ == "__main__":
    print("🔋 Model Bridge Active (Multi-User Support)")
    print("📍 Endpoints:")
    print("   POST /auth - Authenticate and get API key")
    print("   POST /v1/chat/completions - Chat completions")
    print("   GET  /health - Health check")
    print("   GET  / - Info page")
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)