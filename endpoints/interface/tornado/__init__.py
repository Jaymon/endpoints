# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import


import tornado.web
import tornado.routing
import tornado.ioloop
import tornado.httpserver
import tornado.wsgi
import tornado.httputil

from .. import BaseServer
from ...reflection import Reflect
from ...http import Url
from ...utils import String, ByteString
from ... import environ


class Handler(tornado.web.RequestHandler):
#     def __init__(self, call, router, request):
#         self.call = call
#         super(Handler, self).__init__(router, request)

#     def get(self, *args, **kwargs):
#         pout.v(self)
#         pout.v(args, kwargs)
#         self.write("hello world")

    def handle(self, *args, **kwargs):
        c = self.request.call
        c.handle()
        res = c.response

        for h in res.headers.items():
            #pout.v(h, ByteString(h[0]), ByteString(h[1]))
            #self.set_header(ByteString(h[0]), ByteString(h[1]))
            self.set_header(h[0], h[1])

        for s in res:
            #self.write(ByteString(s))
            self.write(s)

    def head(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def get(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def post(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def delete(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def patch(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def put(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def options(self, *args, **kwargs): return self.handle(*args, **kwargs)


class Delegate(tornado.httputil.HTTPMessageDelegate):
    def __init__(self, connection, call):
        #self.server = server
        self.connection = connection
        self.call = call

    def finish(self):
        self.call.handle()
        res = self.call.response
        pout.v(res)
        self.connection.finish()


class Router(tornado.routing.Router):
    def __init__(self, server):
        self.server = server
        super(Router, self).__init__()

    def find_handler(self, request, **kwargs):
        #wsgi_request = tornado.wsgi.WSGIContainer.environ(request)
        #pout.v(request, wsgi_request, kwargs)

        c = self.server.create_call(request)
        return self.server.tornado_delegate_class(request.connection, c)


class Application(tornado.web.Application):
    def __init__(self, server, *args, **kwargs):
        self.server = server
        kwargs.setdefault("default_handler_class", self.server.tornado_handler_class)
        super(Application, self).__init__(*args, **kwargs)

    def find_handler(self, request, **kwargs):
        #wsgi_request = tornado.wsgi.WSGIContainer.environ(request)
        #pout.v(request, wsgi_request, kwargs)
        c = self.server.create_call(request)
        request.call = c
        request.server = self
        return super(Application, self).find_handler(request, **kwargs)


class Server(BaseServer):
    tornado_delegate_class = Delegate
    tornado_handler_class = Handler
    tornado_router_class = Router
    backend_class = tornado.httpserver.HTTPServer
    """the supported server's interface, there is no common interface for this class.
    Basically it is the raw backend class that the BaseServer child is translating
    for endpoints compatibility"""

    @property
    def hostloc(self):
        server_address = []
        for s in self.backend._sockets.values():
            server_address = s.getsockname()
            break
        return ":".join(map(String, server_address))

    def create_backend(self, **kwargs):
        #return self.backend_class(**kwargs)

        hostname, port = Url.split_hostname_from_port(kwargs.pop('host', environ.HOST))
        port = port if port else 0
        #server_address = (hostname, port if port else 0)

        app = Application(self)
        server = app.listen(port, hostname)
        server.start(0)
        return server

        #app = self.tornado_router_class(self)
        app = Application(self)
        server = self.backend_class(app)
        server.bind(port, hostname)
        server.start(0)  # Forks multiple sub-processes
        #pout.v(server, server.conn_params)
        #s = self.backend_class(server_address, WSGIRequestHandler, **kwargs)

        return server


        r = Reflect(self.controller_prefixes)
        for c in r.controllers:
            pout.v(c.decorators)
            pout.x()
            for ms in c.methods.values():
                for m in ms:
                    pout.v(m, m.params)
            #pout.v(c.methods)
            #for m in c.methods:
            #    pout.v(m)
            #pout.v(m.params)
            #pout.v(c.decorators)

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands"""
        r = self.request_class()
        r.set_headers(raw_request.headers)
        r.method = raw_request.method
        r.path = raw_request.path
        r.query = raw_request.query
        r.query_kwargs = raw_request.query_arguments
        r.body_kwargs = raw_request.body_arguments
        r.body = raw_request.body
        r.environ.update(tornado.wsgi.WSGIContainer.environ(raw_request))
        return r

#     def handle_request(self):
#         raise NotImplementedError()

    def serve_forever(self):
        server = self.backend
        tornado.ioloop.IOLoop.current().start()

    def serve_count(self, count):
        raise NotImplementedError()

