class AuthError(Exception):
    pass

class APIError(Exception):
    pass

class GeminiError(Exception):
    pass

class UsageLimitExceeded(GeminiError):
    pass

class ModelInvalid(GeminiError):
    pass

class TemporarilyBlocked(GeminiError):
    pass
