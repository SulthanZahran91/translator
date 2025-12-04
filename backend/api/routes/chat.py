import json
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from backend.api.routes.auth import get_current_user
from backend.core.config import Settings, get_settings
from backend.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None
    temperature: Optional[float] = None
    stream: bool = True

class ChatSettings(BaseModel):
    llm_api_url: str
    llm_api_key: str
    llm_model: str
    temperature: float = 0.7 # Default temperature if not in config

@router.post("/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
):
    """
    Generate chat completions using the configured LLM.
    Proxies requests to the backend's LLM provider (e.g., OpenAI, Local LLM).
    """

    # Use settings from request or default to global config
    model = request.model or settings.llm_model
    api_key = settings.llm_api_key
    base_url = settings.llm_api_url

    # Initialize OpenAI client
    if not current_user.upstream_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated with upstream service. Please login again."
        )
    
    client = AsyncOpenAI(api_key=current_user.upstream_token, base_url=base_url)

    try:
        if request.stream:
            return StreamingResponse(
                stream_generator(client, request.messages, model, request.temperature),
                media_type="text/event-stream"
            )
        else:
            response = await client.chat.completions.create(
                model=model,
                messages=[m.model_dump() for m in request.messages],
                temperature=request.temperature,
                stream=False
            )
            return response.model_dump()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM Provider Error: {str(e)}"
        )

async def stream_generator(client: AsyncOpenAI, messages: List[Message], model: str, temperature: Optional[float]) -> AsyncGenerator[str, None]:
    """Generator for streaming responses."""
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[m.model_dump() for m in messages],
            temperature=temperature,
            stream=True
        )

        async for chunk in stream:
            # Format as SSE data
            data = json.dumps(chunk.model_dump(), default=str)
            yield f"data: {data}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as e:
        # In a stream, we can't raise HTTP exception easily once started,
        # but we can yield an error message if needed or just stop.
        # For now, we'll log it (conceptually) and stop.
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@router.get("/settings", response_model=ChatSettings)
async def get_chat_settings(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
):
    """Get current global chat settings."""
    return ChatSettings(
        llm_api_url=settings.llm_api_url,
        llm_api_key=settings.llm_api_key,
        llm_model=settings.llm_model,
        temperature=0.7 # Default, as it's not in Settings class explicitly for chat
    )

@router.put("/settings")
async def update_chat_settings(
    new_settings: ChatSettings,
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
):
    """
    Update global chat settings in-memory.
    Note: This does not persist to .env file.
    """
    settings.llm_api_url = new_settings.llm_api_url
    settings.llm_api_key = new_settings.llm_api_key
    settings.llm_model = new_settings.llm_model

    return {"status": "updated", "settings": new_settings}
