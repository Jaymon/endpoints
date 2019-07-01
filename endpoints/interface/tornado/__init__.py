# -*- coding: utf-8 -*-
""" Interface for Tornado webserver

"""
from __future__ import unicode_literals, division, print_function, absolute_import
import json
import logging

import tornado.web
import tornado.websocket
import tornado.routing
import tornado.ioloop
import tornado.httpserver
import tornado.wsgi
import tornado.httputil

from .. import BaseServer, BaseWebsocketServer, Payload
from ...reflection import Reflect
from ...http import Url
from ...utils import String, ByteString, JSONEncoder
from ... import environ


logger = logging.getLogger(__name__)


class WebsocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        self.set_nodelay(True)

        self.call = self.request.application.server.connect_websocket_call(raw_request=self.request)
        req = self.call.request
        logger.info("Websocket {} Connecting".format(req.uuid))
        res = self.call.handle()
        self.send(req, res)

    def on_message(self, message):

        c = self.request.application.server.create_websocket_call(self.call.request, message)
        req = self.call.request
        logger.debug("Websocket {} message".format(req.uuid))
        res = c.handle()
        self.send(req, res)

    def on_close(self):
        c = self.request.application.server.disconnect_websocket_call(self.call.request)
        req = c.request
        logger.info("Websocket {} Disconnecting".format(req.uuid))
        res = c.handle()

    def send(self, req, res):
        for s in self.request.application.server.create_websocket_response_body(req, res):
            self.write_message(s)


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
        # https://www.tornadoweb.org/en/stable/guide/structure.html#handling-request-input
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
    compatible with all of endpoints's stuff

    https://github.com/tornadoweb/tornado/blob/master/tornado/web.py
    https://www.tornadoweb.org/en/stable/web.html
    https://www.tornadoweb.org/en/stable/
    https://www.tornadoweb.org/en/stable/httpserver.html
    https://www.tornadoweb.org/en/stable/guide/structure.html
    https://github.com/tornadoweb/tornado/blob/master/tornado/httpserver.py
    https://github.com/tornadoweb/tornado/blob/master/tornado/tcpserver.py
    https://www.tornadoweb.org/en/stable/guide/structure.html
    """

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
        #server.start(0) # I'm not sure what this did but it messed up py2, py3 stayed the same
        return server

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands

        https://www.tornadoweb.org/en/stable/httputil.html#tornado.httputil.HTTPMessageDelegate
        https://github.com/tornadoweb/tornado/blob/stable/tornado/httputil.py
        """
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

    def serve_forever(self):
        server = self.backend
        tornado.ioloop.IOLoop.current().start()

    def serve_count(self, count):
        """TODO there might be a way to make this work by using IOLoop.run_sync
        but it's not worth figuring out right now
        https://github.com/tornadoweb/tornado/blob/master/tornado/ioloop.py#L460
        """
        raise NotImplementedError()


class WebsocketServer(BaseWebsocketServer, Server):
    """
    https://github.com/tornadoweb/tornado/blob/master/tornado/websocket.py
    https://www.tornadoweb.org/en/stable/websocket.html
    """
    tornado_handler_class = WebsocketHandler

    payload_class = Payload

    def create_backend(self, **kwargs):
        kwargs.setdefault("websocket_ping_interval", 60)
        kwargs.setdefault("websocket_ping_timeout", 60)
        return super(WebsocketServer, self).create_backend(**kwargs)

