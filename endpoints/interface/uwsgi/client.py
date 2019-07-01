# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from ...compat.environ import *
from ...utils import String, Path
from ..client import WebServer as BaseWebServer


class WebServer(BaseWebServer):

    process_count = 1

    host_regex = r"bound\s+to\s+TCP\s+address\s+(([^:]+):(\d+))"

    def get_start_cmd(self):
        cmd = [
            "uwsgi",
            "--need-app",
            "--show-config",
            "--master",
            "--processes", str(self.process_count),
            "--cpu-affinity", "1",
            "--thunder-lock",
            "--http-raw-body",
            "--chdir", self.cwd,
        ]

        if self.host:
            cmd.extend(["--http", self.host])
        else:
            cmd.extend(["--http-socket", "0.0.0.0:0"])

        if self.config_path:
            cmd.extend(['--wsgi-file', Path(self.config_path)])

        else:
            cmd.extend([
                "--module", "{}:Application()".format(".".join(__name__.split(".")[0:-1])),
            ])

        return cmd

#     def find_host(self):
#         host = super(WebServer, self).find_host()
#         pout.v(host)
#         return host


class WebsocketServer(WebServer):

    async_process_count = 50

    def get_start_cmd(self):
        cmd = super(WebsocketServer, self).get_start_cmd()
        cmd.extend([
            "--http-websockets",
            "--gevent", String(self.async_process_count),
        ])
        return cmd

