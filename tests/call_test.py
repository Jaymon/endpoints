# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from . import TestCase, skipIf, SkipTest, Server
import os

import testdata

import endpoints
from endpoints.environ import *
from endpoints.utils import ByteString
from endpoints.http import Request, Response
from endpoints.call import Controller, Router
from endpoints.exception import CallError


class ControllerTest(TestCase):
    def test_any_1(self):
        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def ANY(self):",
            "        return 'any'",
        ])

        res = c.handle("/")
        self.assertEqual(200, res.code)
        self.assertEqual("any", res.body)

        res = c.handle("/", method="POST")
        self.assertEqual(200, res.code)
        self.assertEqual("any", res.body)

        res = c.handle("/foo/bar")
        self.assertEqual(404, res.code)

    def test_any_2(self):
        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def ANY(self, **kwargs):",
            "        return 'any'",
            "    def POST(self, **kwargs):",
            "        return 'post'",
        ])

        res = c.handle("/")
        self.assertEqual(200, res.code)
        self.assertEqual("any", res.body)

        res = c.handle("/", method="POST")
        self.assertEqual(200, res.code)
        self.assertEqual("post", res.body)

    def test_unsupported_method_404(self):
        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def POST(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar")
        self.assertEqual(404, res.code)

        res = c.handle("/foo")
        self.assertEqual(404, res.code)

        res = c.handle("/")
        self.assertEqual(501, res.code)

    def test_cors(self):
        class Cors(Controller):
            def __init__(self, *args, **kwargs):
                super(Cors, self).__init__(*args, **kwargs)
                self.handle_cors()
            def POST(self): pass

        res = Response()
        req = Request()
        c = Cors(req, res)
        self.assertTrue(c.OPTIONS)
        self.assertFalse('Access-Control-Allow-Origin' in c.response.headers)

        req.set_header('Origin', 'http://example.com')
        c = Cors(req, res)
        self.assertEqual(req.get_header('Origin'), c.response.get_header('Access-Control-Allow-Origin')) 

        req.set_header('Access-Control-Request-Method', 'POST')
        req.set_header('Access-Control-Request-Headers', 'xone, xtwo')
        c = Cors(req, res)
        c.OPTIONS()
        self.assertEqual(req.get_header('Origin'), c.response.get_header('Access-Control-Allow-Origin'))
        self.assertEqual(req.get_header('Access-Control-Request-Method'), c.response.get_header('Access-Control-Allow-Methods')) 
        self.assertEqual(req.get_header('Access-Control-Request-Headers'), c.response.get_header('Access-Control-Allow-Headers')) 

        c = Cors(req, res)
        c.POST()
        self.assertEqual(req.get_header('Origin'), c.response.get_header('Access-Control-Allow-Origin')) 

    def test_bad_typeerror(self):
        """There is a bug that is making the controller method is throw a 404 when it should throw a 500"""
        c = Server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self):",
            "        raise TypeError('This should not cause a 404')"
        ])
        res = c.handle('/')
        self.assertEqual(500, res.code)

        c = Server(contents=[
            "from endpoints import Controller",
            "class Bogus(object):",
            "    def handle_controller(self, foo):",
            "        pass",
            "",
            "class Default(Controller):",
            "    def GET(self):",
            "        b = Bogus()",
            "        b.handle_controller()",
        ])
        res = c.handle('/')
        self.assertEqual(500, res.code)

