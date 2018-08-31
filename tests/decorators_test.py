# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from . import TestCase, skipIf, SkipTest, Server
import time
import re

import testdata

import endpoints
from endpoints import CallError
from endpoints.utils import ByteString, Base64, String
from endpoints.http import Request
from endpoints.decorators import param, post_param
from endpoints.decorators.limit import ratelimit, \
    ratelimit_ip, \
    ratelimit_param, \
    ratelimit_param_ip, \
    ratelimit_token


def create_controller():
    class FakeController(endpoints.Controller):
        def POST(self): pass
        def GET(self): pass

    res = endpoints.Response()

    req = endpoints.Request()
    req.method = 'GET'

    c = FakeController(req, res)
    return c


class RatelimitTest(TestCase):
    def set_bearer_auth_header(self, request, access_token):
        request.set_header("authorization", 'Bearer {}'.format(access_token))

    def test_throttle(self):
        class TARA(object):
            @ratelimit(limit=3, ttl=1)
            def foo(self): return 1

            @ratelimit(limit=10, ttl=1)
            def bar(self): return 2


        r_foo = endpoints.Request()
        r_foo.set_header("X_FORWARDED_FOR", "276.0.0.1")
        r_foo.path = "/foo"
        c = TARA()
        c.request = r_foo

        for x in range(3):
            r = c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(CallError):
                c.foo()

        # make sure another path isn't messed with by foo
        r_bar = Request()
        r_bar.set_header("X_FORWARDED_FOR", "276.0.0.1")
        r_bar.path = "/bar"
        c.request = r_bar
        for x in range(10):
            r = c.bar()
            self.assertEqual(2, r)
            time.sleep(0.1)

        with self.assertRaises(CallError):
            c.bar()

        c.request = r_foo

        for x in range(3):
            r = c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(CallError):
                c.foo()

    def test_ratelimit_ip(self):
        class MockObject(object):
            @ratelimit_ip(limit=3, ttl=1)
            def foo(self): return 1

        o = MockObject()
        o.request = Request()
        o.request.set_header("X_FORWARDED_FOR", "100.1.1.1")
        o.request.path = "/fooip"

        o.foo()
        o.foo()
        o.foo()
        with self.assertRaises(CallError) as cm:
            o.foo()
        self.assertEqual(429, cm.exception.code)

        # make sure another request gets through just fine
        orig_r = o.request
        o.request = Request()
        o.request.path = "/fooip"
        o.request.set_header("X_FORWARDED_FOR", "100.1.1.2")
        o.foo()
        o.request = orig_r

        time.sleep(1)
        o.request.set_header("X_FORWARDED_FOR", "100.1.1.1")
        r = o.foo()
        self.assertEqual(1, r)

    def test_ratelimit_token(self):
        class MockObject(object):
            @ratelimit_token(limit=2, ttl=1)
            def foo(self): return 1

        o = MockObject()
        o.request = Request()
        self.set_bearer_auth_header(o.request, "footoken")
        o.request.path = "/footoken"

        o.request.set_header("X_FORWARDED_FOR", "1.1.1.1")
        o.foo()

        o.request.set_header("X_FORWARDED_FOR", "1.1.1.2")
        o.foo()

        with self.assertRaises(CallError) as cm:
            o.foo()
        self.assertEqual(429, cm.exception.code)

        # make sure another request gets through just fine
        orig_r = o.request
        o.request = Request()
        o.request.path = "/footoken"
        self.set_bearer_auth_header(o.request, "footoken2")
        o.foo()
        o.request = orig_r

        time.sleep(1)
        self.set_bearer_auth_header(o.request, "footoken")
        o.request.set_header("X_FORWARDED_FOR", "1.1.1.3")
        r = o.foo()
        self.assertEqual(1, r)

    def test_ratelimit_param(self):
        class MockObject(object):
            @ratelimit_param("bar", limit=2, ttl=1)
            def foo(self, **kwargs): return 1

        o = MockObject()
        o.request = Request()
        self.set_bearer_auth_header(o.request, "footoken")
        o.request.path = "/fooparam"

        o.foo(bar="che")

        o.foo(bar="che")

        with self.assertRaises(CallError) as cm:
            o.foo(bar="che")
        self.assertEqual(429, cm.exception.code)

        # make sure bar not existing is not a problem
        for x in range(5):
            self.assertEqual(1, o.foo())

        # just make sure something else goes through just fine
        orig_r = o.request
        o.request = Request()
        o.request.path = "/fooparam"
        o.foo(bar="baz")
        o.request = orig_r

        time.sleep(1)
        r = o.foo(bar="che")
        self.assertEqual(1, r)

    def test_ratelimit_param_ip(self):
        def create_request(ip):
            r = Request()
            r.path = "/fooparam"
            r.set_header("X_FORWARDED_FOR", ip)
            self.set_bearer_auth_header(r, "footoken")
            return r

        class MockObject(object):
            @ratelimit_param_ip("bar", limit=1, ttl=1)
            def foo(self, **kwargs): return 1

        o = MockObject()
        o.request = create_request("200.1.1.1")
        o.foo(bar="che")

        with self.assertRaises(CallError) as cm:
            o.foo(bar="che")
        self.assertEqual(429, cm.exception.code)

        # now make sure another ip address can get through
        o.request = create_request("200.1.1.2")
        o.foo(bar="che")

        with self.assertRaises(CallError) as cm:
            o.foo(bar="che")
        self.assertEqual(429, cm.exception.code)

        # now make sure another value makes it through
        o.foo(bar="baz")
        with self.assertRaises(CallError):
            o.foo(bar="baz")

        # make sure bar not existing is not a problem
        for x in range(5):
            self.assertEqual(1, o.foo())


