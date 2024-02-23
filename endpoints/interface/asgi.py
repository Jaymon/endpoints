# -*- coding: utf-8 -*-

from ..compat import *
from .base import BaseApplication
from ..utils import String


class Application(BaseApplication):
    """ASGI HTTP and WebSocket Interface support

    Good intro tutorial:
        https://www.encode.io/articles/asgi-http

    HTTP lifecycle:
        https://asgi.readthedocs.io/en/latest/specs/www.html#http-connection-scope

    WebSocket lifecycle:
        https://asgi.readthedocs.io/en/latest/specs/www.html#websocket-connection-scope
    """
    def normalize_call_kwargs(self, scope, receive, send, **kwargs):
        return {
            "scope": scope,
            "receive": receive,
            "send": send,
            **kwargs
        }

    def is_http_call(self, scope, **kwargs):
        return scope["type"] == "http"

    def is_websocket_call(self, scope, **kwargs):
        return scope["type"] == "websocket"

    async def start_response(self, send, response):
        await send({
            "type": "http.response.start",
            "status": response.code,
            "headers": list(response.headers.asgi()),
        })

    async def handle_http(self, **kwargs):
        request = self.create_request(**kwargs)

        d = await self.recv_websocket(**kwargs)
        body = d["body"]
        while d["more_body"]:
            d = await self.recv_websocket(**kwargs)
            body += d["body"]

        self.set_request_body(request, body, **kwargs)

        response = self.create_response()
        await self.handle(request, response)

        sent_response = False

        try:
            # https://peps.python.org/pep-0525/
            # https://stackoverflow.com/a/37550568
            async for body in self.get_response_body(response):
                if not sent_response:
                    await self.start_response(kwargs["send"], response)
                    sent_response = True

                await kwargs["send"]({
                    "type": "http.response.body",
                    "body": body,
                    "more_body": True,
                })

        except Exception:
            response.code = 500
            raise

        finally:
            if not sent_response:
                await self.start_response(kwargs["send"], response)
                sent_response = True

            await kwargs["send"]({
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            })

    def is_websocket_recv(self, data, **kwargs):
        return data["type"] == "websocket.receive"

    def is_websocket_close(self, data, **kwargs):
        return data["type"] == "websocket.disconnect"

    async def handle_websocket_recv(self, data, **kwargs):
        # https://asgi.readthedocs.io/en/latest/specs/www.html#receive-receive-event
        request = self.create_request(**kwargs)
        response = self.create_response()

        d = self.get_websocket_loads(data["text"])

        for k in ["path", "uuid", "method"]:
            if k in d:
                setattr(request, k, d[k])

        if "body" in d:
            self.set_request_body(request, d["body"])

        if d["headers"]:
            request.add_headers(d["headers"])

        await self.handle(request, response, **kwargs)
        await self.send_websocket(request, response, **kwargs)

    async def recv_websocket(self, **kwargs):
        return await kwargs["receive"]()

    async def send_websocket(self, request, response, **kwargs):
        d = {
            "type": "websocket.send",
            "text": self.get_websocket_dumps(
                uuid=request.uuid,
                code=response.code,
                path=request.path,
                body=response.body,
            )
        }
        await kwargs["send"](d)

    async def handle_websocket_connect(self, **kwargs):
        d = await self.recv_websocket(**kwargs)
        if d["type"] == "websocket.connect":
            await super().handle_websocket_connect(**kwargs)

        else:
            response = self.create_response(**kwargs)
            response.code = 1002
            await self.send_websocket_connect(None, response, **kwargs)

    async def send_websocket_connect(self, request, response, **kwargs):
        if response.is_success():
            await kwargs["send"]({
                "type": "websocket.accept",
            })
            await self.send_websocket(request, response, **kwargs)

        else:
            await self.send_websocket_disconnect(request, response, **kwargs)

    async def send_websocket_disconnect(self, request, response, **kwargs):
        body = b""
        async for part in self.get_response_body(response):
            body += part

        r = await kwargs["send"]({
            "type": "websocket.close",
            "code": response.code,
            "reason": String(body),
        })

    def create_request(self, **kwargs):
        raw_request = kwargs["scope"]
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
    """This is convenience wrapper to make it easy to call daphne, because you
    can just do this:

        $ daphne -b 0.0.0.0 -p 4000 -v 3 endpoints.interface.asgi.ApplicationFactory
    """
    application = None
    """Will hold a cached instance of .application_class"""

    application_class = Application
    """The application class that will be created"""

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

