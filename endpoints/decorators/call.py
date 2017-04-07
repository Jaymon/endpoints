# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import inspect
import re

from decorators import FuncDecorator

from ..exception import CallError, RouteError, VersionError


logger = logging.getLogger(__name__)


class route(FuncDecorator):
    def decorate(slf, func, callback, *args, **kwargs):
        def decorated(self, *args, **kwargs):
            yes = callback(self.request)
            if not yes:
                raise RouteError()

            return func(self, *args, **kwargs)

        return decorated


class version(FuncDecorator):
    def decorate(slf, func, *versions):
        versions = set(versions)
        def decorated(self, *args, **kwargs):
            req = self.request
            req_version = req.version(self.content_type)
            if req_version not in versions:
                raise VersionError(req_version, versions)

            return func(self, *args, **kwargs)

        return decorated

