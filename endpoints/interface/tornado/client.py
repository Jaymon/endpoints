# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from ...compat.environ import *
from ..client import WebServer as BaseWebServer


class WebServer(BaseWebServer):
    def get_server_classpath(self):
        return ".".join(__name__.split(".")[:-1]) + ".Server"


class WebsocketServer(WebServer):
    def get_server_classpath(self):
        return ".".join(__name__.split(".")[:-1]) + ".WebsocketServer"


