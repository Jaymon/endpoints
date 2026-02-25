# -*- coding: utf-8 -*-
import re

from datatypes import ModuleCommand, Host

from . import _HTTPTestCase
from endpoints.config import environ



from .. import Server
from threading import Thread
import time
from wsgiref.simple_server import make_server
from datatypes import ReflectName

class Server(Server):
    def __init__(self, controller_prefix: str, host: str = "", **kwargs):
        self.controller_prefix = controller_prefix
        self.app_path = f"{self.controller_prefix}:application"
        self.server = None

        if not host:
            host = environ.HOST

        if host:
            self.host = Host(host)
            cmd_host = self.host.hostname
            cmd_port = self.host.port

        else:
            cmd_host = "0.0.0.0"
            cmd_port = "4000"
            self.host = Host(cmd_host, cmd_port).client()

        #self.host = Host("0.0.0.0", 4000).client()

    def start(self):
        self.server = make_server("0.0.0.0", 4000, ReflectName(self.app_path).resolve())

        def target():
            self.server.serve_forever(0.1)

        self.thread = Thread(target=target)
        self.thread.daemon = True

        self.thread.start()

        #with pout.p("server starting"):
        while getattr(self.server, "server_address", None) is None:
            #pout.v("waiting for server to start")
            time.sleep(0.01)

    def stop(self, **kwargs):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()






# class XServer(ModuleCommand):
#     @property
#     def environ(self):
#         env = super().environ
#         for env_name in environ.get_prefix_names("ENDPOINTS_PREFIX"):
#             env.pop(env_name)
#         env["ENDPOINTS_PREFIX"] = self.controller_prefix
#         return env
# 
#     def __init__(self, controller_prefix, host="", **kwargs):
#         self.controller_prefix = controller_prefix
#         if host:
#             self.host = Host(host)
# 
#         else:
#             self.host = Host("0.0.0.0", "4000").client()
# 
#         app_path = f"{self.controller_prefix}:application"
# 
#         cmd = [
#             "--host", str(self.host),
#             "--prefix", self.controller_prefix,
#             app_path,
#         ]
# 
#         super().__init__(
#             "endpoints",
#             command=cmd,
#             **kwargs
#         )
# 
#     def start(self, **kwargs):
#         super().start(**kwargs)
# 
#         regex = re.compile(r"Listening\s+on\s+(([^:]+):(\d+))")
#         r = self.wait_for(regex)


class HTTPTest(_HTTPTestCase):
    server_class = Server

