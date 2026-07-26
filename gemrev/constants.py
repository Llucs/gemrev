import re
import json

STREAMING_FLAG_INDEX = 7
GEM_FLAG_INDEX = 19
TEMPORARY_CHAT_FLAG_INDEX = 45

CARD_CONTENT_RE = re.compile(r'^http://googleusercontent\.com/card_content/\d+')
ARTIFACTS_RE = re.compile(r'http://googleusercontent\.com/\w+/\d+\n*')
DEFAULT_METADATA = ['', '', '', None, None, None, None, None, None, '']
MODEL_HEADER_KEY = 'x-goog-ext-525001261-jspb'


def build_model_header(model_id, capacity_tail, model_number=1):
    tail = str(capacity_tail)
    return {
        MODEL_HEADER_KEY: json.dumps([
            1, None, None, None, model_id, None, None, 0,
            [4, 5, 6, 8], None, None, capacity_tail, None, None, model_number
        ]),
        'x-goog-ext-73010989-jspb': '[0]',
        'x-goog-ext-73010990-jspb': '[0,0,0]',
    }


class Endpoint:
    GOOGLE = 'https://www.google.com'
    INIT = 'https://gemini.google.com/app'
    GENERATE = 'https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate'
    UPLOAD = 'https://content-push.googleapis.com/upload'
    BATCH_EXEC = 'https://gemini.google.com/_/BardChatUi/data/batchexecute'


class GRPC:
    LIST_CHATS = 'MaZiqc'
    READ_CHAT = 'hNvQHb'
    DELETE_CHAT_1 = 'GzXR5e'
    DELETE_CHAT_2 = 'qWymEb'
    LIST_GEMS = 'CNgdBe'
    CREATE_GEM = 'oMH3Zd'
    UPDATE_GEM = 'kHv0Vd'
    DELETE_GEM = 'UXcSJb'
    DEEP_RESEARCH_STATUS = 'kwDCne'
    GET_FULL_SIZE_IMAGE = 'c8o8Fe'


class Headers:
    REFERER = {
        'Origin': 'https://gemini.google.com',
        'Referer': 'https://gemini.google.com/',
    }
    SAME_DOMAIN = {
        'X-Same-Domain': '1',
    }
    GEMINI = {
        'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
        'Origin': 'https://gemini.google.com',
        'Referer': 'https://gemini.google.com/',
    }
    UPLOAD = {'X-Tenant-Id': 'bard-storage'}
    BATCH_EXEC = {
        'x-goog-ext-525001261-jspb': json.dumps([1, None, None, None, None, None, None, None, [4, 5, 6, 8], None, None, None, None, None, None, None]),
        'x-goog-ext-73010989-jspb': '[0]',
    }


_MODEL_KEYS = [
    'UNSPECIFIED', 'BASIC_PRO', 'BASIC_FLASH', 'BASIC_LITE', 'BASIC_THINKING',
    'PLUS_PRO', 'PLUS_FLASH', 'PLUS_LITE',
    'ADVANCED_PRO', 'ADVANCED_FLASH', 'ADVANCED_LITE',
]


class ModeCategory:
    FAST = 1
    THINKING = 2
    PRO = 3
    AUTO = 4
    FAST_DYNAMIC_THINKING = 5
    FLASH_LITE = 6


class Model:
    UNSPECIFIED = {'model_name': 'unspecified', 'model_header': {}, 'advanced_only': False}
    BASIC_PRO = {
        'model_name': 'gemini-3-pro',
        'model_header': build_model_header('9d8ca3786ebdfbea', 1, 3),
        'advanced_only': False,
    }
    BASIC_FLASH = {
        'model_name': 'gemini-3-flash',
        'model_header': build_model_header('fbb127bbb056c959', 1, 1),
        'advanced_only': False,
    }
    BASIC_LITE = {
        'model_name': 'gemini-3-lite',
        'model_header': build_model_header('cf41b0e0dd7d53e5', 1, 6),
        'advanced_only': False,
    }
    BASIC_THINKING = {
        'model_name': 'gemini-3-thinking',
        'model_header': build_model_header('5bf011840784117a', 1, 15),
        'advanced_only': False,
    }
    PLUS_PRO = {
        'model_name': 'gemini-3-pro-plus',
        'model_header': build_model_header('e6fa609c3fa255c0', 4, 3),
        'advanced_only': True,
    }
    PLUS_FLASH = {
        'model_name': 'gemini-3-flash-plus',
        'model_header': build_model_header('56fdd199312815e2', 4, 1),
        'advanced_only': True,
    }
    PLUS_LITE = {
        'model_name': 'gemini-3-lite-plus',
        'model_header': build_model_header('8c46e95b1a07cecc', 4, 6),
        'advanced_only': True,
    }
    ADVANCED_PRO = {
        'model_name': 'gemini-3-pro-advanced',
        'model_header': build_model_header('e6fa609c3fa255c0', 2, 3),
        'advanced_only': True,
    }
    ADVANCED_FLASH = {
        'model_name': 'gemini-3-flash-advanced',
        'model_header': build_model_header('56fdd199312815e2', 2, 1),
        'advanced_only': True,
    }
    ADVANCED_LITE = {
        'model_name': 'gemini-3-lite-advanced',
        'model_header': build_model_header('8c46e95b1a07cecc', 2, 6),
        'advanced_only': True,
    }

    @classmethod
    def from_name(cls, name):
        lower = name.lower()
        for k in _MODEL_KEYS:
            m = getattr(cls, k)
            if isinstance(m, dict) and m.get('model_name') == lower:
                return m
        names = ', '.join(getattr(cls, k)['model_name'] for k in _MODEL_KEYS if isinstance(getattr(cls, k), dict))
        raise ValueError(f'Unknown model name: {name}. Available: {names}')

    @classmethod
    def from_dict(cls, d):
        if not d.get('model_name') or not isinstance(d.get('model_header'), dict):
            raise ValueError('model_name and model_header (dict) required')
        return {'model_name': d['model_name'], 'model_header': d['model_header'], 'advanced_only': False}

    @classmethod
    def model_id(cls, model):
        header_value = model and model.get('model_header', {}).get(MODEL_HEADER_KEY)
        if not header_value:
            return ''
        try:
            parsed = json.loads(header_value) if isinstance(header_value, str) else header_value
            return parsed[4] if parsed and len(parsed) > 4 else ''
        except (json.JSONDecodeError, IndexError, TypeError):
            return ''


class ErrorCode:
    TEMPORARY_ERROR_1013 = 1013
    USAGE_LIMIT_EXCEEDED = 1037
    MODEL_INCONSISTENT = 1050
    MODEL_HEADER_INVALID = 1052
    IP_TEMPORARILY_BLOCKED = 1060
    FEATURE_NOT_AVAILABLE = 1097
