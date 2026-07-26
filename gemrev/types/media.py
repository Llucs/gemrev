import httpx
import os
import hashlib
import re
import time


def sanitize_filename(name, max_len=50):
    if not name:
        return ''
    name = re.sub(r'[^a-zA-Z0-9\s_-]', '', name)
    name = re.sub(r'\s+', '_', name)
    name = name[:max_len]
    return name.rstrip('_')


class Image:
    def __init__(self, url='', title='[Image]', alt='', proxy=None, client_ref=None):
        self.url = url
        self.title = title
        self.alt = alt
        self.proxy = proxy
        self.client_ref = client_ref

    def _get_url_for_hash(self):
        return self.url

    def __repr__(self):
        short = self.url if len(self.url) <= 20 else self.url[:8] + '...' + self.url[-12:]
        return f"Image(title='{self.title}', alt='{self.alt}', url='{short}')"

    async def save(self, path='temp', filename=None, verbose=False):
        if not filename or not os.path.splitext(filename)[1]:
            timestamp = time.strftime('%Y%m%d%H%M%S', time.gmtime())
            url_hash = hashlib.sha256(self._get_url_for_hash().encode()).hexdigest()[:10]
            base = os.path.splitext(filename)[0] if filename else (sanitize_filename(self.alt) or 'image')
            filename = f'{timestamp}_{url_hash}_{base}'
        os.makedirs(path, exist_ok=True)
        return await self._perform_save(path, filename, verbose)

    async def _perform_save(self, save_path, filename, verbose):
        img_url = self.url
        proxy_url = self.proxy
        cookie_str = ''
        if self.client_ref:
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.client_ref.cookies.items())

        async with httpx.AsyncClient(
            headers={
                'Origin': 'https://gemini.google.com',
                'Referer': 'https://gemini.google.com/',
                **({'Cookie': cookie_str} if cookie_str else {}),
            },
            follow_redirects=True,
            proxy=proxy_url,
        ) as client:
            res = await client.get(img_url)

        if verbose:
            print(f'HTTP Request: GET {img_url} [{res.status_code}]')
        if res.status_code != 200:
            raise ValueError(f'Error downloading image: {res.status_code}')

        content_type = res.headers.get('content-type', '').split(';')[0].strip().lower()
        ext = os.path.splitext(filename)[1]
        if not ext:
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'webp' in content_type:
                ext = '.webp'
            elif 'gif' in content_type:
                ext = '.gif'
            else:
                ext = '.png'
            filename += ext

        dest = os.path.join(save_path, filename)
        with open(dest, 'wb') as f:
            f.write(res.content)
        if verbose:
            print(f'Image saved as {os.path.abspath(dest)}')
        return os.path.abspath(dest)


class WebImage(Image):
    def __init__(self, url='', title='[Image]', alt='', proxy=None, client_ref=None):
        super().__init__(url=url, title=title, alt=alt, proxy=proxy, client_ref=client_ref)


class GeneratedImage(Image):
    def __init__(self, url='', title='[Image]', alt='', proxy=None, client_ref=None,
                 cid='', rid='', rcid='', image_id=''):
        super().__init__(url=url, title=title, alt=alt, proxy=proxy, client_ref=client_ref)
        self.cid = cid
        self.rid = rid
        self.rcid = rcid
        self.image_id = image_id

    async def _perform_save(self, save_path, filename, verbose, full_size=True):
        if full_size:
            if self.client_ref and self.cid and self.rid and self.rcid and self.image_id:
                try:
                    original_url = await self.client_ref._get_full_size_image(
                        self.cid, self.rid, self.rcid, self.image_id
                    )
                    if original_url:
                        self.url = original_url
                        return await super()._perform_save(save_path, filename, verbose)
                except Exception as e:
                    if verbose:
                        print(f'Failed to fetch full size image via RPC: {e}, falling back.')
            if '=s1024-rj' in self.url:
                self.url = self.url.replace('=s1024-rj', '=s2048-rj')
            elif '=s2048-rj' not in self.url:
                self.url += '=s2048-rj'
        else:
            if '=s2048-rj' in self.url:
                self.url = self.url.replace('=s2048-rj', '=s1024-rj')
            elif '=s1024-rj' not in self.url:
                self.url += '=s1024-rj'
        return await super()._perform_save(save_path, filename, verbose)

    async def save(self, path='temp', filename=None, verbose=False, full_size=True):
        if not filename or not os.path.splitext(filename)[1]:
            timestamp = time.strftime('%Y%m%d%H%M%S', time.gmtime())
            url_hash = hashlib.sha256(self._get_url_for_hash().encode()).hexdigest()[:10]
            base = os.path.splitext(filename)[0] if filename else (sanitize_filename(self.alt) or 'generated_image')
            filename = f'{timestamp}_{url_hash}_{base}'
        os.makedirs(path, exist_ok=True)
        return await self._perform_save(path, filename, verbose, full_size)


