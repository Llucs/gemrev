import time
import html


def decode_html(s):
    if not s:
        return s
    s = html.unescape(s)
    return s


class Candidate:
    def __init__(self, rcid='', index=0, text='', text_delta=None,
                 thoughts=None, thoughts_delta=None,
                 web_images=None, generated_images=None,
                 generated_videos=None, generated_media=None,
                 deep_research_plan=None, done=False):
        self.index = index
        self.rcid = rcid
        self.text = decode_html(text)
        self.text_delta = text_delta
        self.thoughts = decode_html(thoughts) if thoughts else None
        self.thoughts_delta = thoughts_delta
        self.web_images = web_images or []
        self.generated_images = generated_images or []
        self.generated_videos = generated_videos or []
        self.generated_media = generated_media or []
        self.deep_research_plan = deep_research_plan
        self.done = done
        self._tool_calls = None

    @property
    def images(self):
        return self.web_images + self.generated_images

    @property
    def videos(self):
        return self.generated_videos

    @property
    def media(self):
        return self.generated_media

    def __str__(self):
        return self.text


class ModelOutput:
    def __init__(self, metadata, candidates, chosen=0, model='', gem=None):
        if isinstance(metadata, (list, tuple)):
            self.cid = metadata[0] if len(metadata) > 0 else ''
            self.rid = metadata[1] if len(metadata) > 1 else ''
        else:
            self.cid = ''
            self.rid = ''
        self.model = model
        self.gem = gem
        self.created = int(time.time() * 1000)
        self.candidates = candidates
        self.chosen = chosen
        self._metadata = metadata

    @property
    def rcid(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.rcid if c else ''

    @property
    def done(self):
        return len(self.candidates) > 0 and all(c.done for c in self.candidates)

    @property
    def text(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.text if c else ''

    @property
    def text_delta(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.text_delta if c else ''

    @property
    def thoughts(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.thoughts if c else None

    @property
    def thoughts_delta(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.thoughts_delta if c else ''

    @property
    def images(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.images if c else []

    @property
    def videos(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.videos if c else []

    @property
    def media(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.media if c else []

    @property
    def deep_research_plan(self):
        c = self.candidates[self.chosen] if self.candidates else None
        return c.deep_research_plan if c else None

    @property
    def metadata(self):
        return self._metadata

    @metadata.setter
    def metadata(self, v):
        self._metadata = v

    async def save_all(self, path='temp', verbose=False):
        c = self.candidates[self.chosen] if self.candidates else None
        if not c:
            return {'images': [], 'videos': [], 'media': []}
        import asyncio
        images = await asyncio.gather(*[img.save(path=path, verbose=verbose) for img in c.images])
        videos = await asyncio.gather(*[vid.save(savePath=path, verbose=verbose) for vid in c.videos])
        media = await asyncio.gather(*[m.save(savePath=path, verbose=verbose) for m in c.media])
        return {'images': images, 'videos': videos, 'media': media}

    def __str__(self):
        return self.text
