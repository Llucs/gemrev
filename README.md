# GemRev

An unofficial Python client for Google Gemini's web interface.

## Features

- **Guest Mode** — Works without any Google account or cookies. Supports multi-turn chat sessions.
- **Image Generation** — Generate and edit images with natural language.
- **Video Generation** — Generate short videos from text prompts.
- **Audio & Music Generation** — Generate audio and music content.
- **Deep Research** — Full deep research workflow with plan creation, status polling, and result retrieval.
- **Extended Thinking** — Enables deeper reasoning mode on supported models.
- **System Prompt via Gems** — Customize the model's behavior with Gemini Gems.
- **Extension Support** — Generate content with Gemini extensions (YouTube, Gmail, etc.).
- **Classified Outputs** — Categorizes text, thoughts, images, videos, and audio in the response.
- **Streaming Mode** — Stream generation with incremental stateful frame parsing.
- **Tool/Function Calling** — Define and invoke tools in conversations.
- **Mode Category Selection** — Simplified model selection via mode category (Fast, Thinking, Pro, Auto, etc.).

## Installation

```bash
pip install httpx
```

## Quick Start

### Guest Mode (no account required)

```python
import asyncio
from gemrev import Gemini

async def main():
    client = Gemini()
    chat = client.new_chat()
    response = await chat.generate_content(prompt="Hello!")
    print(response.text)

asyncio.run(main())
```

### Authenticated Mode

```python
from gemrev import Gemini, Model

client = Gemini(secure_1psid="YOUR__Secure-1PSID")
chat = client.new_chat(model=Model.BASIC_FLASH)
response = await chat.generate_content(prompt="Explain Python async/await.")
print(response.text)
```

### Streaming

```python
chat = client.new_chat()
async for chunk in chat.generate_content_stream(prompt="Tell me a story."):
    if chunk.text_delta:
        print(chunk.text_delta, end="")
```

### Tool/Function Calling

```python
from gemrev import ToolDefinition

chat = client.new_chat()
response = await chat.generate_content(
    prompt="What's the weather in Tokyo?",
    tools=[ToolDefinition(name="get_weather", description="Get weather for a city")],
)
if response.candidates[0]._tool_calls:
    print("Tool calls:", response.candidates[0]._tool_calls)
```

## API Overview

| Method | Description |
|--------|-------------|
| `Gemini()` | Create a client (guest if no cookie, authenticated with `secure_1psid`) |
| `client.new_chat()` | Create a chat session |
| `chat.generate_content()` | Send a prompt and get a response |
| `chat.generate_content_stream()` | Stream a response |
| `client.ask()` | One-shot prompt without creating a chat |
| `client.models()` | List available models |
| `client.chats()` | List recent conversations |
| `client.read_chat(cid)` | Read conversation history |
| `client.gems()` | List available Gems |
| `client.research()` | Start a deep research query |

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
