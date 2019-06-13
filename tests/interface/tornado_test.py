# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
#import codecs
#import hashlib
#import random
#import os

#import testdata

#from endpoints.compat.environ import *
#from endpoints.utils import ByteString
#from endpoints.interface.uwsgi.client import UWSGIServer, WebsocketClient, WebsocketServer
#from endpoints.interface.tornado import Server
from endpoints.interface.tornado.client import WebServer, WebsocketServer

#from . import TestCase

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

