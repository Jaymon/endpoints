from unittest import TestCase
import os
import urlparse
import json
import logging

import testdata

import endpoints
import endpoints.call


logging.basicConfig()


def create_modules(controller_prefix):
    r = testdata.create_modules({
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
    })

    s = set([
        controller_prefix,
        '{}.foo.baz'.format(controller_prefix),
        '{}.default'.format(controller_prefix),
        '{}.foo'.format(controller_prefix)
    ])
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
        self.assertEqual(req.headers['Access-Control-Request-Method'], c.response.headers['Access-Control-Allow-Method']) 
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


class ResponseTest(TestCase):
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
        statuses = r.statuses
        for code, status in statuses.iteritems():
            r.code = code
            self.assertEqual(status, r.status)
            r.code = None
            r.status = None

        r = endpoints.Response()
        r.code = 1000
        self.assertEqual("UNKNOWN", r.status)

    def test_body(self):
        b = {'foo': 'bar'}

        r = endpoints.Response()
        self.assertEqual(None, r.body)
        r.body = b
        self.assertEqual(b, r.body)

        r = endpoints.Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = b
        self.assertEqual(json.dumps(b), r.body)

        r = endpoints.Response()
        self.assertEqual(None, r.body)
        self.assertEqual(None, r.body) # Make sure it doesn't change
        r.body = b
        self.assertEqual(b, r.body)

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

        # TODO: this really needs to be tested with unicode data

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
        del(r._code)
        self.assertEqual(204, r.code)


class RequestTest(TestCase):

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
        self.assertEqual(body_r, r.body)

        r.body = u""
        body_r = {}
        self.assertEqual(body_r, r.body)

        r.headers = {
            'content-type': u"application/json",
        }
        r.body = '{"person":{"name":"bob"}}'
        body_r = {u'person': {"name":"bob"}}
        self.assertEqual(body_r, r.body)

        r.body = u""
        body_r = None
        self.assertEqual(body_r, r.body)

        r.headers = {}
        body = '{"person":{"name":"bob"}}'
        r.body = body
