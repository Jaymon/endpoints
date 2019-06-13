# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import threading
import os
import inspect
import subprocess
import time
import sys
from collections import deque

from ...compat.environ import *
from ...utils import Path, String
from ...http import Url
from ... import environ
from ...reflection import ReflectModule
from ..client import WebServer


class WebServer(WebServer):
    """This "client" is handy to get a simple wsgi server up and running

    it is mainly handy for testing purposes, we found that we were copy/pasting
    basically the same code to test random services and so it seemed like a good
    idea to move the base code into endpoints so all our projects could share it.

    example --

        server = WSGIServer("foo.bar")
        server.start()
    """
    def get_server_classpath(self):
        return ".".join(__name__.split(".")[:-1]) + ".Server"


class WebsocketServer(WebServer):
    def get_server_classpath(self):
        return ".".join(__name__.split(".")[:-1]) + ".WebsocketServer"


