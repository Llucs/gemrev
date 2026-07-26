class ToolDefinition:
    def __init__(self, name='', description='', parameters=None):
        self.name = name
        self.description = description
        self.parameters = parameters or {}

    @classmethod
    def from_dict(cls, d):
        fn = d
        if isinstance(d, dict) and d.get('type') == 'function':
            fn = d.get('function', d)
        if isinstance(d, dict) and 'function' in d:
            fn = d['function']
        return cls(
            name=fn.get('name', '') if isinstance(fn, dict) else '',
            description=fn.get('description', '') if isinstance(fn, dict) else '',
            parameters=fn.get('parameters', {}) if isinstance(fn, dict) else {},
        )

    def to_dict(self):
        return {
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters,
        }


class ToolCall:
    def __init__(self, id='', name='', arguments=None):
        self.id = id
        self.name = name
        self.arguments = arguments or {}

    def to_dict(self):
        return {
            'id': self.id,
            'type': 'function',
            'function': {
                'name': self.name,
                'arguments': self.arguments,
            },
        }
