# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import codecs
import hashlib
import random
import os

import testdata

#from endpoints.compat.environ import *
#from endpoints.utils import ByteString
#from endpoints.interface.uwsgi.client import UWSGIServer, WebsocketClient, WebsocketServer
from endpoints.interface.tornado import Server

from . import TestCase

#from .wsgi_test import TestCase, WSGITest, WSGIServerTest


# class UWSGITest(WSGITest):
#     server_class = UWSGIServer
#     def create_server(self, controller_prefix, contents, config_contents='', **kwargs):
#         pass


class ServerTest(TestCase):
    def test_backend(self):
        modpath = testdata.create_module("foo", [
            "from endpoints import Controller",
            "from endpoints.decorators import param",
            "",
            "class Foo(Controller):",
            "    @param(0)",
            "    @param(1)",
            "    @param('bar', default='barkwarg')",
            "    @param('che')",
            "    def GET(self, *args, **kwargs): pass",
            "",
            "    @param(0)",
            "    @param('baz')",
            "    def POST(self, *args, **kwargs): pass",
            "",
            "class Bar(Controller):",
            "    @param('baz')",
            "    def POST(self, *args, **kwargs): pass",
            "",
            "class Baz(Controller):",
            "    @param(0, default='bazarg')",
            "    @param(1)",
            "    def POST(self, **kwargs): pass",
            "",
            "class Che(Controller):",
            "    def POST(self, *args, **kwargs): pass",
            "",
            "class Boom(Controller):",
            "    def POST(self): pass",
            "",
        ])

        pout.v(modpath, modpath.path)

        s = Server([modpath])
        s.backend



#del WSGITest
#del WSGIServerTest
