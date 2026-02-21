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
        if host:
            self.host = Host(host)

        else:
            self.host = Host("0.0.0.0", "4000").client()

        app_path = f"{self.controller_prefix}:application"

        cmd = [
            "--host", str(self.host),
            "--prefix", self.controller_prefix,
            app_path,
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


class HTTPTest(_HTTPTestCase):
    server_class = Server

