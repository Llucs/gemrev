import httpx
import re
from ..constants import Endpoint, Headers
from ..errors import AuthError


def cookie_str(cookies):
    return '; '.join(f'{k}={v}' for k, v in cookies.items())


def _split_set_cookie_header(raw):
    """Split a concatenated Set-Cookie header into individual cookie strings.

    A comma inside a cookie value would naïvely break ``raw.split(',')``, but
    cookies can contain a comma inside ``Expires=Wed, 21-Oct-2025 ...``. We
    use the heuristic that a new cookie starts right after ``;`` (or after the
    Expires value). See RFC 6265: cookies are separated by ``, `` but a comma
    preceded by a digit/month inside an Expires attribute is part of the date.
    """
    if not raw:
        return []
    # A robust approach: split on commas followed by a cookie name pattern
    # ("name="). Keeps dates intact because dates contain ", " followed by
    # anything but "<name>=".
    parts = []
    buffer = ''
    i = 0
    n = len(raw)
    while i < n:
        comma_pos = raw.find(',', i)
        if comma_pos == -1:
            buffer += raw[i:]
            break
        # look-ahead: is the segment after the comma a new "<name>=" cookie?
        next_segment = raw[comma_pos + 1:].lstrip()
        # A cookie name typically starts with a token char and is followed by '='
        # within a few characters. Expires dates contain ", HH:MM:SS" or
        # similar (no '=' shortly after).
        equals_pos = next_segment.find('=')
        semicolon_pos = next_segment.find(';')
        # if equal sign comes before any semicolon and reasonably close, treat
        # comma as a separator
        if (equals_pos != -1 and (semicolon_pos == -1 or equals_pos < semicolon_pos)
                and equals_pos < 64 and re.match(r'[A-Za-z0-9_\-+.]+', next_segment)):
            buffer += raw[i:comma_pos]
            if buffer.strip():
                parts.append(buffer)
            buffer = ''
            i = comma_pos + 1
        else:
            # comma is inside a value (e.g. date) — keep it
            buffer += raw[i:comma_pos + 1]
            i = comma_pos + 1
    if buffer.strip():
        parts.append(buffer)
    return parts


def parse_cookies(headers, base=None):
    out = dict(base or {})
    raw = headers.get('set-cookie') or ''
    if isinstance(raw, str):
        cookie_strs = _split_set_cookie_header(raw)
    elif isinstance(raw, (list, tuple)):
        cookie_strs = list(raw)
    else:
        cookie_strs = []
    for s in cookie_strs:
        p = s.split(';')[0].strip()
        if '=' in p:
            k, v = p.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def parse_proxy(proxy_str):
    if not proxy_str:
        return None
    return proxy_str


async def send_init_request(cookies, proxy=None):
    client_kwargs = {
        'headers': {**Headers.GEMINI, 'Cookie': cookie_str(cookies)},
        'follow_redirects': True,
    }
    p = parse_proxy(proxy)
    if p:
        client_kwargs['proxy'] = p

    async with httpx.AsyncClient(**client_kwargs) as client:
        res = await client.get(Endpoint.INIT)

    t = res.text
    snlm0e = re.search(r'"SNlM0e":\s*"(.*?)"', t)
    cfb2h = re.search(r'"cfb2h":\s*"(.*?)"', t)
    fdrfje = re.search(r'"FdrFJe":\s*"(.*?)"', t)
    language = re.search(r'"TuX5cc":\s*"(.*?)"', t)
    push_id = re.search(r'"qKIAYe":\s*"(.*?)"', t)

    snlm0e_v = snlm0e.group(1) if snlm0e else None
    cfb2h_v = cfb2h.group(1) if cfb2h else None
    fdrfje_v = fdrfje.group(1) if fdrfje else None
    language_v = language.group(1) if language else None
    push_id_v = push_id.group(1) if push_id else None

    if not cfb2h_v and not fdrfje_v and not language_v:
        raise AuthError('Cookies invalid.')

    valid_cookies = parse_cookies(res.headers, cookies)
    return snlm0e_v, cfb2h_v, fdrfje_v, language_v, push_id_v, valid_cookies


async def get_access_token(base_cookies, proxy=None, verbose=False):
    extra_cookies = {}
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(Endpoint.GOOGLE)
        if r.status_code == 200:
            extra_cookies = parse_cookies(r.headers)
    except Exception:
        pass

    cookies = {**extra_cookies, **base_cookies}

    if '__Secure-1PSID' not in cookies:
        raise AuthError('__Secure-1PSID cookie required for authentication.')

    return await send_init_request(cookies, proxy)
