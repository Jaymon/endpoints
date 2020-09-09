# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import sys
import subprocess

from ...compat import *
from ...utils import String, Path
from ..client import WebServer as BaseWebServer


class WebServer(BaseWebServer):

    process_count = 1

    host_regex = r"bound\s+to\s+TCP\s+address\s+(([^:]+):(\d+))"

    def get_plugins(self):
        vi = sys.version_info

        bp = subprocess.check_output(["which", "uwsgi"]).strip()
        plugins_dir = Path(bp).resolve().parent

        return [
            "--plugins-dir", plugins_dir,
            "--autoload",
            "--plugin", "python",
            "--plugin", "python{}{}".format(vi.major, vi.minor),
        ]

    def get_start_cmd(self):
        cmd = [
            "uwsgi",
        ]

        cmd.extend(self.get_plugins())

        cmd.extend([
            "--need-app",
            "--show-config",
            "--plugin-list",
            #"--master",
            "--processes", str(self.process_count),
            "--cpu-affinity", "1",
            "--thunder-lock",
            "--http-raw-body",
            "--chdir", self.cwd,
        ])

        if "VIRTUAL_ENV" in os.environ:
            cmd.extend(["--virtualenv", os.environ["VIRTUAL_ENV"]])

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


class WebsocketServer(WebServer):

    async_process_count = 50

    def get_plugins(self):
        ret = super(WebsocketServer, self).get_plugins()

        vi = sys.version_info
        ret.extend([
            "--plugin", "gevent",
            "--plugin", "gevent{}{}".format(vi.major, vi.minor),
        ])

        return ret

    def get_start_cmd(self):
        cmd = super(WebsocketServer, self).get_start_cmd()
        cmd.extend([
            "--http-websockets",
            "--gevent", String(self.async_process_count),
        ])
        return cmd

