# -*- coding: utf-8 -*-
import asyncio

from datatypes import (
    Host,
    ThreadingWSGIServer,
    logging,
)

from ..compat import *
from ..config import environ
from .base import BaseApplication


logger = logging.getLogger(__name__)


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

    def normalize_call_kwargs(self, environ, start_response):
        return {
            "environ": environ,
            "start_response": start_response,
        }

    async def handle_http(self, environ, start_response):
        request = self.create_request(environ)
        response = self.create_response()
        await self.handle(request, response)

        start_response(
            '{} {}'.format(response.code, response.status),
            list(response.headers.items())
        )

        # https://peps.python.org/pep-0530/
        return [body async for body in self.get_response_body(response)]

    def create_request(self, raw_request, **kwargs):
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

        self.set_request_body(
            r,
            raw_request.get('wsgi.input', None)
        )

        r.raw_request = raw_request
        return r


class Server(ThreadingWSGIServer):
    """A simple python WSGI Server

    you would normally only use this with the endpoints command, if you
    want to use it outside of that, then look at that script for inspiration
    """
    application_class = Application

    def __enter__(self):
        logger.info("Server is listening on {}".format(
            self.server_address.client()
        ))
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        logger.info(
            "Server {} is shutting down".format(
                self.server_address.client()
            )
        )
        self.server_close()

    def __init__(self, server_address=None, **kwargs):

        if not server_address:
            server_address = Host(kwargs.pop('host', environ.HOST))

        if "wsgifile" not in kwargs and "application" not in kwargs:
            kwargs["application"] = self.application_class(**kwargs)

        super().__init__(server_address, **kwargs)

        # we want to make sure we have a Host instance for the server address
        self.server_address = Host(*self.server_address)

