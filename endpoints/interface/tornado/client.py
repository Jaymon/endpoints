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
from ..wsgi.client import WSGIServer


class WebServer(WSGIServer):
    """This "client" is handy to get a simple wsgi server up and running

    it is mainly handy for testing purposes, we found that we were copy/pasting
    basically the same code to test random services and so it seemed like a good
    idea to move the base code into endpoints so all our projects could share it.

    example --

        server = WSGIServer("foo.bar")
        server.start()
    """
    def get_start_cmd(self):
        interface = ".".join(__name__.split(".")[:-1])
        cmd = [
            "python",
            "-m",
            __name__.split(".")[0],
            "--host", self.host.netloc,
            "--prefix", self.controller_prefix,
            "--interface", interface
        ]

        return cmd



