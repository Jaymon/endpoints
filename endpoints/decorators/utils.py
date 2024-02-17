# -*- coding: utf-8 -*-
import re
import cgi
import logging

from .base import ControllerDecorator

from ..compat import *
from ..exception import CallError
from ..call import Param


logger = logging.getLogger(__name__)


class httpcache(ControllerDecorator):
    """
    sets the cache headers so the response can be cached by the client

    link -- https://developers.google.com/web/fundamentals/performance/optimizing-content-efficiency/http-caching

    ttl -- integer -- how many seconds to have the client cache the request
    """
    def definition(self, ttl, **kwargs):
        self.ttl = int(ttl)
        super().definition(**kwargs)

    async def handle_request(self, controller, *args, **kwargs):
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
    async def handle_request(self, controller, *args, **kwargs):
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


class param(ControllerDecorator):
    """
    decorator to allow setting certain expected query/body values and options

    this tries to be as similar to python's built-in argparse as possible

    This checks both POST and GET query args

    :Example:

        @param('name', type=int, action='store_list')

    Check `call.Param` to see what you can pass into this decorator since this
    is basically just a wrapper around that class

    raises CallError with 400 status code on any param validation failures
    """
    def decorate(self, func, *args, **kwargs):
        wrapped = self.get_wrapped_method(func)

        # how we figure out what params have been set and when to check during
        # runtime we use the original func as our source of truth, we place a
        # counter and the seen params on the original function and then, during
        # runtime we only go through the params and normalize the values on the
        # first param instance, all the others just return
        params = getattr(wrapped, "params", [])
        params.append(Param(*args, **kwargs))
        wrapped.params = params

        param_count = getattr(wrapped, "param_count", 0)
        self.param_count = param_count + 1
        wrapped.param_count = self.param_count

        if self.param_count == 1:
            # tricksy pointers, we use the original function as the source of
            # truth but we keep a reference pointer to those params so we can
            # access it in self in order to actually check the params
            self.params = params

        return super().decorate(func, *args, **kwargs)

    async def handle_request(self, controller, controller_args, controller_kwargs):
        """this is where all the magic happens, this will try and find the
        param and put its value in kwargs if it has a default and stuff"""
        # the first param decorator on the wrapped method is the one that will
        # actually do the checking and normalizing of the passed in values
        if self.param_count == 1:
            for param in self.params:
                param.encoding = controller.request.encoding

                try:
                    controller_args, controller_kwargs = param.handle(
                        controller_args,
                        controller_kwargs
                    )

                except ValueError as e:
                    raise CallError(400, String(e)) from e

        return controller_args, controller_kwargs

