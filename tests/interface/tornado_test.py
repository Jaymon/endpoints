# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from endpoints.interface.tornado.client import WebServer, WebsocketServer
from . import WebTestCase, WebsocketTestCase, WebServerTestCase


class WebTest(WebTestCase):
    server_class = WebServer


class WebsocketTest(WebsocketTestCase):
    server_class = WebsocketServer


class WebServerTest(WebServerTestCase):
    server_class = WebServer


del WebTestCase
del WebsocketTestCase
del WebServerTestCase

