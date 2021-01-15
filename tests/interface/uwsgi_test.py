# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

import testdata

from endpoints.compat import *
from endpoints.interface.uwsgi.client import WebServer, WebsocketServer
from . import WebTestCase, WebServerTestCase, WebsocketTestCase


class WebTest(WebTestCase):

    server_class = WebServer

    def create_server(self, contents, config_contents='', **kwargs):
        config_contents = [
            "import os",
            "import sys",
            "import logging",
            "logging.basicConfig(",
            "    format=\"[%(levelname).1s] %(message)s\",",
            "    level=logging.DEBUG,",
            "    stream=sys.stdout",
            ")",
            "",
            "from endpoints.interface.uwsgi import Application",
            ""
            "##############################################################",
            config_contents if isinstance(config_contents, basestring) else "\n".join(config_contents),
            "##############################################################",
            "application = Application()",
            ""
        ]

        return super(WebTest, self).create_server(
            contents=contents,
            config_contents=config_contents,
        )


class WebsocketTest(WebsocketTestCase):
    server_class = WebsocketServer

    def create_server(self, contents, config_contents='', **kwargs):
        config_contents = [
            "import os",
            "import sys",
            "import logging",
            "logging.basicConfig(",
            "    format=\"[%(levelname).1s] %(message)s\",",
            "    level=logging.DEBUG,",
            "    stream=sys.stdout",
            ")",
            "",
            #"import gevent",
            #"import gevent.monkey",
            #"if not gevent.monkey.saved:",
            #"    gevent.monkey.patch_all()",
            "",
            "from endpoints.interface.uwsgi.gevent import WebsocketApplication as Application",
            "",
            "##############################################################",
            config_contents if isinstance(config_contents, basestring) else "\n".join(config_contents),
            "##############################################################",
            "application = Application()",
            ""
        ]

        return super(WebsocketTest, self).create_server(
            contents=contents,
            config_contents=config_contents,
        )


class WebServerTest(WebServerTestCase, WebTest):
    pass


del WebTestCase
del WebsocketTestCase
del WebServerTestCase

