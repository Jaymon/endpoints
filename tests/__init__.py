# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from unittest import skipIf, SkipTest
import os
import sys
import logging
import asyncio

import testdata

from endpoints import environ
from endpoints.interface.base import BaseApplication
from endpoints.http import Request


testdata.basic_logging()
#testdata.basic_logging(format='[%(levelname).1s|%(asctime)s|%(filename)s:%(lineno)s] %(message)s')
#logging.basicConfig(format="[%(levelname).1s] %(message)s", level=logging.DEBUG, stream=sys.stdout)
#logger = logging.getLogger(__name__)


class Server(object):
    """This is just a wrapper to get access to the Interface handling code"""
    def __init__(self, *args, **kwargs):
        self.application = BaseApplication(*args, **kwargs)

    def create_request(self, path, method, **kwargs):
        req = asyncio.run(self.application.create_request(None))
        req.method = method.upper()

        version = kwargs.pop("version", None)
        if version is not None:
            req.set_header('Accept', '*/*;version={}'.format(version))

        d = dict(kwargs)
        d.setdefault("host", "endpoints.fake")
        for k, v in d.items():
            setattr(req, k, v)

        req.path = path
        return req

    def start(self):
        pass

    def stop(self):
        pass

#     def create_response(self):
#         return asyncio.run(self.application.create_response())
# 
#     def create_controller(self, path, method, **kwargs):
#         request = self.create_request(path, method, **kwargs)
#         response = asyncio.run(self.application.create_response())
#         return asyncio.run(self.application.create_controller(request, response))

    def handle(self, path="", method="GET", **kwargs):
        """This isn't technically needed but just makes it explicit you pass in the
        path you want and this will translate that and handle the request

        :param path: string, full URI you are requesting (eg, /foo/bar)
        """
        request = self.create_request(path, method, **kwargs)
        response = asyncio.run(self.application.create_response())
        asyncio.run(self.application.handle(request, response))
        return response

    def post(self, path, body_kwargs, **kwargs):
        return self.handle(path, method="POST", body_kwargs=body_kwargs, **kwargs)

    def get(self, path, query_kwargs, **kwargs):
        return self.handle(path, method="GET", query_kwargs=query_kwargs, **kwargs)

    def find(self, path="", method="GET", **kwargs):
        request = self.create_request(path, method, **kwargs)
        return asyncio.run(
            self.application.find_controller_info(request, **kwargs)
        )


#     def path(self, *args):
#         bits = [""]
#         pout.v(self.controller.name)
#         bits.append(self.controller.name)
#         bits.extend(args)
#         return "/".join(bits)


class TestCase(testdata.TestCase):
    server = None

    server_class = Server

    application_class = BaseApplication

    def get_host(self):
        return environ.HOST

    def create_server(self, contents="", config_contents="", **kwargs):
        if contents:
            tdm = self.create_controller_module(contents, **kwargs)
            kwargs["cwd"] = tdm.basedir
            kwargs["controller_prefix"] = tdm

        kwargs["host"] = self.get_host()

        if config_contents:
            config_path = testdata.create_file(
                data=config_contents,
                ext=".py",
            )
            kwargs["config_path"] = config_path

        server = self.server_class(**kwargs)
        server.stop()
        server.start()
        self.server = server
        return server

    def create_controller_module(self, contents, **kwargs):
        if isinstance(contents, dict):
            controller_prefix = kwargs.get("controller_prefix", "")
            if not controller_prefix:
                controller_prefix = testdata.get_module_name()

            basedir = testdata.create_modules({controller_prefix: contents})
            controller_prefix = basedir.modpath(controller_prefix)

        else:
            controller_prefix = testdata.create_module(
                data=contents,
                modpath=kwargs.get("controller_prefix", "")
            )

        return controller_prefix

    def create_application(self, *args, **kwargs):
        return self.application_class(*args, **kwargs)

#     def create_request(self, path="", method="GET"):
#         request = Request()
#         request.method = method
#         request.path = path
#         return request

