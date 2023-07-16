# -*- coding: utf-8 -*-
import os
import re

from ...compat import *
from ..base import BaseApplication
#from ...http import Host
#from ...decorators import property
from ...utils import ByteString, String
from ... import environ


from datatypes import Command, Host
from datatypes import ModuleCommand




class Server(Command):
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

        app_path = "endpoints.interface.asgi:ApplicationFactory"
        super().__init__(
            f"daphne -b {cmd_host} -p {cmd_port} -v 3 {app_path}",
            **kwargs
        )

    def start(self, **kwargs):
        super().start(**kwargs)

        regex = re.compile(r"Listening\s+on\s+TCP\s+address\s+(([^:]+):(\d+))")
        r = self.wait_for(regex)
        m = regex.search(r)
        self.host = Host(m.group(2), m.group(3)).client()

#     def __init__(self, command, cwd="", environ=None, **kwargs):
# 
# 
#     def create_cmd(self, command, arg_str):
# 
# 
# 
#     def get_application_classpath(self):
#         return "endpoints.interface.asgi:Application"





