import json
import re


FLICKER_ESC_RE = re.compile(r'\\+[`*_~].*$')
LENGTH_MARKER_RE = re.compile(r'^(\d+)\n')


def get_clean_text(s):
    if not s:
        return ''
    if s.endswith('\n```'):
        s = s[:-4]
    return FLICKER_ESC_RE.sub('', s)


def longest_common_subsequence_blocks(a, b):
    blocks = []
    if not a or not b:
        return blocks
    m, n = len(a), len(b)

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1

    i = j = 0
    while i < m and j < n:
        if a[i] == b[j]:
            size = 0
            ai_i, bj_j = i, j
            while i < m and j < n and a[i] == b[j]:
                i += 1
                j += 1
                size += 1
            if size > 0:
                blocks.append({'a': ai_i, 'b': bj_j, 'size': size})
        else:
            best_len = 0
            best_i, best_j = i + 1, j + 1
            for ni in range(i, min(i + 50, m)):
                for nj in range(j, min(j + 50, n)):
                    if dp[ni][nj] > best_len:
                        best_len = dp[ni][nj]
                        best_i, best_j = ni, nj
            i, j = best_i, best_j
    return blocks


def get_delta_by_fp_len(new_raw, last_sent_clean, is_final):
    new_c = new_raw if is_final else get_clean_text(new_raw)

    if new_c.startswith(last_sent_clean):
        return new_c[len(last_sent_clean):], new_c

    search_len = min(3000, max(1000, len(last_sent_clean)))
    actual_len = min(search_len, len(last_sent_clean), len(new_c))

    if actual_len == 0:
        return new_c, new_c

    tail_last = last_sent_clean[-actual_len:]
    tail_new = new_c[-actual_len:]

    blocks = longest_common_subsequence_blocks(tail_last, tail_new)
    if blocks:
        last_match = blocks[-1]
        match_end = last_match['b'] + last_match['size']
        return tail_new[match_end:], new_c

    blocks_all = longest_common_subsequence_blocks(last_sent_clean, new_c)
    if blocks_all:
        last_match = blocks_all[-1]
        match_end = last_match['b'] + last_match['size']
        return new_c[match_end:], new_c

    return new_c, new_c


def get_nested_value(data, path, default=None):
    cur = data
    for k in path:
        if cur is None:
            return default
        if isinstance(k, int):
            if not isinstance(cur, (list, tuple)):
                return default
            if k < -len(cur) or k >= len(cur):
                return default
            cur = cur[k if k >= 0 else len(cur) + k]
        else:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
    return cur if cur is not None else default


class StreamingFrameParser:
    def __init__(self):
        self.buffer = ''
        self.expected_units = None
        self.payload_start = 0
        self.scanned_chars = 0
        self.scanned_units = 0
        self.prefix_checked = False

    def reset(self):
        self.buffer = ''
        self._reset_frame_state()
        self.prefix_checked = False

    def feed(self, content):
        if not isinstance(content, str):
            raise TypeError(f'Expected str, got {type(content)}')
        if content:
            self.buffer += content
        self._strip_prefix_once()

        parsed = []
        while True:
            if self.expected_units is None:
                if not self._read_length_marker():
                    break
            if self.expected_units is None:
                break

            self._scan_available_payload()
            if self.scanned_units < self.expected_units:
                break

            end_pos = self.payload_start + self.scanned_chars
            chunk = self.buffer[self.payload_start:end_pos]
            self.buffer = self.buffer[end_pos:]
            self._reset_frame_state()

            if not chunk.strip():
                continue

            try:
                p = json.loads(chunk)
                if isinstance(p, list):
                    parsed.extend(p)
                else:
                    parsed.append(p)
            except (json.JSONDecodeError, ValueError):
                pass
        return parsed

    def flush(self):
        return self.feed('')

    def _reset_frame_state(self):
        self.expected_units = None
        self.payload_start = 0
        self.scanned_chars = 0
        self.scanned_units = 0

    def _strip_prefix_once(self):
        if self.prefix_checked:
            return
        prefix = ")]}'"
        if self.buffer.startswith(prefix):
            self.buffer = self.buffer[len(prefix):].lstrip()
        self.prefix_checked = True

    def _read_length_marker(self):
        pos = 0
        while pos < len(self.buffer) and self.buffer[pos].isspace():
            pos += 1
        if pos:
            self.buffer = self.buffer[pos:]
        if not self.buffer:
            return False

        m = LENGTH_MARKER_RE.match(self.buffer)
        if not m:
            return False

        len_str = m.group(1)
        self.expected_units = int(len_str)
        self.payload_start = len(len_str)
        self.scanned_chars = 0
        self.scanned_units = 0
        return True

    def _scan_available_payload(self):
        if self.expected_units is None:
            return
        idx = self.payload_start + self.scanned_chars
        limit = len(self.buffer)

        while self.scanned_units < self.expected_units and idx < limit:
            cp = ord(self.buffer[idx])
            u = 2 if cp > 0xFFFF else 1
            if self.scanned_units + u > self.expected_units:
                break
            self.scanned_units += u
            self.scanned_chars += 1
            idx += 1


def parse_response_by_frame(content):
    parser = StreamingFrameParser()
    frames = parser.feed(content)
    frames.extend(parser.flush())
    return frames, parser.buffer


def clean_gemini_text(text):
    text = re.sub(
        r'```(?:python|javascript|text)\?code_(?:reference|stdout)&code_event_index=\d+\n.*?```\n?',
        '', text, flags=re.DOTALL
    )
    return text.strip()


def extract_json_from_response(text):
    if not isinstance(text, str):
        raise TypeError(f'Expected str, got {type(text)}')
    parser = StreamingFrameParser()
    result = parser.feed(text)
    result.extend(parser.flush())
    if result:
        return result

    c = text[4:].lstrip() if text.startswith(")]}'") else text.strip()
    try:
        p = json.loads(c.strip())
        return p if isinstance(p, list) else [p]
    except (json.JSONDecodeError, ValueError):
        pass

    lines = []
    for line in c.strip().split('\n'):
        try:
            p = json.loads(line.strip())
            if isinstance(p, list):
                lines.extend(p)
            elif isinstance(p, dict):
                lines.append(p)
        except (json.JSONDecodeError, ValueError):
            pass
    if lines:
        return lines
    raise ValueError('Could not find valid JSON in response.')
