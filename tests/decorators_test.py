from . import TestCase, skipIf, SkipTest
import time
import re
import base64

import testdata

import endpoints
from endpoints import CallError
from endpoints.decorators import param, post_param


def create_controller():
    class FakeController(endpoints.Controller, endpoints.CorsMixin):
        def POST(self): pass
        def GET(self): pass

    res = endpoints.Response()

    req = endpoints.Request()
    req.method = 'GET'

    c = FakeController(req, res)
    return c


class DecoratorsRatelimitTest(TestCase):
    def test_throttle(self):

        class TARA(object):
            @endpoints.decorators.ratelimit(limit=3, ttl=1)
            def foo(self): return 1

            @endpoints.decorators.ratelimit(limit=10, ttl=1)
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
            with self.assertRaises(endpoints.CallError):
                c.foo()

        # make sure another path isn't messed with by foo
        r_bar = endpoints.Request()
        r_bar.set_header("X_FORWARDED_FOR", "276.0.0.1")
        r_bar.path = "/bar"
        c.request = r_bar
        for x in range(10):
            r = c.bar()
            self.assertEqual(2, r)
            time.sleep(0.1)

        with self.assertRaises(endpoints.CallError):
            c.bar()

        c.request = r_foo

        for x in range(3):
            r = c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(endpoints.CallError):
                c.foo()


class DecoratorsAuthTest(TestCase):
    def get_basic_auth_header(self, username, password):
        credentials = base64.b64encode('{}:{}'.format(username, password)).strip()
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

    def test_basic_auth(self):
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
    def test_require_params(self):
        class MockObject(object):
            request = endpoints.Request()

            @endpoints.decorators.require_params('foo', 'bar')
            def foo(self, *args, **kwargs): return 1

            @endpoints.decorators.require_params('foo', 'bar', allow_empty=True)
            def bar(self, *args, **kwargs): return 2

        o = MockObject()
        o.request.method = 'GET'
        o.request.query_kwargs = {'foo': 1}

        with self.assertRaises(endpoints.CallError):
            o.foo()

        with self.assertRaises(endpoints.CallError):
            o.bar()

        o.request.query_kwargs['bar'] = 2
        r = o.foo(**o.request.query_kwargs)
        self.assertEqual(1, r)

        r = o.bar(**o.request.query_kwargs)
        self.assertEqual(2, r)

        o.request.query_kwargs['bar'] = 0
        with self.assertRaises(endpoints.CallError):
            o.foo(**o.request.query_kwargs)

        r = o.bar(**o.request.query_kwargs)
        self.assertEqual(2, r)

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
        charset = r.charset
        c.request = r
        #self.assertEqual("UTF-8", charset)

        @endpoints.decorators.param('foo', type=str)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        words = testdata.get_unicode_words()
        ret = foo(c, **{"foo": words})
        self.assertEqual(ret, words.encode("UTF-8"))

    #def test_param_append_list(self):
        # TODO -- make this work


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
        self.assertEqual(range(1, 6), r)

        c.request.query_kwargs = {'foo': '1,2,3,4'}
        @endpoints.decorators.get_param('foo', type=int, action='store_list')
        def foo(*args, **kwargs):
            return kwargs['foo']
        r = foo(c, **c.request.query_kwargs)
        self.assertEqual(range(1, 5), r)

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

        @endpoints.decorators.param('foo', regex="^\S+@\S+$")
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = foo(c, **{'foo': 'foo@bar.com'})

        with self.assertRaises(endpoints.CallError):
            r = foo(c, **{'foo': ' foo@bar.com'})

        @endpoints.decorators.param('foo', regex=re.compile("^\S+@\S+$", re.I))
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

