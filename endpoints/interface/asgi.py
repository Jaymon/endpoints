from datatypes import logging

from ..compat import *
from .base import Interface
from ..utils import String


logger = logging.getLogger(__name__)


class Interface(Interface):
    """ASGI HTTP and WebSocket Interface support

    Good intro tutorial:
        https://www.encode.io/articles/asgi-http

    HTTP lifecycle:
        https://asgi.readthedocs.io/en/latest/specs/www.html#http-connection-scope

    WebSocket lifecycle:
        https://asgi.readthedocs.io/en/latest/specs/www.html#websocket-connection-scope
    """
    async def __call__(self, scope, receive, send):
        """this is what will be called for each request that the server handles

        This can return something (WSGI needs a `list[bytes]` returned while
        ASGI handles the sending on its own and returns None
        """
        call_kwargs = {
            "scope": scope,
            "receive": receive,
            "send": send,
        }

        try:
            if self.is_http_call(scope):
                return await self.handle_http(**call_kwargs)

            elif self.is_websocket_call(scope):
                return await self.handle_websocket(**call_kwargs)

            elif self.is_lifespan_call(**call_kwargs):
                return await self.handle_lifespan(**call_kwargs)

            else:
                logger.warning(
                    "Scope type %s was not http, websocket, or lifespan",
                    scope["type"],
                )

        except Exception as e:
            # this should almost never hit, but if it does we want to log the
            # exception before re-raising it because some servers will bury
            # uncaught exceptions and this block is only for errors raised
            # outside of all the error handling logic
            logger.exception(e)
            raise e

#     def normalize_call_kwargs(self, scope, receive, send, **kwargs):
#         return {
#             "scope": scope,
#             "receive": receive,
#             "send": send,
#             **kwargs
#         }

    def is_lifespan_call(self, scope, **kwargs):
        return scope["type"] == "lifespan"

#     def is_lifespan_startup(self, data, **kwargs):
#         return data["type"] == "lifespan.startup"
# 
#     def is_lifespan_shutdown(self, data, **kwargs):
#         return data["type"] == "lifespan.shutdown"

    def is_http_call(self, scope, **kwargs):
        return scope["type"] == "http"

    def is_websocket_call(self, scope, **kwargs):
        return scope["type"] == "websocket"

    def is_websocket_recv(self, data, **kwargs):
        return data["type"] == "websocket.receive"

    def is_websocket_close(self, data, **kwargs):
        return data["type"] == "websocket.disconnect"

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

        request.body = body

        response = self.create_response()

        controller = await self.application.handle(request, response)

        sent_response = False

        try:
            # https://peps.python.org/pep-0525/
            # https://stackoverflow.com/a/37550568
            async for body in controller:
                if not sent_response:
                    await self.start_response(kwargs["send"], response)
                    sent_response = True

                await kwargs["send"]({
                    "type": "http.response.body",
                    "body": body,
                    "more_body": True,
                })

        finally:
            if not sent_response:
                await self.start_response(kwargs["send"], response)

            await kwargs["send"]({
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            })

    async def handle_websocket_recv(self, data, **kwargs):
        # https://asgi.readthedocs.io/en/latest/specs/www.html#receive-receive-event
        request = self.create_request(**kwargs)
        response = self.create_response()

        d = self.application.get_websocket_loads(data["text"])

        for k in ["path", "uuid", "method"]:
            if k in d:
                setattr(request, k, d[k])

        if "body" in d:
            request.body = d["body"]

        if d["headers"]:
            request.add_headers(d["headers"])

        await self.application.handle(request, response, **kwargs)
        await self.send_websocket(request, response, **kwargs)

    async def recv_websocket(self, receive, **kwargs):
        return await receive()

    async def send_websocket(self, request, response, **kwargs):
        d = {
            "type": "websocket.send",
            "bytes": self.application.get_websocket_dumps(
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
#         body = b""
#         async for part in self.get_response_body(response):
#             body += part

        r = await kwargs["send"]({
            "type": "websocket.close",
            "code": response.code,
#             "reason": String(body),
        })

    async def handle_lifespan(self, scope, receive, send, **kwargs):
        d = await self.recv_websocket(receive)
        if d["type"] == "lifespan.startup":
            try:
                await self.handle_lifespan_startup(scope, **kwargs)

            except Exception:
                await send({"type": "lifespan.startup.failed"})

            else:
                await send({"type": "lifespan.startup.complete"})

        elif d["type"] == "lifespan.shutdown":
            await self.handle_lifespan_shutdown(scope, **kwargs)
            await send({"type": "lifespan.shutdown.complete"})

        else:
            raise ValueError("Unknown lifespan type: {}".format(d["type"]))

    async def handle_lifespan_startup(self, scope, **kwargs):
        return

    async def handle_lifespan_shutdown(self, scope, **kwargs):
        return

    def create_request(self, **kwargs):
        raw_request = kwargs["scope"]
        request = self.application.request_class()
        request.add_headers(raw_request.get("headers", []))

        request.path = raw_request['path']
        request.query = raw_request['query_string']
        request.host, request.port = raw_request["server"]

        if self.is_http_call(raw_request):
            request.method = raw_request['method']
            request.scheme = raw_request.get("scheme", "http")
            request.protocol = "{}/{}".format(
                raw_request["type"].upper(),
                raw_request["http_version"],
            )

        elif self.is_websocket_call(raw_request):
            request.scheme = raw_request.get("scheme", "ws")

        request.raw_request = raw_request
        return request

