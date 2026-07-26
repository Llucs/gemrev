from time import time
from uuid import uuid4


def _count_tokens(s):
    try:
        import tiktoken
        enc = tiktoken.get_encoding('o200k_base')
        return len(enc.encode(s)) if s else 0
    except ImportError:
        return max(1, len(s) // 4)


def _system_fingerprint():
    return f"fp_{uuid4().hex[:16]}"


def build_chat_response(
    result,
    prompt_text,
    model,
    system_fingerprint=None,
):
    now = int(time())
    msg_id = f'chatcmpl-{uuid4().hex[:16]}'

    if hasattr(result, 'text'):
        text = result.text
    elif isinstance(result, dict):
        text = result.get('text', '')
    else:
        text = str(result)

    if hasattr(result, 'thoughts'):
        reasoning = result.thoughts
    elif isinstance(result, dict):
        reasoning = result.get('reasoning') or result.get('thoughts')
    else:
        reasoning = None

    finish_reason = 'stop'

    choice_msg = {'role': 'assistant', 'content': text}
    if reasoning:
        choice_msg['reasoning_content'] = reasoning

    choices = [{
        'index': 0,
        'message': choice_msg,
        'finish_reason': finish_reason,
    }]

    pt = _count_tokens(prompt_text)
    ct = _count_tokens(text)
    rt = _count_tokens(reasoning) if reasoning else 0

    usage = {'prompt_tokens': pt, 'completion_tokens': ct, 'total_tokens': pt + ct}
    if rt:
        usage['completion_tokens_details'] = {'reasoning_tokens': rt}

    body = {
        'id': msg_id,
        'object': 'chat.completion',
        'created': now,
        'model': model or 'gemini',
        'choices': choices,
        'usage': usage,
        'system_fingerprint': system_fingerprint or _system_fingerprint(),
    }

    return body


def build_stream_chunk(msg_id, created, model, delta, finish_reason=None):
    return {
        'id': msg_id,
        'object': 'chat.completion.chunk',
        'created': created,
        'model': model,
        'choices': [{
            'index': 0,
            'delta': delta,
            'finish_reason': finish_reason,
        }],
    }
