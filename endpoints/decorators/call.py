# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import inspect
import re

from ..exception import CallError, RouteError, VersionError
from ..http import Url
from .base import ControllerDecorator


logger = logging.getLogger(__name__)


class route(ControllerDecorator):
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
    def definition(self, callback, *args, **kwargs):
        self.callback = callback
        self.error_code = kwargs.pop("error_code", 405)

    def handle(self, request):
        return self.callback(request)

    def handle_args(self, controller, controller_args, controller_kwargs):
        return [controller.request]

    def handle_error(self, controller, e):
        raise RouteError(instance=self)

    def handle_failure(self, controller):
        """This is called if all routes fail, it's purpose is to completely
        fail the request

        This is not a great solution because it uses the assumption that all the
        route decorators for a given set of methods on the controller (ie all the
        GET_* methods) will be the same, so if the first failing instance of this
        decorator will have its failure method set as the global failure method
        and it will be called if all the potential routes fail

        :param controller: Controller, the controller that was trying to find a 
            method to route to
        """
        req = controller.request

        # https://www.w3.org/Protocols/rfc2616/rfc2616-sec5.html#sec5.1
        # An origin server SHOULD return the status code 405 (Method Not Allowed)
        # if the method is known by the origin server but not allowed for the
        # requested resource
        raise CallError(self.error_code, "Could not find a method to satisfy {}".format(
            req.path
        ))


class route_path(route):
    """easier route decorator that will check the sub paths to make sure they are part 
    of the full endpoint path

    :Example:

        class Foo(Controller):
            @path_route("bar", "che")
            def GET(self, *args):
                # you can only get here by requesting /foo/bar/che where /foo is
                # the controller path and /bar/che is the path_route
    """
    def definition(self, *paths, **kwargs):
        self.paths = paths
        self.error_code = kwargs.pop("error_code", 404)

    def handle(self, request):
        ret = True
        pas = Url.normalize_paths(self.paths)
        method_args = request.controller_info["method_args"]
        for i, p in enumerate(pas):
            try:
                if method_args[i] != p:
                    ret = False
                    break

            except IndexError:
                ret = False
                break

        return ret


class route_param(route):
    """easier route decorator that will check the parameters to make sure they are part 
    of the request

    :Example:

        class Foo(Controller):
            @route_param(bar="che")
            def GET(self, **kwargs):
                # you can only get here by requesting /foo?bar=che where /foo is
                # the controller path and ?bar=che is one of the query parameters
    """
    def definition(self, *keys, **matches):
        self.keys = keys
        self.matches = matches

        # we throw a 400 here to match @param failures
        self.error_code = 400

    def handle(self, request):
        ret = True
        method_kwargs = request.controller_info["method_kwargs"]
        for k in self.keys:
            if k not in method_kwargs:
                ret = False
                break

        if ret:
            for k, v in self.matches.items():
                try:
                    if type(v)(method_kwargs[k]) != v:
                        ret = False
                        break

                except KeyError:
                    ret = False
                    break

        return ret


class version(route):
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

    If this decorator is used then all GET methods in the controller have to have
    a unique name (ie, there can be no just GET method, they have to be GET_1, etc.)
    """
    def definition(self, *versions, **kwargs):
        self.versions = set(versions)
        self.error_code = kwargs.pop("error_code", 404)

    def handle_args(self, controller, controller_args, controller_kwargs):
        return [controller]

    def handle_error(self, controller, e):
        raise

    def handle(self, controller):
        req_version = controller.request.version(controller.content_type)
        if req_version not in self.versions:
            raise VersionError(self, req_version, self.versions)

