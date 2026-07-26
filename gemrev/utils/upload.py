import httpx
import os
import mimetypes
from ..constants import Endpoint, Headers


def generate_random_name(ext='.txt'):
    import random
    return f'input_{random.randint(1000000, 9999999)}{ext}'


def parse_file_name(file):
    if isinstance(file, str):
        fp = os.path.abspath(file)
        if not os.path.exists(fp):
            raise ValueError(f'{fp} is not a valid file.')
        return os.path.basename(fp)
    if isinstance(file, bytes):
        return generate_random_name()
    return generate_random_name()


async def upload_file(file, proxy=None, push_id='', cookies=None):
    if isinstance(file, str):
        fp = os.path.abspath(file)
        if not os.path.exists(fp):
            raise ValueError(f'{fp} is not a valid file.')
        fname = os.path.basename(fp)
        with open(fp, 'rb') as f:
            content = f.read()
    elif isinstance(file, bytes):
        content = file
        fname = generate_random_name()
    else:
        raise ValueError(f'Unsupported file type: {type(file)}')

    content_type = mimetypes.guess_type(fname)[0] or 'application/octet-stream'

    cookie_str = '; '.join(f'{k}={v}' for k, v in (cookies or {}).items())

    headers = {
        **Headers.REFERER,
        **Headers.UPLOAD,
        'Push-ID': push_id,
    }
    if cookie_str:
        headers['Cookie'] = cookie_str

    files = {'file': (fname, content, content_type)}

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        proxy=proxy,
    ) as client:
        res = await client.post(Endpoint.UPLOAD, files=files)
        return res.text
