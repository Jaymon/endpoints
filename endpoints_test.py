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

    def test_instantiation(self):
        return

        r = endpoints.Request()

        # we need to mimic the request object that comes from the mongrel2 python module
        class Mongrel2MockRequest(object): pass
        r = Mongrel2MockRequest()
        r.sender = 'server-uuid'
        r.ident = '4'
        r.path = '/foo/bar'
        r.headers = {
            u"accept-language": u"en-US,en;q=0.5",
            u"accept-encoding": u"gzip, deflate",
            u"PATTERN": u"/",
            u"x-forwarded-for": u"10.0.2.2",
            u"host": u"localhost:4000",
            u"accept": u"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            u"user-agent": u"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.8; rv:21.0) Gecko/20100101 Firefox/21.0",
            u"connection": u"keep-alive",
            u"VERSION": u"HTTP/1.1",
            u"QUERY": u"foo=bar&che=baz",
            u"PATH": u"/foo/bar",
            u"METHOD": u"GET",
            u"URI": u"/foo/bar?foo=bar&che=baz"
        }
        r.body = ''

        rm = endpoints.Mongrel2Request(r)

        self.assertEqual(rm.path, r.headers[u'PATH'])
        self.assertEqual(rm.path_args, [u'foo', u'bar'])

        self.assertEqual(rm.query, r.headers[u'QUERY'])
        self.assertEqual(rm.query_kwargs, {u'foo': u'bar', u'che': u'baz'})

        # test array query strings
        rm_query = u"foo=bar&che=baz&foo=che"
        rm.query = rm_query
        self.assertEqual(rm.query, rm_query)
        self.assertEqual(rm.query_kwargs, {u'foo': [u'bar', u'che'], u'che': u'baz'})

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













