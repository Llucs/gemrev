import json as _json
import logging
import os
from time import time
from uuid import uuid4

from gemrev import Gemini, Model

logger = logging.getLogger('gemrev')

from gemrev.api.response import build_chat_response, build_stream_chunk

try:
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError:
    FastAPI = None


if FastAPI is not None:

    class Message(BaseModel):
        role: str
        content: str | None = None

    class ChatRequest(BaseModel):
        messages: list[Message]
        model: str = 'auto'
        stream: bool = False
        cookie: str | None = None
        proxy: str | None = None
        temperature: float | None = None
        top_p: float | None = None
        max_tokens: int | None = None
        extended: bool = False

    app = FastAPI(title='gemrev-api', version='2.0.0')

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    def _get_client(req):
        cookie = req.cookie or os.environ.get('GEMINI_COOKIE', '')
        proxy = req.proxy or os.environ.get('GEMINI_PROXY', '')
        return Gemini(
            secure_1psid=cookie if cookie else None,
            proxy=proxy if proxy else None,
        )

    def _build_prompt(messages):
        parts = []
        for m in messages:
            role = m.role
            content = m.content or ''
            if role == 'system':
                parts.append(f'system: {content}')
            elif role == 'user':
                parts.append(f'user: {content}')
            elif role == 'assistant':
                parts.append(f'assistant: {content}')
            elif role == 'tool':
                parts.append(f'tool: {content}')
        return '\n'.join(parts)

    def _resolve_model(model_name):
        if model_name and model_name != 'auto':
            try:
                return Model.from_name(model_name)
            except ValueError:
                pass
        return Model.UNSPECIFIED

    @app.post('/v1/chat/completions')
    async def chat_completions(req: ChatRequest):
        if not req.messages:
            return JSONResponse(
                content={'error': {'message': 'messages is required', 'type': 'invalid_request_error'}},
                status_code=400,
            )

        last_msg = next((m for m in reversed(req.messages) if m.role == 'user'), None)
        if not last_msg:
            return JSONResponse(
                content={'error': {'message': 'No user message found', 'type': 'invalid_request_error'}},
                status_code=400,
            )

        prompt_text = _build_prompt(req.messages)
        model = _resolve_model(req.model)

        client = _get_client(req)

        if req.stream:
            now = int(time())
            msg_id = f'chatcmpl-{uuid4().hex[:16]}'

            async def stream():
                chat = client.new_chat(model=model)
                yield f'data: {_json.dumps(build_stream_chunk(msg_id, now, req.model, {"role": "assistant", "content": ""}))}\n\n'
                try:
                    async for chunk in chat.generate_content_stream(
                        prompt=last_msg.content or '',
                        messages=req.messages if len(req.messages) > 1 else None,
                    ):
                        if chunk.text_delta:
                            chunk_data = build_stream_chunk(msg_id, now, req.model, {'content': chunk.text_delta})
                            yield f'data: {_json.dumps(chunk_data)}\n\n'
                except Exception as e:
                    logger.exception('stream failed')
                chunk_data = build_stream_chunk(msg_id, now, req.model, {}, 'stop')
                yield f'data: {_json.dumps(chunk_data)}\n\n'
                yield 'data: [DONE]\n\n'

            return StreamingResponse(stream(), media_type='text/event-stream')

        chat = client.new_chat(model=model)
        result = await chat.generate_content(
            prompt=last_msg.content or '',
            messages=req.messages if len(req.messages) > 1 else None,
        )

        body = build_chat_response(result, prompt_text, req.model)
        return body

    @app.get('/v1/models')
    async def list_models():
        try:
            client = Gemini()
            models = await client.models()
        except Exception:
            models = []

        def _build(m):
            return {
                'id': m.model_name,
                'name': m.display_name,
                'object': 'model',
                'owned_by': 'google',
            }

        return {'object': 'list', 'data': [_build(m) for m in models]}

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'version': '2.0.0'}
else:
    app = None
