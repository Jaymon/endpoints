# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import json

try:
    from cstringio import StringIO
except ImportError:
    from StringIO import StringIO

logger = logging.getLogger(__name__)

try:
    import uwsgi
except ImportError:
    uwsgi = None

from ..wsgi import Application as BaseApplication


class Payload(object):
    def __init__(self, *args, **kwargs):
        payload = None
        path = None
        body = None

        if len(args) == 0:
            payload = kwargs.pop("payload", None)
            path = kwargs.pop("path", None)
            body = kwargs.pop("body", None)

        elif len(args) == 1:
            if "path" in kwargs:
                path = kwargs.pop("path")
                body = args[0]

            elif "body" in kwargs:
                path = args[0]
                body = kwargs.pop("body")

            else:
                payload = args[0]

        elif len(args) == 2:
            path = args[0]
            body = args[1]

        else:
            raise ValueError("Payload(path, body) or Payload(body)")

        if payload:
            path, body, kwargs = self.normalize_response(payload, **kwargs)

        else:
            payload = self.normalize_request(path, body, **kwargs)

        self.path = path
        self.body = body
        self.payload = payload
        self.kwargs = kwargs

    def normalize_request(self, path, body, **kwargs):
        payload = {
            "path": path,
            "body": body
        }
        payload.update(kwargs)
        return json.dumps(payload)

    def normalize_response(self, payload, **kwargs):
        d = json.loads(payload)
        path = d.pop("path")
        body = d.pop("body")
        return path, body, d



class UWSGIChunkedBody(object):
    """Micro-WSGI has support for chunked transfer encoding, this class is a small
    wrapper around uWSGI's chunked transfer mechanism so the rest of endpoints doesn't
    have to know anything about what uWSGI is doing under the hood.

    http://uwsgi-docs.readthedocs.org/en/latest/Chunked.html

    Right now, this is a resetting body, which means when it is done being read it
    will reset so it can be read again. Also, using StringIO means that the raw body
    gets stored for the life of the request, which is not memory efficient
    """

    def __init__(self):
        self._body = StringIO()

    def _chunked_read(self):
        size = 0
        try:
            chunk = uwsgi.chunked_read()
            old_pos = self._body.pos
            self._body.write(chunk)
            self._body.pos = old_pos
            size = len(chunk)

            if not size:
                self._body.pos = 0

        except IOError as e:
            raise IOError("Error reading chunk, is --http-raw-body enabled? Error: {}".format(e))

        return size

    def __iter__(self):
        yield self.readline()

    def read(self, size=-1):
        while size < 0 or size > (self._body.len - self._body.pos):
            chunk_size = self._chunked_read()
            if not chunk_size:
                break

        return self._body.read(size)

    def readline(self, size=0):
        line = self._body.readline(size)
        if not line:
            chunked_size = self._chunked_read()
            if chunked_size:
                line = self._body.readline(size)

        return line


class Application(BaseApplication):
    def handle_chunked_request(self, req):
        req.body_input = UWSGIChunkedBody()


