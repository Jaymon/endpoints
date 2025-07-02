# -*- coding: utf-8 -*-

from ..compat import *
from ..exception import VersionError
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

    async def handle_handle_error(self, controller, e):
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