class AuthTest(TestCase):
    def get_basic_auth_header(self, username, password):
        credentials = Base64.encode('{}:{}'.format(username, password))
        return 'Basic {}'.format(credentials)

    def get_bearer_auth_header(self, access_token):
        return 'Bearer {}'.format(access_token)


    def test_bad_setup(self):

        def target(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.token_auth(target=target)
            def foo_token(self): pass

            @endpoints.decorators.auth.client_auth(target=target)
            def foo_client(self): pass

            @endpoints.decorators.auth.basic_auth(target=target)
            def foo_basic(self): pass

            @endpoints.decorators.auth.auth(target=target)
            def foo_auth(self): pass

        r = endpoints.Request()
        c = TARA()
        c.request = r

        for m in ["foo_token", "foo_client", "foo_basic", "foo_auth"]: 
            with self.assertRaises(endpoints.AccessDenied):
                getattr(c, m)()

    def test_token_auth(self):
        def target(request, access_token):
            if access_token != "bar":
                raise ValueError()
            return True

        def target_bad(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.token_auth(target=target)
            def foo(self): pass

            @endpoints.decorators.auth.token_auth(target=target_bad)
            def foo_bad(self): pass

        r = endpoints.Request()
        c = TARA()
        c.request = r

        r.set_header('authorization', self.get_bearer_auth_header("foo"))
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        r.set_header('authorization', self.get_bearer_auth_header("bar"))
        c.foo()

        r = endpoints.Request()
        c.request = r

        r.body_kwargs["access_token"] = "foo"
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        r.body_kwargs["access_token"] = "bar"
        c.foo()

        r = endpoints.Request()
        c.request = r

        r.query_kwargs["access_token"] = "foo"
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        r.query_kwargs["access_token"] = "bar"
        c.foo()

        with self.assertRaises(endpoints.AccessDenied):
            c.foo_bad()

    def test_client_auth(self):
        def target(request, client_id, client_secret):
            return client_id == "foo" and client_secret == "bar"

        def target_bad(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.client_auth(target=target)
            def foo(self): pass

            @endpoints.decorators.auth.client_auth(target=target_bad)
            def foo_bad(self): pass

        client_id = "foo"
        client_secret = "..."
        r = endpoints.Request()
        r.set_header('authorization', self.get_basic_auth_header(client_id, client_secret))

        c = TARA()
        c.request = r
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        client_secret = "bar"
        r.set_header('authorization', self.get_basic_auth_header(client_id, client_secret))
        c.foo()

        with self.assertRaises(endpoints.AccessDenied):
            c.foo_bad()

    def test_basic_auth_simple(self):
        def target(request, username, password):
            if username != "bar":
                raise ValueError()
            return True

        def target_bad(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.basic_auth(target=target)
            def foo(self): pass

            @endpoints.decorators.auth.basic_auth(target=target_bad)
            def foo_bad(self): pass

        username = "foo"
        password = "..."
        r = endpoints.Request()
        r.set_header('authorization', self.get_basic_auth_header(username, password))

        c = TARA()
        c.request = r

        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        username = "bar"
        r.set_header('authorization', self.get_basic_auth_header(username, password))
        c.foo()

        with self.assertRaises(endpoints.AccessDenied):
            c.foo_bad()

    def test_basic_auth_same_kwargs(self):
        def target(request, username, password):
            if username != "bar":
                raise ValueError()
            return True

        class MockObject(object):
            @endpoints.decorators.auth.basic_auth(target=target)
            def foo(self, *args, **kwargs): return 1

        c = MockObject()
        username = "bar"
        password = "..."
        r = endpoints.Request()
        r.set_header('authorization', self.get_basic_auth_header(username, password))
        c.request = r

        # if no TypeError is raised then it worked :)
        r = c.foo(request="this_should_error_out")
        self.assertEqual(1, r)

    def test_auth(self):
        def target(request, controller_args, controller_kwargs):
            if request.body_kwargs["foo"] != "bar":
                raise ValueError()
            return True

        def target_bad(request, *args, **kwargs):
            pass

        class TARA(object):
            @endpoints.decorators.auth.auth(target=target)
            def foo(self): pass

            @endpoints.decorators.auth.auth(target=target_bad)
            def foo_bad(self): pass

        r = endpoints.Request()
        r.body_kwargs = {"foo": "che"}

        c = TARA()
        c.request = r
        with self.assertRaises(endpoints.AccessDenied):
            c.foo()

        r.body_kwargs = {"foo": "bar"}
        c.foo()


class PropertyTest(TestCase):
    def test__property_init(self):
        counts = dict(fget=0, fset=0, fdel=0)
        def fget(self):
            counts["fget"] += 1
            return self._v

        def fset(self, v):
            counts["fset"] += 1
            self._v = v

        def fdel(self):
            counts["fdel"] += 1
            del self._v

        class FooPropInit(object):
            v = endpoints.decorators._property(fget, fset, fdel, "this is v")
        f = FooPropInit()
        f.v = 6
        self.assertEqual(6, f.v)
        self.assertEqual(2, sum(counts.values()))
        del f.v
        self.assertEqual(3, sum(counts.values()))

        counts = dict(fget=0, fset=0, fdel=0)
        class FooPropInit2(object):
            v = endpoints.decorators._property(fget=fget, fset=fset, fdel=fdel, doc="this is v")
        f = FooPropInit2()
        f.v = 6
        self.assertEqual(6, f.v)
        self.assertEqual(2, sum(counts.values()))
        del f.v
        self.assertEqual(3, sum(counts.values()))

    def test__property_allow_empty(self):
        class PAE(object):
            foo_val = None
            @endpoints.decorators._property(allow_empty=False)
            def foo(self):
                return self.foo_val

        c = PAE()
        self.assertEqual(None, c.foo)
        self.assertFalse('_foo' in c.__dict__)

        c.foo_val = 1
        self.assertEqual(1, c.foo)
        self.assertTrue('_foo' in c.__dict__)

    def test__property_setter(self):
        class WPS(object):
            foo_get = False
            foo_set = False
            foo_del = False

            @endpoints.decorators._property
            def foo(self):
                self.foo_get = True
                return 1

            @foo.setter
            def foo(self, val):
                self.foo_set = True
                self._foo = val

            @foo.deleter
            def foo(self):
                self.foo_del = True
                del(self._foo)

        c = WPS()

        self.assertEqual(1, c.foo)

        c.foo = 5
        self.assertEqual(5, c.foo)

        del(c.foo)
        self.assertEqual(1, c.foo)

        self.assertTrue(c.foo_get)
        self.assertTrue(c.foo_set)
        self.assertTrue(c.foo_del)

    def test__property__strange_behavior(self):
        class BaseFoo(object):
            def __init__(self):
                setattr(self, 'bar', None)

            def __setattr__(self, n, v):
                super(BaseFoo, self).__setattr__(n, v)

        class Foo(BaseFoo):
            @endpoints.decorators._property(allow_empty=False)
            def bar(self):
                return 1

        f = Foo()
        self.assertEqual(1, f.bar)

        f.bar = 2
        self.assertEqual(2, f.bar)

    def test__property___dict__direct(self):
        """
        this is a no win situation

        if you have a bar _property and a __setattr__ that modifies directly then
        the other _property values like __set__ will not get called, and you can't
        have _property.__get__ look for the original name because there are times
        when you want your _property to override a parent's original value for the
        property, so I've chosen to just ignore this case and not support it
        """
        class Foo(object):
            @endpoints.decorators._property
            def bar(self):
                return 1
            def __setattr__(self, field_name, field_val):
                self.__dict__[field_name] = field_val
                #super(Foo, self).__setattr__(field_name, field_val)

        f = Foo()
        f.bar = 2 # this will be ignored
        self.assertEqual(1, f.bar)

    def test__property(self):
        class WP(object):
            count_foo = 0

            @endpoints.decorators._property(True)
            def foo(self):
                self.count_foo += 1
                return 1

            @endpoints.decorators._property(read_only=True)
            def baz(self):
                return 2

            @endpoints.decorators._property()
            def bar(self):
                return 3

            @endpoints.decorators._property
            def che(self):
                return 4

        c = WP()
        r = c.foo
        self.assertEqual(1, r)
        self.assertEqual(1, c._foo)
        with self.assertRaises(AttributeError):
            c.foo = 2
        with self.assertRaises(AttributeError):
            del(c.foo)
        c.foo
        c.foo
        self.assertEqual(1, c.count_foo)

        r = c.baz
        self.assertEqual(2, r)
        self.assertEqual(2, c._baz)
        with self.assertRaises(AttributeError):
            c.baz = 3
        with self.assertRaises(AttributeError):
            del(c.baz)

        r = c.bar
        self.assertEqual(3, r)
        self.assertEqual(3, c._bar)
        c.bar = 4
        self.assertEqual(4, c.bar)
        self.assertEqual(4, c._bar)
        del(c.bar)
        r = c.bar
        self.assertEqual(3, r)

        r = c.che
        self.assertEqual(4, r)
        self.assertEqual(4, c._che)
        c.che = 4
        self.assertEqual(4, c.che)
        del(c.che)
        r = c.che
        self.assertEqual(4, r)


class ParamTest(TestCase):
    def test_type_issue_76(self):
        """
        https://github.com/Jaymon/endpoints/issues/76
        """
        c = Server("type_issue_76", [
            "from endpoints import Controller, param",
            "",
            "class Query(object):",
            "    def get(self, v): return v",
            "",
            "class FooType(object):",
            "    query = Query()",
            "",
            "class Foo(Controller):",
            "    @param(0, default=None, type=FooType.query.get)",
            "    def GET(self, f):",
            "        return f",
            "",
            "class Bar(Controller):",
            "    @param(0, default=None, type=lambda x: FooType.query.get(x))",
            "    def GET(self, f):",
            "        return f",
        ])

        res = c.handle("/foo/bar")
        self.assertEqual("bar", res._body)

        res = c.handle("/bar/foo")
        self.assertEqual("foo", res._body)

    def test_regex_issue_77(self):
        """
        https://github.com/Jaymon/endpoints/issues/77
        """
        c = Server("regex_issue_77", [
            "import datetime",
            "from endpoints import Controller, param",
            "",
            "def parse(dts):",
            "    return datetime.datetime.strptime(dts, '%Y-%m-%d')",
            "",
            "class Foo(Controller):",
            "    @param('dt', regex=r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$', type=parse)",
            "    def GET(self, **kwargs):",
            "        return kwargs['dt']",
            "",
        ])

        res = c.handle("/foo", query="dt=2018-01-01")
        self.assertEqual(res._body.year, 2018)
        self.assertEqual(res._body.month, 1)
        self.assertEqual(res._body.day, 1)
        #self.assertEqual("bar", res._body)


    def test_append_list_choices(self):
        c = create_controller()

        @param('foo', action="append_list", type=int, choices=[1, 2])
        def foo(self, *args, **kwargs):
            return kwargs["foo"]

        #r = foo(c, **{'foo': "1,2"})
        r = foo(c, foo="1,2")
        self.assertEqual([1, 2], r)

        with self.assertRaises(CallError):
            r = foo(c, **{'foo': "1,2,3"})

        r = foo(c, **{'foo': 1})
        self.assertEqual([1], r)

        with self.assertRaises(CallError):
            r = foo(c, **{'foo': 3})

    def test_metavar(self):
        raise SkipTest("not sure what to do with this test yet")
        class MockMetavar(object):
            request = Request()

            @param(0, metavar="bar")
            def foo(self, bar, **kwargs): return 1


        o = MockMetavar()
        o.request.method = 'GET'
        o.request.path = "/0"

        o.foo("0")

    def test_param_dest(self):
        """make sure the dest=... argument works"""
        # https://docs.python.org/2/library/argparse.html#dest
        c = create_controller()

        @endpoints.decorators.param('foo', dest='bar')
        def foo(self, *args, **kwargs):
            return kwargs.get('bar')

        r = foo(c, **{'foo': 1})
        self.assertEqual(1, r)

    def test_param_multiple_names(self):
        c = create_controller()

        @endpoints.decorators.param('foo', 'foos', 'foo3', type=int)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        r = foo(c, **{'foo': 1})
        self.assertEqual(1, r)

        r = foo(c, **{'foos': 2})
        self.assertEqual(2, r)

        r = foo(c, **{'foo3': 3})
        self.assertEqual(3, r)

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo4': 0})

    def test_param_callable_default(self):
        c = create_controller()

        @endpoints.decorators.param('foo', default=time.time)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        start = time.time()
        r1 = foo(c, **{})
        self.assertLess(start, r1)

        time.sleep(0.25)
        r2 = foo(c, **{})
        self.assertLess(r1, r2)


    def test_param_not_required(self):
        c = create_controller()

        @param('foo', required=False)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = foo(c, **{'foo': 1})
        self.assertTrue(r)

        r = foo(c, **{})
        self.assertFalse(r)

        @param('foo', required=False, default=5)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = foo(c, **{})
        self.assertTrue(r)

        @param('foo', type=int, required=False)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = foo(c, **{})
        self.assertFalse(r)


    def test_param_unicode(self):
        c = create_controller()
        r = endpoints.Request()
        r.set_header("content-type", "application/json;charset=UTF-8")
        charset = r.encoding
        c.request = r
        #self.assertEqual("UTF-8", charset)

        @endpoints.decorators.param('foo', type=str)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        words = testdata.get_unicode_words()
        ret = foo(c, **{"foo": words})
        self.assertEqual(String(ret), String(words))

    def test_param(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=int)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': 0})

        @endpoints.decorators.param('foo', default=0)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        r = foo(c, **{})
        self.assertEqual(0, r)

        @endpoints.decorators.param('foo', type=int, choices=set([1, 2, 3]))
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        c.request.method = 'POST'
        c.request.body_kwargs = {'foo': '1'}
        r = foo(c, **c.request.body_kwargs)
        self.assertEqual(1, r)

        c.request.body_kwargs = {}
        r = foo(c, **{'foo': '2'})
        self.assertEqual(2, r)

    def test_post_param(self):
        c = create_controller()
        c.request.method = 'POST'

        @post_param('foo', type=int, choices=set([1, 2, 3]))
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        with self.assertRaises(CallError):
            r = foo(c)

        c.request.query_kwargs['foo'] = '1'
        with self.assertRaises(CallError):
            r = foo(c, **{'foo': '1'})

        c.request.body_kwargs = {'foo': '8'}
        with self.assertRaises(CallError):
            r = foo(c, **c.request.body_kwargs)

        c.request.query_kwargs = {}
        c.request.body_kwargs = {'foo': '1'}
        r = foo(c, **c.request.body_kwargs)
        self.assertEqual(1, r)

        c.request.query_kwargs = {'foo': '1'}
        c.request.body_kwargs = {'foo': '3'}
        r = foo(c, **{'foo': '3'})
        self.assertEqual(3, r)

    def test_get_param(self):
        c = create_controller()

        c.request.query_kwargs = {'foo': '8'}
        @endpoints.decorators.get_param('foo', type=int, choices=set([1, 2, 3]))
        def foo(*args, **kwargs):
            return kwargs['foo']
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **c.request.query_kwargs)

        c.request.query_kwargs = {'foo': '1'}
        @endpoints.decorators.get_param('foo', type=int, choices=set([1, 2, 3]))
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(1, r)

        c.request.query_kwargs = {'foo': '1', 'bar': '1.5'}
        @endpoints.decorators.get_param('foo', type=int)
        @endpoints.decorators.get_param('bar', type=float)
        def foo(*args, **kwargs):
            return kwargs['foo'], kwargs['bar']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(1, r[0])
        self.assertEqual(1.5, r[1])

        c.request.query_kwargs = {'foo': '1'}
        @endpoints.decorators.get_param('foo', type=int, action='blah')
        def foo(*args, **kwargs):
            return kwargs['foo']
        with self.assertRaises(RuntimeError):
            r = foo(c, **c.request.query_kwargs)

        c.request.query_kwargs = {'foo': ['1,2,3,4', '5']}
        @endpoints.decorators.get_param('foo', type=int, action='store_list')
        def foo(*args, **kwargs):
            return kwargs['foo']
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **c.request.query_kwargs)

        c.request.query_kwargs = {'foo': ['1,2,3,4', '5']}
        @endpoints.decorators.get_param('foo', type=int, action='append_list')
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(list(range(1, 6)), r)

        c.request.query_kwargs = {'foo': '1,2,3,4'}
        @endpoints.decorators.get_param('foo', type=int, action='store_list')
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(list(range(1, 5)), r)

        c.request.query_kwargs = {}

        @endpoints.decorators.get_param('foo', type=int, default=1, required=False)
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c)
        self.assertEqual(1, r)

        @endpoints.decorators.get_param('foo', type=int, default=1, required=True)
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c)
        self.assertEqual(1, r)

        @endpoints.decorators.get_param('foo', type=int, default=1)
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c)
        self.assertEqual(1, r)

        @endpoints.decorators.get_param('foo', type=int)
        def foo(*args, **kwargs):
            return kwargs['foo']
        with self.assertRaises(endpoints.CallError):
            r = foo(c)

        c.request.query_kwargs = {'foo': '1'}
        @endpoints.decorators.get_param('foo', type=int)
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(1, r)

    def test_param_size(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=int, min_size=100)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': 0})
        r = foo(c, **{'foo': 200})
        self.assertEqual(200, r)

        @endpoints.decorators.param('foo', type=int, max_size=100)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': 200})
        r = foo(c, **{'foo': 20})
        self.assertEqual(20, r)

        @endpoints.decorators.param('foo', type=int, min_size=100, max_size=200)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = foo(c, **{'foo': 120})
        self.assertEqual(120, r)

        @endpoints.decorators.param('foo', type=str, min_size=2, max_size=4)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = foo(c, **{'foo': 'bar'})
        self.assertEqual('bar', r)
        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': 'barbar'})

    def test_param_lambda_type(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=lambda x: x.upper())
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = foo(c, **{'foo': 'bar'})
        self.assertEqual('BAR', r)

    def test_param_empty_default(self):
        c = create_controller()

        @endpoints.decorators.param('foo', default=None)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = foo(c, **{})
        self.assertEqual(None, r)

    def test_param_reference_default(self):
        c = create_controller()

        @param('foo', default={})
        def foo(self, *args, **kwargs):
            kwargs['foo'][testdata.get_ascii()] = testdata.get_ascii()
            return kwargs['foo']

        r = foo(c, **{})
        self.assertEqual(1, len(r))

        r = foo(c, **{})
        self.assertEqual(1, len(r))

        @endpoints.decorators.param('foo', default=[])
        def foo(self, *args, **kwargs):
            kwargs['foo'].append(testdata.get_ascii())
            return kwargs['foo']

        r = foo(c, **{})
        self.assertEqual(1, len(r))

        r = foo(c, **{})
        self.assertEqual(1, len(r))

    def test_param_regex(self):
        c = create_controller()

        @endpoints.decorators.param('foo', regex=r"^\S+@\S+$")
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': 'foo@bar.com'})

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': ' foo@bar.com'})

        @endpoints.decorators.param('foo', regex=re.compile(r"^\S+@\S+$", re.I))
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': 'foo@bar.com'})

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': ' foo@bar.com'})

    def test_param_bool(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=bool, allow_empty=True)
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': 'true'})
        self.assertEqual(True, r)

        r = foo(c, **{'foo': 'True'})
        self.assertEqual(True, r)

        r = foo(c, **{'foo': '1'})
        self.assertEqual(True, r)

        r = foo(c, **{'foo': 'false'})
        self.assertEqual(False, r)

        r = foo(c, **{'foo': 'False'})
        self.assertEqual(False, r)

        r = foo(c, **{'foo': '0'})
        self.assertEqual(False, r)

        @endpoints.decorators.param('bar', type=bool, require=True)
        def bar(self, *args, **kwargs):
            return kwargs['bar']

        r = bar(c, **{'bar': 'False'})
        self.assertEqual(False, r)

    def test_param_list(self):
        c = create_controller()

        @endpoints.decorators.param('foo', type=list)
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': ['bar', 'baz']})
        self.assertEqual(r, ['bar', 'baz'])

    def test_param_arg(self):
        """Make sure positional args work"""
        c = create_controller()

        @param(0)
        def foo(self, *args, **kwargs):
            return list(args)

        r = foo(c, 1)
        self.assertEqual([1], r)

        with self.assertRaises(CallError):
            foo(c)

        @param(0, type=str)
        @param(1, default=20, type=int)
        def foo(self, *args, **kwargs):
            return list(args)

        r = foo(c, 1)
        self.assertEqual(["1", 20], r)

        r = foo(c, 1, 2)
        self.assertEqual(["1", 2], r)

        @param(0, type=str)
        @param(1, default=20, type=int)
        @param("foo", default="bar")
        def foo(self, *args, **kwargs):
            r = list(args) + [kwargs["foo"]]
            return r

        r = foo(c, 1, 2, foo="che")
        self.assertEqual(["1", 2, "che"], r)

        r = foo(c, 1, foo="che")
        self.assertEqual(["1", 20, "che"], r)

        r = foo(c, 1)
        self.assertEqual(["1", 20, "bar"], r)


