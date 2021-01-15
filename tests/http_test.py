# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import json
import io

from requests.auth import _basic_auth_str

from endpoints.compat import *
from endpoints.http import Headers, Url, Response, Request, Environ, Body
from endpoints.utils import String, ByteString
from . import testdata, TestCase, Server


class BodyTest(TestCase):
    def test_bad_content_type(self):
        """make sure a form upload content type with json body fails correctly"""
        r = Request()
        r.environ["REQUEST_METHOD"] = "POST"

        b = b"plain text body"
        r.headers.update({'content-length': String(len(b))})
        r.headers.pop("content-type", None)
        body = Body(io.BytesIO(b), r)
        self.assertEqual(b, body.file.read())

        b = b"foo=bar&che=baz&foo=che"
        r.headers.update({'content-type': 'application/json', 'content-length': String(len(b))})
        if is_py2:
            with self.assertRaises(ValueError):
                body = Body(io.BytesIO(b), r)

        else:
            with self.assertRaises(json.JSONDecodeError):
                body = Body(io.BytesIO(b), r)

        b = b'{"foo": ["bar", "che"], "che": "baz"}'
        r.headers.update({'content-type': "application/x-www-form-urlencoded", 'content-length': String(len(b))})
        with self.assertRaises(ValueError):
            body = Body(io.BytesIO(b), r)


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

    def test_override(self):

        class RO(Request):
            def __setattr__(self, k, v):
                super(RO, self).__setattr__(k, v)
                #pout.v(k, v)
                #self.__dict__[k] = v

        req = RO()
        req.path = "/foo/bar"
        #pout.v(req.path, req)

    def test_copy(self):
        r = Request()
        r.set_headers({
            "Host": "localhost",
        })
        r.query = "foo=bar"
        r.path = "/baz/che"
        r.environ['wsgi.url_scheme'] = "http"
        r.environ['SERVER_PORT'] = "80"
        r.foo = 1

        r2 = r.copy()
        self.assertEqual(r.foo, r2.foo)
        self.assertEqual(r.environ["SERVER_PORT"], r2.environ["SERVER_PORT"])

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
        r.environ['wsgi.url_scheme'] = "http"
        r.environ['SERVER_PORT'] = "80"
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
        r.set_header("Via", "1.1 ironport1.orlando.cit:80 (Cisco-WSA/9.0.1-162)")
        self.assertEqual("", r.ip)

        r = Request()
        r.set_header('REMOTE_ADDR', "54.241.34.107")
        r.set_header("Via", "1.1 ironport1.orlando.cit:80 (Cisco-WSA/9.0.1-162)")
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
        self.assertEqual(parse.parse_qs(r.query, True), parse.parse_qs(query, True))
        self.assertEqual(r.query_kwargs, query_kwargs)

        r = Request()
        r.query_kwargs = query_kwargs
        self.assertEqual(parse.parse_qs(r.query, True), parse.parse_qs(query, True))
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
        r.code = 1000
        self.assertEqual("UNKNOWN", r.status)

    def test_body_file(self):
        r = Response()
        self.assertFalse("Content-Type" in r.headers)
        self.assertFalse("Content-Length" in r.headers)

        path = testdata.create_file("foo.jpg", "12345")
        with path.open() as fp:
            r.body = fp
            mt = r.headers["Content-Type"]
            fs = r.headers["Content-Length"]
            self.assertEqual("image/jpeg", mt)
            self.assertEqual(5, int(fs))

        path = testdata.create_file("foo.txt", "123")
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


class UrlTest(TestCase):
    def test_module(self):
        c = Server(contents={
            "foo": [
                "from endpoints import Controller",
                "class Bar(Controller):",
                "    def GET(self):",
                "        u = self.request.url",
                "        return u.module()",
                "",
                "class Default(Controller):",
                "    def GET(self):",
                "        u = self.request.url",
                "        return u.module()",
                "",
            ],
        })

        res = c.handle("/foo/bar")
        self.assertEqual("http://endpoints.fake/foo", res._body)

        res = c.handle("/foo")
        self.assertEqual("http://endpoints.fake/foo", res._body)

    def test_controller(self):
        u = Url("http://example.com/foo/bar/che", class_path="foo")
        u2 = u.controller(che=4)
        self.assertEqual("http://example.com/foo?che=4", u2)

