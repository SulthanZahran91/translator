# OpenAI-Compatible Proxy Documentation

A lightweight proxy server that bridges OpenAI-compatible clients to a custom upstream LLM API with per-session authentication.

## Architecture Overview

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Client (Cline, │      │                 │      │   Upstream API  │
│  Continue, etc) │ ───► │  Proxy Server   │ ───► │  (AIDD LLM)     │
│                 │      │  localhost:8000 │      │                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘
     OpenAI API              Session Mgmt           Custom Auth
     Compatible              Token Caching          Custom Headers
```

---

## Configuration

### Environment Variables (`.env`)

| Variable | Description | Example |
|----------|-------------|---------|
| `UPSTREAM_AUTH_URL` | Upstream authentication endpoint | `https://aiddllm.singlex.com/aidd/auth` |
| `UPSTREAM_COMPLETION_URL` | Upstream completion endpoint | `https://aiddllm.singlex.com/aidd/completions` |
| `PROXY_API_KEY` | Key to authenticate with this proxy | `my-secret-key` |

### Example `.env` file

```env
UPSTREAM_AUTH_URL=https://aiddllm.singlex.com/aidd/auth
UPSTREAM_COMPLETION_URL=https://aiddllm.singlex.com/aidd/completions
PROXY_API_KEY=my-secret-proxy-key
```

---

## Downstream API (Client → Proxy)

These are the endpoints your clients (Cline, Continue, custom apps) will call.

### 1. Authentication

Creates a session with your upstream credentials. Returns a session token for subsequent requests.

**Endpoint:** `POST /auth`

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <PROXY_API_KEY>` |
| `Content-Type` | Yes | `application/json` |

**Request Body:**
```json
{
  "email": "your-email@example.com",
  "password": "your-password"
}
```

**Response (200 OK):**
```json
{
  "session_token": "sess_a1b2c3d4e5f6...",
  "message": "Authenticated successfully"
}
```

**Response (401 Unauthorized):**
```json
{
  "detail": "Invalid proxy API key"
}
```
or
```json
{
  "detail": "Upstream authentication failed"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/auth" \
  -H "Authorization: Bearer my-secret-proxy-key" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "zahranm@lgsinarmas.com",
    "password": "aidd"
  }'
```

---

### 2. Chat Completions

OpenAI-compatible chat completion endpoint. Use the session token from `/auth`.

**Endpoints:** 
- `POST /v1/chat/completions`
- `POST /chat/completions` (alias)

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <SESSION_TOKEN>` |
| `Content-Type` | Yes | `application/json` |

**Request Body:**
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | No | Model identifier (default: `gpt-3.5-turbo`) |
| `messages` | array | Yes | Array of message objects |
| `temperature` | float | No | Sampling temperature (default: 0.7) |
| `max_tokens` | int | No | Maximum tokens to generate |
| `stream` | bool | No | Enable streaming (default: false) |

**Response (200 OK):**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1699000000,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
  -H "Authorization: Bearer sess_a1b2c3d4e5f6..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

---

### 3. Dashboard

Web-based log viewer showing the last 50 requests.

**Endpoint:** `GET /dashboard`

**Authentication:** None required

**Response:** HTML page (auto-refreshes every 5 seconds)

**URL:** `http://localhost:8000/dashboard`

---

## Upstream API (Proxy → AIDD)

These are the calls the proxy makes to your upstream LLM service.

### 1. Authentication

**Endpoint:** `POST {UPSTREAM_AUTH_URL}`

**Query Parameters:**
| Parameter | Value |
|-----------|-------|
| `email` | User's email |
| `password` | User's password |

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "email": "user@example.com",
  "password": "password"
}
```

**Expected Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

The proxy looks for the token in these fields (in order):
1. `token`
2. `access_token`
3. `data.token`

---

### 2. Completions

**Endpoint:** `POST {UPSTREAM_COMPLETION_URL}`

**Headers:**
| Header | Value |
|--------|-------|
| `Authorization` | `Bearer <upstream_token>` |
| `Content-Type` | `application/json` |
| `email` | User's email |
| `product` | `API` |
| `version` | `1.0.0` |

**Body:**
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 1000
}
```

**Expected Response:**
```json
{
  "id": "chatcmpl-xxx",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Response text"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

---

## Client Configuration Examples

### Cline (VS Code Extension)

```json
{
  "cline.apiProvider": "openai-compatible",
  "cline.openaiCompatible.baseUrl": "http://localhost:8000/v1",
  "cline.openaiCompatible.apiKey": "sess_your_session_token",
  "cline.openaiCompatible.model": "gpt-4"
}
```

### Continue (VS Code Extension)

In `~/.continue/config.json`:
```json
{
  "models": [
    {
      "title": "AIDD Proxy",
      "provider": "openai",
      "model": "gpt-4",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "sess_your_session_token"
    }
  ]
}
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sess_your_session_token"
)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

---

## Session Management

| Aspect | Behavior |
|--------|----------|
| Storage | In-memory only (lost on restart) |
| Token refresh | Automatic when upstream token expires |
| Token lifetime | ~55 minutes (cached for 3300 seconds) |
| Scope | Per-session (each user has own credentials) |

---

## Error Codes

| Status | Meaning | Solution |
|--------|---------|----------|
| 401 | Invalid proxy API key | Check `PROXY_API_KEY` in `.env` |
| 401 | Invalid session token | Re-authenticate via `/auth` |
| 401 | Upstream auth failed | Check email/password |
| 403 | Missing Authorization header | Add `Authorization: Bearer <token>` |
| 500 | Upstream request failed | Check logs, verify upstream is reachable |

---

## Running the Proxy

```bash
# Install dependencies
pip install fastapi uvicorn httpx python-dotenv pydantic

# Run
python proxy.py
```

Server starts at:
- API: `http://localhost:8000`
- Dashboard: `http://localhost:8000/dashboard`

---

## Logs

- **File:** `proxy.log` (application logs)
- **Database:** `proxy_logs.db` (request history, viewable via dashboard)