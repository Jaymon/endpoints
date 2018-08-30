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
from ...http import ResponseBody
from ..wsgi import Application
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


