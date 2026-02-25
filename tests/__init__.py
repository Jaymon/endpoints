# -*- coding: utf-8 -*-
import asyncio
from functools import cached_property

import testdata
from testdata import IsolatedAsyncioTestCase
from datatypes import ReflectName, Host

from endpoints.config import environ
from endpoints.interface.base import Application
from endpoints.call import Request, Controller


testdata.basic_logging(
    levels={
        "datatypes": "WARNING",
        "asyncio": "WARNING",
    },
)


class Server(object):
    @cached_property
    def application(self):
        return ReflectName(self.app_path).resolve()

    def __init__(self, controller_prefix: str, host: str = "", **kwargs):
        self.controller_prefix = controller_prefix
        self.app_path = f"{self.controller_prefix}:application"

        if not host:
            host = environ.HOST

        if host:
            self.server_host = Host(host)

        else:
            self.server_host = Host("0.0.0.0", "4000")

        self.host = self.server_host.client()

    def create_request(self, path, method, **kwargs):
        if not (req := kwargs.pop("request", None)):
            req = self.application.request_class()
            req.method = method.upper()
            req.path = path

        version = kwargs.pop("version", None)
        if version is not None:
            req.set_header('Accept', '*/*;version={}'.format(version))

        d = dict(kwargs)
        d.setdefault("host", self.host)
        for k, v in d.items():
            if k == "query_kwargs":
                k = "query_keywords"

            elif k == "body_kwargs":
                k = "body_keywords"

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
        response = self.application.response_class()
        asyncio.run(self.application.handle(request, response))

        # makes call.Response look more like client response
        response._body = response.body

        return response

    def post(self, path, body_kwargs=None, **kwargs):
        return self.handle(
            path,
            method="POST",
            body=body_kwargs if body_kwargs else None,
            **kwargs
        )

    def get(self, path, query_kwargs=None, **kwargs):
        return self.handle(
            path,
            method="GET",
            query_keywords=query_kwargs or {},
            **kwargs
        )

    def get_request(self, path="", method="GET", **kwargs):
        request = self.create_request(path, method, **kwargs)
        self.application._update_request(request)
        return request

    def find(self, path="", method="GET", **kwargs):
        request = self.get_request(path, method, **kwargs)
        return request.pathfinder_value


class TestCase(IsolatedAsyncioTestCase):
    server_class = Server

    application_class = Application

    def setUp(self):
        Controller.controller_classes = {}

    def get_host(self):
        return environ.HOST

    def create_server(self, contents="", **kwargs):
        # if we don't pass in module contents then we will want to start with
        # a blank slate module, this is because we don't want the autodiscover
        # functionality to trigger during tests
        tdm = self.create_controller_module(contents, **kwargs)
        kwargs["cwd"] = tdm.basedir
        kwargs["controller_prefix"] = tdm
        kwargs["host"] = self.get_host()
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
                "import io",
                "from typing import *",
                "from endpoints import *",
                "from endpoints.decorators import *",
                "from endpoints.compat import *",
                "from {} import {} as Application".format(
                    self.application_class.__module__,
                    self.application_class.__name__,
                ),
            ]

        footer = "application = Application([__name__])"

        if isinstance(contents, dict):
            if "" in contents:
                if isinstance(contents[""], str):
                    contents[""] = [contents[""]]

            else:
                contents.setdefault("", [])

            contents[""].append(footer)
            footer = ""

        controller_prefix = testdata.create_module(
            data=contents,
            modpath=controller_prefix,
            header=header,
            footer=footer,
        )

        return controller_prefix

    def create_application(self, *args, **kwargs):
        return self.application_class(*args, **kwargs)

