# -*- coding: utf-8 -*-
import asyncio

import testdata
from testdata import IsolatedAsyncioTestCase as BaseAsyncTestCase

from endpoints.config import environ
from endpoints.interface.base import BaseApplication
from endpoints.call import Request, Controller


testdata.basic_logging(
    levels={
        "datatypes": "WARNING",
        "asyncio": "WARNING",
    },
#     format="|".join([
#         '[%(levelname).1s',
#         '%(asctime)s',
#         '%(process)d.%(thread)d',
#         '%(name)s', # logger name
#         '%(pathname)s:%(lineno)s] %(message)s',
#     ]),
)


class Server(object):
    """This is just a wrapper to get access to the Interface handling code"""
    @property
    def controller_prefix(self):
        return self.application.controller_prefixes[0]

    def __init__(self, *args, **kwargs):
        self.application = BaseApplication(*args, **kwargs)

    def create_request(self, path, method, **kwargs):
        if not (req := kwargs.pop("request", None)):
            req = self.application.create_request(None)
            req.method = method.upper()
            req.path = path

        version = kwargs.pop("version", None)
        if version is not None:
            req.set_header('Accept', '*/*;version={}'.format(version))

        d = dict(kwargs)
        d.setdefault("host", "endpoints.fake")
        for k, v in d.items():
            setattr(req, k, v)

        return req

    def start(self):
        pass

    def stop(self):
        pass

    def handle(self, path="", method="GET", **kwargs):
        """This isn't technically needed but just makes it explicit you pass in
        the path you want and this will translate that and handle the request

        :param path: string, full URI you are requesting (eg, /foo/bar)
        """
        request = self.create_request(path, method, **kwargs)
        response = self.application.create_response()
        asyncio.run(self.application.handle(request, response))

        # makes call.Response look more like client response
        response._body = response.body

        return response

    def post(self, path, body_kwargs=None, **kwargs):
        return self.handle(
            path,
            method="POST",
            body_kwargs=body_kwargs or {},
            **kwargs
        )

    def get(self, path, query_kwargs=None, **kwargs):
        return self.handle(
            path,
            method="GET",
            query_kwargs=query_kwargs or {},
            **kwargs
        )

    def find(self, path="", method="GET", **kwargs):
        kwargs["request"] = self.create_request(path, method, **kwargs)
        return self.application.router.find_controller_info(**kwargs)


class TestCase(BaseAsyncTestCase):
    server = None

    server_class = Server

    application_class = BaseApplication

    def setUp(self):
        Controller.controller_classes = {}

    def get_host(self):
        return environ.HOST

    def create_server(self, contents="", config_contents="", **kwargs):
        # if we don't pass in module contents then we will want to start with
        # a blank slate module, this is because we don't want the autodiscover
        # functionality to trigger during tests
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
        # we reset all the controller classes because if we are requesting a
        # new controller module then we probably want a fresh new start
        # with the loaded controllers
        if not contents:
            contents = [""]

        Controller.controller_classes = {}
        controller_prefix = kwargs.get("controller_prefix", "")

        if "header" in kwargs:
            header = kwargs["header"]

        else:
            header = [
                "from endpoints import *",
                "from endpoints.decorators import *",
            ]

        if not kwargs.get("cors", False):
            header.extend([
                "class Controller(Controller):",
                "    cors = False",
            ])

        controller_prefix = testdata.create_module(
            data=contents,
            modpath=controller_prefix,
            header=header
        )

        return controller_prefix

    def create_application(self, *args, **kwargs):
        return self.application_class(*args, **kwargs)


class IsolatedAsyncioTestCase(TestCase):
    pass

