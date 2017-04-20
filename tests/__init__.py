# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from unittest import TestCase as BaseTestCase, skipIf, SkipTest
import os
import sys
import logging

import testdata

from endpoints.interface import BaseServer


os.environ.setdefault("ENDPOINTS_HOST", "localhost:8080")


#logging.basicConfig()
logging.basicConfig(format="[%(levelname).1s] %(message)s", level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger(__name__)

# logger = logging.getLogger()
# logger.setLevel(logging.DEBUG)
# log_handler = logging.StreamHandler(stream=sys.stderr)
# log_formatter = logging.Formatter('[%(levelname)s] %(message)s')
# log_handler.setFormatter(log_formatter)
# logger.addHandler(log_handler)


class Server(BaseServer):
    """This is just a wrapper to get access to the Interface handling code"""
    def __init__(self, controller_prefix, contents):
        super(Server, self).__init__(
            controller_prefix=controller_prefix,
        )

        if isinstance(contents, dict):
            d = {}
            for k, v in contents.items():
                if k:
                    d[".".join([controller_prefix, k])] = v
                else:
                    d[controller_prefix] = v
            self.controllers = testdata.create_modules(d)

        else:
            self.controller = testdata.create_module(controller_prefix, contents=contents)

    def create_request(self, path):
        req = self.request_class()
        req.method = self.method.upper()

        version = self.kwargs.pop("version", None)
        if version is not None:
            req.set_header('Accept', '*/*;version={}'.format(version))

        for k, v in self.kwargs.items():
            setattr(req, k, v)

        req.path = path
        return req

    def handle(self, path, method="GET", **kwargs):
        """This isn't technically needed but just makes it explicit you pass in the
        path you want and this will translate that and handle the request

        :param path: string, full URI you are requesting (eg, /foo/bar)
        """
        self.method = method
        self.kwargs = kwargs
        c = self.create_call(path)
        c.handle()
        return c.response


class TestCase(BaseTestCase):
    def get_host(self):
        return os.environ.get("ENDPOINTS_HOST")

