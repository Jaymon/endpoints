# -*- coding: utf-8 -*-

from ..compat import *
from ..exception import VersionError, CallError
from .base import ControllerDecorator


class version(ControllerDecorator):
    """Used to provide versioning support to a Controller

    :example:
        class Default(Controller):
            # this GET will handle no version and version v1 requests
            @version("", "v1")
            def GET_1(self):
                pass

            # this GET will handle version v2 request
            @version("v2")
            def GET_2(self):
                pass

    If this decorator is used then all GET methods in the controller have to
    have a unique name (ie, there can be no just GET method, they have to be
    GET_1, etc.)
    """
    def definition(self, *versions, **kwargs):
        self.versions = set(versions)
        self.error_code = kwargs.pop("error_code", 404)

    async def handle(self, controller, **kwargs):
        req_version = controller.request.version()
        return req_version in self.versions

    async def handle_decorator_error(self, controller, e):
        req = controller.request
        req_version = req.version()

        e_msg = (
            "Request Controller method: {}"
            " failed version check ({} not in {})"
        ).format(
            req.controller_info["reflect_method"].callpath,
            req_version,
            self.versions,
        )

        raise VersionError(
            req_version,
            self.versions,
            code=self.error_code,
            msg=e_msg
        ) from e


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


