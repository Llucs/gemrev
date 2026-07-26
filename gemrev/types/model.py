from ..constants import build_model_header


class RPCData:
    def __init__(self, rpcid, payload, identifier='generic'):
        self.rpcid = rpcid
        self.payload = payload
        self.identifier = identifier

    def serialize(self):
        return [self.rpcid, self.payload, None, self.identifier]

    def __repr__(self):
        return f"RPCData(rpcid='{self.rpcid}', payload='{self.payload}', identifier='{self.identifier}')"


class AvailableModel:
    def __init__(self, model_id='', model_name='', display_name='', description='',
                 capacity=0, capacity_field=12, model_number=1, is_available=True):
        self.model_id = model_id
        self.model_name = model_name
        self.display_name = display_name
        self.description = description
        self.capacity = capacity
        self.capacity_field = capacity_field
        self.model_number = model_number
        self.is_available = is_available

    @property
    def model_header(self):
        # capacity_tail at index 11 in the JSON array must be a number (or null),
        # not a string — otherwise Google's API rejects the header.
        if self.capacity_field == 13:
            # Represented as two separate JSON values: null, <capacity>
            return build_model_header(self.model_id, None, self.model_number, capacity_tail_extra=self.capacity)
        return build_model_header(self.model_id, self.capacity, self.model_number)

    @property
    def advanced_only(self):
        return not (self.capacity == 1 and self.capacity_field == 12)

    def __repr__(self):
        return self.model_name or self.display_name or ''
