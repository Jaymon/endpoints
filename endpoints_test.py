import unittest
import endpoints

class RequestTest(unittest.TestCase):

    def test_instantiation(self):

        r = endpoints.Request()
        pout.v(r.path)

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


        #pout.v(rm.query, rm.query_kwargs)

