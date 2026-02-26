# -*- coding: utf-8 -*-
from threading import Thread
import asyncio
import time

import uvicorn

from . import _HTTPTestCase, _WebSocketTestCase, Server


class Server(Server):
    def start(self):
        # https://github.com/Kludex/uvicorn/blob/main/uvicorn/server.py
        self.server = uvicorn.Server(
            # https://github.com/Kludex/uvicorn/blob/main/uvicorn/config.py
            uvicorn.Config(
                self.app_path,
                workers=1,
                host=self.server_host[0],
                port=self.server_host[1],
                factory=True,
            ),
        )

        def target():
            asyncio.run(self.server.serve())

        self.thread = Thread(target=target)
        self.thread.daemon = True

        self.thread.start()

        while self.server.started is False:
            time.sleep(0.01)

    def stop(self, **kwargs):
        if self.server is not None:
            self.server.should_exit = True
            self.thread.join()


class HTTPTest(_HTTPTestCase):
    server_class = Server


class WebSocketTest(_WebSocketTestCase):
    server_class = Server

