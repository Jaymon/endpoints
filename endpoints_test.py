from unittest import TestCase
import os
import urlparse
import json

import testdata

import endpoints

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

        # TODO: this really needs to be tested with unicode data

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

class CallTest(TestCase):

    def test_controller_info(self):
        class MockRequest(object): pass
        r = MockRequest()
        r.path_args = [u"foo", u"bar"]
        r.query_kwargs = {u'foo': u'bar', u'che': u'baz'}
        r.method = u"GET"

        out_d = {
            'class_name': u"Bar",
            'args': [],
            'method': u"get",
            'module': u"foo",
            'kwargs':
                {
                    'foo': u"bar",
                    'che': u"baz"
                }
        }

        c = endpoints.Call()
        c.request = r

        d = c.get_controller_info()
        self.assertEqual(d, out_d)

        r.path_args.append(u"che")
        out_d['args'].append(u"che")

        d = c.get_controller_info()
        self.assertEqual(d, out_d)

        r.path_args = []
        out_d['args'] = []
        out_d['module'] = u'default'
        out_d['class_name'] = u'Default'

        d = c.get_controller_info()
        self.assertEqual(d, out_d)

    def test_callback_info(self):
        class MockRequest(object): pass
        r = MockRequest()
        r.path = u"/foo/bar"
        r.path_args = [u"foo", u"bar"]
        r.query_kwargs = {u'foo': u'bar', u'che': u'baz'}
        r.method = u"GET"
        c = endpoints.Call()
        c.request = r

        with self.assertRaises(endpoints.CallError):
            d = c.get_callback_info()

        contents = os.linesep.join([
            "class Bar(object):",
            "    endpoint_public = True",
            "    def get(*args, **kwargs): pass"
        ])
        testdata.create_module("foo", contents=contents)

        # if it succeeds, then it passed the test :)
        d = c.get_callback_info()

    def test_public_controller(self):
        class MockRequest(object): pass
        r = MockRequest()
        r.path = u"/foo2/bar"
        r.path_args = [u"foo2", u"bar"]
        r.query_kwargs = {u'foo2': u'bar', u'che': u'baz'}
        r.method = u"GET"
        c = endpoints.Call()
        c.request = r

        contents = os.linesep.join([
            "class Bar(object):",
            "    endpoint_public = False",
            "    def get(*args, **kwargs): pass"
        ])
        testdata.create_module("foo2", contents=contents)

        # if it succeeds, then it passed the test :)
        with self.assertRaises(endpoints.CallError):
            d = c.get_callback_info()

class VersionCallTest(TestCase):

    def test_get_version(self):
        r = endpoints.Request()
        r.headers = {u'accept': u'application/json;version=v1'}

        c = endpoints.VersionCall()
        c.version_media_type = u'application/json'
        c.request = r

        v = c.get_version()
        self.assertEqual(u'v1', v)

        c.request.headers = {u'accept': u'application/json'}

        with self.assertRaises(endpoints.CallError):
            v = c.get_version()

        c.default_version = u'v1'
        v = c.get_version()
        self.assertEqual(u'v1', v)

    def test_controller_prefix(self):
        r = endpoints.Request()
        r.headers = {u'accept': u'application/json;version=v1'}

        c = endpoints.VersionCall()
        c.content_type = u'application/json'
        c.request = r

        cp = c.get_normalized_prefix()
        self.assertEqual(u"v1", cp)

        c.controller_prefix = "foo.bar"
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

    def test_get_endpoints(self):
        # putting the C back in CRUD
        tmpdir = testdata.create_dir("reflecttest")
        contents = os.linesep.join([
            "import endpoints",
            "class default(endpoints.Controller):",
            "    endpoint_public = True",
            "    def get(*args, **kwargs): pass",
            ""
        ])
        testdata.create_module("controller.default", contents=contents, tmpdir=tmpdir)

        contents = os.linesep.join([
            "import endpoints",
            "class default(endpoints.Controller):",
            "    endpoint_public = True",
            "    def get(*args, **kwargs): pass",
            ""
        ])
        testdata.create_module("controller.foo", contents=contents, tmpdir=tmpdir)

        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Baz(Controller):",
            "    endpoint_public = True",
            "    def post(*args, **kwargs): pass",
            ""
        ])
        testdata.create_module("controller.che", contents=contents, tmpdir=tmpdir)

        contents = os.linesep.join([
            "from endpoints import Controller as Con",
            "class Base(Con):",
            "    def get(*args, **kwargs): pass",
            "",
            "class Boo(Base):",
            "    endpoint_public = True",
            "    def delete(*args, **kwargs): pass",
            "    def post(*args, **kwargs): pass",
            ""
            "class Bah(Base):",
            "    '''this is the doc string'''",
            "    endpoint_public = True",
            "    endpoint_options = ['head']",
            ""
        ])
        testdata.create_module("controller.bam", contents=contents, tmpdir=tmpdir)

        r = endpoints.Reflect("controller")
        l = r.get_endpoints()
        self.assertEqual(5, len(l))

        def get_match(endpoint, l):
            for d in l:
                if d['endpoint'] == endpoint:
                    return d

        d = get_match("/bam/bah", l)
        self.assertEqual(d['options'], ["head"])
        self.assertGreater(len(d['doc']), 0)

        d = get_match("/", l)
        self.assertNotEqual(d, {})

        d = get_match("/foo", l)
        self.assertNotEqual(d, {})

class VersionReflectTest(TestCase):

    def test_get_endpoints(self):
        # putting the C back in CRUD
        tmpdir = testdata.create_dir("versionreflecttest")
        contents = os.linesep.join([
            "import endpoints",
            "class Bar(endpoints.Controller):",
            "    endpoint_public = True",
            "    def get(*args, **kwargs): pass",
            ""
        ])
        testdata.create_module("controller.v1.foo", contents=contents, tmpdir=tmpdir)
        contents = os.linesep.join([
            "from endpoints import Controller",
            "class Baz(Controller):",
            "    endpoint_public = True",
            "    def get(*args, **kwargs): pass",
            ""
        ])
        testdata.create_module("controller.v2.che", contents=contents, tmpdir=tmpdir)

        r = endpoints.VersionReflect("controller", 'application/json')
        l = r.get_endpoints()

        self.assertEqual(2, len(l))
        for d in l:
            self.assertTrue('headers' in d)


