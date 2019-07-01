# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from . import TestCase, Server
import json

import testdata

from endpoints.compat.environ import *
from endpoints.compat.imports import parse as urlparse, BaseHTTPRequestHandler
from endpoints.http import Headers, Url, Response, Request, Environ
from endpoints.utils import String, ByteString


class EnvironTest(TestCase):
    def test_values(self):
        d = Environ()

        d["foo"] = None
        self.assertEqual(None, d["foo"])

        d["bar"] = 1
        self.assertEqual(1, d["bar"])


class HeadersTest(TestCase):
    def test_midbody_capital_letter(self):
        """Previously, before June 2019, our headers didn't handle WebSocket correctly
        instead lowercasing the S to Websocket"""
        d = Headers()
        d["Sec-WebSocket-Key"] = "foobar"
        self.assertTrue("Sec-Websocket-Key" in d)
        d2 = dict(d)
        self.assertFalse("Sec-Websocket-Key" in d2)
        self.assertTrue("Sec-WebSocket-Key" in d2)

    def test_bytes(self):
        d = Headers()
        name = testdata.get_unicode()
        val = ByteString(testdata.get_unicode())
        d[name] = val
        self.assertEqual(d[name], String(val))

    def test_different_original_keys(self):
        """when setting headers using 2 different original keys it wouldn't be uniqued"""
        d = Headers()
        d['Content-Type'] = "application/json"
        d['content-type'] = "text/plain"
        self.assertEqual(1, len(d))
        self.assertEqual("text/plain", d["CONTENT-TYPE"])

    def test_lifecycle(self):
        d = Headers()
        d["foo-bar"] = 1
        self.assertEqual("1", d["Foo-Bar"])
        self.assertEqual("1", d["fOO-bAr"])
        self.assertEqual("1", d["fOO_bAr"])

    def test_pop(self):
        d = Headers()
        d['FOO'] = 1
        r = d.pop('foo')
        self.assertEqual("1", r)

        with self.assertRaises(KeyError):
            d.pop('foo')

        with self.assertRaises(KeyError):
            d.pop('FOO')

    def test_normalization(self):

        keys = [
            "Content-Type",
            "content-type",
            "content_type",
            "CONTENT_TYPE"
        ]

        v = "foo"
        d = {
            "CONTENT_TYPE": v,
            "CONTENT_LENGTH": 1234
        }
        headers = Headers(d)

        for k in keys:
            self.assertEqual(v, headers["Content-Type"])

        headers = Headers()
        headers["CONTENT_TYPE"] = v

        for k in keys:
            self.assertEqual(v, headers["Content-Type"])

        #with self.assertRaises(KeyError):
        #    headers["foo-bar"]

        for k in keys:
            self.assertTrue(k in headers)

    def test_iteration(self):
        hs = Headers()
        hs['CONTENT_TYPE'] = "application/json"
        hs['CONTENT-LENGTH'] = "1234"
        hs['FOO-bAR'] = "che"
        for k in hs.keys():
            self.assertRegex(k, r"^[A-Z][a-z]+(?:\-[A-Z][a-z]+)*$")
            self.assertTrue(k in hs)

        for k, v in hs.items():
            self.assertRegex(k, r"^[A-Z][a-z]+(?:\-[A-Z][a-z]+)*$")
            self.assertEqual(hs[k], v)

        for k in hs:
            self.assertRegex(k, r"^[A-Z][a-z]+(?:\-[A-Z][a-z]+)*$")
            self.assertTrue(k in hs)

    def test___init__(self):
        d = {"foo-bar": "1"}
        hs = Headers(d)
        self.assertEqual("1", hs["foo-bar"])
        self.assertEqual(1, len(hs))

        d = [("foo-bar", "1")]
        hs = Headers(d)
        self.assertEqual("1", hs["foo-bar"])
        self.assertEqual(1, len(hs))

        d = [("foo-bar", "1")]
        hs = Headers(d, bar_foo="2")
        self.assertEqual("1", hs["foo-bar"])
        self.assertEqual("2", hs["bar-foo"])
        self.assertEqual(2, len(hs))


