# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
import cgi
import json

from ...compat import *
from .. import BaseServer
from ...http import Host
from ...decorators import property
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
        return self.handle_http_response(environ, start_response)

    def handle_http_response(self, environ, start_response):
        c = self.create_call(environ)
        res = c.handle()

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

        return self.create_response_body(res)

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

        self.create_request_body(r, raw_request, **kwargs)
        r.raw_request = raw_request
        return r

    def create_request_body(self, request, raw_request, **kwargs):
        body_args = []
        body_kwargs = {}
        body = None
        if 'wsgi.input' in raw_request:
            body = raw_request['wsgi.input']
            body = request.create_body(raw_request['wsgi.input'])
            body_kwargs = body.kwargs
            body_args = body.args

        request.body_args = body_args
        request.body_kwargs = body_kwargs
        request.body = body
        return request

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

    @property(cached="_application")
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
        server_address = Host(kwargs.pop('host', environ.HOST))
        s = self.backend_class(server_address, WSGIRequestHandler, **kwargs)
        s.set_app(self.application)
        return s

    def handle_request(self):
        #self.prepare()
        return self.backend.handle_request()

    def serve_forever(self):
        #self.prepare()
        return self.backend.serve_forever()

