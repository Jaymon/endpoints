# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

import logging

from ...compat.environ import *
from ...utils import Path
from ..wsgi.client import WSGIServer


logger = logging.getLogger(__name__)


class UWSGIServer(WSGIServer):

    process_count = 1

    def __init__(self, *args, **kwargs):
        super(UWSGIServer, self).__init__(*args, **kwargs)

    def get_start_cmd(self):
        args = [
            "uwsgi",
            "--need-app",
            "--http", self.host.netloc,
            "--show-config",
            "--master",
            "--processes", str(self.process_count),
            "--cpu-affinity", "1",
            "--thunder-lock",
            "--http-raw-body",
            "--chdir", self.cwd,
        ]

        if self.wsgifile:
            args.extend([
                "--wsgi-file", Path(self.wsgifile),
            ])

        else:
            args.extend([
                #"--module", "endpoints.uwsgi:Application()",
                "--module", "{}:Application()".format(".".join(__name__.split(".")[0:-1])),
            ])

        return args


class WebsocketServer(UWSGIServer):
    gevent_process_count = 50
    def get_start_cmd(self):
        args = super(WebsocketServer, self).get_start_cmd()
        args.extend([
            "--http-websockets",
            "--gevent", str(self.gevent_process_count),
        ])
        return args