class RequestTest(TestCase):
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
        self.assertEqual(urlparse.parse_qs(r.query, True), urlparse.parse_qs(query, True))
        self.assertEqual(r.query_kwargs, query_kwargs)

        r = Request()
        r.query_kwargs = query_kwargs
        self.assertEqual(urlparse.parse_qs(r.query, True), urlparse.parse_qs(query, True))
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
    def test_client_netloc(self):
        u = Url("0.0.0.0:546")
        self.assertFalse("0.0.0.0" in u.client_netloc)
        self.assertTrue("0.0.0.0" in u.netloc)

        u = Url("0.0.0.0")
        self.assertFalse("0.0.0.0" in u.client_netloc)
        self.assertTrue("0.0.0.0" in u.netloc)

    def test_normalize_query_kwargs(self):
        d = {b'foo': [b'bar'], b'baz': [b'che']}
        r = Url.normalize_query_kwargs(d)
        self.assertEqual({'foo': b'bar', 'baz': b'che'}, r)

    def test_parent(self):
        u = Url("http://example.com/foo/bar/che")

        u2 = u.parent(che=4)
        self.assertEqual("http://example.com/foo/bar?che=4", u2)

        u2 = u.parent("baz", che=4)
        self.assertEqual("http://example.com/foo/bar/baz?che=4", u2)

        u = Url("http://example.com/")
        u2 = u.parent("baz", che=5)
        self.assertEqual("http://example.com/baz?che=5", u2)

    def test_module(self):
        controller_prefix = "url_module"
        c = Server(controller_prefix, {
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

    def test_no_scheme(self):
        h = Url("localhost:8080/foo/bar?che=1")
        self.assertEqual(8080, h.port)
        self.assertEqual("localhost", h.hostname)
        self.assertEqual("foo/bar", h.path)
        self.assertEqual("che=1", h.query)

        h = Url("localhost:8080/foo/bar")
        self.assertEqual(8080, h.port)
        self.assertEqual("localhost", h.hostname)

        h = Url("localhost:8080")
        self.assertEqual(8080, h.port)
        self.assertEqual("localhost", h.hostname)

        h = Url("localhost")
        self.assertEqual(80, h.port)
        self.assertEqual("localhost", h.hostname)

    def test_controller(self):
        u = Url("http://example.com/foo/bar/che", class_path="foo")
        u2 = u.controller(che=4)
        self.assertEqual("http://example.com/foo?che=4", u2)

    def test_base(self):
        u = Url("http://example.com/path/part")
        u2 = u.base(che=4)
        self.assertEqual("http://example.com/path/part?che=4", u2)

        u = Url("http://example.com/path/part/?che=3")
        u2 = u.base("foo", "bar", che=4)
        self.assertEqual("http://example.com/path/part/foo/bar?che=4", u2)

        u = Url("http://example.com/")
        u2 = u.base("foo", "bar", che=4)
        self.assertEqual("http://example.com/foo/bar?che=4", u2)

    def test_host(self):
        u = Url("http://example.com/path/part/?che=3")
        u2 = u.host("foo", "bar", che=4)
        self.assertEqual("http://example.com/foo/bar?che=4", u2)
        self.assertEqual(u2.host(), u.host())

    def test_copy(self):
        u = Url("http://example.com/path/part/?che=3")
        u2 = u.copy()
        self.assertEqual(u, u2)

    def test_query(self):
        h = Url(query="foo=bar")
        self.assertEqual({"foo": "bar"}, h.query_kwargs)

    def test_query_kwargs(self):
        u = Url("http://example.com/path/part/?che=3", query="baz=4&bang=5", query_kwargs={"foo": 1, "bar": 2})
        self.assertEqual({"foo": 1, "bar": 2, "che": "3", "baz": "4", "bang": "5"}, u.query_kwargs)

        u = Url("http://example.com/path/part/?che=3", query_kwargs={"foo": 1, "bar": 2})
        self.assertEqual({"foo": 1, "bar": 2, "che": "3"}, u.query_kwargs)

        u = Url("http://example.com/path/part/", query_kwargs={"foo": 1, "bar": 2})
        self.assertEqual({"foo": 1, "bar": 2}, u.query_kwargs)

    def test_create(self):
        u = Url("http://example.com/path/part/?query1=val1")
        self.assertEqual("http://example.com/path/part", u.base())
        self.assertEqual({"query1": "val1"}, u.query_kwargs)

        u2 = u.host("/foo/bar", query1="val2")
        self.assertEqual("http://example.com/foo/bar?query1=val2", u2)

    def test_port_override(self):
        scheme = "http"
        host = "localhost:9000"
        path = "/path/part"
        query = "query1=val1"
        port = "9000"
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("http://localhost:9000/path/part?query1=val1", u)

        port = "1000"
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("http://localhost:1000/path/part?query1=val1", u)

        host = "localhost"
        port = "2000"
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("http://localhost:2000/path/part?query1=val1", u)

        host = "localhost"
        port = "80"
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("http://localhost/path/part?query1=val1", u)

        scheme = "https"
        host = "localhost:443"
        port = None
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("https://localhost/path/part?query1=val1", u)

    def test_port_standard(self):
        h = Url("localhost:80")
        self.assertEqual("http://localhost", h)
        self.assertEqual(80, h.port)

        h = Url("http://localhost:80")
        self.assertEqual("http://localhost", h)
        self.assertEqual(80, h.port)

        h = Url("http://example.com:80")
        self.assertEqual("http://example.com", h)
        self.assertEqual(80, h.port)

        h = Url("http://user:pass@foo.com:80")
        self.assertEqual("http://user:pass@foo.com", h)
        self.assertEqual(80, h.port)

        h = Url("https://user:pass@bar.com:443")
        self.assertEqual("https://user:pass@bar.com", h)
        self.assertEqual(443, h.port)

        h = Url("http://localhost:8000")
        self.assertEqual("http://localhost:8000", h)
        self.assertEqual(8000, h.port)

        h = Url("http://localhost:4436")
        self.assertEqual("http://localhost:4436", h)
        self.assertEqual(4436, h.port)

        h = Url("http://localhost")
        self.assertEqual("http://localhost", h)
        self.assertEqual(80, h.port)

    def test_merge(self):
        us = "http://foo.com/path?arg1=1&arg2=2#fragment"
        parts = Url.merge(us, query="foo3=3")
        self.assertTrue("foo3=3" in parts["urlstring"])

        us1 = "http://foo.com/path?arg1=1&arg2=2#fragment"
        parts1 = Url.merge(us, username="john", password="doe")
        us2 = "http://john:doe@foo.com/path?arg1=1&arg2=2#fragment"
        parts2 = Url.merge(us2)
        self.assertEqual(parts1, parts2)

    def test___add__(self):

        h = Url("http://localhost")

        h2 = h + {"arg1": 1}
        self.assertEqual("{}?arg1=1".format(h), h2)

        h2 = h + ("foo", "bar")
        self.assertEqual("{}/foo/bar".format(h), h2)

        h2 = h + "/foo/bar"
        self.assertEqual("{}/foo/bar".format(h), h2)

        h2 = h + b"/foo/bar"
        self.assertEqual("{}/foo/bar".format(h), h2)

        h2 = h + ["foo", "bar"]
        self.assertEqual("{}/foo/bar".format(h), h2)

        h = Url("http://localhost/1/2")

        h2 = h + "/foo/bar"
        self.assertEqual("{}/foo/bar".format(h.root), h2)

        h2 = h + b"/foo/bar"
        self.assertEqual("{}/foo/bar".format(h.root), h2)

        h2 = h + ["foo", "bar"]
        self.assertEqual("{}/foo/bar".format(h), h2)

        h2 = h + ["/foo", "bar"]
        self.assertEqual("{}/foo/bar".format(h.root), h2)

    def test___sub__(self):
        h = Url("http://foo.com/1/2/3?arg1=1&arg2=2#fragment")

        h2 = h - "2/3"
        self.assertFalse("2/3" in h2)

        h2 = h - ["2", "3"]
        self.assertFalse("2/3" in h2)

        h2 = h - ("2", "3")
        self.assertFalse("2/3" in h2)

        h2 = h - {"arg1": 1}
        self.assertFalse("arg1" in h2)

    def test___isub__(self):
        h = Url("http://foo.com/1/2/3?arg1=1&arg2=2#fragment")

        h -= "2/3"
        self.assertFalse("2/3" in h)

        h -= ["2", "3"]
        self.assertFalse("2/3" in h)

        h -= ("2", "3")
        self.assertFalse("2/3" in h)

        h -= {"arg1": 1}
        self.assertFalse("arg1" in h)

    def test_add(self):
        u = Url("http://example.com/path/part/?che=3")
        u2 = u.add(query_kwargs={"foo": 1})
        self.assertEqual({"foo": 1, "che": "3"}, u2.query_kwargs)
        self.assertEqual("http://example.com/path/part", u2.base())

    def test_subtract(self):
        h = Url("http://foo.com/1/2/3?arg1=1&arg2=2#fragment")

        h2 = h.subtract("2", "3")
        self.assertFalse("2/3" in h2)

        h2 = h.subtract(query_kwargs={"arg1": 1})
        self.assertFalse("arg1" in h2)


