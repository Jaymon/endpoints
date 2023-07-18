# -*- coding: utf-8 -*-

from endpoints.interface.asgi.server import Server
from endpoints.interface.asgi import Application
#from endpoints.interface.asgi
from . import WebTestCase


class ApplicationTest(WebTestCase):
    server_class = Server
    application_class = Application


# class WebServerTest(WebServerTestCase):
#     server_class = WebServer

