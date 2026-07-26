import httpx
import json
import uuid
import random
import time
import asyncio
from urllib.parse import urlencode

from .constants import (
    Endpoint, GRPC, Headers, Model, ErrorCode,
    TEMPORARY_CHAT_FLAG_INDEX, STREAMING_FLAG_INDEX, GEM_FLAG_INDEX,
    CARD_CONTENT_RE, ARTIFACTS_RE, DEFAULT_METADATA, MODEL_HEADER_KEY,
)
from .errors import APIError, GeminiError, UsageLimitExceeded, ModelInvalid, TemporarilyBlocked
from .types.model import AvailableModel, RPCData
from .types.output import Candidate, ModelOutput
from .types.media import WebImage, GeneratedImage, GeneratedVideo, GeneratedMedia
from .types.research import DeepResearchPlan, DeepResearchStatus, DeepResearchResult
from .utils.auth import get_access_token, cookie_str, parse_cookies, parse_proxy
from .utils.upload import upload_file, parse_file_name
from .utils.parser import get_delta_by_fp_len, get_nested_value, extract_json_from_response, StreamingFrameParser
from .utils.research import extract_deep_research_plan, extract_deep_research_status_payload
from .chat import ChatSession


def _sleep(seconds):
    return asyncio.sleep(seconds)


