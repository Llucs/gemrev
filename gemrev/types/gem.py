class Gem:
    def __init__(self, id='', name='', description=None, prompt=None, predefined=False):
        self.id = id
        self.name = name
        self.description = description
        self.prompt = prompt
        self.predefined = predefined

    def __repr__(self):
        return f"Gem(id='{self.id}', name='{self.name}', predefined={self.predefined})"


class GemJar:
    def __init__(self, entries=None):
        self._store = {}
        if entries:
            for gid, gem in entries:
                self._store[gid] = gem

    def set(self, gid, gem):
        self._store[gid] = gem

    def get(self, id=None, name=None, default=None):
        if id is None and name is None:
            raise ValueError('At least one of gem id or name must be provided.')
        if id is not None:
            gem = self._store.get(id)
            if not gem:
                return default
            if name is not None:
                return gem if gem.name == name else default
            return gem
        for gem in self._store.values():
            if gem.name == name:
                return gem
        return default

    def filter(self, predefined=None, name=None):
        result = GemJar()
        for gid, gem in self._store.items():
            if predefined is not None and gem.predefined != predefined:
                continue
            if name is not None and gem.name != name:
                continue
            result.set(gid, gem)
        return result

    def values(self):
        return list(self._store.values())

    def keys(self):
        return list(self._store.keys())

    def entries(self):
        return list(self._store.items())

    def __iter__(self):
        return iter(self._store.values())

    def to_dict(self):
        return dict(self._store)
