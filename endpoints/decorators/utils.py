# -*- coding: utf-8 -*-

from .base import ControllerDecorator

from ..compat import *
from ..exception import CallError


class httpcache(ControllerDecorator):
    """
    sets the cache headers so the response can be cached by the client

    link -- https://developers.google.com/web/fundamentals/performance/optimizing-content-efficiency/http-caching

    ttl -- integer -- how many seconds to have the client cache the request
    """
    def definition(self, ttl, **kwargs):
        self.ttl = int(ttl)
        super().definition(**kwargs)

    async def handle(self, controller, **kwargs):
        controller.response.add_headers({
            "Cache-Control": "max-age={}".format(self.ttl),
        })
        # TODO -- figure out how to set ETag
        #if not self.response.has_header('ETag')


class nohttpcache(ControllerDecorator):
    """
    sets all the no cache headers so the response won't be cached by the client

    https://devcenter.heroku.com/articles/increasing-application-performance-with-http-cache-headers#cache-prevention
    """
    async def handle(self, controller, **kwargs):
        controller.response.add_headers({
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache", 
            "Expires": "0"
        })


class code_error(ControllerDecorator):
    """
    When placed on HTTPMETHOD methods (eg, GET) this will allow you to easily
    map raised exceptions to http status codes

    :example:
        class Foo(Controller):
            @code_error(406, AttributeError, IndexError)
            def GET(self): raise AttributeError()

    :param code: integer, an http status code
        https://en.wikipedia.org/wiki/List_of_HTTP_status_codes
    :param **exc_classes: tuple, one or more exception classes that will be
        checked against the raised error
    """
    def definition(self, code, *exc_classes):
        self.code = code
        self.exc_classes = exc_classes

    async def handle_error(self, controller, e):
        if isinstance(e, self.exc_classes):
            raise CallError(self.code, e) from e

        else:
            return await super().handle_error(controller, e)

