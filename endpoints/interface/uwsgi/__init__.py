# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import json

logger = logging.getLogger(__name__)

try:
    import uwsgi
except ImportError:
    uwsgi = None

from ...compat.environ import *
from ...compat.imports import StringIO
from ...http import ResponseBody
from ..wsgi import Application as BaseApplication
from ...utils import String, ByteString


class Payload(object):
    @property
    def payload(self):
        #kwargs = {r[0]:r[1] for r in self.__dict__.items() if not r[0].startswith("_")}
        kwargs = self.__dict__
        return json.dumps(kwargs, cls=ResponseBody)

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

        #kwargs["payload"] = json.dumps(kwargs, cls=ResponseBody)

        for k, v in kwargs.items():
            setattr(self, k, v)

    def loads(self, raw):
        kwargs = json.loads(raw)
        kwargs.pop("payload", None)

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
        self._size = 0
        self._filled = False

    def _chunked_read(self):
        if self._filled: return 0

        size = 0
        try:
            chunk = String(uwsgi.chunked_read())
            #old_pos = self._body.pos
            old_pos = self._body.tell()
            self._body.write(chunk)
            #self._body.pos = old_pos
            self._body.seek(old_pos)
            size = len(chunk)

            if not size:
                #self._body.pos = 0
                #self._body.seek(0)
                self._filled = True
            else:
                self._size += size

        except IOError as e:
            raise IOError("Error reading chunk, is --http-raw-body enabled? Error: {}".format(e))

        return size

    def __iter__(self):
        yield self.readline()

    def read(self, size=-1):
        if not self._filled:
            while size < 0 or size > (self._size - self._body.tell()):
                chunk_size = self._chunked_read()
                if not chunk_size:
                    break

        ret = ByteString(self._body.read(size))

#         if self._body.tell() >= self._size:
#             self._body.seek(0)

        return ret

    def readline(self, size=-1):
        line = self._body.readline(size)
        if not line:
            chunk_size = self._chunked_read()
            if chunk_size:
                line = self._body.readline(size)

#         if self._body.tell() >= self._size:
#             self._body.seek(0)

        pout.v(line)
        return ByteString(line)

    def seek(self, *args, **kwargs):
        self._body.seek(*args, **kwargs)

    def tell(self):
        return self._body.tell()


class Application(BaseApplication):
    def handle_chunked_request(self, req):
        req.body_input = UWSGIChunkedBody()


