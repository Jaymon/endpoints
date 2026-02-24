# -*- coding: utf-8 -*-

from endpoints.compat import *
from endpoints.call import (
    Controller,
    CORSMixin,
    Request,
    Response,
)

from . import TestCase


class ControllerTest(TestCase):
    def test_any_1(self):
        c = self.create_server([
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

    def test_bad_typeerror(self):
        """There is a bug that is making the controller method throw a 404 when
        it should throw a 500"""
        c = self.create_server([
            "class Default(Controller):",
            "    def GET(self):",
            "        raise TypeError('This should not cause a 404')"
        ])
        res = c.handle('/')
        self.assertEqual(500, res.code)

        c = self.create_server([
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

    def test_get_name_ext(self):
        class _FooBar(Controller): pass
        self.assertEqual("_FooBar", _FooBar.get_name())

        class FooBar(Controller): pass
        self.assertEqual("foo-bar", FooBar.get_name())

        class FooBar_txt(Controller): pass
        self.assertEqual("foo-bar.txt", FooBar_txt.get_name())

        class FooBar_(Controller): pass
        self.assertEqual("foo-bar", FooBar_.get_name())

        class Foobar(Controller): pass
        self.assertEqual("foobar", Foobar.get_name())

    def test_get_name_default(self):
        class Default(Controller): pass
        self.assertEqual(None, Default.get_name())

        class Default_html(Controller): pass
        self.assertEqual("index.html", Default_html.get_name())

    def test_ext_mediatype(self):
        """If the endpoint has an extension try and set the media type off
        the extension first"""
        c = self.create_server("""
            class Foo_xml(Controller):
                async def ANY(self) -> str:
                    return ""
        """)
        res = c.handle("/foo.xml")
        self.assertEqual(200, res.code)
        self.assertTrue("application/xml" in res.headers["Content-Type"])

    def test_coroutine_unwind(self):
        """Make sure multiple coroutine unwinds work as expected"""
        c = self.create_server([
            "class Default(Controller):",
            "    async def ANY(self):",
            "        return self.get_coroutine()",
            "",
            "    async def get_coroutine(self):",
            "        return 1"
        ])
        res = c.handle("/")
        self.assertEqual(200, res.code)
        self.assertEqual(1, res.body)

    def test_error_response_code_already_set(self):
        """If the controller body sets a response.code and then an error is
        raised the code should be overridden"""
        """If the controller body sets the response.code don't override it
        even in the error handler"""
        c = self.create_server("""
            class Default(Controller):
                async def ANY(self):
                    self.response.code = 330
                    self.response.body = "this should be overridden"
                    raise ValueError("this should be the body")
        """)

        res = c.handle("/")
        self.assertEqual(500, res.code)
        self.assertTrue(isinstance(res.body, ValueError))

    def test_casting(self):
        c = self.create_server("""
            class Default(Controller):
                async def GET(self, foo: int, bar: int|None = None, /):
                    return {"foo_is_int": isinstance(foo, int)}
        """)

        res = c.handle("/12/")
        self.assertTrue(res.body["foo_is_int"])

    def test_get_response_media_type(self):
        c = self.create_server("""
            class Default(Controller):
                async def GET(self) -> Annotated[str, "plain/text"]:
                    return "success"
        """)

        res = c.handle("/")
        self.assertTrue("plain/text" in res.headers.get("Content-Type"))


class CORSMixinTest(TestCase):
    async def test_cors(self):
        class Cors(Controller, CORSMixin):
            def POST(self): pass

        res = Response()
        req = Request()
        c = Cors(req, res)
        await c.handle_cors()
        self.assertTrue(c.OPTIONS)
        self.assertFalse('Access-Control-Allow-Origin' in c.response.headers)

        req.set_header('Origin', 'http://example.com')
        c = Cors(req, res)
        await c.handle_cors()
        self.assertEqual(
            req.get_header('Origin'),
            c.response.get_header('Access-Control-Allow-Origin')
        ) 

        req.set_header('Access-Control-Request-Method', 'POST')
        req.set_header('Access-Control-Request-Headers', 'xone, xtwo')
        c = Cors(req, res)
        await c.handle_cors()
        await c.OPTIONS()
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
        await c.handle_cors()
        c.POST()
        self.assertEqual(
            req.get_header('Origin'),
            c.response.get_header('Access-Control-Allow-Origin')
        ) 


class RequestTest(TestCase):
    def test_get_auth_scheme_is_auth(self):
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

        # r.basic_auth("foo", "bar")
        r.set_headers({"Authorization": "Basic foobar"})
        self.assertTrue(r.is_auth("basic"))
        self.assertTrue(r.is_auth("client"))
        self.assertFalse(r.is_auth("token"))
        self.assertFalse(r.is_auth("access"))

        r.headers["Authorization"] = "Bearer FOOBAR"
        self.assertFalse(r.is_auth("basic"))
        self.assertFalse(r.is_auth("client"))
        self.assertTrue(r.is_auth("token"))
        self.assertTrue(r.is_auth("access"))

        r.headers.pop("Authorization")
        self.assertFalse(r.is_auth("basic"))
        self.assertFalse(r.is_auth("client"))
        self.assertFalse(r.is_auth("token"))
        self.assertFalse(r.is_auth("access"))

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
        self.assertEqual("UTF-8", charset.upper())

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

        r = Response()
        r.code = 10000000
        self.assertEqual("UNKNOWN", r.status)

