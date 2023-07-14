# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os

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
        request = await self.create_request(scope, receive)
        c = self.create_call(scope, request=request)
        res = c.handle() # TODO this should be async

        await send({
            "type": "http.response.start",
            "status": res.code,
            "headers": res.headers.bytes(),
        })
        await send({
            "type": "http.response.body",
            "body": b"".join(self.create_response_body(res)), # TODO this should be async
        })

    async def create_request(self, raw_request, receive, **kwargs):
        """
        create instance of request

        raw_request -- the raw request object retrieved from a WSGI server
        """
        r = self.request_class()
        r.add_headers(raw_request.get("headers", []))

        r.method = raw_request['method']
        r.path = raw_request['path']
        r.query = raw_request['query_string']
        r.scheme = raw_request["scheme"]
        r.host, r.port = raw_request["server"]

        await self.create_request_body(r, receive, **kwargs)

        r.raw_request = raw_request
        return r

    async def create_request_body(self, request, receive, **kwargs):
        request.body = request.create_body(await receive())
        body_kwargs = request.body.kwargs
        body_args = request.body.args
        return request

