# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler

from ...compat.environ import *
from ...compat.imports import socketserver
from .. import BaseServer
from ...http import Url
from ...decorators import _property
from ...utils import ByteString, String
from ... import environ


class Application(BaseServer):
    """The Application that a WSGI server needs

    this extends Server just to make it easier on the end user, basically, all you
    need to do to use this is in your wsgi-file, you can just do:

        from endpoints.interface.wsgi import Application
        application = Application()

    and be good to go
    """
    def __call__(self, environ, start_response):
        """this is what will be called for each request that that WSGI server handles"""
        c = self.create_call(environ)
        c.handle()
        return self.handle_http_response(c, start_response)

    def handle_http_response(self, call, start_response):
        res = call.response

        if is_py2:
            start_response(
                ByteString('{} {}'.format(res.code, res.status)).raw(),
                list((ByteString(h[0]).raw(), ByteString(h[1]).raw()) for h in res.headers.items())
            )

        else:
            start_response(
                '{} {}'.format(res.code, res.status),
                list(res.headers.items())
            )

        # returning the Response, it needs to have an __iter__ for internal wsgi 
        # methods to know how to handle the Response
        return res

    def create_request(self, raw_request, **kwargs):
        """
        create instance of request

        raw_request -- the raw request object retrieved from a WSGI server
        """
        r = self.request_class()
        for k, v in raw_request.items():
            if k.startswith('HTTP_'):
                r.set_header(k[5:], v)
            else:
                r.environ[k] = v

        r.method = raw_request['REQUEST_METHOD']
        r.path = raw_request['PATH_INFO']
        r.query = raw_request['QUERY_STRING']

        # handle headers not prefixed with http
        for k in ['CONTENT_TYPE', 'CONTENT_LENGTH']:
            v = r.environ.pop(k, None)
            if v:
                r.set_header(k, v)

        if 'wsgi.input' in raw_request:

            if int(r.get_header("CONTENT_LENGTH", 0)) <= 0:
                r.body_kwargs = {}

            else:
                if r.get_header('transfer-encoding', "").lower().startswith('chunked'):
                    raise IOError("Server does not support chunked requests")

                else:
                    r.body_input = raw_request['wsgi.input']

        else:
            r.body_kwargs = {}

        return r

    def create_backend(self, **kwargs):
        raise NotImplementedError()

    def handle_request(self):
        raise NotImplementedError()

    def serve_forever(self):
        raise NotImplementedError()

    def serve_count(self, count):
        raise NotImplementedError()


# http://stackoverflow.com/questions/20745352/creating-a-multithreaded-server
class WSGIHTTPServer(socketserver.ThreadingMixIn, WSGIServer):
#class WSGIHTTPServer(socketserver.ForkingMixIn, WSGIServer):
    """This is here to make the standard wsgi server multithreaded"""
    pass


class Server(BaseServer):
    """A simple python WSGI Server

    you would normally only use this with the bin/wsgiserver.py script, if you
    want to use it outside of that, then look at that script for inspiration
    """
    application_class = Application

    backend_class = WSGIHTTPServer

    @property
    def hostloc(self):
        return ":".join(map(String, self.backend.server_address))

    @_property
    def application(self):
        """if no application has been set, then create it using application_class"""
        app = self.application_class()
        return app

    @application.setter
    def application(self, v):
        """allow overriding of the application factory, this allows you to set
        your own application callable that will be used to handle requests, see
        bin/wsgiserver.py script as an example of usage"""
        self._application = v
        self.backend.set_app(v)

    def create_backend(self, **kwargs):
        hostname, port = Url.split_hostname_from_port(kwargs.pop('host', environ.HOST))
#         if not port:
#             raise RuntimeError("Please specify a port using the format host:PORT")
        server_address = (hostname, port if port else 0)

        s = self.backend_class(server_address, WSGIRequestHandler, **kwargs)
        s.set_app(self.application)
        return s

    def handle_request(self):
        #self.prepare()
        return self.backend.handle_request()

    def serve_forever(self):
        #self.prepare()
        return self.backend.serve_forever()


