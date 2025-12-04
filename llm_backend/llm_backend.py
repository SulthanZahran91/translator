import json
import time
import os
import uuid
import re
import httpx
import uvicorn
import asyncio
import asyncio
import logging
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

# Set up standard file logging (replaces print)
logging.basicConfig(
    filename='proxy.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

class Settings(BaseModel):
    upstream_auth_url: str
    upstream_completion_url: str
    upstream_email: str
    upstream_password: str
    token_json_key: str = "token"
    timeout_seconds: int = 120
    proxy_api_key: str = "test"

    @classmethod
    def from_env(cls):
        return cls(
            upstream_auth_url=os.getenv("UPSTREAM_AUTH_URL", "http://localhost:8001/auth"),
            upstream_completion_url=os.getenv("UPSTREAM_COMPLETION_URL", "http://localhost:8001/v1/chat/completions"),
            upstream_email=os.getenv("UPSTREAM_EMAIL", "test@example.com"),
            upstream_password=os.getenv("UPSTREAM_PASSWORD", "pass"),
            proxy_api_key=os.getenv("PROXY_API_KEY", "test")
        )

try:
    settings = Settings.from_env()
except Exception as e:
    logger.error(f"Failed to load settings: {e}")
    settings = None





# --- APP SETUP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings: 
        logger.info("Adapter Configured Successfully")
    yield

app = FastAPI(title="OpenAI-Compatible Bridge", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# --- OPENAI SCHEMAS ---
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

# --- TOKEN CACHE LOGIC ---
token_store: Dict[str, Dict] = {}

def get_cached_token() -> Optional[str]:
    cache_key = f"{settings.upstream_email}@{settings.upstream_auth_url}"
    entry = token_store.get(cache_key)
    if entry and entry['expiry'] > time.time(): return entry['token']
    return None

def save_token(token: str, expires_in: int = 3300):
    cache_key = f"{settings.upstream_email}@{settings.upstream_auth_url}"
    token_store[cache_key] = {"token": token, "expiry": time.time() + expires_in}

def clear_token_cache():
    cache_key = f"{settings.upstream_email}@{settings.upstream_auth_url}"
    if cache_key in token_store: del token_store[cache_key]

async def get_upstream_token() -> str:
    cached = get_cached_token()
    if cached: return cached
    logger.info("Authenticating...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                settings.upstream_auth_url,
                params={"email": settings.upstream_email, "password": settings.upstream_password},
                json={"email": settings.upstream_email, "password": settings.upstream_password},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            token = data.get(settings.token_json_key) or data.get("access_token") or data.get("data", {}).get("token")
            if not token: raise ValueError("Token not found")
            save_token(token)
            return token
        except Exception as e:
            logger.error(f"Auth failed: {e}")
            raise HTTPException(status_code=401, detail=f"Auth Failed: {str(e)}")

# --- STREAM GENERATOR ---
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



# --- MAIN ENDPOINT ---
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
        if auth.credentials != settings.proxy_api_key:
            status_code = 401
            raise HTTPException(status_code=401, detail="Invalid Proxy Key")

        # --- Prepare Payload (Force Stream: False) ---
        messages_payload = []
        for m in request.messages:
            msg_dict = {"role": m.role}
            msg_dict["content"] = m.content if m.content is not None else ""
            if m.tool_calls: msg_dict["tool_calls"] = m.tool_calls
            if m.tool_call_id: msg_dict["tool_call_id"] = m.tool_call_id
            messages_payload.append(msg_dict)
        
        payload = {
            "model": request.model,
            "messages": messages_payload,
            "stream": False # FORCE FALSE UPSTREAM
        }
        
        if request.temperature is not None: payload["temperature"] = request.temperature
        if request.max_tokens is not None: payload["max_tokens"] = request.max_tokens

        # --- RETRY LOOP ---
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                upstream_token = await get_upstream_token()
                
                headers = {
                    "Authorization": f"Bearer {upstream_token}",
                    "Content-Type": "application/json",
                    "email": settings.upstream_email,
                    "product": "API",
                    "version": "1.0.0",
                    "version": "1.0.0"
                }

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        settings.upstream_completion_url,
                        json=payload,
                        headers=headers,
                        timeout=settings.timeout_seconds
                    )
                    
                    if resp.status_code == 401:
                        logger.warning(f"Got 401 Unauthorized. Attempt {attempt}")
                        if attempt < max_retries:
                            clear_token_cache() 
                            continue 
                        status_code = 401
                        raise HTTPException(status_code=401, detail="Token rejected.")

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
                                if "type" not in tc: tc["type"] = "function"
                                if "function" not in tc: tc["function"] = {"name": "unknown", "arguments": "{}"}
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
                        response_data["usage"] = {k:v for k,v in response_data["usage"].items() if v is not None}
                    
                    status_code = 200
                    
                    # --- CHECK STREAM REQUEST ---
                    if request.stream:
                        return StreamingResponse(
                            generate_fake_stream(response_data),
                            media_type="text/event-stream"
                        )
                    else:
                        return JSONResponse(content=response_data)

            except HTTPException: raise
            except Exception as e:
                if attempt < max_retries and "401" in str(e):
                     clear_token_cache()
                     continue
                logger.error(f"Error: {e}")
                status_code = 500
                response_data = {"error": str(e)}
                raise HTTPException(status_code=500, detail=str(e))
    
    except Exception as e:
        status_code = 500 if status_code == 200 else status_code
        response_data = {"error": str(e)}
        raise e
        


@app.post("/chat/completions")
async def chat_completions_alias(raw_request: Request, req: OpenAIRequest, auth: HTTPAuthorizationCredentials = Depends(security)):
    return await chat_completions(raw_request, req, auth)

if __name__ == "__main__":
    print("🔋 Model Bridge Active (XML-to-JSON + Stream Faker)")
    print("📊 Dashboard available at http://localhost:8000/dashboard")
    uvicorn.run(app, host="0.0.0.0", port=8000)