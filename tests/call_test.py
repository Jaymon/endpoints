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


class CallTest(TestCase):
    def test_routing_error_unexpected_args(self):
        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(foo=2))
        self.assertEqual(404, res.code)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(che=2))
        self.assertEqual(404, res.code)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(404, res.code)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(409, res.code)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo", query_kwargs=dict(bar=2))
        self.assertEqual(405, res.code)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar")
        self.assertEqual(404, res.code)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo, **kwargs):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(404, res.code)

    def test_routing_error_no_args(self):
        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self):",
            "        pass",
        ])
        res = c.handle("/foo/bar/che/baz/boom/bam/blah")
        self.assertEqual(404, res.code)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, **kwargs):",
            "        pass",
        ])
        res = c.handle("/foo/bar/che/baz/boom/bam/blah", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(404, res.code)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, **kwargs):",
            "        return kwargs",
        ])
        res = c.handle("/", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(200, res.code)
        self.assertTrue("foo" in res._body)

        c = Server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self):",
            "        return kwargs",
        ])
        res = c.handle("/", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(405, res.code)

    def test_lowercase_method(self):
        c = Server("controller2", {"foo2": [
            "from endpoints import Controller",
            "class Bar(Controller):",
            "    def get(*args, **kwargs): pass"
        ]})

        res = c.handle("/foo2/bar", query_kwargs={'foo2': 'bar', 'che': 'baz'})
        self.assertEqual(501, res.code)

    def test_handle_redirect(self):
        c = Server("controllerhr", {"handle": [
            "from endpoints import Controller, Redirect",
            "class Testredirect(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise Redirect('http://example.com')"
        ]})

        res = c.handle("/handle/testredirect")
        self.assertEqual(302, res.code)
        self.assertEqual('http://example.com', res.headers['Location'])

    def test_handle_404_typeerror_1(self):
        """make sure not having a controller is correctly identified as a 404"""
        c = Server(contents=[
            "from endpoints import Controller, Redirect",
            "class NoFoo(Controller):",
            "    def GET(*args, **kwargs):",
            "        pass",
        ])

        res = c.handle("/foo/boom")
        self.assertEqual(404, res.code)

    def test_handle_405_typeerror_2(self):
        """make sure 405 works when a path bit is missing"""
        controller_prefix = "h404te2"
        c = Server(controller_prefix, [
            "from endpoints import Controller, decorators",
            "class Default(Controller):",
            "    def GET(self, needed_bit, **kwargs):",
            "       return ''",
            "",
            "    def POST(self, needed_bit, **kwargs):",
            "       return ''",
            "",
            "class Htype(Controller):",
            "    def POST(self, needed_bit, **kwargs):",
            "       return ''",
            "",
            "class Hdec(Controller):",
            "    @decorators.param('foo', default='bar')",
            "    def POST(self, needed_bit, **kwargs):",
            "       return ''",
            "",
        ])

        res = c.handle("/hdec", "POST")
        self.assertEqual(405, res.code)

        res = c.handle("/htype", "POST")
        self.assertEqual(405, res.code)

        res = c.handle("/")
        self.assertEqual(405, res.code)

        res = c.handle("/", "POST")
        self.assertEqual(405, res.code)

    def test_handle_404_typeerror_3(self):
        """there was an error when there was only one expected argument, turns out
        the call was checking for "arguments" when the message just had "argument" """
        c = Server(contents=[
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
        ])

        res = c.handle("/foo/bar/baz", query='che=1&boo=2')
        self.assertEqual(404, res.code)

    def test_handle_accessdenied(self):
        """raising an AccessDenied error should set code to 401 and the correct header"""
        controller_prefix = "haccessdenied"
        c = Server(controller_prefix, [
            "from endpoints import Controller, AccessDenied",
            "class Default(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise AccessDenied(scheme='basic')",
            "class Bar(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise AccessDenied()",
        ])

        res = c.handle("/")
        self.assertEqual(401, res.code)
        self.assertTrue('Basic' in res.headers['WWW-Authenticate'])

        res = c.handle("/bar")
        self.assertEqual(401, res.code)
        self.assertTrue('Auth' in res.headers['WWW-Authenticate'])

    def test_handle_callstop(self):
        controller_prefix = "handlecallstop"
        c = Server(controller_prefix, [
            "from endpoints import Controller, CallStop",
            "class Testcallstop(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise CallStop(205, None)",
            "",
            "class Testcallstop2(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise CallStop(200, 'this is the body')",
            "",
            "class Testcallstop3(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise CallStop(204, 'this is ignored')",
        ])

        res = c.handle("/testcallstop")
        self.assertEqual(None, res.body)
        self.assertEqual(None, res._body)
        self.assertEqual(205, res.code)

        res = c.handle("/testcallstop2")
        self.assertEqual("this is the body", res.body)
        self.assertEqual(200, res.code)

        res = c.handle("/testcallstop3")
        self.assertEqual(None, res._body)
        self.assertEqual(204, res.code)

    def test_nice_error_405(self):
        controller_prefix = "nicerr405"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self, bar): pass",
            "",
        ])

        # TODO -- capture stdout to make sure the error printed out, until then
        # you will just have to manually check to make sure the warning was raised
        # correctly
        res = c.handle("/foo/bar/che")

    def test_handle_method_chain(self):
        controller_prefix = "handle_method_chain"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def handle_GET(self, *args, **kwargs):",
            "        self.response.handle_GET_called = True",
            "        self.handle(*args, **kwargs)",
            "",
            "    def handle(self, *args, **kwargs):",
            "        self.response.handle_called = True",
            "        super(Foo, self).handle(*args, **kwargs)",
            "",
            "    def GET(self, *args, **kwargs):",
            "        self.response.GET_called = True",
            "",
        ])

        res = c.handle("/foo")
        self.assertTrue(res.handle_GET_called)
        self.assertTrue(res.handle_called)
        self.assertTrue(res.GET_called)


class CallVersioningTest(TestCase):
    def test_get_version(self):
        r = Request()
        r.set_header('accept', 'application/json;version=v1')

        v = r.version()
        self.assertEqual("v1", v)

        v = r.version("application/json")
        self.assertEqual("v1", v)

        v = r.version("plain/text")
        self.assertEqual("", v)

    def test_get_version_default(self):
        """turns out, calls were failing if there was no accept header even if there were defaults set"""
        r = Request()
        r.headers = {}
        self.assertEqual("", r.version('application/json'))

        r = Request()
        r.set_header('accept', 'application/json;version=v1')
        self.assertEqual('v1', r.version())

        r = Request()
        r.set_header('accept', '*/*')
        self.assertEqual("", r.version('application/json'))

        r = Request()
        r.set_header('accept', '*/*;version=v8')
        self.assertEqual('v8', r.version('application/json'))

