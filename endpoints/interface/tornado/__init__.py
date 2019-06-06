# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import json

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
    """All requests will go through this handler, specifically the handle method"""
    def handle(self, *args, **kwargs):
        """all the magic happens here, this will take the tornado request, create
        an endpoints request and then create the call instance and let endpoints
        handle the request and then pass the result back to tornado

        all the http method class basically just wrap this method, but you could
        override any of the http methods individually if you wanted, or you can
        override this method if you want to have common functionality"""

        # !!! if I create the call before right here (like say in Application.find_handler
        # then the request body won't be populated, I have no idea why
        c = self.request.application.server.create_call(self.request)

        # just in case the endpoints code needs the tornado code for some reason
        c.application = self.request.application
        c.tornado = self

        c.handle()
        res = c.response

        self.set_status(res.code)

        for h in res.headers.items():
            #pout.v(h, ByteString(h[0]), ByteString(h[1]))
            #self.set_header(ByteString(h[0]), ByteString(h[1]))
            self.set_header(h[0], h[1])

        for s in self.request.application.server.create_response_body(res):
            self.write(s)

    def head(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def get(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def post(self, *args, **kwargs):
        return self.handle(*args, **kwargs)
    def delete(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def patch(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def put(self, *args, **kwargs): return self.handle(*args, **kwargs)
    def options(self, *args, **kwargs): return self.handle(*args, **kwargs)


class Application(tornado.web.Application):
    """The tornado application instance handles the routing, we override it so we
    can use endpoints's routing stuff and so tornado's handler can get access to
    the endpoints's Server instance so endpoints can do its thing"""
    def __init__(self, server, *args, **kwargs):
        self.server = server
        kwargs.setdefault("default_handler_class", self.server.tornado_handler_class)
        super(Application, self).__init__(*args, **kwargs)

    def find_handler(self, request, **kwargs):
        """This injects self into the request instance so the actual handler instance
        can get access to the Server instance to create endpoints compatible things
        and handle the request"""
        request.application = self
        return super(Application, self).find_handler(request, **kwargs)


class Server(BaseServer):
    """This is the bridge class between tornado and endpoints, this makes tornado
    compatible with all of endpoints's stuff"""

    tornado_handler_class = Handler

    tornado_application_class = Application

    @property
    def hostloc(self):
        server_address = []
        for s in self.backend._sockets.values():
            server_address = s.getsockname()
            break
        return ":".join(map(String, server_address))

    def create_backend(self, **kwargs):
        hostname, port = Url.split_hostname_from_port(kwargs.pop('host', environ.HOST))
        port = port if port else 0

        app = self.tornado_application_class(self)
        server = app.listen(port, hostname)
        server.start(0)
        return server

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands"""
        #pout.v(raw_request)
        r = self.request_class()
        r.set_headers(raw_request.headers)

        # this call actually modifies the raw request by popping headers
        environ = tornado.wsgi.WSGIContainer.environ(raw_request)
        r.environ.update(environ)

        r.method = raw_request.method
        r.path = raw_request.path
        #r.query = raw_request.query
        r.query_kwargs = Url.normalize_query_kwargs(raw_request.query_arguments)

        self.create_request_body(r, raw_request, **kwargs)
        r.raw_request = raw_request
        return r

    def create_request_body(self, request, raw_request, **kwargs):
        body_kwargs = {}
        body = None
        if raw_request.body_arguments:
            body_kwargs = Url.normalize_query_kwargs(raw_request.body_arguments)

        if raw_request.files:
            for k, vs in Url.normalize_query_kwargs(raw_request.files).items():
                body_kwargs[k] = vs

        if raw_request.body:
            # tornado won't un-jsonify stuff automatically, so if there aren't
            # any body arguments there might still be something in body
            if request.is_json():
                body_kwargs = json.loads(raw_request.body)

            body = raw_request.body

        #pout.v(r.body_kwargs)
        #pout.v(r)
        request.body_kwargs = body_kwargs
        request.body = body
        return request

#     def handle_request(self):
#         raise NotImplementedError()

#     def normalize_kwargs(self, d):
#         for k, v in d.items():
#             if isinstance(k, bytes):
#                 k = String(k)
# 
#             if

    def serve_forever(self):
        server = self.backend
        tornado.ioloop.IOLoop.current().start()

    def serve_count(self, count):
        """TODO there might be a way to make this work buy using IOLoop.run_sync
        but it's not worth figuring out right now
        https://github.com/tornadoweb/tornado/blob/master/tornado/ioloop.py#L460
        """
        raise NotImplementedError()

