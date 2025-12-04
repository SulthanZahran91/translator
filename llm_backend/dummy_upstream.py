import uuid
import time
from typing import List, Optional, Dict, Union
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Dummy Upstream LLM")

# In-memory store for tokens
# token -> {email, expires_at}
TOKENS = {}

class AuthRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    token: str
    expires_in: int

class Message(BaseModel):
    role: str
    content: str

class CompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: bool = False

@app.post("/auth")
async def auth(req: Optional[AuthRequest] = None, email: Optional[str] = None, password: Optional[str] = None):
    # Accept any email/password for dummy purposes
    # Check body first, then query params
    req_email = req.email if req and req.email else email
    req_password = req.password if req and req.password else password

    if not req_email or not req_password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    token = f"dummy_token_{uuid.uuid4().hex[:8]}"
    TOKENS[token] = {
        "email": req_email,
        "expires_at": time.time() + 3600 # 1 hour
    }
    
    # Format A: Just the token
    return {"token": token}

async def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != 'bearer':
            raise HTTPException(status_code=401, detail="Invalid auth scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid auth header format")

    if token not in TOKENS:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    if time.time() > TOKENS[token]["expires_at"]:
        del TOKENS[token]
        raise HTTPException(status_code=401, detail="Token expired")
    
    return TOKENS[token]

@app.post("/v1/chat/completions")
async def openai_completion(
    req: CompletionRequest, 
    user_info: dict = Depends(verify_token),
    email: str = Header(...),
    product: str = Header(...),
    version: str = Header(...)
):
    # Header Validation
    if email != user_info['email']:
        raise HTTPException(status_code=403, detail="Email header does not match token owner")
    if product != "API":
        raise HTTPException(status_code=400, detail="Invalid product header")
    if version != "1.0.0":
        raise HTTPException(status_code=400, detail="Invalid version header")

    # Body Validation
    if req.stream:
        raise HTTPException(status_code=400, detail="Stream must be false")

    # Simulate an OpenAI response
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Dummy OpenAI response for {user_info['email']}: I received your message."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "total_tokens": 20
        }
    }

if __name__ == "__main__":
    # Run on port 8001 to avoid conflict with main backend (8000)
    uvicorn.run(app, host="0.0.0.0", port=8001)
