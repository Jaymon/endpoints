# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from endpoints.interface.wsgi.client import WebServer
from . import WebTestCase, WebServerTestCase


class WebTest(WebTestCase):
    server_class = WebServer


class WebServerTest(WebServerTestCase):
    server_class = WebServer


del WebTestCase
del WebServerTestCase

