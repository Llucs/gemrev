# GemRev

Unofficial Python client for Google Gemini's web interface + OpenAI-compatible API server.

## Features

- **Guest Mode** — Works without any Google account or cookies.
- **OpenAI-Compatible API** — Drop-in replacement for OpenAI's `/v1/chat/completions`.
- **Local Server** — Run `python app.py` for a full API server.
- **CLI Mode** — Use `python -m gemrev` or `gemrev` directly.
- **Universal Hosting** — Deploy on Vercel, Railway, Render, or any ASGI platform.
- **Streaming** — SSE streaming compatible with OpenAI format.
- **Multi-turn Chat** — Full conversation history support.
- **Image Generation** — Generate and edit images with natural language.
- **Video Generation** — Generate short videos from text prompts.
- **Audio & Music Generation** — Generate audio and music content.
- **Deep Research** — Full deep research workflow.
- **Extended Thinking** — Deeper reasoning mode on supported models.
- **Tool/Function Calling** — Define and invoke tools in conversations.

## Installation

```bash
pip install httpx
```

For server mode:
```bash
pip install fastapi uvicorn pydantic
```

For everything:
```bash
pip install fastapi uvicorn pydantic tiktoken
```

## Usage

### CLI (direct, no server)

```bash
# Guest mode
python -m gemrev "Hello!" --stream

# Authenticated
python -m gemrev "Explain quantum computing" --cookie "YOUR__Secure-1PSID"

# List models
python -m gemrev --list-models

# OpenAI-compatible JSON output
python -m gemrev "Hello" --json
```

Or after `pip install -e .`:
```bash
gemrev "Hello" --stream --guest
```

### Local Server

```bash
python app.py
# Server at http://localhost:8000

# Custom port
python app.py --port 8080
```

### API Endpoints

**POST /v1/chat/completions** — OpenAI-compatible chat completions.

```json
{
  "model": "gemini-3-flash",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false,
  "cookie": "__Secure-1PSID=abc123"
}
```

Response:
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gemini-3-flash",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello! How can I help you?"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}
}
```

**GET /v1/models** — List available models.

**GET /health** — Health check.

### Streaming (SSE)

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Count to 5."}],"stream":true}'
```

### Python Library

```python
import asyncio
from gemrev import Gemini, Model

async def main():
    client = Gemini(secure_1psid="YOUR__Secure-1PSID")
    chat = client.new_chat(model=Model.BASIC_FLASH)
    response = await chat.generate_content(prompt="Hello!")
    print(response.text)

asyncio.run(main())
```

## Hosting

### Vercel

Deploy the `api/` directory as serverless functions:

```bash
vercel deploy
```

Set environment variables:
- `GEMINI_COOKIE` — Your `__Secure-1PSID` cookie

### Railway / Render

```bash
# Start command
uvicorn gemrev.api.server:app --host 0.0.0.0 --port $PORT
```

### Docker

```dockerfile
FROM python:3.12
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn pydantic httpx
CMD ["uvicorn", "gemrev.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Models

| Constant | Name | Tier |
|----------|------|------|
| `Model.BASIC_FLASH` | gemini-3-flash | Free |
| `Model.BASIC_PRO` | gemini-3-pro | Free |
| `Model.PLUS_FLASH` | gemini-3-flash-plus | Plus |
| `Model.ADVANCED_PRO` | gemini-3-pro-advanced | Advanced |

## Legal Disclaimer

This project is an unofficial, open-source client for research and educational purposes only.

- It is **not affiliated with, endorsed by, or sponsored by Google**.
- It interacts with Google Gemini through the same public web interface available to any user.
- Users are responsible for complying with Google's Terms of Service.
- The authors assume no liability for any misuse of this software.

## License

MIT License — see [LICENSE](LICENSE).

## References

- [Gemini-Reverse](https://github.com/rynn-k/Gemini-Reverse) — original Node.js implementation
- [Gemini-API](https://github.com/HanaokaYuzu/Gemini-API) — Python reverse engineering project
