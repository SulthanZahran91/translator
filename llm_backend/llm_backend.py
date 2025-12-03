import json
import time
import os
import uuid
import re
import httpx
import uvicorn
import asyncio
import sqlite3
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

DB_PATH = "proxy_logs.db"

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
            upstream_auth_url=os.getenv("UPSTREAM_AUTH_URL", ""),
            upstream_completion_url=os.getenv("UPSTREAM_COMPLETION_URL", ""),
            upstream_email=os.getenv("UPSTREAM_EMAIL", ""),
            upstream_password=os.getenv("UPSTREAM_PASSWORD", ""),
            proxy_api_key=os.getenv("PROXY_API_KEY", "test")
        )

try:
    settings = Settings.from_env()
except Exception as e:
    logger.error(f"Failed to load settings: {e}")
    settings = None

# --- DATABASE HELPERS ---
def init_db():
    """Initialize the SQLite database for persistent logging."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS request_logs (
            id TEXT PRIMARY KEY,
            timestamp DATETIME,
            model TEXT,
            status_code INTEGER,
            duration_ms REAL,
            request_body TEXT,
            response_body TEXT,
            upstream_url TEXT
        )
    ''')
    conn.commit()
    conn.close()

def log_request_to_db(
    request_id: str, 
    model: str, 
    status_code: int, 
    duration_ms: float, 
    req_body: dict, 
    res_body: Any,
    upstream_url: str
):
    """Background task to write logs to DB without blocking the API."""
    try:
        # Convert objects to JSON strings for storage
        req_json = json.dumps(req_body, default=str)
        
        # Handle response body which might be a dict or a string/exception
        if isinstance(res_body, dict):
            res_json = json.dumps(res_body, default=str)
        else:
            res_json = str(res_body)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO request_logs 
            (id, timestamp, model, status_code, duration_ms, request_body, response_body, upstream_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            request_id, 
            datetime.now(), 
            model, 
            status_code, 
            duration_ms, 
            req_json, 
            res_json, 
            upstream_url
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to write to DB: {e}")

# --- XML PARSING HELPER ---
def parse_xml_to_tool_calls(content: str) -> tuple[str, List[Dict]]:
    if not content: return "", []
    tool_calls = []
    
    # Define patterns for known Cline tools
    tool_patterns = [
        ("ask_followup_question", r'<ask_followup_question>(.*?)</ask_followup_question>'),
        ("execute_command", r'<execute_command>(.*?)</execute_command>'),
        ("read_file", r'<read_file>(.*?)</read_file>'),
        ("write_to_file", r'<write_to_file>(.*?)</write_to_file>'),
        ("replace_in_file", r'<replace_in_file>(.*?)</replace_in_file>'),
        ("search_files", r'<search_files>(.*?)</search_files>'),
        ("list_files", r'<list_files>(.*?)</list_files>'),
        ("list_code_definition_names", r'<list_code_definition_names>(.*?)</list_code_definition_names>'),
        ("browser_action", r'<browser_action>(.*?)</browser_action>'),
        ("attempt_completion", r'<attempt_completion>(.*?)</attempt_completion>'),
        ("plan_mode_respond", r'<plan_mode_respond>(.*?)</plan_mode_respond>'),
        ("use_mcp_tool", r'<use_mcp_tool>(.*?)</use_mcp_tool>'),
        ("access_mcp_resource", r'<access_mcp_resource>(.*?)</access_mcp_resource>'),
    ]

    for tool_name, pattern in tool_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            inner_xml = match.group(1)
            arguments = {}
            # Extract arguments
            arg_matches = re.finditer(r'<([a-zA-Z0-9_]+)>(.*?)</\1>', inner_xml, re.DOTALL)
            for arg_match in arg_matches:
                arg_name = arg_match.group(1)
                arg_val = arg_match.group(2).strip()
                arguments[arg_name] = arg_val

            tool_call = {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(arguments)
                }
            }
            tool_calls.append(tool_call)
            content = content.replace(match.group(0), "").strip()

    return content, tool_calls

# --- APP SETUP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

# --- DASHBOARD ENDPOINT ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM request_logs ORDER BY timestamp DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()

    rows_html = ""
    for row in rows:
        status_color = "green" if 200 <= row['status_code'] < 300 else "red"
        # Truncate bodies for display
        req_preview = (row['request_body'][:100] + '...') if row['request_body'] and len(row['request_body']) > 100 else row['request_body']
        res_preview = (row['response_body'][:100] + '...') if row['response_body'] and len(row['response_body']) > 100 else row['response_body']
        
        rows_html += f"""
        <tr>
            <td>{row['timestamp']}</td>
            <td>{row['model']}</td>
            <td style="color:{status_color}; font-weight:bold;">{row['status_code']}</td>
            <td>{int(row['duration_ms'])}ms</td>
            <td><div class="code-box" title="{row['request_body']}">{req_preview}</div></td>
            <td><div class="code-box" title="{row['response_body']}">{res_preview}</div></td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>API Proxy Dashboard</title>
        <style>
            body {{ font-family: -apple-system, system-ui, sans-serif; padding: 20px; background: #f4f4f9; }}
            h1 {{ color: #333; }}
            table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f8f9fa; font-weight: 600; color: #555; }}
            tr:hover {{ background-color: #f1f1f1; }}
            .code-box {{ font-family: monospace; background: #eee; padding: 4px; border-radius: 4px; font-size: 0.9em; cursor: help; }}
        </style>
        <meta http-equiv="refresh" content="5">
    </head>
    <body>
        <h1>📊 Proxy Request Log (Last 50)</h1>
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Model</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Request Preview</th>
                    <th>Response Preview</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- MAIN ENDPOINT ---
@app.post("/v1/chat/completions")
async def chat_completions(
    raw_request: Request,
    request: OpenAIRequest, 
    background_tasks: BackgroundTasks,
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
                    "recommend":"test-recommendation-API-call"
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
                        
                        # DETECT XML & CONVERT
                        existing_tools = msg.get("tool_calls", [])
                        if not existing_tools:
                            cleaned_content, extracted_tools = parse_xml_to_tool_calls(content)
                            if extracted_tools:
                                logger.info(f"Detected {len(extracted_tools)} XML tools! Converting...")
                                existing_tools = extracted_tools

                        # CLEANUP TOOLS
                        clean_tool_calls = []
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
        
    finally:
        duration = (time.time() - start_time) * 1000
        # Register the log writing to happen AFTER the response is sent
        background_tasks.add_task(
            log_request_to_db, 
            req_id, 
            request.model, 
            status_code, 
            duration, 
            request.model_dump(), 
            response_data, 
            settings.upstream_completion_url
        )

@app.post("/chat/completions")
async def chat_completions_alias(raw_request: Request, req: OpenAIRequest, background_tasks: BackgroundTasks, auth: HTTPAuthorizationCredentials = Depends(security)):
    return await chat_completions(raw_request, req, background_tasks, auth)

if __name__ == "__main__":
    print("🔋 Model Bridge Active (XML-to-JSON + Stream Faker)")
    print("📊 Dashboard available at http://localhost:8000/dashboard")
    uvicorn.run(app, host="0.0.0.0", port=8000)