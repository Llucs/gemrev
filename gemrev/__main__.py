import argparse
import asyncio
import json
import sys
from time import time
from uuid import uuid4

from gemrev import Gemini, Model
from gemrev.api.response import build_chat_response, build_stream_chunk


def main():
    parser = argparse.ArgumentParser(description='gemrev — Google Gemini CLI')
    parser.add_argument('message', nargs='*', help='Message to send')
    parser.add_argument('--cookie', help='__Secure-1PSID cookie')
    parser.add_argument('--proxy', help='Proxy (http://user:pass@host:port)')
    parser.add_argument('--model', default='auto', help='Model name (default: auto)')
    parser.add_argument('--stream', action='store_true', help='Stream response (OpenAI SSE format)')
    parser.add_argument('--text', action='store_true', help='Output plain text instead of JSON')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress logs')
    parser.add_argument('--list-models', action='store_true', help='List available models')
    parser.add_argument('--guest', action='store_true', help='Use guest mode (no cookie)')

    args = parser.parse_args()

    if args.list_models:
        async def _list():
            client = Gemini()
            models = await client.models()
            data = [
                {
                    'id': m.model_name,
                    'name': m.display_name,
                    'object': 'model',
                    'owned_by': 'google',
                }
                for m in models
            ]
            print(json.dumps({'object': 'list', 'data': data}, indent=2))
        asyncio.run(_list())
        return

    if args.message:
        text = ' '.join(args.message)
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        parser.print_help()
        return

    cookie = args.cookie or ''
    if args.guest:
        cookie = ''

    if args.stream:
        async def _stream():
            client = Gemini(
                secure_1psid=cookie if cookie else None,
                proxy=args.proxy,
            )
            model = Model.UNSPECIFIED if args.model == 'auto' else Model.from_name(args.model)
            chat = client.new_chat(model=model)

            now = int(time())
            msg_id = f'chatcmpl-{uuid4().hex[:16]}'
            resolved_model = args.model
            first = True

            async for chunk in chat.generate_content_stream(prompt=text):
                if first:
                    resolved_model = chunk.model or args.model
                    sys.stdout.write(
                        f'data: {json.dumps(build_stream_chunk(msg_id, now, resolved_model, {"role": "assistant"}))}\n\n'
                    )
                    sys.stdout.flush()
                    first = False
                if chunk.text_delta:
                    c = build_stream_chunk(msg_id, now, resolved_model, {'content': chunk.text_delta})
                    sys.stdout.write(f'data: {json.dumps(c)}\n\n')
                    sys.stdout.flush()

            last = build_stream_chunk(msg_id, now, resolved_model, {}, 'stop')
            sys.stdout.write(f'data: {json.dumps(last)}\n\n')
            sys.stdout.write('data: [DONE]\n\n')
            sys.stdout.flush()

        asyncio.run(_stream())
        return

    async def _run():
        client = Gemini(
            secure_1psid=cookie if cookie else None,
            proxy=args.proxy,
        )
        model = Model.UNSPECIFIED if args.model == 'auto' else Model.from_name(args.model)
        chat = client.new_chat(model=model)
        result = await chat.generate_content(prompt=text)

        prompt_text = f'user: {text}'
        resp = build_chat_response(result, prompt_text, args.model)

        if args.text:
            if result.thoughts:
                print(f'[thinking]\n{result.thoughts}\n[/thinking]')
            print(result.text)
        else:
            print(json.dumps(resp, indent=2, ensure_ascii=False))

    asyncio.run(_run())


if __name__ == '__main__':
    main()
