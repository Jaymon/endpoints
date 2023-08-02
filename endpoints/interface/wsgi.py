# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
import cgi
import json
import asyncio

from datatypes import (
    property as cachedproperty,
    Host,
    ThreadingWSGIServer,
)


from ..utils import ByteString, String
from ..config import environ


from ..compat import *
from .base import BaseApplication


class Application(BaseApplication):
    """The Application that a WSGI server needs

    this extends Server just to make it easier on the end user, basically, all
    you need to do to use this is in your wsgi-file, you can just do:

        from endpoints.interface.wsgi import Application
        application = Application()

    and you're good to go
    """
    def __call__(self, environ, start_response):
        """this is what will be called for each request that that WSGI server
        handles"""

        return asyncio.run(super().__call__(environ, start_response))

#         yield from asyncio.run(self.get_response_body(response))
#         for body in asyncio.run(self.get_response_body(response)):
#             yield body


#         with asyncio.Runner() as runner:
#             response = runner.run(super().__call__(environ, start_response))
#             pout.v(response)
        #yield from asyncio.run(ret)
        #return asyncio.run(super().__call__(environ, start_response))

    def normalize_call_kwargs(self, environ, start_response):
        return {
            "environ": environ,
            "start_response": start_response,
        }

    async def handle_http(self, environ, start_response):
        request = await self.create_request(environ)

#         content_length = request.get_header("Content-Length")
#         if content_length:
#             if 'wsgi.input' in environ:
#                 body = environ['wsgi.input'].read()
#             await self.set_request_body(request, body, **kwargs)

#         await self.set_request_body(
#             request,
#             environ.get('wsgi.input', None),
#         )

        response = await self.create_response()
        await self.handle(request, response)

        start_response(
            '{} {}'.format(response.code, response.status),
            list(response.headers.items())
        )

        # https://peps.python.org/pep-0530/
        return [body async for body in self.get_response_body(response)]

#         body_generator = self.get_response_body(response)
#         while True:
#             try:
#                 body = await anext(body_generator)
#                 yield body
# 
#             except StopAsyncIteration:
#                 break

        #return response

        # https://peps.python.org/pep-0525/
        # https://stackoverflow.com/a/37550568
#         async for body in self.get_response_body(response):
#             yield body

    async def create_request(self, raw_request, **kwargs):
        r = self.request_class()
        for k, v in raw_request.items():
            if k.startswith('HTTP_'):
                r.set_header(k[5:], v)

            elif k in ['CONTENT_TYPE', 'CONTENT_LENGTH']:
                r.set_header(k, v)

        r.method = raw_request['REQUEST_METHOD']
        r.path = raw_request['PATH_INFO']
        r.query = raw_request['QUERY_STRING']
        r.scheme = raw_request.get('wsgi.url_scheme', "http")
        r.host = raw_request["HTTP_HOST"]

        await self.set_request_body(
            r,
            raw_request.get('wsgi.input', None),
        )

        r.raw_request = raw_request
        return r





#     def handle_http_response(self, environ, start_response):
#         c = self.create_call(environ)
#         res = c.handle()
# 
#         if is_py2:
#             start_response(
#                 ByteString('{} {}'.format(res.code, res.status)).raw(),
#                 list((ByteString(h[0]).raw(), ByteString(h[1]).raw()) for h in res.headers.items())
#             )
# 
#         else:
#             start_response(
#                 '{} {}'.format(res.code, res.status),
#                 list(res.headers.items())
#             )
# 
#         return self.create_response_body(res)
# 
#     def create_request_body(self, request, raw_request, **kwargs):
#         body_args = []
#         body_kwargs = {}
#         body = None
#         if 'wsgi.input' in raw_request:
#             body = raw_request['wsgi.input']
#             body = request.create_body(raw_request['wsgi.input'])
#             body_kwargs = body.kwargs
#             body_args = body.args
# 
#         request.body_args = body_args
#         request.body_kwargs = body_kwargs
#         request.body = body
#         return request


# http://stackoverflow.com/questions/20745352/creating-a-multithreaded-server
# class WSGIHTTPServer(socketserver.ThreadingMixIn, WSGIServer):
# #class WSGIHTTPServer(socketserver.ForkingMixIn, WSGIServer):
#     """This is here to make the standard wsgi server multithreaded"""
#     pass


class Server(ThreadingWSGIServer):
    """A simple python WSGI Server

    you would normally only use this with the bin/wsgiserver.py script, if you
    want to use it outside of that, then look at that script for inspiration
    """
    application_class = Application

    @property
    def hostloc(self):
        return ":".join(map(String, self.server_address))

    def __init__(self, server_address=None, **kwargs):

        if not server_address:
            server_address = Host(kwargs.pop('host', environ.HOST))

        if "wsgifile" not in kwargs and "application" not in kwargs:
            kwargs["application"] = self.application_class()

        super().__init__(server_address, **kwargs)


#     backend_class = WSGIHTTPServer
# 
#     @cachedproperty(cached="_backend")
#     def backend(self):
#         return self.create_backend()

#     @cachedproperty(cached="_application")
#     def application(self):
#         """if no application has been set, then create it using application_class"""
#         app = self.application_class()
#         return app
# 
#     @application.setter
#     def application(self, v):
#         """allow overriding of the application factory, this allows you to set
#         your own application callable that will be used to handle requests, see
#         bin/wsgiserver.py script as an example of usage"""
#         self._application = v
#         self.set_app(v)
#         if backend := getattr(self, "_backend", None):
#             backend.set_app(v)

#     def create_backend(self, **kwargs):
#         pout.b("Creating backend")
#         server_address = Host(kwargs.pop('host', environ.HOST))
#         s = self.backend_class(server_address, WSGIRequestHandler, **kwargs)
#         s.set_app(self.application)
#         return s

#     def handle_request(self):
#         return self.backend.handle_request()
# 
#     def serve_forever(self):
#         return self.backend.serve_forever()
# 
#     def serve_count(self, count):
#         for _ in range(count):
#             self.handle_request()