class Video:
    def __init__(self, url='', title='[Video]', proxy=None, client_ref=None):
        self.url = url
        self.title = title
        self.proxy = proxy
        self.client_ref = client_ref
        self._default_filename_suffix = 'video'

    def _get_url_for_hash(self):
        return self.url

    def __repr__(self):
        return f'Video(title={self.title}, url={self.url})'

    async def save(self, savePath='temp', filename=None, verbose=False):
        if not filename or not os.path.splitext(filename)[1]:
            timestamp = time.strftime('%Y%m%d%H%M%S', time.gmtime())
            url_hash = hashlib.sha256(self._get_url_for_hash().encode()).hexdigest()[:10]
            base = os.path.splitext(filename)[0] if filename else self._default_filename_suffix
            filename = f'{timestamp}_{url_hash}_{base}'
        os.makedirs(savePath, exist_ok=True)
        return await self._perform_save(savePath, filename, verbose)

    async def _perform_save(self, save_path, filename, verbose):
        file_path = await self._download_file(self.url, save_path, filename, '.mp4', verbose)
        return {'video': file_path, 'video_thumbnail': None}

    async def _download_file(self, url, save_path, filename, default_ext='.mp4', verbose=False):
        proxy_url = self.proxy
        cookie_str = ''
        if self.client_ref:
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.client_ref.cookies.items())

        async with httpx.AsyncClient(
            headers={
                'Origin': 'https://gemini.google.com',
                'Referer': 'https://gemini.google.com/',
                **({'Cookie': cookie_str} if cookie_str else {}),
            },
            proxy=proxy_url,
        ) as client:
            res = await client.get(url)

        if verbose:
            print(f'HTTP Request: GET {url} [{res.status_code}]')

        if res.status_code == 200:
            content_type = res.headers.get('content-type', '').split(';')[0].strip().lower()
            ext_map = {
                'mp4': '.mp4', 'mp3': '.mp3', 'mpeg': '.mp3',
                'jpeg': '.jpg', 'png': '.png', 'webm': '.webm'
            }
            ext = default_ext
            for ct_key, ct_ext in ext_map.items():
                if ct_key in content_type:
                    ext = ct_ext
                    break

            if not os.path.splitext(filename)[1]:
                filename += ext
            dest = os.path.join(save_path, filename)
            with open(dest, 'wb') as f:
                f.write(res.content)
            if verbose:
                print(f'File saved as {os.path.abspath(dest)}')
            return os.path.abspath(dest)
        elif res.status_code == 206:
            return '206'
        else:
            raise ValueError(f'Error downloading file: {res.status_code}')


