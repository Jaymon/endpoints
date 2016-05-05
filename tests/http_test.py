from . import TestCase
import urlparse
from BaseHTTPServer import BaseHTTPRequestHandler
import json

import testdata

from endpoints.http import Headers, Url, Response, Request


class HeadersTest(TestCase):
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
        self.assertEqual(1, d["Foo-Bar"])
        self.assertEqual(1, d["fOO-bAr"])
        self.assertEqual(1, d["fOO_bAr"])

    def test_pop(self):
        d = Headers()
        d['FOO'] = 1
        r = d.pop('foo')
        self.assertEqual(1, 1)

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

        with self.assertRaises(KeyError):
            headers["foo-bar"]

        for k in keys:
            self.assertTrue(k in headers)

    def test_iteration(self):
        hs = Headers()
        hs['CONTENT_TYPE'] = "application/json"
        hs['CONTENT-LENGTH'] = "1234"
        hs['FOO-bAR'] = "che"
        for k in hs.keys():
            self.assertRegexpMatches(k, "^[A-Z][a-z]+(?:\-[A-Z][a-z]+)*$")
            self.assertTrue(k in hs)

        for k, v in hs.items():
            self.assertRegexpMatches(k, "^[A-Z][a-z]+(?:\-[A-Z][a-z]+)*$")
            self.assertEqual(hs[k], v)

        for k in hs:
            self.assertRegexpMatches(k, "^[A-Z][a-z]+(?:\-[A-Z][a-z]+)*$")
            self.assertTrue(k in hs)