class RouteTest(TestCase):
    def test_simple(self):
        controller_prefix = "route_simple"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "from endpoints.decorators import route",
            "class Foo(Controller):",
            "    @route(lambda req: len(req.path_args) == 1)",
            "    def GET_1(*args, **kwargs):",
            "        return len(args)",
            "",
            "    @route(lambda req: len(req.path_args) == 2)",
            "    def GET_2(*args, **kwargs):",
            "        return len(args)",
            "",
            "    @route(lambda req: len(req.path_args) == 3)",
            "    def GET_3(*args, **kwargs):",
            "        return len(args)",
            "",
            "    def POST(*args, **kwargs):",
            "        return 4",
        ])

        res = c.handle("/foo")
        self.assertEqual(1, res._body)

        res = c.handle("/foo/2")
        self.assertEqual(2, res._body)

        res = c.handle("/foo/2/3")
        self.assertEqual(3, res._body)

        res = c.handle("/foo", "POST")
        self.assertEqual(4, res._body)

    def test_extend_1(self):
        controller_prefix = "route_extend1"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "from endpoints.decorators import route",
            "",
            "class Foo1(Controller):",
            "    def GET(self): return 1",
            "    def POST(*args, **kwargs): return 5",
            ""
            "class Foo2(Foo1):",
            "    GET = None",
            "    @route(lambda req: len(req.path_args) == 1)",
            "    def GET_1(self): return super(Foo2, self).GET()",
            "    @route(lambda req: len(req.path_args) == 2)",
            "    def GET_2(*args, **kwargs): return len(args)",
            "",
            "class Foo3(Foo2):",
            "    @route(lambda req: len(req.path_args) == 3)",
            "    def GET_3(*args, **kwargs): return len(args)",
            "",
            "class Foo4(Foo3):",
            "    @route(lambda req: len(req.path_args) == 4)",
            "    def GET_4(*args, **kwargs): return len(args)",
        ])

        for path in ["/foo1", "/foo2", "/foo3", "/foo4"]:
            res = c.handle(path)
            self.assertEqual(1, res._body)

        for path in ["/foo2/2", "/foo3/2", "/foo4/2"]:
            res = c.handle(path)
            self.assertEqual(2, res._body)

        res = c.handle("/foo1/2")
        self.assertEqual(405, res.code)

        for path in ["/foo3/2/3", "/foo4/2/3"]:
            res = c.handle(path)
            self.assertEqual(3, res._body)

        res = c.handle("/foo1/2/3")
        self.assertEqual(405, res.code)
        res = c.handle("/foo2/2/3")
        self.assertEqual(405, res.code)

        for path in ["/foo1/2/3/4", "/foo2/2/3/4", "/foo3/2/3/4"]:
            res = c.handle(path)
            self.assertEqual(405, res.code)

        res = c.handle("/foo4/2/3/4")
        self.assertEqual(4, res._body)

        for path in ["/foo1", "/foo2", "/foo3", "/foo4"]:
            res = c.handle(path, "POST")
            self.assertEqual(5, res._body)

    def test_extend_2(self):
        controller_prefix = "route_extend2"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "from endpoints.decorators import route",
            "",
            "class Foo1(Controller):",
            "    def GET(self): return 1",
            "    def POST(*args, **kwargs): return 5",
            ""
            "class Foo2(Foo1):",
            "    @route(lambda req: len(req.path_args) == 2)",
            "    def GET_2(*args, **kwargs): return len(args)",
        ])

        res = c.handle("/foo1")
        self.assertEqual(1, res._body)

        res = c.handle("/foo2")
        self.assertEqual(500, res.code)

    def test_mixed(self):
        """make sure plays nice with param"""
        controller_prefix = "route_mixed"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "from endpoints.decorators import route, param",
            "class Foo(Controller):",
            "    @route(lambda req: len(req.path_args) == 1)",
            "    @param('bar')",
            "    def GET_1(*args, **kwargs):",
            "        return len(args)",
            "",
            "    @param('bar')",
            "    @route(lambda req: len(req.path_args) == 2)",
            "    def GET_2(*args, **kwargs):",
            "        return len(args)",
            "",
        ])

        res = c.handle("/foo")
        self.assertEqual(400, res.code)
        res = c.handle("/foo", query="bar=1")
        self.assertEqual(1, res._body)

        res = c.handle("/foo/2")
        self.assertEqual(400, res.code)
        res = c.handle("/foo/2", query="bar=1")
        self.assertEqual(2, res._body)


