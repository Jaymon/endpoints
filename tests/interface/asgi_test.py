# -*- coding: utf-8 -*-
import re

from datatypes import (
    Command,
    Host,
)

from endpoints.interface.asgi import Application
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
        self.host = Host(host) if host else None

        cmd_host = "0.0.0.0"
        cmd_port = "4000"
        if self.host:
            cmd_host = self.host.hostname
            cmd_port = self.host.port

        #app_path = "endpoints.interface.asgi:Application.factory"
        app_path = f"{self.controller_prefix}:Application.factory"
        super().__init__(
            f"daphne -b {cmd_host} -p {cmd_port} -v 3 {app_path}",
            **kwargs
        )

    def start(self, **kwargs):
        super().start(**kwargs)

        regex = re.compile(r"Listening\s+on\s+TCP\s+address\s+(([^:]+):(\d+))")
        r = self.wait_for(regex)

        m = regex.search(r)
        if m:
            self.host = Host(m.group(2), m.group(3)).client()

        else:
            self.murder()
            self.start()


class HTTPTest(_HTTPTestCase):
    server_class = Server
    application_class = Application

    def test_response_body_error(self):
        s = self.create_server("""
            class Application(Application):
                sentinel = False
                @classmethod
                def dump_json(cls, body, **kwargs):
                    if cls.sentinel:
                       return super().dump_json(body, **kwargs)
                    cls.sentinel = True
                    raise ValueError()

            class Default(Controller):
                def GET(self): return 1
        """)
        c = self.create_client()

        r = c.get("/")
        self.assertEqual(500, r.code)
        self.assertEqual("", r.json())


class WebSocketTest(_WebSocketTestCase):
    server_class = Server
    application_class = Application

