# Upstream API Documentation

## 1\. Authentication

The API uses a token-based authentication system. You must exchange credentials for a session token before making inference requests.

**Endpoint:** `POST <UPSTREAM_AUTH_URL>`
**Content-Type:** `application/json`

### Request Body

```json
{
  "email": "user@example.com",
  "password": "your_password"
}
```

### Response

The API returns a JSON object containing the token.

**Output Formats:**

```json
// Format A
{ "token": "eyJhbGciOi..." }

```

-----

## 2\. Chat Completions

This is the main inference endpoint.

**Endpoint:** `POST <UPSTREAM_COMPLETION_URL>`
**Content-Type:** `application/json`

### Required Headers

This upstream API requires several specific custom headers to function, likely for internal tracking or firewall rules.

| Header | Value | Notes |
| :--- | :--- | :--- |
| `Authorization` | `Bearer <YOUR_TOKEN>` | From the Auth endpoint. |
| `email` | `<YOUR_EMAIL>` | Must match the auth email. |
| `product` | `API` | Hardcoded requirement. |
| `version` | `1.0.0` | Hardcoded requirement. |
| `recommend` | `test-recommendation-API-call` | **Crucial:** Appears to be a required magic string. |

### Request Body

The payload is similar to the OpenAI standard but strictly **non-streaming**.

```json
{
  "model": "gpt-4", 
  "messages": [
    {
      "role": "user",
      "content": "Hello world"
    }
  ],
  "stream": false,  // MUST be false. Upstream does not support SSE.
  "temperature": 0.7,
  "max_tokens": 1000
}
```

### Response Format

The API returns a JSON object. It appears to behave in two possible ways regarding the content:

**Scenario A: Standard Structure**

```json
{
  "id": "chatcmpl-123",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help?" // May contain XML tags
      },
      "finish_reason": "stop"
    }
  ],
  "usage": { ... }
}
```

**Scenario B: Flattened Response (Legacy/Custom)**
If the `choices` array is missing, the API returns a direct text response which the proxy wraps.

```json
{
  "response": "Hello! <attempt_completion>result</attempt_completion>"
}
```

