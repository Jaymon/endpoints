# -*- coding: utf-8 -*-

from ..compat import *
from ..exception import CallError
from .base import ControllerDecorator


class httpcache(ControllerDecorator):
    """
    sets the cache headers so the response can be cached by the client

    https://developers.google.com/web/fundamentals/performance/optimizing-content-efficiency/http-caching

    """
    def definition(self, ttl: int, **kwargs):
        """
        :param ttl: how many seconds to have the client cache the request
        """
        self.ttl = int(ttl)
        super().definition(**kwargs)

    async def handle(self, controller, **kwargs):
        controller.response.headers.update({
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
        controller.response.headers.update({
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache", 
            "Expires": "0"
        })


