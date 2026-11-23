"""Vercel Python Function entry point.

The browser UI and API share one request handler. Vercel invokes this class per
request instead of running the local ThreadingHTTPServer from app.server.
"""
from app.server import Handler


class handler(Handler):
    pass
