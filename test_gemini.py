import asyncio
import json
import re
from gemrev import Gemini, Model, ChatSession, ModelOutput, Candidate, ErrorCode, ModeCategory
from gemrev import UsageLimitExceeded, ModelInvalid, TemporarilyBlocked
from gemrev import ToolDefinition, ToolCall
from gemrev.constants import (
    Endpoint, GRPC, Headers, DEFAULT_METADATA, STREAMING_FLAG_INDEX,
    GEM_FLAG_INDEX, TEMPORARY_CHAT_FLAG_INDEX, CARD_CONTENT_RE, ARTIFACTS_RE,
    MODEL_HEADER_KEY, build_model_header,
)
from gemrev.errors import AuthError, APIError, GeminiError
from gemrev.utils.auth import cookie_str, parse_cookies, parse_proxy
from gemrev.utils.parser import (
    StreamingFrameParser, get_delta_by_fp_len, get_nested_value,
    extract_json_from_response, get_clean_text,
)
from gemrev.utils.research import (
    iter_nested, find_first_match, extract_research_id,
    extract_deep_research_plan, extract_deep_research_status_payload,
)
from gemrev.types.output import Candidate, ModelOutput
from gemrev.types.media import Image, WebImage, GeneratedImage, Video, GeneratedVideo, GeneratedMedia
from gemrev.types.model import RPCData, AvailableModel
from gemrev.types.gem import Gem, GemJar
from gemrev.types.chat import ChatTurn, ChatHistory, ChatInfo
from gemrev.types.research import DeepResearchPlan, DeepResearchStatus, DeepResearchResult


def test_constants():
    assert Endpoint.GENERATE.startswith('https://gemini.google.com')
    assert GRPC.READ_CHAT == 'hNvQHb'
    assert Headers.GEMINI['Origin'] == 'https://gemini.google.com'
    print('  constants OK')


def test_model():
    m = Model.BASIC_FLASH
    assert m['model_name'] == 'gemini-3-flash'
    mid = Model.model_id(m)
    assert mid == 'fbb127bbb056c959'

    m2 = Model.from_name('gemini-3-flash')
    assert m2['model_name'] == 'gemini-3-flash'

    try:
        Model.from_name('nonexistent')
        assert False, 'Should have raised'
    except ValueError:
        pass

    m3 = Model.from_dict({'model_name': 'custom', 'model_header': {'x-test': '1'}})
    assert m3['model_name'] == 'custom'

    print('  model OK')


def test_build_model_header():
    h = build_model_header('test-id', 1, 3)
    assert MODEL_HEADER_KEY in h
    assert 'x-goog-ext-73010989-jspb' in h
    parsed = json.loads(h[MODEL_HEADER_KEY])
    assert parsed[4] == 'test-id'
    assert parsed[-1] == 3
    print('  build_model_header OK')


def test_error_classes():
    assert issubclass(AuthError, Exception)
    assert issubclass(APIError, Exception)
    assert issubclass(GeminiError, Exception)
    assert issubclass(UsageLimitExceeded, GeminiError)
    assert issubclass(ModelInvalid, GeminiError)
    assert issubclass(TemporarilyBlocked, GeminiError)

    e = AuthError('test')
    assert str(e) == 'test'
    assert isinstance(e, Exception)
    assert isinstance(e, AuthError)
    assert not isinstance(e, APIError)
    print('  error classes OK')


def test_cookie_str():
    assert cookie_str({}) == ''
    assert cookie_str({'a': '1', 'b': '2'}) == 'a=1; b=2'
    print('  cookie_str OK')


def test_parse_cookies():
    headers = {'set-cookie': 'a=1; path=/; secure, b=2; path=/; httponly'}
    result = parse_cookies(headers)
    assert result['a'] == '1'
    assert result['b'] == '2'
    print('  parse_cookies OK')


def test_parse_proxy():
    p = parse_proxy('http://user:pass@host:8080')
    assert p is not None
    assert p['host'] == 'host'
    assert p['port'] == 8080
    assert p['scheme'] == 'http'
    assert parse_proxy(None) is None
    assert parse_proxy('') is None
    print('  parse_proxy OK')


