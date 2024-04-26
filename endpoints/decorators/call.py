# -*- coding: utf-8 -*-
import logging
import inspect

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
    param_class = Param

    def create_param(self, *args, **kwargs):
        """Create the param instance that will be passed to .handle_param
        when all the params are actually checked.

        :param *args: The arguments passed to this decorator
        :param **kwargs: the keyword arguments passed to this decorator
        :returns: Param, or an instance of whatever class is set int
            .param_class
        """
        return self.param_class(*args, **kwargs)

    def decorate(self, func, *args, **kwargs):
        wrapped = self.get_wrapped_method(func)

        self.param = self.create_param(*args, **kwargs)

        # how we figure out what params have been set and when to check during
        # runtime we use the original func as our source of truth, we place a
        # counter and the seen params on the original function and then, during
        # runtime we only go through the params and normalize the values on the
        # first param instance, all the others just return
        params = getattr(wrapped, "params", [])
        params.append(self)
        wrapped.params = params

        param_count = getattr(wrapped, "param_count", 0)
        self.param_count = param_count + 1
        wrapped.param_count = self.param_count

        if self.param_count == 1:
            # tricksy pointers, we use the original function as the source of
            # truth but we keep a reference pointer to those params so we can
            # access it in self in order to actually check the params at
            # runtime
            self.params = params

        return super().decorate(func, *args, **kwargs)

    async def handle_param(self, controller, *args, **kwargs):
        """This will use param to check and normalize the controllers args
        and kwargs

        :param controller: Controller
        :param args: the current state of the controller args that will be
            passed to the controller method that will handle the request
        :param kwargs: the current state of the controller kwargs that will
            be passed to the controller method handling the request
        :returns: tuple(Sequence, Mapping), the return value will be passed
            to the controller method handling the request as *args, **kwargs
        """
        param = self.param

        if inspect.iscoroutinefunction(param.handle):
            return await param.handle(args, kwargs)

        else:
            return param.handle(args, kwargs)

    async def handle_params(self, controller, *args, **kwargs):
        """Called from .get_controller_params and only called when the params
        should actually be handled. This loops through all the param_class
        instances and normalizes/checks them by calling .handle_param
        for each parameter in self.params

        :param controller: Controller, the controller instance handling this
            request
        :param args: the current state of the controller args that will be
            passed to the controller method that will handle the request
        :param kwargs: the current state of the controller kwargs that will
            be passed to the controller method handling the request
        :returns: tuple(Sequence, Mapping), the return value will be passed
            to the controller method handling the request as *args, **kwargs
        """
        for param in self.params:
            param.encoding = controller.request.encoding

            args, kwargs = await param.handle_param(
                controller,
                *args,
                **kwargs
            )

        return args, kwargs

    async def get_controller_params(self, controller, *args, **kwargs):
        """this is where all the magic happens, this will try and find the
        param and put its value in kwargs if it has a default and stuff

        :param controller: Controller, the controller instance handling this
            request
        :param args: the current state of the controller args that will be
            passed to the controller method that will handle the request
        :param kwargs: the current state of the controller kwargs that will
            be passed to the controller method handling the request
        :returns: tuple(Sequence, Mapping), the return value will be passed
            to the controller method handling the request as *args, **kwargs
        """
        # the first param decorator on the wrapped method is the one that will
        # actually do the checking and normalizing of the passed in values
        if self.param_count == 1:
            try:
                args, kwargs = await self.handle_params(
                    controller,
                    *args,
                    **kwargs
                )

            except ValueError as e:
                raise CallError(400, String(e)) from e

        return args, kwargs


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

