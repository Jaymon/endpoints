# -*- coding: utf-8 -*-
import logging

from ..exception import CallError, VersionError
from ..utils import Url
from .base import ControllerDecorator


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

    async def handle_error(self, controller, e):
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

    async def handle_error(self, controller, e):
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

