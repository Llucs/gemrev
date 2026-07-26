class ChatTurn:
    def __init__(self, role, text, model_output=None):
        self.role = role
        self.text = text
        self.model_output = model_output

    def __repr__(self):
        preview = (self.text[:100] + '...') if self.text and len(self.text) > 100 else (self.text or '')
        return f'{self.role.upper()}: {preview}'


class ChatHistory:
    def __init__(self, cid='', turns=None):
        self.cid = cid
        self.turns = turns or []

    def __repr__(self):
        return f'ChatHistory(cid={self.cid})'


class ChatInfo:
    def __init__(self, cid='', title='', is_pinned=False, timestamp=0):
        self.cid = cid
        self.title = title
        self.is_pinned = is_pinned
        self.timestamp = timestamp

    def __repr__(self):
        pin = '[Pinned] ' if self.is_pinned else ''
        title = self.title or f'Chat({self.cid})'
        from datetime import datetime
        dt = datetime.fromtimestamp(self.timestamp).isoformat() if self.timestamp else ''
        return f'{pin}{title} ({dt})'
