import httpx
import re
from urllib.parse import urlparse
from ..constants import Endpoint, Headers
from ..errors import AuthError


def cookie_str(cookies):
    return '; '.join(f'{k}={v}' for k, v in cookies.items())


def parse_cookies(headers, base=None):
    out = dict(base or {})
    raw = headers.get('set-cookie') or ''
    if isinstance(raw, str):
        for part in raw.split(','):
            p = part.split(';')[0].strip()
            if '=' in p:
                k, v = p.split('=', 1)
                out[k.strip()] = v.strip()
    elif isinstance(raw, (list, tuple)):
        for s in raw:
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
