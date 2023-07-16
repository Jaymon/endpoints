# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import io

from ...compat import *
from ..base import BaseApplication
#from ...http import Host
#from ...decorators import property
from ...utils import ByteString, String
from ... import environ


class Application(BaseApplication):
    async def __call__(self, scope, receive, send):
        """this is what will be called for each request that that ASGI server
        handles"""

        request = await self.create_request(scope, receive=receive)
        response = await self.create_response()
        controller = await self.create_controller(request, response)
        await self.handle(controller)

#         c = await self.create_call(scope, receive=receive)
#         res = c.handle() # TODO this should be async

        await send({
            "type": "http.response.start",
            "status": response.code,
            "headers": list(response.headers.bytes()),
        })

        # https://peps.python.org/pep-0525/
        # https://stackoverflow.com/a/37550568
        async for body in self.get_response_body(response):
            await send({
                "type": "http.response.body",
                "body": body,
                "more_body": True,
            })

        await send({
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        })

    async def create_request(self, raw_request, receive, **kwargs):
        """
        create instance of request

        raw_request -- the raw request object retrieved from a WSGI server
        """
        request = self.request_class()
        request.add_headers(raw_request.get("headers", []))

        request.method = raw_request['method']
        request.path = raw_request['path']
        request.query = raw_request['query_string']
        request.scheme = raw_request["scheme"]
        request.host, request.port = raw_request["server"]

        #pout.v(request.headers)

        d = await receive()
        body = d["body"]
        while d["more_body"]:
            d = await receive()
            body += d["body"]

        await self.set_request_body(request, body, **kwargs)

        request.raw_request = raw_request
        return request


#     async def create_request_body(self, request, receive, **kwargs):
#         d = await receive()
#         body = d["body"]
#         while d["more_body"]:
#             d = await receive()
#             body += d["body"]
# 
#         return await super().create_request_body(
#             request,
#             body,
#             **kwargs
#         )

#         request.body = request.create_body(io.BytesIO(body))
#         body_kwargs = request.body.kwargs
#         body_args = request.body.args
#         return request


class ApplicationFactory(object):

    application = None

    application_class = Application

    @classmethod
    def get_application(cls, **kwargs):
        if not cls.application:
            cls.application = cls.application_class(**kwargs)
        return cls.application

    def __init__(self, scope, **kwargs):
        self.scope = scope

    async def __call__(self, receive, send):
        application = self.get_application()
        await application(self.scope, receive, send)
        #await super().__call__(self.scope, receive, send)