class GeneratedVideo(Video):
    def __init__(self, url='', thumbnail=None, cid='', rid='', rcid='',
                 client_ref=None, proxy=None):
        super().__init__(url=url, title='[Generated Video]', proxy=proxy, client_ref=client_ref)
        self.thumbnail = thumbnail
        self.cid = cid
        self.rid = rid
        self.rcid = rcid
        self._default_filename_suffix = 'generated_video'

    async def _perform_save(self, save_path, filename, verbose):
        video_path = await self._poll_download(self.url, save_path, filename, '.mp4', verbose, 'video')
        thumb_path = None
        if self.thumbnail:
            thumb_path = await self._download_thumbnail(self.thumbnail, save_path, filename + '_thumb', verbose)
        return {'video': video_path, 'video_thumbnail': thumb_path}

    async def _poll_download(self, url, save_path, filename, ext, verbose, key):
        while True:
            file_path = await self._download_file(url, save_path, filename, ext, verbose)
            if file_path == '206':
                if verbose:
                    print(f'Media ({key}) still generating (206), retrying in 10s...')
                await asyncio_sleep(10)
            else:
                return file_path

    async def _download_thumbnail(self, url, save_path, filename, verbose):
        try:
            file_path = await self._download_file(url, save_path, filename, '.jpg', verbose)
            return file_path if file_path != '206' else None
        except Exception as e:
            if verbose:
                print(f'Failed to save thumbnail: {e}')
            return None


class GeneratedMedia(Video):
    def __init__(self, url='', thumbnail=None, mp3_url='', mp3_thumbnail=None,
                 cid='', rid='', rcid='', client_ref=None, proxy=None):
        super().__init__(url=url, title='[Generated Media]', proxy=proxy, client_ref=client_ref)
        self.thumbnail = thumbnail
        self.mp3_url = mp3_url
        self.mp3_thumbnail = mp3_thumbnail
        self.cid = cid
        self.rid = rid
        self.rcid = rcid
        self._default_filename_suffix = 'generated_media'

    async def _perform_save(self, save_path, filename, verbose):
        import asyncio
        tasks = []
        if self.url:
            tasks.append(self._poll_download(self.url, save_path, filename, '.mp4', verbose, 'mp4'))
        if self.mp3_url:
            tasks.append(self._poll_download(self.mp3_url, save_path, filename, '.mp3', verbose, 'mp3'))

        results = await asyncio.gather(*tasks)
        out = {'mp4': None, 'mp3': None, 'mp4_thumbnail': None, 'mp3_thumbnail': None}
        idx = 0
        if self.url:
            out['mp4'] = results[idx]
            idx += 1
        if self.mp3_url:
            out['mp3'] = results[idx]
            idx += 1

        thumb_tasks = []
        if self.thumbnail:
            thumb_tasks.append(self._download_thumbnail(self.thumbnail, save_path, filename + '_mp4_thumb', verbose))
        if self.mp3_thumbnail:
            thumb_tasks.append(self._download_thumbnail(self.mp3_thumbnail, save_path, filename + '_mp3_thumb', verbose))
        if thumb_tasks:
            thumb_results = await asyncio.gather(*thumb_tasks)
            ti = 0
            if self.thumbnail:
                out['mp4_thumbnail'] = thumb_results[ti]
                ti += 1
            if self.mp3_thumbnail:
                out['mp3_thumbnail'] = thumb_results[ti]
        return out

    async def _poll_download(self, url, save_path, filename, ext, verbose, key):
        while True:
            file_path = await self._download_file(url, save_path, filename, ext, verbose)
            if file_path == '206':
                if verbose:
                    print(f'Media ({key}) still generating (206), retrying in 10s...')
                await asyncio_sleep(10)
            else:
                return file_path

    async def _download_thumbnail(self, url, save_path, filename, verbose):
        try:
            file_path = await self._download_file(url, save_path, filename, '.jpg', verbose)
            return file_path if file_path != '206' else None
        except Exception as e:
            if verbose:
                print(f'Failed to save thumbnail: {e}')
            return None

    def __repr__(self):
        urls = []
        if self.url:
            urls.append(f'mp4={self.url}')
        if self.mp3_url:
            urls.append(f'mp3={self.mp3_url}')
        return f"GeneratedMedia(title={self.title}, urls={', '.join(urls)})"


def asyncio_sleep(seconds):
    import asyncio
    return asyncio.sleep(seconds)
