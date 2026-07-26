import re
from .parser import get_nested_value

_RESEARCH_ID_RE = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I)
_CHAT_ID_RE = re.compile(r'\bc_[A-Za-z0-9_]+\b')
_URL_RE = re.compile(r'^https?://')


def iter_nested(data):
    yield data
    if isinstance(data, (list, tuple)):
        for item in data:
            yield from iter_nested(item)
    elif isinstance(data, dict):
        for item in data.values():
            yield from iter_nested(item)


def find_first_match(data, pattern):
    for item in iter_nested(data):
        if isinstance(item, str):
            m = pattern.search(item)
            if m:
                return m.group()
    return None


def find_first_string(data, exclude=None):
    exclude = exclude or set()
    for item in iter_nested(data):
        if isinstance(item, str) and item and item not in exclude:
            return item
    return None


def extract_research_id(data):
    return find_first_match(data, _RESEARCH_ID_RE)


def extract_chat_id(data):
    return find_first_match(data, _CHAT_ID_RE)


def collect_research_notes(data, exclude=None):
    exclude = exclude or set()
    notes = []
    seen = set()
    for item in iter_nested(data):
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in exclude or text in seen or _URL_RE.match(text) or len(text) < 12:
            continue
        seen.add(text)
        notes.append(text)
        if len(notes) >= 12:
            break
    return notes


def find_first_dict_key(data, key):
    for item in iter_nested(data):
        if isinstance(item, dict) and not isinstance(item, (list, tuple)) and key in item:
            return item
    return None


def extract_deep_research_plan(candidate_data, fallback_text=''):
    meta_dict = None
    payload = None

    for key in ('56', '57'):
        meta_dict = find_first_dict_key(candidate_data, key)
        if meta_dict and isinstance(meta_dict.get(key), (list, tuple)):
            payload = meta_dict[key]
            break

    if not meta_dict or not payload:
        return None

    research_id = extract_research_id(candidate_data)
    title = get_nested_value(payload, [0])
    steps_payload = get_nested_value(payload, [1], [])
    steps = []
    if isinstance(steps_payload, (list, tuple)):
        for step in steps_payload:
            if isinstance(step, (list, tuple)):
                label = step[1] if len(step) > 1 and isinstance(step[1], str) else None
                body = step[2] if len(step) > 2 and isinstance(step[2], str) else None
                if label and body:
                    steps.append(f'{label}: {body}')
                elif body:
                    steps.append(body)
                elif label:
                    steps.append(label)

    modify_payload = get_nested_value(payload, [5])
    modify_prompt = None
    if isinstance(modify_payload, (list, tuple)):
        modify_prompt = find_first_string(modify_payload)

    query_val = get_nested_value(payload, [1, 0, 2])
    query = query_val if isinstance(query_val, str) else None
    eta_val = get_nested_value(payload, [2])
    eta_text = eta_val if isinstance(eta_val, str) else None
    confirm_val = get_nested_value(payload, [3, 0])
    confirm_prompt = confirm_val if isinstance(confirm_val, str) else None
    confirm_url_val = get_nested_value(payload, [4, 0])
    confirmation_url = confirm_url_val if isinstance(confirm_url_val, str) else None
    raw_state_70 = meta_dict.get('70')
    raw_state = raw_state_70 if isinstance(raw_state_70, (int, float)) else None

    if not title and not query and not steps and not eta_text and not confirm_prompt and not confirmation_url and not modify_prompt:
        return None

    return {
        'research_id': research_id,
        'title': title if isinstance(title, str) else None,
        'query': query,
        'steps': steps,
        'eta_text': eta_text,
        'confirm_prompt': confirm_prompt,
        'confirmation_url': confirmation_url,
        'modify_prompt': modify_prompt,
        'raw_state': raw_state,
        'response_text': fallback_text or None,
    }


def extract_deep_research_status_payload(payload):
    data = payload[0] if isinstance(payload, (list, tuple)) and len(payload) > 0 and isinstance(payload[0], (list, tuple)) else payload
    research_id = extract_research_id(data)
    if not research_id:
        return None

    title = get_nested_value(data, [1, 4, 0])
    query = get_nested_value(data, [1, 4, 1])
    cid = get_nested_value(data, [1, 3, 0]) or extract_chat_id(data)

    raw_state = None
    meta_dict = find_first_dict_key(data, '70')
    if meta_dict and isinstance(meta_dict.get('70'), (int, float)):
        raw_state = meta_dict['70']

    marker_strings = []
    for item in iter_nested(data):
        if isinstance(item, str) and item:
            marker_strings.append(item)

    done = any('immersive_entry_chip' in s for s in marker_strings)
    awaiting_confirmation = any('deep_research_confirmation_content' in s for s in marker_strings)
    state = 'completed' if done else ('awaiting_confirmation' if awaiting_confirmation else 'running')

    exclude = {s for s in [title, query, research_id, cid] if isinstance(s, str)}
    notes = collect_research_notes(data, exclude)

    return {
        'research_id': research_id,
        'state': state,
        'title': title if isinstance(title, str) else None,
        'query': query if isinstance(query, str) else None,
        'cid': cid if isinstance(cid, str) else None,
        'notes': notes,
        'done': done,
        'raw_state': raw_state,
        'raw': payload,
    }