#        with self.assertRaises(ValueError):
#            r.body
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

    def test_get_controller_info_advanced(self):
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

            d = c.get_controller_info_advanced()
            for key, val in t['out'].iteritems():
                self.assertEqual(val, d[key])

    def test_get_controller_info_simple(self):
        """while the method should work in real life with valid controller modules
        I haven't updated this test to use testdata.create_modules, so I'm just
        disabling it for right now"""
        return
        class MockRequest(object): pass

        r = MockRequest()
        r.path_args = [u'user', u'verify_credentials']
        r.query_kwargs = {}
        r.method = u"GET"
        out_d = {
            'class_name': u"Verify_credentials",
            'args': [],
            'method': u"GET",
            'module': u"controller.user",
            'kwargs': {}
        }

        c = endpoints.Call("controller")
        c.request = r

        d = c.get_controller_info_simple()
        self.assertEqual(d, out_d)

        r = MockRequest()
        r.path_args = [u"foo", u"bar"]
        r.query_kwargs = {u'foo': u'bar', u'che': u'baz'}
        r.method = u"GET"

        out_d = {
            'class_name': u"Bar",
            'args': [],
            'method': u"GET",
            'module': u"controller.foo",
            'kwargs':
                {
                    'foo': u"bar",
                    'che': u"baz"
                }
        }

        c = endpoints.Call("controller")
        c.request = r

        d = c.get_controller_info_simple()
        self.assertEqual(d, out_d)

        r.path_args.append(u"che")
        out_d['args'].append(u"che")

        d = c.get_controller_info()
        self.assertEqual(d, out_d)

        r.path_args = []
        out_d['args'] = []
        out_d['module'] = u'controller.default'
        out_d['class_name'] = u'Default'

        d = c.get_controller_info_simple()
        self.assertEqual(d, out_d)

    def test_callback_info(self):
        controller_prefix = "callback_info"
        class MockRequest(object): pass
        r = MockRequest()
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
        class MockRequest(object): pass
        r = MockRequest()
        r.path = u"/foo2/bar"
        r.path_args = [u"foo2", u"bar"]
        r.query_kwargs = {u'foo2': u'bar', u'che': u'baz'}
        r.method = u"GET"
        c = endpoints.Call("controller")
        c.request = r

        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Bar(Controller):",
            "    def get(*args, **kwargs): pass"
        ])
        testdata.create_module("controller.foo2", contents=contents)

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
        testdata.create_module("controller.handle", contents=contents)

        class MockRequest(object): pass
        r = MockRequest()
        r.path = u"/handle/testredirect"
        r.path_args = [u'handle', u'testredirect']
        r.query_kwargs = {}
        r.method = u"GET"
        c = endpoints.Call("controller")
        c.request = r

        res = c.handle()
        self.assertEqual(302, res.code)
        self.assertEqual('http://example.com', res.headers['Location'])


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
                "import endpoints",
                "class Default(endpoints.Controller):",
                "    @dec_func",
                "    def GET(*args, **kwargs): pass",
                "    @dec_cls",
                "    def POST(*args, **kwargs): pass",
                ""
            ])
        })

        r = endpoints.Reflect("controller_reflect")
        l = r.get_endpoints()
        self.assertEqual(1, len(l))
        self.assertEqual(u'/foo', l[0]['endpoint'])
        self.assertEqual(['GET', 'POST'], l[0]['options'])

    def test_walk_files(self):

        tmpdir, ds, fs = testdata.create_file_structure(os.linesep.join([
            "foo/",
            "  __init__.py",
            "  bar/",
            "    __init__.py",
            "    che.py",
            "  baz/",
            "    __init__.py",
            "    boom/",
            "      __init__.py",
            "      pez.py",
            ""
        ]))

        r = endpoints.Reflect("foo")
        count = 0
        for f in r.walk_files(tmpdir):
            count += 1
            self.assertTrue(f[0] in fs)

        self.assertEqual(len(fs), count)


    def test_normalize_controller_module(self):

        r = endpoints.Reflect("controller_reflect")
        r._controller_path = "/some/long/path/controller_reflect"

        name = r.normalize_controller_module("/some/long/path/controller_reflect/foo/bar.py")
        self.assertEqual("controller_reflect.foo.bar", name)

        name = r.normalize_controller_module("/some/long/path/controller_reflect/__init__.py")
        self.assertEqual("controller_reflect", name)

        name = r.normalize_controller_module("/some/long/path/controller_reflect/foo/__init__.py")
        self.assertEqual("controller_reflect.foo", name)

    def test_get_endpoints(self):
        # putting the C back in CRUD
        tmpdir = testdata.create_dir("reflecttest")
        testdata.create_modules(
            {
                "controller_reflect": os.linesep.join([
                    "import endpoints",
                    "class Default(endpoints.Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect.foo": os.linesep.join([
                    "import endpoints",
                    "class Default(endpoints.Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect.che": os.linesep.join([
                    "from endpoints import Controller",
                    "class Baz(Controller):",
                    "    def POST(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect.che.bam": os.linesep.join([
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

        r = endpoints.Reflect("controller_reflect")
        l = r.get_endpoints()
        self.assertEqual(5, len(l))

        def get_match(endpoint, l):
            for d in l:
                if d['endpoint'] == endpoint:
                    return d

        d = get_match("/che/bam/bah", l)
        self.assertEqual(d['options'], ["GET", "HEAD"])
        self.assertGreater(len(d['doc']), 0)

        d = get_match("/", l)
        self.assertNotEqual(d, {})

        d = get_match("/foo", l)
        self.assertNotEqual(d, {})


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

        r = endpoints.VersionReflect("controller_vreflect", 'application/json')
        l = r.get_endpoints()

        self.assertEqual(2, len(l))
        for d in l:
            self.assertTrue('headers' in d)
            self.assertTrue("version" in d)

        def get_match(endpoint, l):
            ret = {}
            for d in l:
                if d['endpoint'] == endpoint:
                    ret = d
            return ret

        d = get_match("/foo/bar", l)
        self.assertNotEqual({}, d)


class EndpointsTest(TestCase):
    def test_get_controllers(self):
        controller_prefix = "get_controllers"
        s = create_modules(controller_prefix)

        controllers = endpoints.call.get_controllers(controller_prefix)
        self.assertEqual(s, controllers)

        # just making sure it always returns the same list
        controllers = endpoints.call.get_controllers(controller_prefix)
        self.assertEqual(s, controllers)

