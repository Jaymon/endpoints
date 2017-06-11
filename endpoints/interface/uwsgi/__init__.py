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
from ...http import ResponseBody


class Payload(object):
    def __init__(self, raw=None, **kwargs):
        self.uuid = None

        if raw:
            self.loads(raw)
        else:
            self.dumps(**kwargs)

    def dumps(self, **kwargs):

        for k in ["path", "body"]:
            if k not in kwargs:
                raise ValueError("[{}] is required".format(k))

        if "meta" not in kwargs:
            kwargs["meta"] = {}

        if "method" not in kwargs and "code" not in kwargs:
            raise ValueError("one of [method, code] is required")

        kwargs["payload"] = json.dumps(kwargs, cls=ResponseBody)

        for k, v in kwargs.items():
            setattr(self, k, v)

    def loads(self, raw):
        kwargs = json.loads(raw)

        for k, v in kwargs.items():
            setattr(self, k, v)


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


