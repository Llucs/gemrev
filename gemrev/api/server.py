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

    def _resolve_model(model_name):
        if model_name and model_name != 'auto':
            try:
                return Model.from_name(model_name)
            except ValueError:
                pass
        return Model.UNSPECIFIED

    def _model_name(model):
        if isinstance(model, dict) and model.get('model_name'):
            return model['model_name']
        return 'auto'

    @app.post('/v1/chat/completions')
    async def chat_completions(req: ChatRequest):
        if not req.messages:
            return JSONResponse(
                status_code=400,
                content={'error': {'message': 'messages is required', 'type': 'invalid_request_error'}},
            )

        last_user = None
        for m in reversed(req.messages):
            if m.role == 'user':
                last_user = m
                break

        if not last_user:
            return JSONResponse(
                status_code=400,
                content={'error': {'message': 'No user message found', 'type': 'invalid_request_error'}},
            )

        model = _resolve_model(req.model)
        client = _get_client(req)

        if req.stream:
            now = int(time())
            msg_id = f'chatcmpl-{uuid4().hex[:16]}'
            resolved_model_holder = [req.model]

            async def stream():
                chat = client.new_chat(model=model)
                first = True
                try:
                    async for chunk in chat.generate_content_stream(
                        prompt=last_user.content or '',
                        messages=req.messages if len(req.messages) > 1 else None,
                    ):
                        if first:
                            resolved_model_holder[0] = chunk.model or req.model
                            first_chunk = build_stream_chunk(
                                msg_id, now, resolved_model_holder[0],
                                {'role': 'assistant'},
                            )
                            yield f'data: {_json.dumps(first_chunk)}\n\n'
                            first = False
                        if chunk.text_delta:
                            c = build_stream_chunk(
                                msg_id, now, resolved_model_holder[0],
                                {'content': chunk.text_delta},
                            )
                            yield f'data: {_json.dumps(c)}\n\n'
                except Exception as e:
                    logger.exception('stream failed')
                last = build_stream_chunk(
                    msg_id, now, resolved_model_holder[0],
                    {}, 'stop',
                )
                yield f'data: {_json.dumps(last)}\n\n'
                yield 'data: [DONE]\n\n'

            return StreamingResponse(stream(), media_type='text/event-stream')

        chat = client.new_chat(model=model)
        result = await chat.generate_content(
            prompt=last_user.content or '',
            messages=req.messages if len(req.messages) > 1 else None,
        )
        prompt_text = '\n'.join(f'{m.role}: {m.content}' for m in req.messages if m.content)
        return build_chat_response(result, prompt_text, req.model)

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
