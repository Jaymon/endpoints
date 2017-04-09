# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import inspect
import re

from decorators import FuncDecorator

from ..exception import CallError, RouteError, VersionError


logger = logging.getLogger(__name__)


class route(FuncDecorator):
    """Used to decide if the Controller's method should be used to satisfy the request

    :example:
        class Default(Controller):
            # this GET will handle /:uid/:title requests
            @route(lambda req: len(req.path_args) == 2)
            def GET_1(self, uid, title):
                pass

            # this GET will handle /:username requests
            @route(lambda req: len(req.path_args) == 1)
            def GET_2(self, username):
                pass

    If this decorator is used then all GET methods in the controller have to have
    a unique name (ie, there can be no just GET method, they have to be GET_1, etc.)
    """
    def decorate(slf, func, callback, *args, **kwargs):
        def decorated(self, *args, **kwargs):
            yes = callback(self.request)
            if not yes:
                raise RouteError()

            return func(self, *args, **kwargs)

        return decorated


class version(FuncDecorator):
    """Used to provide versioning support to a Controller

    :example:
        class Default(Controller):
            # this GET will handle no version and version v1 requests
            @version("", "v1")
            def GET_1(self):
                pass

            # this GET will handle version v2 request
            def GET_2(self):
                pass

    If this decorator is used then all GET methods in the controller have to have
    a unique name (ie, there can be no just GET method, they have to be GET_1, etc.)
    """
    def decorate(slf, func, *versions):
        versions = set(versions)
        def decorated(self, *args, **kwargs):
            req = self.request
            req_version = req.version(self.content_type)
            if req_version not in versions:
                raise VersionError(req_version, versions)

            return func(self, *args, **kwargs)

        return decorated

