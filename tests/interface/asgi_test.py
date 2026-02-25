# -*- coding: utf-8 -*-
import re

from datatypes import (
    Command,
    Host,
)

from endpoints.config import environ

from . import _HTTPTestCase, _WebSocketTestCase


from .. import Server
import uvicorn
from threading import Thread
import asyncio
import time

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
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.app_path,
                workers=1,
                host="0.0.0.0",
                port=4000,
                factory=True,
            ),
        )

        def target():
            asyncio.run(self.server.serve())

        self.thread = Thread(target=target)
        self.thread.daemon = True

        self.thread.start()

        #with pout.p("server starting"):
        while self.server.started is False:
            #pout.v("waiting for server to start")
            time.sleep(0.01)

    def stop(self, **kwargs):
        if self.server is not None:
            #with pout.p("server stopping"):
            self.server.should_exit = True
            self.thread.join()


# class XServer(Command):
#     """
#     https://github.com/django/daphne
#     """
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
# 
#         if not host:
#             host = environ.HOST
# 
#         if host:
#             self.host = Host(host)
#             cmd_host = self.host.hostname
#             cmd_port = self.host.port
# 
#         else:
#             cmd_host = "0.0.0.0"
#             cmd_port = "4000"
#             self.host = Host(cmd_host, cmd_port).client()
# 
#         self.wait_for_str = f"{cmd_host}:{cmd_port}"
#         app_path = f"{self.controller_prefix}:application"
# 
#         cmd = [
#             "uvicorn",
#             "--host", cmd_host,
#             "--port", cmd_port,
#             "--factory",
#             app_path,
#         ]
# 
#         # I can't get granian to cleanup correctly, it spawns a worker and
#         # a runtime thread, I think I would need to spend some time and 
#         # test sending the right signal
#         # python -B -Wdefault -c from multiprocessing.spawn import spawn_main;
#         # spawn_main(tracker_fd=6, pipe_handle=12) --multiprocessing-fork
#         # python -B -Wdefault -c from multiprocessing.resource_tracker import main;main(5)
#         #cmd = [
#         #    "granian",
#         #    "--host", cmd_host,
#         #    "--port", cmd_port,
#         #    "--factory",
#         #    "--ws",
#         #    "--interface", "asgi",
#         #    "--log-level", "debug",
#         #    "--runtime-mode", "st", # single-threaded
#         #    "--workers", "1",
#         #    #"--blocking-threads", "1",
#         #    "--runtime-threads", "1",
#         #    #"--no-respawn-failed-workers",
#         #    app_path,
#         #]
#         cmd = [
#             "granian",
#             "--host", cmd_host,
#             "--port", cmd_port,
#             "--factory",
#             "--ws",
#             "--interface", "asgi",
#             "--log-level", "debug",
#             "--runtime-mode", "st", # single-threaded
#             #"--workers", "1",
#             #"--blocking-threads", "1",
#             #"--runtime-threads", "1",
#             #"--no-respawn-failed-workers",
#             #"--backpressure", "1",
#             app_path,
#         ]
# 
# 
# 
#         # way slower than uvicorn for testing
#         #cmd = [
#         #    "hypercorn",
#         #    "--bind", f"{cmd_host}:{cmd_port}",
#         #    f"asgi:{app_path}",
#         #    "--workers", "0",
#         #]
#         xcmd = [
#             "hypercorn",
#             "--bind", f"{cmd_host}:{cmd_port}",
#             f"asgi:{app_path}",
#             "--workers", "0",
#         ]
# 
# 
#         #f"daphne -b {cmd_host} -p {cmd_port} -v 3 {app_path}",
# 
#         super().__init__(cmd, **kwargs)
# 
#     def start(self, **kwargs):
#         super().start(**kwargs)
# 
#         # daphne: Listening on TCP address 0.0.0.0:4000
#         # uvicorn: Uvicorn running on http://0.0.0.0:4000 (Press CTRL+C to quit)
#         # granian: Listening at: http://0.0.0.0:4000
#         # hypercorn: Running on http://0.0.0.0:4000
#         #regex = re.compile(r"{self.host[0]}:{self.host[1]}")
#         regex = re.compile(re.escape(self.wait_for_str))
#         #regex = re.compile(r"Uvicorn\s+running")
#         r = self.wait_for(regex)


class HTTPTest(_HTTPTestCase):
    server_class = Server


class WebSocketTest(_WebSocketTestCase):
    server_class = Server

