# -*- coding: utf-8 -*-
import asyncio
from typing import Callable
from collections.abc import Iterable

from datatypes import logging

from ..compat import *
from ..config import environ
from ..call import Response
from .base import Interface


logger = logging.getLogger(__name__)


class Interface(Interface):
    """The Interface that a WSGI application needs"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._asyncioRunner = asyncio.Runner()

    def __call__(self, environ, start_response) -> Iterable[bytes]:
        """this is what will be called for each request that that WSGI server
        handles"""
        return self._asyncioRunner.run(
            self._handle_http(environ, start_response),
        )

    def __del__(self):
        self._asyncioRunner.close()

    async def _handle_http(self, environ, start_response) -> Iterable[bytes]:
        # we return a list because if we try to yield it will get messed
        # up in BaseApplication because it awaits this method, so it has
        # to return something that doesn't also need to be awaited, like
        # an AsyncGenerator
        chunks = []

        request = self.create_request(environ)
        response = self.create_response()
        controller = await self.application.handle(request, response)

        sent_response = False

        try:
            # https://peps.python.org/pep-0525/
            # https://stackoverflow.com/a/37550568
            async for body in controller:
                if not sent_response:
                    await self._start_response(start_response, response)
                    sent_response = True

                chunks.append(body)

        finally:
            if not sent_response:
                await self._start_response(start_response, response)

        # https://peps.python.org/pep-0530/
        return chunks

    async def _start_response(self, callback: Callable, response: Response):
        callback(
            '{} {}'.format(response.code, response.status),
            list(response.headers.items())
        )

    def create_request(self, environ, **kwargs):
        r = self.application.request_class()
        for k, v in environ.items():
            if k.startswith('HTTP_'):
                r.headers[k[5:]] = v

            elif k in ['CONTENT_TYPE', 'CONTENT_LENGTH']:
                r.headers[k] = v

        r.method = environ['REQUEST_METHOD']
        r.path = environ['PATH_INFO']
        r.query = environ['QUERY_STRING']
        r.scheme = environ.get('wsgi.url_scheme', "http")
        r.host = environ["HTTP_HOST"]
        r.protocol = environ.get("SERVER_PROTOCOL", None) # eg, HTTP/1.1

        r.body = environ.get('wsgi.input', None)
        r.environ = environ
        return r

