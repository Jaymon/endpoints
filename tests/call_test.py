# -*- coding: utf-8 -*-
import asyncio

from requests.auth import _basic_auth_str

from endpoints.compat import *
from endpoints.utils import ByteString
from endpoints.call import Controller, Request, Response, Router

from . import TestCase, testdata


class ControllerTest(TestCase):
    def test_any_1(self):
        c = self.create_server([
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
        c = self.create_server([
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
        c = self.create_server([
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
                super().__init__(*args, **kwargs)
                self.handle_cors()
            def POST(self): pass

        res = Response()
        req = Request()
        c = Cors(req, res)
        self.assertTrue(c.OPTIONS)
        self.assertFalse('Access-Control-Allow-Origin' in c.response.headers)

        req.set_header('Origin', 'http://example.com')
        c = Cors(req, res)
        self.assertEqual(
            req.get_header('Origin'),
            c.response.get_header('Access-Control-Allow-Origin')
        ) 

        req.set_header('Access-Control-Request-Method', 'POST')
        req.set_header('Access-Control-Request-Headers', 'xone, xtwo')
        c = Cors(req, res)
        asyncio.run(c.OPTIONS())
        self.assertEqual(
            req.get_header('Origin'),
            c.response.get_header('Access-Control-Allow-Origin')
        )
        self.assertEqual(
            req.get_header('Access-Control-Request-Method'),
            c.response.get_header('Access-Control-Allow-Methods')
        ) 
        self.assertEqual(
            req.get_header('Access-Control-Request-Headers'),
            c.response.get_header('Access-Control-Allow-Headers')
        ) 

        c = Cors(req, res)
        c.POST()
        self.assertEqual(
            req.get_header('Origin'),
            c.response.get_header('Access-Control-Allow-Origin')
        ) 

    def test_bad_typeerror(self):
        """There is a bug that is making the controller method throw a 404 when
        it should throw a 500"""
        c = self.create_server([
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self):",
            "        raise TypeError('This should not cause a 404')"
        ])
        res = c.handle('/')
        self.assertEqual(500, res.code)

        c = self.create_server([
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

    def test_get_module_path_args(self):
        modpath = self.create_module(
            [
                "from endpoints import Controller",
                "",
                "class Foo(Controller):",
                "    def GET(self):",
                "        pass",
            ],
            modpath=self.get_module_name(3)
        )

        foo_class = modpath.get_module().Foo
        parts = modpath.split(".")

        # make sure the anywhere syntax (eg, .<PREFIX>) works
        self.assertEqual(
            [parts[2]],
            foo_class.get_module_path_args([f".{parts[1]}"])
        )

        # make sure a normal prefix works
        mp = ".".join(parts[:-1])
        self.assertEqual([parts[2]], foo_class.get_module_path_args([mp]))

        # we want to make sure we can't just match the beginning of a module
        # path segment
        mp = f".{parts[1][:3]}"
        self.assertEqual(parts, foo_class.get_module_path_args([mp]))

        self.assertEqual([], foo_class.get_module_path_args([modpath]))

    def test_get_class_path_args(self):
        foo_class = self.create_module_class(
            [
                "from endpoints import Controller",
                "",
                "class Foo(Controller):",
                "    def GET(self):",
                "        pass",
            ]
        )

        path_args = foo_class.get_class_path_args()
        self.assertEqual(["foo"], path_args)

        path_args = foo_class.get_class_path_args("Foo")
        self.assertEqual([], path_args)


class RouterTest(TestCase):

    def test_paths_depth_1(self):
        for cb in [self.create_module, self.create_package]:
            modpath = cb(
                [
                    "from endpoints import Controller",
                    "",
                    "class Foo(Controller): pass"
                ],
                modpath=self.get_module_name(count=2, name="controllers")
            )

            cs = Router(paths=[modpath.basedir])
            self.assertTrue(
                issubclass(cs._controller_pathfinder["foo"], Controller)
            )

    def test_paths_depth_n(self):
        for cb in [self.create_module, self.create_package]:
            modpath = cb(
                [
                    "from endpoints import Controller",
                    "",
                    "class Foo(Controller): pass",
                    "class Bar(Controller): pass",
                    "class Default(Controller): pass",
                ],
                modpath=self.get_module_name(count=2, name="controllers")
            )

            cs = Router(paths=[modpath.basedir])

            for k in ["foo", "bar", ""]:
                self.assertTrue(
                    issubclass(cs._controller_pathfinder[k], Controller)
                )

    def test_pathfinder_1(self):
        modpath = self.get_module_name(count=2, name="controllers")
        basedir = self.create_modules({
            modpath: [
                "from endpoints import Controller",
                "",
                "class One(Controller): pass",
                "class Default(Controller): pass",
            ],
            "bar": [
                "from endpoints import Controller",
                "",
                "class Two(Controller): pass",
            ]
        })

        # load bar so the controllers load into memory
        basedir.get_module("bar")

        cs = Router(
            controller_prefixes=[modpath],
        )

        self.assertEqual(1, len(cs._controller_modules))
        self.assertTrue(modpath in cs._controller_modules)
        for k in ["one", "two", ""]:
            self.assertTrue(
                issubclass(cs._controller_pathfinder[k], Controller)
            )

    def test_pathfinder_2(self):
        """test a multiple submodule controller"""
        modpath = self.get_module_name(count=2, name="controllers")
        basedir = self.create_modules({
            modpath: {
                "bar": [
                    "from endpoints import Controller",
                    "",
                    "class One(Controller): pass",
                    "class Default(Controller): pass",
                ],
                "che": {
                    "boo": [
                        "from endpoints import Controller",
                        "",
                        "class Two(Controller): pass",
                        "class Default(Controller): pass",
                    ],
                },
            },
        })

        cs = Router(
            paths=[basedir],
        )

        controller_path_args = [
            ["che", "boo", "two"],
            ["che", "boo", ""],
            ["bar", "one"],
            ["bar", ""],
        ]

        for path_args in controller_path_args:
            self.assertTrue(issubclass(
                cs._controller_pathfinder[path_args],
                Controller
            ))

    def test_pathfinder_3(self):
        """test non-python module subpath (eg, pass in foo/ as the paths and
        then have foo/bin/MODULE/controllers.py where foo/bin is not a module
        """
        cwd = self.create_dir()
        modpath = self.get_module_name(count=2, name="controllers")

        basedir = self.create_modules(
            {
                modpath: {
                    "bar": [
                        "from endpoints import Controller",
                        "",
                        "class One(Controller): pass",
                        "class Default(Controller): pass",
                    ],
                    "che": {
                        "boo": [
                            "from endpoints import Controller",
                            "",
                            "class Two(Controller): pass",
                            "class Default(Controller): pass",
                        ],
                    },
                },
            },
            tmpdir=cwd.child_dir("src")
        )

        cs = Router(
            paths=[cwd],
        )

        controller_path_args = [
            ["che", "boo", "two"],
            ["che", "boo", ""],
            ["bar", "one"],
            ["bar", ""],
        ]

        for path_args in controller_path_args:
            self.assertTrue(issubclass(
                cs._controller_pathfinder[path_args],
                Controller
            ))

    def test_find_controller_1(self):
        modpath = self.get_module_name(count=2, name="controllers")
        basedir = self.create_modules({
            modpath: {
                "bar": [
                    "from endpoints import Controller",
                    "",
                    "class One(Controller): pass",
                    "class Default(Controller): pass",
                ],
                "che": {
                    "boo": [
                        "from endpoints import Controller",
                        "",
                        "class Two(Controller): pass",
                        "class Default(Controller): pass",
                    ],
                },
            },
        })

        cs = Router(controller_prefixes=[modpath])

        r = cs.find_controller(["bar", "one", "arg1", "arg2"])
        self.assertEqual("One", r[0].__name__)
        self.assertEqual(2, len(r[1]))

        r = cs.find_controller(["bar", "arg1", "arg2", "arg3"])
        self.assertEqual("Default", r[0].__name__)
        self.assertEqual(3, len(r[1]))

        r = cs.find_controller(["che", "boo", "arg1", "arg2", "arg3"])
        self.assertEqual("Default", r[0].__name__)
        self.assertEqual(3, len(r[1]))

        r = cs.find_controller(["che", "boo", "two", "arg1", "arg2"])
        self.assertEqual("Two", r[0].__name__)
        self.assertEqual(2, len(r[1]))

        r = cs.find_controller(["che", "boo", "two"])
        self.assertEqual("Two", r[0].__name__)
        self.assertEqual(0, len(r[1]))

        r = cs.find_controller(["che", "boo"])
        self.assertEqual("Default", r[0].__name__)
        self.assertEqual(0, len(r[1]))

        with self.assertRaises(TypeError):
            cs.find_controller(["does", "not", "exist"])


class RequestTest(TestCase):
    def test_get_auth_scheme(self):
        r = Request()
        r.set_headers({
            "Authorization": "Basic FOOBAR",
        })

        self.assertEqual("Basic", r.get_auth_scheme())
        self.assertTrue(r.is_auth("basic"))
        self.assertTrue(r.is_auth("Basic"))
        self.assertFalse(r.is_auth("bearer"))

        r.headers["Authorization"] = "BLAH_TOKEN"
        self.assertEqual("", r.get_auth_scheme())
        self.assertFalse(r.is_auth("basic"))

    def test_is_oauth(self):
        username = "foo"
        password = "bar"
        r = Request()

        r.set_headers({"Authorization": _basic_auth_str(username, password)})
        self.assertTrue(r.is_oauth("basic"))
        self.assertTrue(r.is_oauth("client"))
        self.assertFalse(r.is_oauth("token"))
        self.assertFalse(r.is_oauth("access"))

        r.headers["Authorization"] = "Bearer FOOBAR"
        self.assertFalse(r.is_oauth("basic"))
        self.assertFalse(r.is_oauth("client"))
        self.assertTrue(r.is_oauth("token"))
        self.assertTrue(r.is_oauth("access"))

        r.headers.pop("Authorization")
        self.assertFalse(r.is_oauth("basic"))
        self.assertFalse(r.is_oauth("client"))
        self.assertFalse(r.is_oauth("token"))
        self.assertFalse(r.is_oauth("access"))

    def test_copy(self):
        r = Request()
        r.set_headers({
            "Host": "localhost",
        })
        r.query = "foo=bar"
        r.path = "/baz/che"
        r.scheme = "http"
        r.port = "80"
        r.foo = 1

        r2 = r.copy()
        self.assertEqual(r.foo, r2.foo)
        self.assertEqual(r.port, r2.port)

        r2.headers["foo"] = "bar"
        self.assertFalse("foo" in r.headers)
        self.assertTrue("foo" in r2.headers)

    def test_url(self):
        """make sure the .url attribute is correctly populated"""
        # this is wsgi configuration
        r = Request()
        r.set_headers({
            "Host": "localhost",
        })
        r.query = "foo=bar"
        r.path = "/baz/che"
        r.scheme = "http"
        r.port = "80"
        u = r.url
        self.assertEqual("http://localhost/baz/che?foo=bar", r.url)
        r.port = 555
        u = r.url
        self.assertEqual("http://localhost:555/baz/che?foo=bar", r.url)

        # handle proxied connections
        r.host = "localhost:10000"
        r.port = "9000"
        u = r.url
        self.assertTrue(":10000" in u)

    def test_charset(self):
        r = Request()
        r.set_header("content-type", "application/json;charset=UTF-8")
        charset = r.encoding
        self.assertEqual("UTF-8", charset)

        r = Request()
        r.set_header("content-type", "application/json")
        charset = r.encoding
        self.assertEqual(None, charset)

    def test_ip(self):
        r = Request()
        r.set_header('REMOTE_ADDR', '172.252.0.1')
        self.assertEqual('172.252.0.1', r.ip)

        r = Request()
        r.set_header('REMOTE_ADDR', '1.241.34.107')
        self.assertEqual('1.241.34.107', r.ip)

        r = Request()
        r.set_header('x-forwarded-for', '54.241.34.107')
        self.assertEqual('54.241.34.107', r.ip)

        r.set_header('x-forwarded-for', '127.0.0.1, 54.241.34.107')
        self.assertEqual('54.241.34.107', r.ip)

        r.set_header('x-forwarded-for', '127.0.0.1')
        r.set_header('client-ip', '54.241.34.107')
        self.assertEqual('54.241.34.107', r.ip)

    def test_ip_bad(self):
        r = Request()
        r.set_header('REMOTE_ADDR', "10.0.2.2")
        r.set_header(
            "Via",
            "1.1 ironport1.orlando.cit:80 (Cisco-WSA/9.0.1-162)"
        )
        self.assertEqual("", r.ip)

        r = Request()
        r.set_header('REMOTE_ADDR', "54.241.34.107")
        r.set_header(
            "Via",
            "1.1 ironport1.orlando.cit:80 (Cisco-WSA/9.0.1-162)"
        )
        self.assertEqual("54.241.34.107", r.ip)

    def test_properties(self):

        path = '/foo/bar'
        path_args = ['foo', 'bar']

        r = Request()
        r.path = path
        self.assertEqual(r.path, path)
        self.assertEqual(r.path_args, path_args)

        r = Request()
        r.path_args = path_args
        self.assertEqual(r.path, path)
        self.assertEqual(r.path_args, path_args)

        query = "foo=bar&che=baz&foo=che"
        query_kwargs = {'foo': ['bar', 'che'], 'che': 'baz'}

        r = Request()
        r.query = query
        self.assertEqual(
            parse.parse_qs(r.query, True),
            parse.parse_qs(query, True)
        )
        self.assertEqual(r.query_kwargs, query_kwargs)

        r = Request()
        r.query_kwargs = query_kwargs
        self.assertEqual(
            parse.parse_qs(r.query, True),
            parse.parse_qs(query, True)
        )
        self.assertEqual(r.query_kwargs, query_kwargs)

    def test_get_header(self):
        r = Request()

        r.set_headers({
            'foo': 'bar',
            'Content-Type': 'application/json',
            'Happy-days': 'are-here-again'
        })
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
        """turns out, calls were failing if there was no accept header even if
        there were defaults set"""
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


class ResponseTest(TestCase):
    def test_headers(self):
        """make sure headers don't persist between class instantiations"""
        r = Response()
        r.headers["foo"] = "bar"
        self.assertEqual("bar", r.headers["foo"])
        self.assertEqual(1, len(r.headers))

        r = Response()
        self.assertFalse("foo" in r.headers)
        self.assertEqual(0, len(r.headers))

    def test_status(self):
        r = Response()
        for code, status in BaseHTTPRequestHandler.responses.items():
            r.code = code
            self.assertEqual(status[0], r.status)
            r.code = None
            r.status = None

        r = Response()
        r.code = 10000000
        self.assertEqual("UNKNOWN", r.status)

    def test_body_file(self):
        r = Response()
        self.assertFalse("Content-Type" in r.headers)
        self.assertFalse("Content-Length" in r.headers)

        path = testdata.create_file("12345", ext="jpg")
        with path.open() as fp:
            r.body = fp
            mt = r.headers["Content-Type"]
            fs = r.headers["Content-Length"]
            self.assertEqual("image/jpeg", mt)
            self.assertEqual(5, int(fs))

        path = testdata.create_file("123", ext="txt")
        with path.open() as fp:
            r.body = fp
            mt = r.headers["Content-Type"]
            fs = r.headers["Content-Length"]
            self.assertEqual("text/plain", mt)
            self.assertEqual(3, int(fs))

    def test_code(self):
        r = Response()
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