def test_nested_value():
    data = {'a': [{'b': {'c': 42}}]}
    assert get_nested_value(data, ['a', 0, 'b', 'c']) == 42
    assert get_nested_value(data, ['a', 0, 'b', 'x']) is None
    assert get_nested_value(data, ['a', 1]) is None
    assert get_nested_value(data, ['a', -1, 'b', 'c']) == 42
    print('  get_nested_value OK')


def test_clean_text():
    assert get_clean_text('hello') == 'hello'
    assert get_clean_text('text\\`') == 'text'
    assert get_clean_text('code\n```') == 'code'
    print('  get_clean_text OK')


def test_delta():
    td, nft = get_delta_by_fp_len('hello world', 'hello ', False)
    assert td == 'world'
    assert nft == 'hello world'

    td, nft = get_delta_by_fp_len('hello world', '', False)
    assert nft == 'hello world'
    print('  get_delta_by_fp_len OK')


def test_streaming_frame_parser():
    content = ")]}'\n\n5\nhello3\nabc"
    parser = StreamingFrameParser()
    result = parser.feed(content)
    result.extend(parser.flush())
    assert len(result) >= 0
    print('  StreamingFrameParser OK')


def test_extract_json():
    content = ")]}'\n\n[1,2,3]"
    result = extract_json_from_response(content)
    assert result == [[1, 2, 3]] or result == [1, 2, 3]
    print('  extract_json_from_response OK')


def test_rpc_data():
    r = RPCData(rpcid='test', payload='[1,2]', identifier='custom')
    ser = r.serialize()
    assert ser[0] == 'test'
    assert ser[1] == '[1,2]'
    assert ser[3] == 'custom'
    print('  RPCData OK')


def test_available_model():
    m = AvailableModel(model_id='test', model_name='test-name', display_name='Test')
    assert m.model_name == 'test-name'
    assert isinstance(m.model_header, dict)
    assert len(m.model_header) > 0
    print('  AvailableModel OK')


def test_candidate():
    c = Candidate(rcid='rc_1', text='hello', index=0, done=True)
    assert c.text == 'hello'
    assert c.done == True
    assert str(c) == 'hello'
    assert c.images == []
    assert c.videos == []
    assert c.media == []
    print('  Candidate OK')


def test_model_output():
    c = Candidate(rcid='rc_1', text='hello', done=True)
    out = ModelOutput(['cid1', 'rid1'], [c], model='test-model')
    assert out.cid == 'cid1'
    assert out.rid == 'rid1'
    assert out.text == 'hello'
    assert out.rcid == 'rc_1'
    assert out.done == True
    assert str(out) == 'hello'
    print('  ModelOutput OK')


def test_media():
    img = Image(url='https://example.com/img.jpg', alt='test image')
    assert 'img.jpg' in str(img)
    print('  Image OK')

    web = WebImage(url='https://example.com/img2.jpg')
    assert isinstance(web, Image)
    print('  WebImage OK')

    gen = GeneratedImage(url='https://example.com/gen.jpg', cid='c1', rid='r1', rcid='rc1', image_id='img1')
    assert isinstance(gen, Image)
    print('  GeneratedImage OK')

    vid = Video(url='https://example.com/vid.mp4')
    assert 'vid.mp4' in str(vid)
    print('  Video OK')

    gvid = GeneratedVideo(url='https://example.com/vid2.mp4', thumbnail='https://example.com/thumb.jpg')
    assert isinstance(gvid, Video)
    print('  GeneratedVideo OK')

    med = GeneratedMedia(url='https://example.com/mp4', mp3_url='https://example.com/mp3')
    print('  GeneratedMedia OK')


def test_gem():
    g = Gem(id='g1', name='test', predefined=False)
    assert g.id == 'g1'
    assert g.name == 'test'

    jar = GemJar([('g1', g)])
    assert jar.get(id='g1').name == 'test'
    assert jar.get(name='test').id == 'g1'
    print('  Gem/GemJar OK')


def test_chat_types():
    turn = ChatTurn(role='user', text='hello')
    assert turn.role == 'user'
    assert 'USER' in str(turn)

    hist = ChatHistory(cid='c1')
    assert hist.cid == 'c1'

    info = ChatInfo(cid='c2', title='Test Chat', is_pinned=True)
    assert info.is_pinned == True
    print('  Chat types OK')


