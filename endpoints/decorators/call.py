# -*- coding: utf-8 -*-
import logging

from ..compat import *
from ..exception import CallError, VersionError
from ..utils import Url
from ..call import Param
from .base import ControllerDecorator


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
            # access it in self in order to actually check the params at runtime
            self.params = params

        return super().decorate(func, *args, **kwargs)

    async def handle_method_input(self, controller, *controller_args, **controller_kwargs):
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


class route(ControllerDecorator):
    """Used to decide if the Controller's method should be used to satisfy the
    request

    TODO? Honestly, I don't think this is very useful anymore, routing between
    the various methods is more just built-in now, I'll keep this for now but
    I think I'll probably be removing it in the future, version is still really
    handy though (2024-02-19)

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

    If this decorator is used then all GET methods in the controller have to
    have a unique name (ie, there can be no just GET method, they have to be
    GET_1, etc.)
    """
    def definition(self, callback, *args, **kwargs):
        """
        :param callback: callable[Request]
        :param *args: any other values passed into the decorator
        :param **kwargs: any other keyword values passed into the decorator
        """
        self.callback = callback
        self.error_code = kwargs.pop("error_code", 405)

    async def handle(self, controller, **kwargs):
        return self.callback(controller.request)

    async def handle_handle_error(self, controller, e):
        req = controller.request

        e_msg = " ".join([
            "Request Controller method: {}:{}.{}".format(
                req.controller_info['module_name'],
                req.controller_info['class_name'],
                req.controller_info['method_name'],
            ),
            "failed routing check",
        ])

        raise CallError(
            self.error_code,
            e_msg
        ) from e


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

    If this decorator is used then all GET methods in the controller have to
    have a unique name (ie, there can be no just GET method, they have to be
    GET_1, etc.)
    """
    def definition(self, *versions, **kwargs):
        self.versions = set(versions)
        self.error_code = kwargs.pop("error_code", 404)

    async def handle(self, controller, **kwargs):
        req_version = controller.request.version(controller.content_type)
        return req_version in self.versions

    async def handle_handle_error(self, controller, e):
        req = controller.request
        req_version = req.version(controller.content_type)

        e_msg = " ".join([
            "Request Controller method: {}:{}.{}".format(
                req.controller_info['module_name'],
                req.controller_info['class_name'],
                req.controller_info['method_name'],
            ),
            "failed version check ({} not in {})".format(
                req_version,
                self.versions,
            ),
        ])

        raise VersionError(
            req_version,
            self.versions,
            code=self.error_code,
            msg=e_msg
        ) from e

