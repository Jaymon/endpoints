# -*- coding: utf-8 -*-
from threading import Thread
import time
from wsgiref.simple_server import make_server

from . import _HTTPTestCase, Server


class Server(Server):
    def start(self):
        self.server = make_server(
            self.server_host[0],
            self.server_host[1],
            self.application,
        )

        def target():
            self.server.serve_forever(0.1)

        self.thread = Thread(target=target)
        self.thread.daemon = True

        self.thread.start()

        while getattr(self.server, "server_address", None) is None:
            time.sleep(0.01)

    def stop(self, **kwargs):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()


class HTTPTest(_HTTPTestCase):
    server_class = Server

