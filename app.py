import os
import sys

from gemrev.api.server import app


if __name__ == '__main__':
    if app is None:
        print('Dependencies not installed.')
        print('Install: pip install fastapi uvicorn pydantic')
        sys.exit(1)

    try:
        from uvicorn import run
    except ImportError:
        print('uvicorn not installed. Install: pip install uvicorn')
        sys.exit(1)

    _port = int(os.environ.get('PORT', 8000))
    for _i, _a in enumerate(sys.argv):
        if _a == '--port' and _i + 1 < len(sys.argv):
            _port = int(sys.argv[_i + 1])
    run(app, host='0.0.0.0', port=_port, log_level='info')
