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
async def auth(req: AuthRequest):
    # Accept any email/password for dummy purposes
    # In reality, this would check credentials
    if not req.email or not req.password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    token = f"dummy_token_{uuid.uuid4().hex[:8]}"
    TOKENS[token] = {
        "email": req.email,
        "expires_at": time.time() + 3600 # 1 hour
    }
    
    return AuthResponse(token=token, expires_in=3600)

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

@app.post("/completion")
async def completion(req: CompletionRequest, user_info: dict = Depends(verify_token)):
    # Simulate a simple response
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
                    "content": f"Dummy response for {user_info['email']}: I received your message."
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

@app.post("/v1/chat/completions")
async def openai_completion(req: CompletionRequest, user_info: dict = Depends(verify_token)):
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
