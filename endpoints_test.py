#import unittest
from unittest import TestCase
import endpoints
import testdata
import os
import urlparse

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

#    def test_instantiation(self):
#        return
#
#        r = endpoints.Request()
#
#        # we need to mimic the request object that comes from the mongrel2 python module
#        class Mongrel2MockRequest(object): pass
#        r = Mongrel2MockRequest()
#        r.sender = 'server-uuid'
#        r.ident = '4'
#        r.path = '/foo/bar'
#        r.headers = {
#            u"accept-language": u"en-US,en;q=0.5",
#            u"accept-encoding": u"gzip, deflate",
#            u"PATTERN": u"/",
#            u"x-forwarded-for": u"10.0.2.2",
#            u"host": u"localhost:4000",
#            u"accept": u"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#            u"user-agent": u"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.8; rv:21.0) Gecko/20100101 Firefox/21.0",
#            u"connection": u"keep-alive",
#            u"VERSION": u"HTTP/1.1",
#            u"QUERY": u"foo=bar&che=baz",
#            u"PATH": u"/foo/bar",
#            u"METHOD": u"GET",
#            u"URI": u"/foo/bar?foo=bar&che=baz"
#        }
#        r.body = ''
#
#        rm = endpoints.Mongrel2Request(r)
#
#        self.assertEqual(rm.path, r.headers[u'PATH'])
#        self.assertEqual(rm.path_args, [u'foo', u'bar'])
#
#        self.assertEqual(rm.query, r.headers[u'QUERY'])
#        self.assertEqual(rm.query_kwargs, {u'foo': u'bar', u'che': u'baz'})
#
#        # test array query strings
#        rm_query = u"foo=bar&che=baz&foo=che"
#        rm.query = rm_query
#        self.assertEqual(rm.query, rm_query)
#        self.assertEqual(rm.query_kwargs, {u'foo': [u'bar', u'che'], u'che': u'baz'})

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
            "    request = None",
            "    response = None",
            "    def get(*args, **kwargs): pass"
        ])

        testdata.create_module("foo", contents=contents)

        # if it succeeds, then it passed the test :)
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
        c.version_media_type = u'application/json'
        c.request = r

        cp = c.controller_prefix
        self.assertEqual(u"v1", cp)

        c.controller_prefix = "foo.bar"
        cp = c.controller_prefix
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