class VersionTest(TestCase):
    def test_simple(self):
        controller_prefix = "version_simple"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "from endpoints.decorators import version",
            "class Foo(Controller):",
            "    @version('', 'v1')",
            "    def GET_1(self):",
            "        return 1",
            "",
            "    @version('v2')",
            "    def GET_2(self):",
            "        return 2",
        ])

        res = c.handle("/foo", version="v1")
        self.assertEqual(1, res._body)

        res = c.handle("/foo", version="")
        self.assertEqual(1, res._body)

        res = c.handle("/foo")
        self.assertEqual(1, res._body)

        res = c.handle("/foo", version="v2")
        self.assertEqual(2, res._body)

        res = c.handle("/foo", version="v3")
        self.assertEqual(405, res.code)

    def test_complex(self):
        controller_prefix = "version_complex"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "from endpoints.decorators import version, route",
            "",
            "class Foo(Controller):",
            "    @version('v1')",
            "    @route(lambda req: len(req.path_args) == 1)",
            "    def GET_1_v1(self):",
            "        return 1",
            "",
            "    @version('v2')",
            "    @route(lambda req: len(req.path_args) == 1)",
            "    def GET_1_v2(self):",
            "        return 12",
            "",
            "    @route(lambda req: len(req.path_args) == 2)",
            "    @version('v1')",
            "    def GET_2_v1(self, bit):",
            "        return 2",
            "",
            "    @route(lambda req: len(req.path_args) == 2)",
            "    @version('v2')",
            "    def GET_2_v2(self, bit):",
            "        return 22",
        ])

        res = c.handle("/foo", version="v1")
        self.assertEqual(1, res._body)
        res = c.handle("/foo", version="v2")
        self.assertEqual(12, res._body)

        res = c.handle("/foo/2", version="v1")
        self.assertEqual(2, res._body)
        res = c.handle("/foo/2", version="v2")
        self.assertEqual(22, res._body)


class CodeErrorTest(TestCase):
    def test_raise(self):
        controller_prefix = "ce_raise"
        c = Server(controller_prefix, [
            "from endpoints import Controller",
            "from endpoints.decorators import code_error, param",
            "",
            "class Foo(Controller):",
            "    @code_error(330, ValueError, IndexError)",
            "    @param(0, metavar='error_type', choices=['value', 'index', 'another'])",
            "    def GET(self, error_type):",
            "        if error_type.startswith('value'):",
            "            raise ValueError()",
            "        elif error_type.startswith('index'):",
            "            raise IndexError()",
            "        else:",
            "            raise RuntimeError()",
        ])

        res = c.handle("/foo/value")
        self.assertEqual(330, res.code)

        res = c.handle("/foo/index")
        self.assertEqual(330, res.code)

        res = c.handle("/foo/another")
        self.assertEqual(500, res.code)

        res = c.handle("/foo/bar")
        self.assertEqual(400, res.code)

