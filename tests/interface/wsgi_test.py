# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import re

from datatypes import ModuleCommand, Host

#from endpoints.interface.wsgi.client import WebServer
from . import _HTTPTestCase
from endpoints.config import environ


class Server(ModuleCommand):
    @property
    def environ(self):
        env = super().environ
        for env_name in environ.get_prefix_names("ENDPOINTS_PREFIX"):
            env.pop(env_name)
        env["ENDPOINTS_PREFIX"] = self.controller_prefix
        return env

    def __init__(self, controller_prefix, host="", **kwargs):
        self.controller_prefix = controller_prefix
        if not host:
            host = environ.HOST
        self.host = Host(host) if host else None

        cmd_host = "0.0.0.0:4000"
        if self.host:
            cmd_host = self.host.netloc

        cmd = [
            "--host", cmd_host,
            "--prefix", self.controller_prefix,
            "--server", "endpoints.interface.wsgi:Server",
        ]

        super().__init__(
            "endpoints",
            command=cmd,
            **kwargs
        )

    def start(self, **kwargs):
        super().start(**kwargs)

        regex = re.compile(r"Listening\s+on\s+(([^:]+):(\d+))")
        r = self.wait_for(regex)
        m = regex.search(r)
        self.host = Host(m.group(2), m.group(3)).client()


class HTTPTest(_HTTPTestCase):
    server_class = Server

#     def test_foo(self):
#         from datatypes import ReflectName
# 
#         s = ReflectName("endpoints.interface.wsgi:Server")
#         pout.v(s.module_name, s.class_name)
# 
#         c = s.get_class()
#         pout.v(c)
#         c.start()

