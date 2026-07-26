import json as _json
import logging
import os
from time import time
from uuid import uuid4

from gemrev import Gemini, Model, ToolDefinition
from gemrev.api.response import build_chat_response, build_stream_chunk

logger = logging.getLogger('gemrev')

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

    class FunctionDef(BaseModel):
        name: str
        description: str = ''
        parameters: dict = {}

    class ToolDef(BaseModel):
        type: str = 'function'
        function: FunctionDef

    class ChatRequest(BaseModel):
        messages: list[Message]
        model: str = 'auto'
        stream: bool = False
        cookie: str | None = None
        proxy: str | None = None
        tools: list[ToolDef] | None = None
        tool_choice: str | None = None

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

    def _to_tool_definitions(tools):
        if not tools:
            return None
        result = []
        for t in tools:
            if t.type == 'function':
                result.append(ToolDefinition(
                    name=t.function.name,
                    description=t.function.description,
                    parameters=t.function.parameters,
                ))
        return result if result else None

    def _messages_to_dicts(messages, tools):
        result = []
        if tools:
            result.append({
                'role': 'system',
                'content': (
                    'You have access to the following tools. '
                    'When you need to use a tool, respond EXCLUSIVELY with:\n'
                    '[TOOL_CALL]tool_name|{"arg1":"value1"}[/TOOL_CALL]\n'
                    'Do NOT include any other text, explanation, or natural language. '
                    'Your entire response must be ONLY the tool call — nothing before, nothing after.'
                ),
            })
        for m in messages:
            d = {'role': m.role}
            if m.content is not None:
                d['content'] = m.content
            result.append(d)
        return result

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
        tools = _to_tool_definitions(req.tools)

        msg_dicts = _messages_to_dicts(req.messages, tools)

        if req.stream:
            now = int(time())
            msg_id = f'chatcmpl-{uuid4().hex[:16]}'
            resolved_model_holder = [req.model]

            async def stream():
                chat = client.new_chat(model=model)
                yield f'data: {_json.dumps(build_stream_chunk(msg_id, now, req.model, {"role": "assistant"}))}\n\n'
                buf = []
                tool_calls_result = None
                stream_ok = True
                try:
                    async for chunk in chat.generate_content_stream(
                        prompt=last_user.content or '',
                        messages=msg_dicts,
                        tools=tools,
                    ):
                        if not resolved_model_holder[0] or resolved_model_holder[0] == req.model:
                            resolved_model_holder[0] = chunk.model or req.model

                        if hasattr(chunk, 'candidates') and chunk.candidates:
                            tc = getattr(chunk.candidates[0], '_tool_calls', None)
                            if tc:
                                tool_calls_result = tc
                                break

                        if chunk.text_delta:
                            buf.append(chunk.text_delta)
                except Exception:
                    logger.exception('stream failed')
                    stream_ok = False
                    yield f'data: {_json.dumps({"error": {"message": "Stream failed", "type": "server_error"}})}\n\n'

                if stream_ok:
                    if tool_calls_result:
                        yield f'data: {_json.dumps(build_stream_chunk(msg_id, now, resolved_model_holder[0], {"content": None, "tool_calls": tool_calls_result}, "tool_calls"))}\n\n'
                    else:
                        for delta in buf:
                            yield f'data: {_json.dumps(build_stream_chunk(msg_id, now, resolved_model_holder[0], {"content": delta}))}\n\n'
                        yield f'data: {_json.dumps(build_stream_chunk(msg_id, now, resolved_model_holder[0], {}, "stop"))}\n\n'
                yield 'data: [DONE]\n\n'

            return StreamingResponse(stream(), media_type='text/event-stream')

        chat = client.new_chat(model=model)
        result = await chat.generate_content(
            prompt=last_user.content or '',
            messages=msg_dicts,
            tools=tools,
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
