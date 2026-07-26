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


def _extract_text(result):
    if hasattr(result, 'text'):
        return result.text
    if isinstance(result, dict):
        return result.get('text', '')
    return str(result)


def _extract_model(result, fallback):
    if hasattr(result, 'model') and result.model:
        return result.model
    if isinstance(result, dict) and result.get('model'):
        return result['model']
    return fallback


def build_chat_response(result, prompt_text, model, system_fingerprint=None):
    now = int(time())
    msg_id = f'chatcmpl-{uuid4().hex[:16]}'
    text = _extract_text(result)
    actual_model = _extract_model(result, model)

    choice_msg = {'role': 'assistant', 'content': text}

    choices = [{
        'index': 0,
        'message': choice_msg,
        'finish_reason': 'stop',
    }]

    pt = _count_tokens(prompt_text)
    ct = _count_tokens(text)

    return {
        'id': msg_id,
        'object': 'chat.completion',
        'created': now,
        'model': actual_model,
        'choices': choices,
        'usage': {
            'prompt_tokens': pt,
            'completion_tokens': ct,
            'total_tokens': pt + ct,
        },
        'system_fingerprint': system_fingerprint or _system_fingerprint(),
    }


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