class Gemini:
    def __init__(self, secure_1psid=None, proxy=None, timeout=300000,
                 auto_close=False, close_delay=300000, verbose=False):
        self.cookies = {'__Secure-1PSID': secure_1psid} if secure_1psid else {}
        self.proxy = proxy
        self.verbose = verbose
        self.timeout = timeout
        self.auto_close = auto_close
        self.close_delay = close_delay

        self._ready = False
        self._guest = not bool(secure_1psid)
        self.access_token = None
        self.build_label = None
        self.session_id = None
        self.language = 'en'
        self.push_id = 'feeds/mcudyrk2a4khkz'
        self.close_task = None
        self._reqid = random.randint(10000, 99999)
        self._init_promise = None

    async def _ensure(self):
        if self._ready:
            return
        if self._init_promise is not None:
            return await self._init_promise
        self._init_promise = self._do_init()
        try:
            return await self._init_promise
        finally:
            self._init_promise = None

    async def _do_init(self):
        # NOTE: _ready is only set to True after init succeeds, so concurrent
        # callers awaiting _init_promise will not observe a half-initialized
        # client.
        try:
            if self._guest:
                await self._get_guest_cookie()
            else:
                access_token, build_label, session_id, language, push_id, valid_cookies = await get_access_token(
                    self.cookies, self.proxy, self.verbose
                )
                self.access_token = access_token
                self.build_label = build_label
                self.session_id = session_id
                self.language = language or 'en'
                self.push_id = push_id or 'feeds/mcudyrk2a4khkz'
                self.cookies = valid_cookies
                self._reqid = random.randint(10000, 99999)

                if self.auto_close:
                    self._reset_close_task()
        except Exception as e:
            await self.close()
            raise e
        self._ready = True

    async def init(self):
        return await self._ensure()

    def _resolve_model(self, model):
        if model is None or model is Model.UNSPECIFIED:
            return Model.UNSPECIFIED
        if isinstance(model, AvailableModel):
            return model
        if isinstance(model, str):
            return Model.from_name(model)
        if isinstance(model, dict) and model.get('model_name') and model.get('model_header'):
            return Model.from_dict(model)
        return Model.UNSPECIFIED

    def new_chat(self, model=None, temporary=False, gem=None):
        return ChatSession(self, model=model, temporary=temporary, gem=gem)

    async def chats(self):
        if self._guest:
            return []
        await self._ensure()
        return await self._fetch_recent_chats()

    async def read_chat(self, cid, limit=10):
        if self._guest:
            raise APIError('Chat history not available in guest mode.')
        await self._ensure()
        response = await self._batch_execute([
            RPCData(rpcid=GRPC.READ_CHAT, payload=json.dumps([cid, limit, None, 1, [1], [4], None, 1])),
        ])
        response_json = extract_json_from_response(response.text)
        for part in response_json:
            body_str = get_nested_value(part, [2])
            if not body_str:
                continue
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError:
                continue
            turns_data = get_nested_value(body, [0])
            if not turns_data:
                continue
            turns = []
            for conv_turn in turns_data:
                conv_rid = get_nested_value(conv_turn, [0, 1], '')
                candidates_list = get_nested_value(conv_turn, [3, 0])
                if candidates_list:
                    for cd in candidates_list:
                        rcid = get_nested_value(cd, [0])
                        if not rcid:
                            continue
                        text, thoughts, web_imgs, gen_imgs, gen_vids, gen_media = self._parse_candidate(cd, cid, conv_rid, rcid)
                        turns.append({
                            'role': 'model', 'text': text, 'thoughts': thoughts,
                            'images': web_imgs + gen_imgs, 'videos': gen_vids, 'media': gen_media,
                        })
                user_text = get_nested_value(conv_turn, [2, 0, 0], '')
                if user_text:
                    turns.append({'role': 'user', 'text': user_text})
            return turns
        return []

    async def delete_chat(self, cid):
        if self._guest:
            raise APIError('Chat management not available in guest mode.')
        await self._ensure()
        await self._batch_execute([RPCData(rpcid=GRPC.DELETE_CHAT_1, payload=json.dumps([cid]))])
        await self._batch_execute([RPCData(rpcid=GRPC.DELETE_CHAT_2, payload=json.dumps([cid, [1, None, 0, 1]]))])

    async def gems(self):
        if self._guest:
            raise APIError('Gems not available in guest mode.')
        await self._ensure()
        language = self.language or 'en'
        response = await self._batch_execute([
            RPCData(rpcid=GRPC.LIST_GEMS, payload=json.dumps([3, [language], 0]), identifier='system'),
            RPCData(rpcid=GRPC.LIST_GEMS, payload=json.dumps([2, [language], 0]), identifier='custom'),
        ])
        response_json = extract_json_from_response(response.text)
        predefined = []
        custom = []
        for part in response_json:
            pid = get_nested_value(part, [-1])
            body_str = get_nested_value(part, [2])
            if not body_str:
                continue
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError:
                continue
            if pid == 'system':
                predefined = get_nested_value(body, [2], [])
            elif pid == 'custom':
                custom = get_nested_value(body, [2], [])
        out = []
        for g in predefined:
            if g and g[0]:
                out.append({'id': g[0], 'name': g[1][0] if g[1] else '', 'description': g[1][1] if g[1] and len(g[1]) > 1 else '', 'prompt': g[2][0] if g[2] else None, 'predefined': True})
        for g in custom:
            if g and g[0]:
                out.append({'id': g[0], 'name': g[1][0] if g[1] else '', 'description': g[1][1] if g[1] and len(g[1]) > 1 else '', 'prompt': g[2][0] if g[2] else None, 'predefined': False})
        return out

    async def add_gem(self, name='', prompt='', description=''):
        if self._guest:
            raise APIError('Gems not available in guest mode.')
        await self._ensure()
        if not name or not prompt:
            raise ValueError('Name and prompt required.')
        response = await self._batch_execute([
            RPCData(rpcid=GRPC.CREATE_GEM, payload=json.dumps([[name, description, prompt, None, None, None, None, None, 0, None, 1, None, None, None, []]])),
        ])
        response_json = extract_json_from_response(response.text)
        body_str = get_nested_value(response_json, [0, 2])
        if not body_str:
            raise APIError('Failed to create gem.')
        try:
            gid = get_nested_value(json.loads(body_str), [0])
        except json.JSONDecodeError:
            raise APIError('Failed to create gem.')
        if not gid:
            raise APIError('Failed to create gem.')
        return {'id': gid, 'name': name, 'description': description, 'prompt': prompt, 'predefined': False}

    async def set_gem(self, gem, name='', prompt='', description=''):
        if self._guest:
            raise APIError('Gems not available in guest mode.')
        await self._ensure()
        gid = gem if isinstance(gem, str) else gem.get('id', '')
        if not gid:
            raise ValueError('Gem ID required.')
        await self._batch_execute([
            RPCData(rpcid=GRPC.UPDATE_GEM, payload=json.dumps([gid, [name, description, prompt, None, None, None, None, None, 0, None, 1, None, None, None, [], 0]])),
        ])
        return {'id': gid, 'name': name, 'description': description, 'prompt': prompt, 'predefined': False}

    async def del_gem(self, gem):
        if self._guest:
            raise APIError('Gems not available in guest mode.')
        await self._ensure()
        gid = gem if isinstance(gem, str) else gem.get('id', '')
        if not gid:
            raise ValueError('Gem ID required.')
        await self._batch_execute([RPCData(rpcid=GRPC.DELETE_GEM, payload=json.dumps([gid]))])

    async def models(self):
        await self._ensure()
        seen = set()
        result = []
        keys = [
            'BASIC_PRO', 'BASIC_FLASH', 'BASIC_LITE', 'BASIC_THINKING',
            'PLUS_PRO', 'PLUS_FLASH', 'PLUS_LITE',
            'ADVANCED_PRO', 'ADVANCED_FLASH', 'ADVANCED_LITE',
        ]
        for key in keys:
            m = getattr(Model, key)
            model_id = Model.model_id(m)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            result.append(AvailableModel(
                model_id=model_id, model_name=m['model_name'],
                display_name=key.replace('_', ' ').title(),
                description='Advanced tier' if m.get('advanced_only') else 'Free tier',
                capacity=2 if m.get('advanced_only') else 1,
                capacity_field=12, model_number=1, is_available=True,
            ))
        return result

    async def research(self, prompt, wait=True, poll_interval=10000, timeout=600000, on_status=None):
        if self._guest:
            raise APIError('Deep research not available in guest mode.')
        chat = self.new_chat(model=Model.UNSPECIFIED)
        plan = await self._create_deep_research_plan(prompt, chat)
        if not plan:
            raise GeminiError('Failed to create deep research plan.')
        await self._start_deep_research(plan, chat)
        if not wait:
            return {'plan': plan}
        result = await self._wait_deep_research(plan, poll_interval, timeout, on_status)
        result.plan = plan
        return result

    async def ask(self, prompt, model=None, gem=None, temporary=False, files=None, extended_thinking=False):
        chat = self.new_chat(model=model, gem=gem, temporary=temporary)
        return await chat.generate_content(prompt=prompt, files=files, extended_thinking=extended_thinking)

    async def close(self, delay=0):
        if delay:
            await _sleep(delay)
        self._ready = False
        if self.close_task:
            self.close_task.cancel()
            self.close_task = None

    # camelCase aliases for Node.js API compatibility
    newChat = new_chat
    readChat = read_chat
    deleteChat = delete_chat
    addGem = add_gem
    setGem = set_gem
    delGem = del_gem

    async def _generate_content(self, prompt='', files=None, model=None, gem=None, chat=None,
                                temporary=False, deep_research=False, extended_thinking=False,
                                mode_category=None):
        await self._ensure()
        if self._guest and files:
            raise APIError('File upload not available in guest mode.')
        if self._guest and deep_research:
            raise APIError('Deep research not available in guest mode.')
        file_data = None
        if files and len(files):
            uploaded = await asyncio.gather(*[upload_file(f, self.proxy, self.push_id, self.cookies) for f in files])
            file_data = [[[url], parse_file_name(files[i])] for i, url in enumerate(uploaded)]

        ss = {'last_texts': {}, 'last_thoughts': {}}
        output = None
        async for out in self._generate(prompt=prompt, file_data=file_data, model=model,
                                         gem=gem, chat=chat, temporary=temporary, ss=ss,
                                         deep_research=deep_research, extended_thinking=extended_thinking,
                                         mode_category=mode_category):
            output = out
        if not output:
            raise GeminiError('Failed to generate contents.')
        if chat:
            output.metadata = chat.metadata
            chat.last_output = output
        return output

    async def _generate_content_stream(self, prompt='', files=None, model=None, gem=None, chat=None,
                                       temporary=False, deep_research=False, extended_thinking=False,
                                       mode_category=None):
        await self._ensure()
        if self._guest and files:
            raise APIError('File upload not available in guest mode.')
        if self._guest and deep_research:
            raise APIError('Deep research not available in guest mode.')
        file_data = None
        if files and len(files):
            uploaded = await asyncio.gather(*[upload_file(f, self.proxy, self.push_id, self.cookies) for f in files])
            file_data = [[[url], parse_file_name(files[i])] for i, url in enumerate(uploaded)]

        ss = {'last_texts': {}, 'last_thoughts': {}}
        output = None
        async for out in self._generate(prompt=prompt, file_data=file_data, model=model,
                                         gem=gem, chat=chat, temporary=temporary, ss=ss,
                                         deep_research=deep_research, extended_thinking=extended_thinking,
                                         mode_category=mode_category):
            output = out
            yield out
        if output and chat:
            output.metadata = chat.metadata
            chat.last_output = output

    async def _generate(self, prompt='', file_data=None, model=None, gem=None, chat=None,
                        temporary=False, ss=None, deep_research=False, extended_thinking=False,
                        mode_category=None, retries=5):
        if not prompt:
            raise ValueError('Prompt cannot be empty.')
        if self._guest:
            async for out in self._stream_guest(prompt=prompt, chat=chat, ss=ss):
                yield out
            return
        model = self._resolve_model(model)
        for attempt in range(retries + 1):
            try:
                async for out in self._stream(prompt=prompt, file_data=file_data, model=model,
                                               gem=gem, chat=chat, temporary=temporary, ss=ss,
                                               deep_research=deep_research, extended_thinking=extended_thinking,
                                               mode_category=mode_category):
                    yield out
                return
            except (GeminiError, ModelInvalid, UsageLimitExceeded, TemporarilyBlocked) as e:
                raise e
            except Exception as e:
                if attempt >= retries:
                    raise e
                await _sleep(1.0 * (attempt + 1))

    async def _stream(self, prompt='', file_data=None, model=None, gem=None, chat=None,
                      temporary=False, ss=None, deep_research=False, extended_thinking=False,
                      mode_category=None):
        _reqid = self._reqid
        self._reqid += 100000
        gem_id = gem if isinstance(gem, str) else (gem.get('id') if isinstance(gem, dict) else None)
        chat_backup = {'metadata': list(chat.metadata), 'cid': chat.cid, 'rid': chat.rid, 'rcid': chat.rcid} if chat else None

        inner = [None] * 81
        inner[0] = [prompt, 0, None, file_data, None, None, 0]
        inner[1] = [self.language or 'en']
        inner[2] = chat.metadata if chat else list(DEFAULT_METADATA)
        if deep_research:
            inner[3] = '!' + ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_', k=1950))
            inner[4] = uuid.uuid4().hex
        inner[6] = [1]
        inner[STREAMING_FLAG_INDEX] = 1
        inner[10] = 1
        inner[11] = 0
        inner[17] = [[0]]
        inner[18] = 0
        if gem_id:
            inner[GEM_FLAG_INDEX] = gem_id
        inner[27] = 1
        inner[30] = [4]
        inner[41] = [1]
        if temporary:
            inner[TEMPORARY_CHAT_FLAG_INDEX] = 1
        if deep_research:
            inner[49] = 1
        inner[53] = 0
        if deep_research:
            inner[54] = [[[[[1]]]]]
            inner[55] = [[1]]
        inner[61] = []
        inner[68] = 1
        inner[80] = 2 if extended_thinking else 1

        uid = uuid.uuid4().hex.upper()
        inner[59] = uid

        if mode_category is not None:
            inner[79] = mode_category
        else:
            model_headers = dict(model.get('model_header', {}) if isinstance(model, dict) else {})
            if MODEL_HEADER_KEY in model_headers:
                try:
                    parsed = json.loads(model_headers[MODEL_HEADER_KEY]) if isinstance(model_headers[MODEL_HEADER_KEY], str) else model_headers[MODEL_HEADER_KEY]
                    model_number = parsed[-1] if parsed and isinstance(parsed[-1], (int, float)) else None
                    if model_number is not None:
                        inner[79] = model_number
                except (json.JSONDecodeError, IndexError, TypeError):
                    pass

        model_headers = dict(model.get('model_header', {}) if isinstance(model, dict) else {})
        if MODEL_HEADER_KEY in model_headers:
            try:
                parsed = json.loads(model_headers[MODEL_HEADER_KEY]) if isinstance(model_headers[MODEL_HEADER_KEY], str) else model_headers[MODEL_HEADER_KEY]
                parsed.append(2 if extended_thinking else 1)
                parsed.append(self.session_id)
                model_headers[MODEL_HEADER_KEY] = json.dumps(parsed)
            except (json.JSONDecodeError, IndexError, TypeError):
                pass

        params = {'hl': self.language or 'en', '_reqid': str(_reqid), 'rt': 'c'}
        if self.build_label:
            params['bl'] = self.build_label
        if self.session_id:
            params['f.sid'] = self.session_id

        body_data = {'at': self.access_token or '', 'f.req': json.dumps([None, json.dumps(inner)])}

        headers = {
            **Headers.GEMINI,
            **model_headers,
            'x-goog-ext-525005358-jspb': json.dumps([uid, 1]),
            **Headers.SAME_DOMAIN,
            'Cookie': cookie_str(self.cookies),
        }

        proxy_url = parse_proxy(self.proxy)

        url = f"{Endpoint.GENERATE}?{urlencode(params)}"
        async with httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(self.timeout / 1000.0),
            proxy=proxy_url,
        ) as client:
            async with client.stream('POST', url, data=body_data) as res:
                if res.status_code != 200:
                    await self.close()
                    raise APIError(f'Generate failed. Status: {res.status_code}')

                new_cookies = parse_cookies(res.headers)
                self.cookies.update(new_cookies)

                l_txt = ss.get('last_texts', {}) if ss else {}
                l_thought = ss.get('last_thoughts', {}) if ss else {}
                is_thinking = False
                is_queueing = False
                is_completed = False
                is_final_chunk = False
                cid = chat.cid if chat else ''
                rid = chat.rid if chat else ''
                video_chip_uuid = None
                frame_parser = StreamingFrameParser()
                yielded_outputs = []

                async for chunk in res.aiter_text():
                    parts = frame_parser.feed(chunk)
                    for part in parts:
                        ec = get_nested_value(part, [5, 2, 0, 1, 0])
                        if ec:
                            error_map = {
                                ErrorCode.USAGE_LIMIT_EXCEEDED: UsageLimitExceeded('Usage limit exceeded.'),
                                ErrorCode.MODEL_INCONSISTENT: ModelInvalid('Model inconsistent with conversation history.'),
                                ErrorCode.MODEL_HEADER_INVALID: ModelInvalid('Model unavailable or request structure outdated.'),
                                ErrorCode.IP_TEMPORARILY_BLOCKED: TemporarilyBlocked('IP temporarily blocked by Google.'),
                                ErrorCode.TEMPORARY_ERROR_1013: APIError('Temporary error (1013).'),
                                ErrorCode.FEATURE_NOT_AVAILABLE: UsageLimitExceeded('This feature is not available for your account plan.'),
                            }
                            raise error_map.get(ec, APIError(f'Unknown API error: {ec}'))

                        inner_str = get_nested_value(part, [2])
                        if not inner_str:
                            continue
                        try:
                            pj = json.loads(inner_str)
                        except (json.JSONDecodeError, ValueError):
                            continue

                        m_data = get_nested_value(pj, [1])
                        if m_data:
                            new_cid = get_nested_value(m_data, [0])
                            new_rid = get_nested_value(m_data, [1])
                            if new_cid:
                                cid = new_cid
                            if new_rid:
                                rid = new_rid
                            if chat:
                                chat.metadata = m_data

                        ctx = get_nested_value(pj, [25])
                        if isinstance(ctx, str):
                            is_final_chunk = True
                            if chat:
                                m = list(chat.metadata)
                                m[9] = ctx
                                chat.metadata = m

                        clist = get_nested_value(pj, [4], [])
                        if not clist or not len(clist):
                            continue

                        out_cands = []
                        for i, cd in enumerate(clist):
                            rcid = get_nested_value(cd, [0])
                            if not rcid:
                                continue
                            if chat:
                                chat.rcid = rcid

                            text, thoughts, web_imgs, gen_imgs, gen_vids, gen_media = self._parse_candidate(cd, cid, rid, rcid)

                            if not video_chip_uuid:
                                entry65 = get_nested_value(cd, [12, 0, '65'])
                                if isinstance(entry65, (list, tuple)) and len(entry65) >= 2:
                                    video_chip_uuid = entry65[1]

                            indicator = get_nested_value(cd, [8, 0])
                            is_completed = indicator == 2

                            last_sent_text = l_txt.get(rcid) or l_txt.get(f'idx_{i}') or ''
                            td, nft = get_delta_by_fp_len(text, last_sent_text, is_completed or indicator is None)
                            thdelta = ''
                            nfth = ''
                            if thoughts:
                                last_sent_thought = l_thought.get(rcid) or l_thought.get(f'idx_{i}') or ''
                                thdelta, nfth = get_delta_by_fp_len(thoughts, last_sent_thought, is_completed or indicator is None)

                            l_txt[rcid] = l_txt[f'idx_{i}'] = nft
                            l_thought[rcid] = l_thought[f'idx_{i}'] = nfth

                            dr_plan = None
                            if deep_research:
                                plan_data = extract_deep_research_plan(cd, text)
                                if plan_data:
                                    dr_plan = DeepResearchPlan(**plan_data)
                                    dr_plan.cid = chat.cid if chat else None

                            out_cands.append(Candidate(
                                rcid=rcid, index=i, text=text, text_delta=td,
                                thoughts=thoughts or None, thoughts_delta=thdelta,
                                web_images=web_imgs, generated_images=gen_imgs,
                                generated_videos=gen_vids, generated_media=gen_media,
                                deep_research_plan=dr_plan, done=is_completed,
                            ))

                        if out_cands:
                            metadata = get_nested_value(pj, [1], [])
                            out_obj = ModelOutput(
                                metadata, out_cands,
                                model=model.get('model_name', '') if isinstance(model, dict) else '',
                                gem=gem_id,
                            )
                            yielded_outputs.append(out_obj)
                            yield out_obj

                remaining = frame_parser.flush()
                for part in remaining:
                    inner_str = get_nested_value(part, [2])
                    if not inner_str:
                        continue
                    try:
                        pj = json.loads(inner_str)
                    except (json.JSONDecodeError, ValueError):
                        continue

                    m_data = get_nested_value(pj, [1])
                    if m_data and chat:
                        chat.metadata = m_data

                    clist = get_nested_value(pj, [4], [])
                    if not clist or not len(clist):
                        continue

                    out_cands = []
                    for i, cd in enumerate(clist):
                        rcid = get_nested_value(cd, [0])
                        if not rcid:
                            continue
                        text, thoughts, web_imgs, gen_imgs, gen_vids, gen_media = self._parse_candidate(cd, cid, rid, rcid)
                        indicator = get_nested_value(cd, [8, 0])
                        is_completed = indicator == 2

                        last_sent_text = l_txt.get(rcid) or l_txt.get(f'idx_{i}') or ''
                        td, nft = get_delta_by_fp_len(text, last_sent_text, True)
                        l_txt[rcid] = l_txt[f'idx_{i}'] = nft

                        out_cands.append(Candidate(
                            rcid=rcid, index=i, text=text, text_delta=td,
                            thoughts=thoughts or None,
                            web_images=web_imgs, generated_images=gen_imgs,
                            generated_videos=gen_vids, generated_media=gen_media,
                            done=is_completed,
                        ))

                    if out_cands:
                        metadata = get_nested_value(pj, [1], [])
                        out_obj = ModelOutput(metadata, out_cands,
                                              model=model.get('model_name', '') if isinstance(model, dict) else '',
                                              gem=gem_id)
                        yielded_outputs.append(out_obj)
                        yield out_obj

                has_generated_text = len(yielded_outputs) > 0

                if ((not is_completed) or is_thinking or is_queueing) and cid and is_final_chunk:
                    poll_start = time.time()
                    while True:
                        if (time.time() - poll_start) > self.timeout / 1000.0:
                            await self.close()
                            if has_generated_text:
                                raise GeminiError('Connection lost. Recovery timed out.')
                            else:
                                raise APIError('Polling timed out.')
                        recovered = await self._read_chat_internal(cid)
                        if recovered and len(recovered.get('turns', [])) > 0 and recovered['turns'][0]['role'] == 'model':
                            recovered_out = recovered['turns'][0].get('model_output')
                            if recovered_out and recovered_out.candidates and (recovered_out.text or recovered_out.thoughts or len(recovered_out.images) or len(recovered_out.videos) or len(recovered_out.media)):
                                rec_rcid = recovered_out.rcid
                                prev_rcid = chat_backup.get('rcid', '') if chat_backup else ''
                                if rec_rcid != prev_rcid:
                                    if chat:
                                        recovered_out.metadata = chat.metadata
                                        chat.rcid = rec_rcid
                                    yield recovered_out
                                    return
                        await _sleep(10)

                if video_chip_uuid and not any(o.videos for o in yielded_outputs) and cid:
                    poll_start = time.time()
                    while (time.time() - poll_start) < self.timeout / 1000.0:
                        recovered = await self._read_chat_internal(cid)
                        if recovered:
                            for t in recovered.get('turns', []):
                                if t['role'] == 'model' and t.get('model_output') and t['model_output'].videos:
                                    recovered_out = t['model_output']
                                    if chat:
                                        recovered_out.metadata = chat.metadata
                                        chat.rcid = recovered_out.rcid
                                    yield recovered_out
                                    return
                        await _sleep(10)

    async def _get_guest_cookie(self):
        proxy_url = parse_proxy(self.proxy)

        params = urlencode({
            'rpcids': 'maGuAc', 'source-path': '%2F', 'hl': 'en-US',
            '_reqid': '1', 'rt': 'c',
        })
        async with httpx.AsyncClient(proxy=proxy_url) as client:
            res = await client.post(
                f'{Endpoint.BATCH_EXEC}?{params}',
                data='f.req=%5B%5B%5B%22maGuAc%22%2C%22%5B0%5D%22%2Cnull%2C%22generic%22%5D%5D%5D&',
                headers={'content-type': 'application/x-www-form-urlencoded;charset=UTF-8'},
            )
        cookies = parse_cookies(res.headers)
        if '__Secure-1PSID' in cookies:
            self.cookies['__Secure-1PSID'] = cookies['__Secure-1PSID']
        self.cookies.update(cookies)
        self.access_token = ''
        self.build_label = 'boq_assistant-bard-web-server_20260618.10_p0'
        self.session_id = '6921068608429233100'
        self.language = 'en-US'
        self._reqid = random.randint(10000, 99999)

    async def _stream_guest(self, prompt='', chat=None, ss=None):
        _reqid = self._reqid
        self._reqid += 100000

        chat_meta = list(chat.metadata) if chat else list(DEFAULT_METADATA)
        inner = [None] * 80
        inner[0] = [prompt, 0, None, None, None, None, 0]
        inner[1] = [self.language or 'en-US']
        inner[2] = chat_meta
        inner[6] = [0]
        inner[7] = 1
        inner[10] = 1
        inner[11] = 0
        inner[17] = [[0]]
        inner[18] = 0
        inner[27] = 1
        inner[30] = [4]
        inner[41] = [2]
        inner[53] = 0
        inner[59] = str(uuid.uuid4())
        inner[61] = []
        inner[68] = 1
        inner[79] = 1

        body_data = urlencode({'f.req': json.dumps([None, json.dumps(inner)])})
        headers = {
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://gemini.google.com',
            'referer': 'https://gemini.google.com/app',
            'x-same-domain': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'cookie': cookie_str(self.cookies),
        }

        proxy_url = parse_proxy(self.proxy)

        params = {'hl': self.language or 'en-US', '_reqid': str(_reqid), 'rt': 'c'}
        if self.build_label:
            params['bl'] = self.build_label
        if self.session_id:
            params['f.sid'] = self.session_id

        url = f"{Endpoint.GENERATE}?{urlencode(params)}"
        async with httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(self.timeout / 1000.0),
            proxy=proxy_url,
        ) as client:
            async with client.stream('POST', url, data=body_data, follow_redirects=False) as res:
                if res.status_code != 200:
                    if res.status_code == 302:
                        loc = res.headers.get('location', 'unknown')
                        print(f'[gemrev] 302 redirect to: {loc}')
                    raise APIError(f'Generate failed. Status: {res.status_code}')

                new_cookies = parse_cookies(res.headers)
                self.cookies.update(new_cookies)

                l_txt = ss.get('last_texts', {}) if ss else {}
                frame_parser = StreamingFrameParser()

                is_completed = False

                async for chunk in res.aiter_text():
                    parts = frame_parser.feed(chunk)
                    for part in parts:
                        ec = get_nested_value(part, [5, 2, 0, 1, 0])
                        if ec:
                            error_map = {
                                ErrorCode.USAGE_LIMIT_EXCEEDED: UsageLimitExceeded('Usage limit exceeded.'),
                                ErrorCode.IP_TEMPORARILY_BLOCKED: TemporarilyBlocked('IP temporarily blocked.'),
                            }
                            if ec in (1096, 1097):
                                raise APIError('Session continuation not available in guest mode. Use authenticated mode for multi-turn chat.')
                            raise error_map.get(ec, APIError(f'Guest API error code: {ec}.'))

                        inner_str = get_nested_value(part, [2])
                        if not inner_str:
                            continue
                        try:
                            pj = json.loads(inner_str)
                        except (json.JSONDecodeError, ValueError):
                            continue

                        m_data = get_nested_value(pj, [1])
                        if m_data:
                            if chat:
                                chat.metadata = m_data

                        ctx = get_nested_value(pj, [25])
                        if isinstance(ctx, str) and chat:
                            m = list(chat.metadata)
                            m[9] = ctx
                            chat.metadata = m

                        clist = get_nested_value(pj, [4], [])
                        if not clist or not len(clist):
                            continue

                        for i, cd in enumerate(clist):
                            rcid = get_nested_value(cd, [0])
                            if not rcid:
                                continue
                            if chat:
                                chat.rcid = rcid

                            text = get_nested_value(cd, [1, 0], '')
                            indicator = get_nested_value(cd, [8, 0])
                            is_completed = indicator == 2

                            last_sent_text = l_txt.get(rcid) or l_txt.get(f'idx_{i}') or ''
                            td, nft = get_delta_by_fp_len(text, last_sent_text, is_completed or indicator is None)
                            l_txt[rcid] = l_txt[f'idx_{i}'] = nft

                            cand = Candidate(rcid=rcid, index=i, text=text, text_delta=td, done=is_completed)
                            yield ModelOutput(get_nested_value(pj, [1], []), [cand], model='gemini-3-flash')

    async def _get_full_size_image(self, cid, rid, rcid, image_id):
        try:
            payload = [[[None, None, None, [None, None, None, None, None, '']], [image_id, 0], None, [19, ''], None, None, None, None, None, ''], [rid, rcid, cid, None, ''], 1, 0, 1]
            response = await self._batch_execute([RPCData(rpcid=GRPC.GET_FULL_SIZE_IMAGE, payload=json.dumps(payload))])
            response_data = extract_json_from_response(response.text)
            body_str = get_nested_value(response_data, [0, 2], '[]')
            return get_nested_value(json.loads(body_str), [0])
        except Exception:
            return None

    def _parse_candidate(self, candidate_data, cid, rid, rcid):
        text = get_nested_value(candidate_data, [1, 0], '')
        if CARD_CONTENT_RE.match(text):
            text = get_nested_value(candidate_data, [22, 0]) or text
        text = ARTIFACTS_RE.sub('', text)

        thoughts = get_nested_value(candidate_data, [37, 0, 0]) or ''

        web_images = []
        wi_list = get_nested_value(candidate_data, [12, 1], []) or []
        for img_idx, wi in enumerate(wi_list):
            url = get_nested_value(wi, [0, 0, 0])
            if url:
                web_images.append(WebImage(
                    url=url, title=f'[Image {img_idx + 1}]',
                    alt=get_nested_value(wi, [0, 4], ''),
                    proxy=self.proxy, client_ref=self,
                ))

        generated_images = []
        gen_img_sources = []
        gen_img_sources.extend(get_nested_value(candidate_data, [12, 7, 0], []) or [])
        gen_img_sources.extend(get_nested_value(candidate_data, [12, 0, '8', 0], []) or [])
        for img_idx, gi in enumerate(gen_img_sources):
            url = get_nested_value(gi, [0, 3, 3])
            if url:
                image_id = get_nested_value(gi, [1, 0])
                if not image_id:
                    image_id = f'http://googleusercontent.com/image_generation_content/{img_idx}'
                generated_images.append(GeneratedImage(
                    url=url, title=f'[Generated Image {img_idx}]',
                    alt=get_nested_value(gi, [0, 3, 2], ''),
                    proxy=self.proxy, client_ref=self,
                    cid=cid, rid=rid, rcid=rcid, image_id=image_id,
                ))

        generated_videos = []
        v_list = get_nested_value(candidate_data, [12, 0, '60', 0, 0, 0]) or []
        for v_item in v_list:
            urls = get_nested_value(v_item, [7], [])
            if isinstance(urls, (list, tuple)) and len(urls) >= 2:
                generated_videos.append(GeneratedVideo(
                    url=urls[1], thumbnail=urls[0],
                    cid=cid, rid=rid, rcid=rcid,
                    client_ref=self, proxy=self.proxy,
                ))

        generated_media = []
        media_data = get_nested_value(candidate_data, [12, 86], [])
        if media_data:
            mp3_list = get_nested_value(media_data, [0, 1, 7], [])
            mp3_url = ''
            mp3_thumb = ''
            if isinstance(mp3_list, (list, tuple)) and len(mp3_list) >= 2:
                mp3_thumb = mp3_list[0]
                mp3_url = mp3_list[1]

            mp4_list = get_nested_value(media_data, [1, 1, 7], [])
            mp4_url = ''
            mp4_thumb = ''
            if isinstance(mp4_list, (list, tuple)) and len(mp4_list) >= 2:
                mp4_thumb = mp4_list[0]
                mp4_url = mp4_list[1]

            if mp3_url or mp4_url:
                generated_media.append(GeneratedMedia(
                    url=mp4_url, thumbnail=mp4_thumb,
                    mp3_url=mp3_url, mp3_thumbnail=mp3_thumb,
                    cid=cid, rid=rid, rcid=rcid,
                    client_ref=self, proxy=self.proxy,
                ))

        return text, thoughts, web_images, generated_images, generated_videos, generated_media

    async def _create_deep_research_plan(self, prompt, chat):
        output = await self._collect_research_output(chat, prompt)
        plan = output.deep_research_plan
        if not plan:
            preview = (output.text or '')[:1200]
            raise GeminiError(f'Gemini did not return a deep research plan. Preview: {preview}')
        plan.metadata = list(chat.metadata)
        plan.cid = chat.cid or plan.cid
        if not plan.confirm_prompt:
            plan.confirm_prompt = 'Start research'
        if not plan.response_text:
            plan.response_text = output.text
        return plan

    async def _start_deep_research(self, plan, chat):
        prompt = plan.confirm_prompt or 'Start research'
        return await self._collect_research_output(chat, prompt)

    async def _collect_research_output(self, chat, prompt):
        recoverable_error = None
        try:
            output = await self._generate_content(prompt=prompt, chat=chat, deep_research=True)
            if output.deep_research_plan or (output.text or '').strip():
                chat.last_output = output
                return output
        except (UsageLimitExceeded, ModelInvalid, TemporarilyBlocked) as e:
            raise e
        except (GeminiError, APIError) as e:
            recoverable_error = e
        except Exception as e:
            raise e

        if chat.cid:
            fallback = await self._read_chat_internal(chat.cid)
            if fallback:
                chat.last_output = fallback
                return fallback
        if recoverable_error:
            raise recoverable_error
        raise GeminiError('Gemini returned no usable output for deep research.')

    async def _read_chat_internal(self, cid):
        try:
            response = await self._batch_execute([
                RPCData(rpcid=GRPC.READ_CHAT, payload=json.dumps([cid, 5, None, 1, [1], [4], None, 1])),
            ])
            response_json = extract_json_from_response(response.text)
            for part in response_json:
                body_str = get_nested_value(part, [2])
                if not body_str:
                    continue
                try:
                    body = json.loads(body_str)
                except json.JSONDecodeError:
                    continue
                turns_data = get_nested_value(body, [0])
                if not turns_data:
                    continue
                turns = []
                for conv_turn in turns_data:
                    candidates_list = get_nested_value(conv_turn, [3, 0])
                    if candidates_list:
                        for cd in candidates_list:
                            rcid = get_nested_value(cd, [0])
                            if not rcid:
                                continue
                            text, thoughts, web_imgs, gen_imgs, gen_vids, gen_media = self._parse_candidate(cd, cid, '', rcid)
                            turns.append({
                                'role': 'model', 'text': text,
                                'model_output': ModelOutput(
                                    [cid, ''],
                                    [Candidate(rcid=rcid, index=0, text=text, thoughts=thoughts or None,
                                               web_images=web_imgs, generated_images=gen_imgs,
                                               generated_videos=gen_vids, generated_media=gen_media, done=True)]
                                ),
                            })
                    user_text = get_nested_value(conv_turn, [2, 0, 0], '')
                    if user_text:
                        turns.append({'role': 'user', 'text': user_text})
                return {'cid': cid, 'turns': turns}
            return None
        except Exception:
            return None

    async def _wait_deep_research(self, plan, poll_interval=10000, timeout=600000, on_status=None):
        if not plan.research_id:
            raise GeminiError('Cannot poll: plan.research_id is missing.')
        start = time.time()
        statuses = []
        chat = self.new_chat(metadata=list(plan.metadata), model=Model.UNSPECIFIED)
        chat.cid = plan.cid
        while (time.time() - start) < timeout / 1000.0:
            status = None
            if plan.research_id:
                status = await self._get_deep_research_status(plan.research_id)
            if status:
                statuses.append(status)
                if on_status:
                    on_status(status)
                if status.done:
                    break
            await _sleep(poll_interval / 1000.0)
        if not statuses or not statuses[-1].done:
            pass
        final_output = None
        if chat.cid:
            recovered = await self._read_chat_internal(chat.cid)
            if recovered and recovered.get('turns'):
                for t in recovered['turns']:
                    if t['role'] == 'model' and t.get('model_output'):
                        final_output = t['model_output']
                        break
        done = len(statuses) > 0 and statuses[-1].done
        return DeepResearchResult(plan=plan, statuses=statuses, final_output=final_output, done=done)

    async def _get_deep_research_status(self, research_id):
        response = await self._batch_execute([
            RPCData(rpcid=GRPC.DEEP_RESEARCH_STATUS, payload=json.dumps([research_id])),
        ])
        response_json = extract_json_from_response(response.text)
        for part in response_json:
            body_str = get_nested_value(part, [2])
            if not body_str:
                continue
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError:
                continue
            parsed = extract_deep_research_status_payload(body)
            if parsed:
                return DeepResearchStatus(**parsed)
        return None

    def _reset_close_task(self):
        if self.close_task:
            self.close_task.cancel()
        loop = asyncio.get_event_loop()
        self.close_task = loop.call_later(self.close_delay / 1000.0, lambda: asyncio.create_task(self.close()))

    async def _fetch_recent_chats(self, recent=13):
        async def fetch_batch(payload):
            return await self._batch_execute([
                RPCData(rpcid=GRPC.LIST_CHATS, payload=json.dumps([recent, None, payload])),
            ])
        resp1 = await fetch_batch([1, None, 1])
        resp2 = await fetch_batch([0, None, 1])
        recent_chats = []
        seen_cids = set()
        for response in (resp1, resp2):
            chats_json = extract_json_from_response(response.text)
            for part in chats_json:
                body_str = get_nested_value(part, [2])
                if not body_str:
                    continue
                try:
                    body = json.loads(body_str)
                except json.JSONDecodeError:
                    continue
                chat_list = get_nested_value(body, [2])
                if not isinstance(chat_list, (list, tuple)):
                    continue
                for chat_data in chat_list:
                    if not isinstance(chat_data, (list, tuple)) or len(chat_data) < 2:
                        continue
                    cid = get_nested_value(chat_data, [0], '')
                    title = get_nested_value(chat_data, [1], '')
                    is_pinned = bool(get_nested_value(chat_data, [2]))
                    ts_data = get_nested_value(chat_data, [5])
                    timestamp = 0
                    if isinstance(ts_data, (list, tuple)) and len(ts_data) >= 2:
                        timestamp = float(ts_data[0]) + float(ts_data[1]) / 1e9
                    if cid and cid not in seen_cids:
                        seen_cids.add(cid)
                        recent_chats.append({'cid': cid, 'title': title, 'pinned': is_pinned, 'timestamp': timestamp})
                break
        return recent_chats

    async def _batch_execute(self, payloads, retries=2, source_path='/app'):
        last_err = None
        for attempt in range(retries + 1):
            try:
                _reqid = self._reqid
                self._reqid += 100000
                params = {
                    'rpcids': ','.join(p.rpcid for p in payloads),
                    'hl': self.language or 'en',
                    '_reqid': str(_reqid),
                    'rt': 'c',
                    'source-path': source_path,
                }
                if self.build_label:
                    params['bl'] = self.build_label
                if self.session_id:
                    params['f.sid'] = self.session_id

                body_data = {
                    'at': self.access_token or '',
                    'f.req': json.dumps([[p.serialize() for p in payloads]]),
                }

                proxy_url = parse_proxy(self.proxy)

                headers = {
                    **Headers.GEMINI,
                    **Headers.BATCH_EXEC,
                    **Headers.SAME_DOMAIN,
                    'Cookie': cookie_str(self.cookies),
                }

                async with httpx.AsyncClient(
                    headers=headers,
                    timeout=httpx.Timeout(self.timeout / 1000.0),
                    proxy=proxy_url,
                ) as client:
                    res = await client.post(
                        f'{Endpoint.BATCH_EXEC}?{urlencode(params)}',
                        data=body_data,
                    )

                new_cookies = parse_cookies(res.headers)
                self.cookies.update(new_cookies)

                if res.status_code != 200:
                    raise APIError(f'Batch execution failed with status code {res.status_code}')
                return res
            except Exception as e:
                last_err = e
                if attempt < retries:
                    await _sleep(1.0 * (attempt + 1))
        raise last_err
