# -*- coding: utf-8 -*-
import re

from datatypes import (
    Command,
    Host,
)

from endpoints.config import environ

from . import _HTTPTestCase, _WebSocketTestCase


class Server(Command):
    """
    https://github.com/django/daphne
    """
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

        if host:
            self.host = Host(host)
            cmd_host = self.host.hostname
            cmd_port = self.host.port

        else:
            cmd_host = "0.0.0.0"
            cmd_port = "4000"
            self.host = Host(cmd_host, cmd_port).client()

        app_path = f"{self.controller_prefix}:application"
        super().__init__(
            [
                "uvicorn",
                "--host", cmd_host,
                "--port", cmd_port,
                "--factory",
                app_path,
            ],
            #f"daphne -b {cmd_host} -p {cmd_port} -v 3 {app_path}",
            #f"uvicorn --host {cmd_host} --port {cmd_port} --factory {app_path}",
            **kwargs
        )

    def start(self, **kwargs):
        super().start(**kwargs)

        # daphne: Listening on TCP address 0.0.0.0:4000
        # uvicorn: Uvicorn running on http://0.0.0.0:4000 (Press CTRL+C to quit)

        regex = re.compile(r"Uvicorn\s+running")
        r = self.wait_for(regex)


class HTTPTest(_HTTPTestCase):
    server_class = Server


class WebSocketTest(_WebSocketTestCase):
    server_class = Server

