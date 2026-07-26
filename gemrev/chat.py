import json
import uuid
from .constants import DEFAULT_METADATA, Model


class ChatSession:
    def __init__(self, client, model=None, temporary=False, gem=None, metadata=None):
        self.client = client
        self._meta = list(DEFAULT_METADATA)
        self.gem = gem
        self.temporary = temporary
        self.model = client._resolve_model(model) if model is not None else Model.UNSPECIFIED
        if metadata:
            for i in range(min(len(metadata), 10)):
                if metadata[i] is not None:
                    self._meta[i] = metadata[i]
        self.last_output = None

    @property
    def cid(self):
        return self._meta[0]

    @cid.setter
    def cid(self, v):
        self._meta[0] = v

    @property
    def rid(self):
        return self._meta[1]

    @rid.setter
    def rid(self, v):
        self._meta[1] = v

    @property
    def rcid(self):
        return self._meta[2]

    @rcid.setter
    def rcid(self, v):
        self._meta[2] = v

    @property
    def metadata(self):
        return self._meta

    @metadata.setter
    def metadata(self, v):
        if not isinstance(v, (list, tuple)):
            return
        for i in range(min(len(v), 10)):
            if v[i] is not None:
                self._meta[i] = v[i]

    @staticmethod
    def _messages_to_prompt(messages, tools=None):
        parts = []
        if tools:
            defs = []
            for t in tools:
                if isinstance(t, dict):
                    fn = t.get('function', t) if t.get('type') == 'function' else t
                    defs.append({'name': fn.get('name', ''), 'description': fn.get('description', ''), 'parameters': fn.get('parameters', {})})
                else:
                    defs.append({'name': t.name, 'description': t.description, 'parameters': t.parameters})
            if defs:
                parts.append(
                    '[Available tools]\n'
                    + json.dumps(defs, indent=2)
                    + '\n[/Available tools]'
                )
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if isinstance(content, list):
                content = ' '.join(c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') in ('text', 'input_text'))
            if role == 'system':
                parts.append(f'[System]: {content}')
            elif role == 'assistant':
                tc_block = ''
                for tc in msg.get('tool_calls') or []:
                    fn = tc.get('function', {})
                    tc_block += f'\n[TOOL_CALL]{fn.get("name", "")}|{fn.get("arguments", "{}")}[/TOOL_CALL]'
                parts.append(f'[Assistant]: {content or ""}{tc_block}')
            elif role == 'tool':
                parts.append(f'[TOOL_RESULT]{content}[/TOOL_RESULT]')
            else:
                parts.append(content or '')
        return '\n\n'.join(parts)

    @staticmethod
    def _parse_tool_calls(text):
        import re as _re
        tool_calls = []
        pattern = _re.compile(r'\[TOOL_CALL\](.+?)\[/TOOL_CALL\]', _re.DOTALL)
        for m in pattern.finditer(text):
            raw = m.group(1).strip()
            name = raw
            args = {}
            pipe_pos = raw.find('|')
            if pipe_pos != -1:
                name = raw[:pipe_pos].strip()
                args_str = raw[pipe_pos + 1:].strip()
                if args_str:
                    try:
                        args = json.loads(args_str)
                    except (json.JSONDecodeError, ValueError):
                        args = {}
            tool_calls.append({
                'id': f'call_{uuid.uuid4().hex[:8]}',
                'type': 'function',
                'function': {'name': name, 'arguments': args},
            })
        clean = pattern.sub('', text).strip()
        return clean, tool_calls

    async def generate_content(self, prompt='', files=None, deep_research=False,
                                extended_thinking=False, tools=None, messages=None,
                                mode_category=None):
        if not prompt and not messages:
            raise ValueError('Prompt or messages required.')
        if messages:
            prompt = self._messages_to_prompt(messages, tools)
        output = await self.client._generate_content(
            prompt=prompt, files=files, model=self.model, gem=self.gem,
            chat=self, temporary=self.temporary,
            deep_research=deep_research, extended_thinking=extended_thinking,
            mode_category=mode_category,
        )
        if output and output.text and tools:
            clean, tcs = self._parse_tool_calls(output.text)
            if tcs:
                output.candidates[output.chosen]._tool_calls = tcs
                output.candidates[output.chosen].text = clean
        self.last_output = output
        return output

    async def generate_content_stream(self, prompt='', files=None, deep_research=False,
                                       extended_thinking=False, tools=None, messages=None,
                                       mode_category=None):
        if not prompt and not messages:
            raise ValueError('Prompt or messages required.')
        if messages:
            prompt = self._messages_to_prompt(messages, tools)
        last_output = None
        async for out in self.client._generate_content_stream(
            prompt=prompt, files=files, model=self.model, gem=self.gem,
            chat=self, temporary=self.temporary,
            deep_research=deep_research, extended_thinking=extended_thinking,
            mode_category=mode_category,
        ):
            last_output = out
            yield out
        if last_output and last_output.text and tools:
            clean, tcs = self._parse_tool_calls(last_output.text)
            if tcs:
                last_output.candidates[last_output.chosen]._tool_calls = tcs
                last_output.candidates[last_output.chosen].text = clean
        if last_output:
            self.last_output = last_output

    def choose_candidate(self, index):
        if not self.last_output:
            raise ValueError('No response yet.')
        if index < 0 or index >= len(self.last_output.candidates):
            raise ValueError('Invalid candidate index.')
        self.rcid = self.last_output.candidates[index].rcid
        self.last_output.chosen = index

    async def delete(self):
        if self.cid:
            await self.client.delete_chat(self.cid)

    # camelCase aliases
    generateContent = generate_content
    generateContentStream = generate_content_stream
    chooseCandidate = choose_candidate
