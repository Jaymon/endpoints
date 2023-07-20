# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import io
import logging

from ...compat import *
from ..base import BaseApplication
#from ...http import Host
#from ...decorators import property
from ...utils import ByteString, String
from ... import environ


import json
from ...utils import JSONEncoder
from ...exception import (
    CallStop,
    CloseConnection,
)


logger = logging.getLogger(__name__)


class Application(BaseApplication):
    """

    HTTP lifecycle:
        https://asgi.readthedocs.io/en/latest/specs/www.html#http-connection-scope


    WebSocket lifecycle:
        https://asgi.readthedocs.io/en/latest/specs/www.html#websocket-connection-scope
    """

    def is_http_call(self, scope):
        return scope["type"] == "http"

    def is_websocket_call(self, scope):
        return scope["type"] == "websocket"


    async def handle_websocket(self, scope, receive, send):

        await self.handle_websocket_connect(scope, receive, send)
        disconnect = True

        try:
            while True:
                ws_raw = await receive()

                if ws_raw["type"] == "websocket.receive":
                    # https://asgi.readthedocs.io/en/latest/specs/www.html#receive-receive-event
                    request = await self.create_request(scope)
                    response = await self.create_response()

                    d = self.get_websocket_loads(ws_raw["text"])

                    for k in ["path", "uuid", "method"]:
                        if k in d:
                            setattr(request, k, d[k])

                    if "body" in d:
                        await self.set_request_body(request, d["body"])

                    if d["headers"]:
                        request.add_headers(d["headers"])

                    await self.handle(request, response)

                    await self.send_websocket(request, response, send)

                elif ws_raw["type"] == "websocket.disconnect":
                    # https://asgi.readthedocs.io/en/latest/specs/www.html#disconnect-receive-event-ws
                    #pout.v(ws_raw)
                    disconnect = False
                    break

#                 elif ws_raw["type"] == "websocket.close":
#                     # https://asgi.readthedocs.io/en/latest/specs/www.html#close-send-event
#                     pout.v(ws_raw)
#                     await send({
#                         "type": "websocket.close",
#                         "status": ws_raw.get("code", 1000),
#                         "reason": ws_raw.get(
#                             "reason",
#                             "Websocket closed by client"
#                         ),
#                     })

                    break

        except CloseConnection as e:
            disconnect = True

        finally:
            if disconnect:
                await self.handle_websocket_disconnect(scope, receive, send)

    async def handle_websocket_connect(self, scope, receive, send):
        d = await receive()
        if d["type"] == "websocket.connect":
            request = await self.create_request(scope)
            response = await self.create_response()

            request.method = "CONNECT"

            await self.handle(request, response)

            if response.is_success():
                await send({
                    "type": "websocket.accept",
                })

                await self.send_websocket(request, response, send)

            else:
                await send({
                    "type": "websocket.close",
                    "code": response.code,
                })

#                 pout.v(response.code)
#                 # TODO -- this should be consolidated into an HTTP send method
#                 await send({
#                     "type": "http.response.start",
#                     #"status": response.code,
#                     "status": 403,
#                     "headers": list(response.headers.asgi()),
#                 })
# 
#                 await send({
#                     "type": "http.response.body",
#                     "body": b"",
#                     "more_body": False,
#                 })

        else:
            await send({
                "type": "websocket.close",
                "code": 1002,
                "reason": "WebSocket connect got an unexpected asgi type",
            })

    async def handle_websocket_disconnect(self, scope, receive, send):
        request = await self.create_request(scope)
        response = await self.create_response()

        response.code = 1000
        request.method = "DISCONNECT"

        await self.handle(request, response)

        body = b""
        async for part in self.get_response_body(response):
            body += part

        r = await send({
            "type": "websocket.close",
            "code": response.code,
            "reason": String(body),
        })

    async def send_websocket(self, request, response, send, **kwargs):
        d = {
            "type": "websocket.send",
            "text": self.get_websocket_dumps(
                uuid=request.uuid,
                code=response.code,
                path=request.path,
                body=response.body,
            )
        }
        await send(d)

    async def __call__(self, scope, receive, send):
        """this is what will be called for each request that that ASGI server
        handles"""

        #pout.v(scope)

        if self.is_http_call(scope):
            request = await self.create_request(scope)

            d = await receive()
            body = d["body"]
            while d["more_body"]:
                d = await receive()
                body += d["body"]

            await self.set_request_body(request, body, **kwargs)


            response = await self.create_response()
            await self.handle(request, response)

            await send({
                "type": "http.response.start",
                "status": response.code,
                "headers": list(response.headers.asgi()),
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

        elif self.is_websocket_call(scope):
            await self.handle_websocket(scope, receive, send)

    async def create_request(self, raw_request, **kwargs):
        """
        create instance of request

        raw_request -- the raw request object retrieved from a WSGI server
        """
        request = self.request_class()
        request.add_headers(raw_request.get("headers", []))

        request.path = raw_request['path']
        request.query = raw_request['query_string']
        request.host, request.port = raw_request["server"]

        if self.is_http_call(raw_request):
            request.method = raw_request['method']
            request.scheme = raw_request.get("scheme", "http")

        elif self.is_websocket_call(raw_request):
            request.scheme = raw_request.get("scheme", "ws")

        request.raw_request = raw_request
        return request


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

