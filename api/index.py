from gemrev.api.server import app

try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    handler = app