class RequestTest(TestCase):
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
        self.assertEqual("http://localhost/baz/che?foo=bar", r.url.geturl())
        r.port = 555
        u = r.url
        self.assertEqual("http://localhost:555/baz/che?foo=bar", r.url.geturl())

        # handle proxied connections
        r.host = "localhost:10000"
        r.port = "9000"
        u = r.url
        self.assertTrue(":10000" in u.geturl())

        # TODO -- simple server configuration

    def test_charset(self):
        r = Request()
        r.set_header("content-type", "application/json;charset=UTF-8")
        charset = r.charset
        self.assertEqual("UTF-8", charset)

        r = Request()
        r.set_header("content-type", "application/json")
        charset = r.charset
        self.assertEqual(None, charset)

    def test_ip(self):
        r = Request()
        r.set_header('x-forwarded-for', '54.241.34.107')
        ip = r.ip
        self.assertEqual('54.241.34.107', ip)

        r.set_header('x-forwarded-for', '127.0.0.1, 54.241.34.107')
        ip = r.ip
        self.assertEqual('54.241.34.107', ip)

        r.set_header('x-forwarded-for', '127.0.0.1')
        r.set_header('client-ip', '54.241.34.107')
        ip = r.ip
        self.assertEqual('54.241.34.107', ip)

    def test_body_kwargs_bad_content_type(self):
        """make sure a form upload content type with json body fails correctly"""
        r = Request()
        r.body = u"foo=bar&che=baz&foo=che"
        r.headers = {'content-type': 'application/json'}
        with self.assertRaises(ValueError):
            br = r.body_kwargs

        r.body = u'{"foo": ["bar", "che"], "che": "baz"}'
        r.headers = {'content-type': "application/x-www-form-urlencoded"}

        with self.assertRaises(ValueError):
            br = r.body_kwargs

    def test_body_kwargs(self):
        #body = u"foo=bar&che=baz&foo=che"
        #body_kwargs = {u'foo': [u'bar', u'che'], u'che': u'baz'}
        #body_json = '{"foo": ["bar", "che"], "che": "baz"}'
        cts = {
            u"application/x-www-form-urlencoded": (
                u"foo=bar&che=baz&foo=che",
                {u'foo': [u'bar', u'che'], u'che': u'baz'}
            ),
#             u'application/json': (
#                 '{"foo": ["bar", "che"], "che": "baz"}',
#                 {u'foo': [u'bar', u'che'], u'che': u'baz'}
#             ),
        }

        for ct, bodies in cts.iteritems():
            ct_body, ct_body_kwargs = bodies

            r = Request()
            r.body = ct_body
            r.set_header('content-type', ct)
            self.assertTrue(isinstance(r.body_kwargs, dict))
            self.assertEqual(r.body_kwargs, ct_body_kwargs)

            r = Request()
            r.set_header('content-type', ct)
            self.assertEqual(r.body_kwargs, {})
            self.assertEqual(r.body, None)

            r = Request()
            r.set_header('content-type', ct)
            r.body_kwargs = ct_body_kwargs
            self.assertEqual(r._parse_query_str(r.body), r._parse_query_str(ct_body))

    def test_properties(self):

        path = u'/foo/bar'
        path_args = [u'foo', u'bar']

        r = Request()
        r.path = path
        self.assertEqual(r.path, path)
        self.assertEqual(r.path_args, path_args)

        r = Request()
        r.path_args = path_args
        self.assertEqual(r.path, path)
        self.assertEqual(r.path_args, path_args)

        query = u"foo=bar&che=baz&foo=che"
        query_kwargs = {u'foo': [u'bar', u'che'], u'che': u'baz'}

        r = Request()
        r.query = query
        self.assertEqual(urlparse.parse_qs(r.query, True), urlparse.parse_qs(query, True))
        self.assertEqual(r.query_kwargs, query_kwargs)

        r = Request()
        r.query_kwargs = query_kwargs
        self.assertEqual(urlparse.parse_qs(r.query, True), urlparse.parse_qs(query, True))
        self.assertEqual(r.query_kwargs, query_kwargs)

    def test_body(self):
        # simulate a problem I had with a request with curl
        r = Request()
        r.method = 'GET'
        r.body = ""
        r.set_headers({
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
        })
        self.assertEqual("", r.body)

        r = Request()
        r.method = 'POST'

        r.set_header('content-type', u"application/x-www-form-urlencoded")
        r.body = u"foo=bar&che=baz&foo=che"
        body_r = {u'foo': [u'bar', u'che'], u'che': u'baz'}
        self.assertEqual(body_r, r.body_kwargs)


        r.body = None
        #del(r._body_kwargs)
        body_r = {}
        self.assertEqual(body_r, r.body_kwargs)

        r.set_header('content-type', u"application/json")
        r.body = '{"person":{"name":"bob"}}'
        #del(r._body_kwargs)
        body_r = {u'person': {"name":"bob"}}
        self.assertEqual(body_r, r.body_kwargs)

        r.body = u''
        #del(r._body_kwargs)
        body_r = u''
        self.assertEqual(body_r, r.body)

        r.headers = {}
        body = '{"person":{"name":"bob"}}'
        r.body = body
        self.assertEqual(body, r.body)

        r.method = 'GET'
        r.set_header('content-type', u"application/json")
        r.body = None
        self.assertEqual(None, r.body)

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

    def test_body(self):
        b = {'foo': 'bar'}

        r = Response()
        r.headers['Content-Type'] = 'plain/text'
        self.assertEqual('', r.body)
        r.body = b
        self.assertEqual(str(b), r.body)

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = b
        self.assertEqual(json.dumps(b), r.body)

        r = Response()
        r.headers['Content-Type'] = 'plain/text'
        self.assertEqual('', r.body)
        self.assertEqual('', r.body) # Make sure it doesn't change
        r.body = b
        self.assertEqual(str(b), r.body)

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = {}
        self.assertEqual(r.body, "{}")

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = ValueError("this is the message")
        r.code = 500
        self.assertEqual(r.body, '{"errno": 500, "errmsg": "this is the message"}')
        r.headers['Content-Type'] = ''
        self.assertEqual(r.body, "this is the message")

        r = Response()
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

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = b
        with self.assertRaises(TypeError):
            rb = r.body

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
    def test_no_scheme(self):

        h = Url("localhost:8080/foo/bar?che=1")
        self.assertEqual(8080, h.port)
        self.assertEqual("localhost", h.hostname)
        self.assertEqual("foo/bar", h.path)
        self.assertEqual("che=1", h.query)
        return

        h = Url("localhost:8080/foo/bar")
        self.assertEqual(8080, h.port)
        self.assertEqual("localhost", h.hostname)

        h = Url("localhost:8080")
        self.assertEqual(8080, h.port)
        self.assertEqual("localhost", h.hostname)

        h = Url("localhost")
        self.assertEqual(None, h.port)
        self.assertEqual("localhost", h.hostname)

    def test_controller_url(self):
        u = Url("http://example.com/foo/bar/che", controller_path="foo")
        u2 = u.controller_url(che=4)
        self.assertEqual("http://example.com/foo?che=4", u2.geturl())

    def test_base_url(self):
        u = Url("http://example.com/path/part")
        u2 = u.base_url(che=4)
        self.assertEqual("http://example.com/path/part?che=4", u2.geturl())


        u = Url("http://example.com/path/part/?che=3")
        u2 = u.base_url("foo", "bar", che=4)
        self.assertEqual("http://example.com/path/part/foo/bar?che=4", u2.geturl())

        u = Url("http://example.com/")
        u2 = u.base_url("foo", "bar", che=4)
        self.assertEqual("http://example.com/foo/bar?che=4", u2.geturl())

    def test_host_url(self):
        u = Url("http://example.com/path/part/?che=3")
        u2 = u.host_url("foo", "bar", che=4)
        self.assertEqual("http://example.com/foo/bar?che=4", u2.geturl())
        self.assertEqual(u2.host_url().geturl(), u.host_url().geturl())

    def test_update(self):
        u = Url("http://example.com/path/part/?che=3")
        u.update(query_kwargs={"foo": 1})
        self.assertEqual({"foo": 1, "che": "3"}, u.query_kwargs)
        self.assertEqual("http://example.com/path/part", u.base)

    def test_copy(self):
        u = Url("http://example.com/path/part/?che=3")
        u2 = u.copy()
        self.assertEqual(u.geturl(), u2.geturl())

        u2.query_kwargs = {}
        self.assertNotEqual(u.geturl(), u2.geturl())

    def test_query_kwargs(self):
        u = Url("http://example.com/path/part/?che=3", query="baz=4&bang=5", query_kwargs={"foo": 1, "bar": 2})
        self.assertEqual({"foo": 1, "bar": 2, "che": "3", "baz": "4", "bang": "5"}, u.query_kwargs)

        u = Url("http://example.com/path/part/?che=3", query_kwargs={"foo": 1, "bar": 2})
        self.assertEqual({"foo": 1, "bar": 2, "che": "3"}, u.query_kwargs)

        u = Url("http://example.com/path/part/", query_kwargs={"foo": 1, "bar": 2})
        self.assertEqual({"foo": 1, "bar": 2}, u.query_kwargs)

    def test_create(self):
        u = Url("http://example.com/path/part/?query1=val1")
        self.assertEqual("http://example.com/path/part", u.base_url().geturl())
        self.assertEqual({"query1": "val1"}, u.query_kwargs)

        u2 = u.host_url("/foo/bar", query1="val2")
        self.assertEqual("http://example.com/foo/bar?query1=val2", u2.geturl())

    def test_port(self):
        scheme = "http"
        host = "localhost:9000"
        path = "/path/part"
        query = "query1=val1"
        port = "9000"
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("http://localhost:9000/path/part?query1=val1", u.geturl())

        port = "1000"
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("http://localhost:9000/path/part?query1=val1", u.geturl())

        host = "localhost"
        port = "2000"
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("http://localhost:2000/path/part?query1=val1", u.geturl())

        host = "localhost"
        port = "80"
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("http://localhost/path/part?query1=val1", u.geturl())

        scheme = "https"
        host = "localhost:443"
        port = None
        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        self.assertEqual("https://localhost/path/part?query1=val1", u.geturl())


