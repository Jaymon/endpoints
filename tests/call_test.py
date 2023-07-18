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


class RouterTest(TestCase):
    def get_http_instances(self, path="", method="GET"):
        req = Request()
        req.method = method
        req.path = path
        res = Response()
        return req, res

    def test_multiple_controller_prefixes_1(self):
        r = testdata.create_modules({
            "foo": os.linesep.join([
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ]),
            "bar": os.linesep.join([
                "from endpoints import Controller",
                "class User(Controller): pass",
            ]),
        })
        r = Router(["foo", "bar"])

        t = r.find(*self.get_http_instances("/user"))
        self.assertTrue("bar", t["module_name"])

        t = r.find(*self.get_http_instances("/che"))
        self.assertTrue("foo", t["module_name"])


    def test_routing(self):
        """there was a bug that caused errors raised after the yield to return another
        iteration of a body instead of raising them"""
        controller_prefix = "routing1"
        contents = [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self): pass",
            "",
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
            "class Bar(Controller):",
            "    def GET(self): pass",
        ]
        testdata.create_module(controller_prefix, contents=contents)

        r = Router([controller_prefix])
        info = r.find(*self.get_http_instances())
        self.assertEqual(info['module_name'], controller_prefix)
        self.assertEqual(info['class_name'], "Default")

        r = Router([controller_prefix])
        info = r.find(*self.get_http_instances("/foo/che/baz"))
        self.assertEqual(2, len(info['method_args']))
        self.assertEqual(info['class_name'], "Foo")

    def test_default_match_with_path(self):
        """when the default controller is used, make sure it falls back to default class
        name if the path bit fails to be a controller class name"""
        controller_prefix = "nomodcontroller2"
        c = Server(controller_prefix, {"nmcon": [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self, *args, **kwargs):",
            "        return args[0]"
        ]})
        res = c.handle('/nmcon/8')
        self.assertEqual("8", res.body)

    def test_no_match(self):
        """make sure a controller module that imports a class with the same as
        one of the query args doesen't get picked up as the controller class"""
        controller_prefix = "nomodcontroller"
        contents = {
            "{}.nomod".format(controller_prefix): [
                "class Nomodbar(object): pass",
                ""
            ],
            controller_prefix: [
                "from endpoints import Controller",
                "from .nomod import Nomodbar",
                "class Default(Controller):",
                "    def GET(): pass",
                ""
            ]
        }
        m = testdata.create_modules(contents)

        path = '/nomodbar' # same name as one of the non controller classes
        r = Router([controller_prefix])
        info = r.find(*self.get_http_instances(path))
        self.assertEqual('Default', info['class_name'])
        self.assertEqual('nomodcontroller', info['module_name'])
        self.assertEqual('nomodbar', info['method_args'][0])

    def test_import_error(self):

        controller_prefix = "importerrorcontroller"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "from does_not_exist import FairyDust",
            "class Default(Controller):",
            "    def GET(): pass",
            ""
        ])
        res = c.handle('/')
        self.assertEqual(404, res.code)

    def test_get_controller_info_default(self):
        """I introduced a bug on 1-12-14 that caused default controllers to fail
        to be found, this makes sure that bug is squashed"""
        controller_prefix = "controller_info_default"
        r = testdata.create_modules({
            controller_prefix: os.linesep.join([
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(): pass",
                ""
            ])
        })

        r = Router([controller_prefix])
        info = r.find(*self.get_http_instances("/"))
        self.assertEqual('Default', info['class_name'])
        self.assertTrue(issubclass(info['class'], Controller))

    def test_callback_info(self):
        controller_prefix = "callback_info"
        req, res = self.get_http_instances("/foo/bar")
        req.query_kwargs = {'foo': 'bar', 'che': 'baz'}

        r = Router([controller_prefix])

        with self.assertRaises(ImportError):
            d = r.find(req, res)

        contents = [
            "from endpoints import Controller",
            "class Bar(Controller):",
            "    def GET(*args, **kwargs): pass"
        ]
        testdata.create_module("{}.foo".format(controller_prefix), contents=contents)

        # if it succeeds, then it passed the test :)
        d = r.find(req, res)

    def test_get_controller_info(self):
        controller_prefix = "controller_info_advanced"
        r = testdata.create_modules({
            controller_prefix: [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
            "{}.default".format(controller_prefix): [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
            "{}.foo".format(controller_prefix): [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                "",
                "class Bar(Controller):",
                "    def GET(*args, **kwargs): pass",
                "    def POST(*args, **kwargs): pass",
                ""
            ],
            "{}.foo.baz".format(controller_prefix): [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                "",
                "class Che(Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
            "{}.foo.boom".format(controller_prefix): [
                "from endpoints import Controller",
                "",
                "class Bang(Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
        })

        ts = [
            {
                'in': dict(method="GET", path="/foo/bar/happy/sad"),
                'out': {
                    'module_name': "controller_info_advanced.foo",
                    'class_name': 'Bar',
                    'method_args': ['happy', 'sad'],
                    #'method_name': "GET",
                }
            },
            {
                'in': dict(method="GET", path="/"),
                'out': {
                    'module_name': "controller_info_advanced",
                    'class_name': 'Default',
                    'method_args': [],
                    #'method_name': "GET",
                }
            },
            {
                'in': dict(method="GET", path="/happy"),
                'out': {
                    'module_name': "controller_info_advanced",
                    'class_name': 'Default',
                    'method_args': ["happy"],
                    #'method_name': "GET",
                }
            },
            {
                'in': dict(method="GET", path="/foo/baz"),
                'out': {
                    'module_name': "controller_info_advanced.foo.baz",
                    'class_name': 'Default',
                    'method_args': [],
                    #'method_name': "GET",
                }
            },
            {
                'in': dict(method="GET", path="/foo/baz/che"),
                'out': {
                    'module_name': "controller_info_advanced.foo.baz",
                    'class_name': 'Che',
                    'method_args': [],
                    #'method_name': "GET",
                }
            },
            {
                'in': dict(method="GET", path="/foo/baz/happy"),
                'out': {
                    'module_name': "controller_info_advanced.foo.baz",
                    'class_name': 'Default',
                    'method_args': ["happy"],
                    #'method_name': "GET",
                }
            },
            {
                'in': dict(method="GET", path="/foo/happy"),
                'out': {
                    'module_name': "controller_info_advanced.foo",
                    'class_name': 'Default',
                    'method_args': ["happy"],
                    #'method_name': "GET",
                }
            },
        ]

        for t in ts:
            req, res = self.get_http_instances(**t['in'])

            r = Router([controller_prefix])
            d = r.find(req, res)
            for key, val in t['out'].items():
                self.assertEqual(val, d[key])

