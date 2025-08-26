# -*- coding: utf-8 -*-
import re

from datatypes import ModuleCommand, Host

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

#     def test_wsgi_headers(self):
#         """make sure request url gets controller_path correctly"""
#         server = self.create_server(contents=[
#             "class Default(Controller):",
#             "    def GET(self):",
#             "        return 1",
#             "",
#         ])
# 
#         c = self.create_client()
#         r = c.get("/")
#         pout.v(r.body)
# 
#         # 'GATEWAY_INTERFACE': str (7)
#         # 28040: ܁   ܁   ܁   "
#         # 28040: ܁   ܁   ܁   ܁   CGI/1.1
#         # 28040: ܁   ܁   'SERVER_SOFTWARE': str (14)
#         # 28040: ܁   ܁   ܁   "
#         # 28040: ܁   ܁   ܁   ܁   WSGIServer/0.2
#         # 28128: ܁   ܁   'wsgi.version': tuple (2)
#         # 28128: ܁   ܁   ܁   (
#         # 28128: ܁   ܁   ܁   ܁   0: 1,
#         # 28128: ܁   ܁   ܁   ܁   1: 0
#         # 28128: ܁   ܁   ܁   ),
