# -*- coding: utf-8 -*-

from endpoints.interface.asgi.server import Server
from endpoints.interface.asgi import Application
#from endpoints.interface.asgi
from . import HTTPTestCase, WebSocketTestCase


class HTTPApplicationTest(HTTPTestCase):
    server_class = Server
    application_class = Application


class WebSocketApplicationTest(WebSocketTestCase):
    server_class = Server
    application_class = Application