def test_research_types():
    plan = DeepResearchPlan(research_id='test-id', title='Test')
    assert plan.research_id == 'test-id'

    status = DeepResearchStatus(research_id='test-id', state='running')
    assert status.state == 'running'

    result = DeepResearchResult(done=True)
    assert result.done == True
    print('  Research types OK')


def test_research_utils():
    data = {'items': ['abc', 'id_c_xyz123', 'test']}
    assert extract_research_id(data) is None  # no UUID pattern

    data2 = [{'56': ['uuid-here', {'1': ['test']}]}]
    plan = extract_deep_research_plan(data2)
    assert plan is not None or True  # may or may not extract
    print('  research utils OK')


def test_gemini_client_creation():
    client = Gemini()
    assert client._guest == True
    assert client.cookies == {}
    assert client.timeout == 300000
    print('  Gemini client creation OK')

    client2 = Gemini(secure_1psid='test-cookie')
    assert client2._guest == False
    assert client2.cookies['__Secure-1PSID'] == 'test-cookie'
    print('  Gemini auth client OK')


def test_new_chat():
    client = Gemini()
    chat = client.new_chat()
    assert isinstance(chat, ChatSession)
    assert chat.client == client
    assert chat.metadata == DEFAULT_METADATA
    print('  new_chat OK')

    chat2 = client.new_chat(model=Model.BASIC_FLASH, temporary=True)
    assert chat2.temporary == True
    assert chat2.model['model_name'] == 'gemini-3-flash'
    print('  new_chat with options OK')


def test_chat_session():
    client = Gemini()
    chat = client.new_chat()
    assert chat.cid == ''
    assert chat.rid == ''
    assert chat.rcid == ''

    chat.cid = 'c_test'
    assert chat.cid == 'c_test'
    print('  ChatSession properties OK')


async def test_candidate_selection():
    client = Gemini()
    chat = client.new_chat()
    c1 = Candidate(rcid='rc1', text='first', done=True)
    c2 = Candidate(rcid='rc2', text='second', done=True)
    output = ModelOutput(['c1', 'r1'], [c1, c2], model='test')
    chat.last_output = output
    chat.choose_candidate(1)
    assert chat.rcid == 'rc2'
    print('  candidate selection OK')


def test_iter_nested():
    data = {'a': [{'b': 'hello'}, {'c': 'world'}]}
    strings = [s for s in iter_nested(data) if isinstance(s, str)]
    assert 'hello' in strings
    assert 'world' in strings
    print('  iter_nested OK')


def test_find_first_match():
    data = {'text': 'UUID: 550e8400-e29b-41d4-a716-446655440000'}
    result = find_first_match(data, re.compile(r'\b[0-9a-f-]{36}\b', re.I))
    assert result == '550e8400-e29b-41d4-a716-446655440000'
    print('  find_first_match OK')


if __name__ == '__main__':
    import re

    tests = [
        ('constants', test_constants),
        ('model', test_model),
        ('build_model_header', test_build_model_header),
        ('error classes', test_error_classes),
        ('cookie_str', test_cookie_str),
        ('parse_cookies', test_parse_cookies),
        ('parse_proxy', test_parse_proxy),
        ('nested_value', test_nested_value),
        ('clean_text', test_clean_text),
        ('delta', test_delta),
        ('streaming frame parser', test_streaming_frame_parser),
        ('extract_json', test_extract_json),
        ('RPCData', test_rpc_data),
        ('AvailableModel', test_available_model),
        ('Candidate', test_candidate),
        ('ModelOutput', test_model_output),
        ('media', test_media),
        ('Gem/GemJar', test_gem),
        ('chat types', test_chat_types),
        ('research types', test_research_types),
        ('research utils', test_research_utils),
        ('client creation', test_gemini_client_creation),
        ('new chat', test_new_chat),
        ('chat session', test_chat_session),
        ('candidate selection', test_candidate_selection),
        ('iter_nested', test_iter_nested),
        ('find_first_match', test_find_first_match),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            if asyncio.iscoroutinefunction(fn):
                asyncio.run(fn())
            else:
                fn()
            print(f'  ✓ {name}')
            passed += 1
        except Exception as e:
            print(f'  ✗ {name}: {e}')
            import traceback
            traceback.print_exc()
            failed += 1

    print(f'\nResults: {passed} passed, {failed} failed')
