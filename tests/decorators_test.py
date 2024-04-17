# -*- coding: utf-8 -*-
import time
import re

import endpoints
from endpoints.call import (
    Controller,
    Request,
    Response,
)
from endpoints.exception import (
    CallError,
    AccessDenied,
)
from endpoints.utils import Base64, String
from endpoints.decorators.base import (
    ControllerDecorator,
    BackendDecorator,
)
from endpoints.decorators.limit import (
    RateLimitDecorator,
    ratelimit_ip,
    ratelimit_access_token,
    ratelimit_param,
    ratelimit_param_ip,
)
from endpoints.decorators.auth import (
    AuthDecorator,
    auth_basic,
    auth_client,
    auth_token,
)
from endpoints.decorators.utils import (
    httpcache,
    nohttpcache,
    code_error,
)
from endpoints.decorators.call import (
    param,
)


from . import (
    testdata,
    IsolatedAsyncioTestCase,
)


class TestCase(IsolatedAsyncioTestCase):
    def create_controller(self):
        class FakeController(Controller):
            async def POST(self): pass
            async def GET(self): pass

        res = Response()
        req = Request()
        req.method = 'GET'

        c = FakeController(req, res)
        return c


class ControllerDecoratorTest(TestCase):
    async def test_async_handle(self):
        class Dec(ControllerDecorator):
            async def handle(self, *args, **kwargs):
                return True

        c = self.create_controller()
        @Dec()
        async def func(self):
            return 1

        self.assertEqual(1, await func(c))

    async def test_sync_handle(self):
        class Dec(ControllerDecorator):
            def handle(self, *args, **kwargs):
                return True

        c = self.create_controller()
        @Dec()
        async def func(self):
            return 1

        self.assertEqual(1, await func(c))

    async def test_generator(self):
        """asyncio.iscoroutine treats any generator like a coroutine, this makes
        sure wrapped controller methods function as expected if the controller
        method returns a decorator"""
        c = self.create_controller()

        @ControllerDecorator
        async def func(self):
            for x in range(10):
                yield x

        count = 0
        async for x in await func(c):
            count += 1
        self.assertEqual(10, count)

        @ControllerDecorator
        def func(self):
            for x in range(10):
                yield x

        count = 0
        for x in await func(c):
            count += 1
        self.assertEqual(10, count)


class BackendDecoratorTest(TestCase):
    async def test_async_handle(self):
        class Backend(object):
            async def handle(self, *args, **kwargs):
                return True

        class Dec(BackendDecorator):
            backend_class = Backend

        c = self.create_controller()
        @Dec()
        async def func(self):
            return 1

        self.assertEqual(1, await func(c))

    async def test_sync_handle(self):
        class Backend(object):
            def handle(self, *args, **kwargs):
                return True

        class Dec(BackendDecorator):
            backend_class = Backend

        c = self.create_controller()
        @Dec()
        async def func(self):
            return 1

        self.assertEqual(1, await func(c))


class RateLimitTest(TestCase):
    def set_bearer_auth_header(self, request, access_token):
        request.set_header("authorization", 'Bearer {}'.format(access_token))

    async def test_throttle(self):
        class MockObject(object):
            @ratelimit_ip(limit=3, ttl=1)
            def foo(self):
                return 1

            @ratelimit_ip(limit=10, ttl=1)
            def bar(self):
                return 2


        r_foo = Request()
        r_foo.set_header("X_FORWARDED_FOR", "276.0.0.1")
        r_foo.path = "/foo"
        c = MockObject()
        c.request = r_foo

        for x in range(3):
            r = await c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(CallError):
                await c.foo()

        # make sure another path isn't messed with by foo
        r_bar = Request()
        r_bar.set_header("X_FORWARDED_FOR", "276.0.0.1")
        r_bar.path = "/bar"
        c.request = r_bar
        for x in range(10):
            r = await c.bar()
            self.assertEqual(2, r)
            time.sleep(0.1)

        with self.assertRaises(CallError):
            await c.bar()

        c.request = r_foo

        for x in range(3):
            r = await c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(CallError):
                await c.foo()

    async def test_ratelimit_ip(self):
        class MockObject(object):
            @ratelimit_ip(limit=3, ttl=1)
            def foo(self):
                return 1

        o = MockObject()
        o.request = Request()
        o.request.set_header("X_FORWARDED_FOR", "100.1.1.1")
        o.request.path = "/fooip"

        for _ in range(3):
            await o.foo()

        with self.assertRaises(CallError) as cm:
            await o.foo()
        self.assertEqual(429, cm.exception.code)

        # make sure another request gets through just fine
        orig_r = o.request
        o.request = Request()
        o.request.path = "/fooip"
        o.request.set_header("X_FORWARDED_FOR", "100.1.1.2")
        await o.foo()
        o.request = orig_r

        time.sleep(1)
        o.request.set_header("X_FORWARDED_FOR", "100.1.1.1")
        r = await o.foo()
        self.assertEqual(1, r)

    async def test_ratelimit_access_token(self):
        class MockObject(object):
            @ratelimit_access_token(limit=2, ttl=1)
            def foo(self):
                return 1

        o = MockObject()
        o.request = Request()
        self.set_bearer_auth_header(o.request, "footoken")
        o.request.path = "/footoken"

        o.request.set_header("X_FORWARDED_FOR", "1.1.1.1")
        await o.foo()

        o.request.set_header("X_FORWARDED_FOR", "1.1.1.2")
        await o.foo()

        with self.assertRaises(CallError) as cm:
            await o.foo()
        self.assertEqual(429, cm.exception.code)

        # make sure another request gets through just fine
        orig_r = o.request
        o.request = Request()
        o.request.path = "/footoken"
        self.set_bearer_auth_header(o.request, "footoken2")
        await o.foo()
        o.request = orig_r

        time.sleep(1)
        self.set_bearer_auth_header(o.request, "footoken")
        o.request.set_header("X_FORWARDED_FOR", "1.1.1.3")
        r = await o.foo()
        self.assertEqual(1, r)

    async def test_ratelimit_param_only(self):
        class MockObject(object):
            @ratelimit_param("bar", limit=2, ttl=1)
            def foo(self, **kwargs):
                return 1

        o = MockObject()
        o.request = Request()
        self.set_bearer_auth_header(o.request, "footoken")
        o.request.path = "/fooparam"

        await o.foo(bar="che")
        await o.foo(bar="che")

        with self.assertRaises(CallError) as cm:
            await o.foo(bar="che")
        self.assertEqual(429, cm.exception.code)

        # make sure bar not existing is not a problem
        for x in range(5):
            self.assertEqual(1, await o.foo())

        # just make sure something else goes through just fine
        orig_r = o.request
        o.request = Request()
        o.request.path = "/fooparam"
        await o.foo(bar="baz")
        o.request = orig_r

        time.sleep(1)
        r = await o.foo(bar="che")
        self.assertEqual(1, r)

    async def test_ratelimit_param_ip(self):
        def create_request(ip):
            r = Request()
            r.path = "/fooparam"
            r.set_header("X_FORWARDED_FOR", ip)
            self.set_bearer_auth_header(r, "footoken")
            return r

        class MockObject(object):
            @ratelimit_param_ip("bar", limit=1, ttl=1)
            def foo(self, **kwargs):
                return 1

        o = MockObject()
        o.request = create_request("200.1.1.1")
        await o.foo(bar="che")

        with self.assertRaises(CallError) as cm:
            await o.foo(bar="che")
        self.assertEqual(429, cm.exception.code)

        # now make sure another ip address can get through
        o.request = create_request("200.1.1.2")
        await o.foo(bar="che")

        with self.assertRaises(CallError) as cm:
            await o.foo(bar="che")
        self.assertEqual(429, cm.exception.code)

        # now make sure another value makes it through
        await o.foo(bar="baz")
        with self.assertRaises(CallError):
            await o.foo(bar="baz")

        # make sure bar not existing is not a problem
        for x in range(5):
            self.assertEqual(1, await o.foo())

    async def test_backend(self):
        class Backend(object):
            def handle(self, request, key, limit, ttl):
                return False

        with testdata.environment(RateLimitDecorator, backend_class=Backend):
            class MockObject(object):
                request = Request()

                @ratelimit_ip()
                def rl_ip(self):
                    return 2

                @ratelimit_param_ip("bar")
                def rl_param_ip(self, **kwargs):
                    return 3

                @ratelimit_param("bar")
                def rl_param(self, **kwargs):
                    return 4

                @ratelimit_access_token()
                def rl_access_token(self):
                    return 5

            o = MockObject()

            with self.assertRaises(CallError):
                await o.rl_param_ip(bar=1)

            with self.assertRaises(CallError):
                await o.rl_ip()

            with self.assertRaises(CallError):
                await o.rl_param(bar=1)

            with self.assertRaises(CallError):
                await o.rl_access_token()

    async def test_async(self):
        class MockObject(object):
            request = Request()

            @ratelimit_ip()
            async def rl_ip(self):
                return 2

            @ratelimit_param_ip("bar")
            async def rl_param_ip(self, **kwargs):
                return 3

            @ratelimit_param("bar")
            async def rl_param(self, **kwargs):
                return 4

            @ratelimit_access_token()
            async def rl_access_token(self):
                return 5

        o = MockObject()

        self.assertEqual(2, await o.rl_ip())
        self.assertEqual(3, await o.rl_param_ip(bar=1))
        self.assertEqual(4, await o.rl_param(bar=1))
        self.assertEqual(5, await o.rl_access_token())


class AuthDecoratorTest(TestCase):
    def get_basic_auth_header(self, username, password):
        credentials = Base64.encode('{}:{}'.format(username, password))
        return 'Basic {}'.format(credentials)

    def get_bearer_auth_header(self, access_token):
        return 'Bearer {}'.format(access_token)

    async def test_bad_setup(self):
        async def target(*args, **kwargs):
            return False

        class MockObject(object):
            @auth_token(target=target)
            def foo_token(self):
                pass

            @auth_client(target=target)
            async def foo_client(self):
                pass

            @auth_basic(target=target)
            def foo_basic(self):
                pass

        c = MockObject()
        c.request = Request()

        for m in ["foo_token", "foo_client", "foo_basic"]: 
            with self.assertRaises(AccessDenied):
                await getattr(c, m)()

    async def test_auth_token(self):
        async def target(controller, access_token):
            if access_token == "foo":
                raise ValueError()

            if access_token == "bar":
                return True

            elif access_token == "che":
                return False

        class MockObject(object):
            @auth_token(target=target)
            def foo(self):
                pass

        r = Request()

        c = MockObject()
        c.request = r

        r.set_header('authorization', self.get_bearer_auth_header("foo"))
        with self.assertRaises(AccessDenied):
            await c.foo()

        r.set_header('authorization', self.get_bearer_auth_header("bar"))
        await c.foo()

        r = Request()
        c.request = r

        r.body_kwargs["access_token"] = "foo"
        with self.assertRaises(AccessDenied):
            await c.foo()

        r.body_kwargs["access_token"] = "bar"
        await c.foo()

        r = Request()
        c.request = r

        r.query_kwargs["access_token"] = "foo"
        with self.assertRaises(AccessDenied):
            await c.foo()

        r.query_kwargs["access_token"] = "bar"
        await c.foo()

        r.query_kwargs["access_token"] = "che"
        with self.assertRaises(AccessDenied):
            await c.foo()

    async def test_auth_client(self):
        async def target(controller, client_id, client_secret):
            return client_id == "foo" and client_secret == "bar"

        class MockObject(object):
            @auth_client(target=target)
            async def foo(self):
                pass

        client_id = "foo"
        client_secret = "..."
        r = Request()

        c = MockObject()
        c.request = r

        r.set_header(
            'authorization',
            self.get_basic_auth_header(client_id, client_secret)
        )
        with self.assertRaises(AccessDenied):
            await c.foo()

        client_secret = "bar"
        r.set_header(
            'authorization',
            self.get_basic_auth_header(client_id, client_secret)
        )
        await c.foo()

    async def test_auth_basic_simple(self):
        async def target(controller, username, password):
            if username == "foo":
                raise ValueError()

            elif username == "bar":
                return True

            else:
                return False

        class MockObject(object):
            @auth_basic(target=target)
            async def foo(self):
                pass

        username = "foo"
        password = "..."
        r = Request()
        c = MockObject()
        c.request = r

        r.set_header(
            'authorization',
            self.get_basic_auth_header(username, password)
        )
        with self.assertRaises(AccessDenied):
            await c.foo()

        username = "bar"
        r.set_header(
            'authorization',
            self.get_basic_auth_header(username, password)
        )
        await c.foo()

        username = "che"
        r.set_header(
            'authorization',
            self.get_basic_auth_header(username, password)
        )
        with self.assertRaises(AccessDenied):
            await c.foo()

    async def test_auth_basic_same_kwargs(self):
        async def target(controller, username, password):
            if username == "foo":
                raise ValueError()

            elif username == "bar":
                return True

            else:
                return False

        class MockObject(object):
            @auth_basic(target=target)
            async def foo(self, **kwargs):
                return 1

        c = MockObject()
        username = "bar"
        password = "..."
        r = Request()
        r.set_header(
            'authorization',
            self.get_basic_auth_header(username, password)
        )
        c.request = r

        # if no TypeError is raised then it worked :)
        r = await c.foo(request="this_should_error_out")
        self.assertEqual(1, r)

    async def test_auth_extend(self):
        class auth(AuthDecorator):
            async def handle(self, controller, **kwargs):
                if controller.request.body_kwargs["foo"] == "bar":
                    return True

                elif controller.request.body_kwargs["foo"] == "che":
                    raise ValueError()

                else:
                    return False

        class MockObject(object):
            @auth
            def foo(self):
                pass

        r = Request()
        c = MockObject()
        c.request = r

        r.body_kwargs = {"foo": "che"}
        with self.assertRaises(AccessDenied):
            await c.foo()

        r.body_kwargs = {"foo": "bar"}
        await c.foo()

    def test_no_call(self):
        c = self.create_server([
            "from endpoints import Controller",
            "from endpoints.decorators import AuthDecorator",
            "class auth(AuthDecorator):",
            "    async def handle(self, controller, **kwargs):",
            "        return True",
            "",
            "class Foo(Controller):",
            "    @auth",
            "    async def GET(self):",
            "        return 1",
        ])

        r = c.handle("/foo")
        self.assertEqual(200, r.code)
        self.assertEqual(1, r.body)

    async def test_auth_unrelated_error(self):
        """There was an earlier iteration of AuthDecorator that wrapped every
        single exceptions, even errors that were raised in like a POST method
        body in AccessDenied. This makes sure that is fixed"""
        async def target(controller, **kwargs):
            return True

        class MockObject(object):
            @auth_basic(target=target)
            async def foo_basic(self):
                raise ValueError("foo_basic")

            @auth_client(target=target)
            async def foo_client(self):
                raise ValueError("foo_client")

            @auth_token(target=target)
            async def foo_token(self):
                raise ValueError("foo_token")

        c = MockObject()
        c.request = self.mock(
            get_auth_basic=("foo", "bar"),
            client_tokens=("foo", "bar"),
            get_auth_bearer="foobar",
        )

        with self.assertRaises(ValueError):
            await c.foo_basic()

        with self.assertRaises(ValueError):
            await c.foo_client()

        with self.assertRaises(ValueError):
            await c.foo_token()


class CacheTest(TestCase):
    async def test_httpcache(self):
        c = self.create_controller()

        @httpcache(500)
        async def func(self):
            pass

        await func(c)
        h = c.response.get_header("Cache-Control")
        self.assertTrue("max-age=500" in h)

    async def test_nohttpcache(self):
        c = self.create_controller()

        @nohttpcache
        async def func(self): pass

        await func(c)
        h = c.response.get_header("Cache-Control")
        self.assertTrue("no-cache" in h)

        h = c.response.get_header("Pragma")
        self.assertTrue("no-cache" in h)


class CodeErrorTest(TestCase):
    async def test_code_error(self):
        c = self.create_controller()

        @code_error(413, IOError)
        async def func(self):
            raise IOError()

        with self.assertRaises(CallError) as e:
            await func(c)
            self.assertEqual(413, e.code)

    def test_raise(self):
        c = self.create_server([
            "from endpoints import Controller",
            "from endpoints.decorators import code_error, param",
            "",
            "class Foo(Controller):",
            "    @code_error(330, ValueError, IndexError)",
            "    @param(",
            "        0,",
            "        metavar='error_type',",
            "        choices=['value', 'index', 'another'],"
            "    )",
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


class ParamTest(TestCase):
    def test_type_string_casting(self):
        """I made a change in v4.0.0 that would encode a value to String when the 
        param type was a str descendent, but my change was bad because it would 
        just cast it to a String, not to the type, this makes sure that's fixed"""
        c = self.create_server([
            "from endpoints.compat import String",
            "from endpoints import Controller, param",
            "",
            "class Che(String):",
            "    def __new__(cls, *args, **kwargs):",
            "        return super(Che, cls).__new__(cls, *args, **kwargs)",
            "",
            "class Default(Controller):",
            "    @param('che', type=Che)",
            "    def POST_bar(self, **kwargs):",
            "        t = kwargs['che']",
            "        return t.__class__.__name__",
        ])

        r = c.post("/", {"che": "1234"})
        self.assertEqual("Che", r._body)

    def test_type_issue_76(self):
        """
        https://github.com/Jaymon/endpoints/issues/76
        """
        c = self.create_server([
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
        c = self.create_server([
            "import datetime",
            "from endpoints import Controller, param",
            "",
            "def parse(dts):",
            "    return datetime.datetime.strptime(dts, '%Y-%m-%d')",
            "",
            "class Foo(Controller):",
            "    @param(",
            "        'dt',",
            "        regex=r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$',",
            "        type=parse",
            "    )",
            "    def GET(self, **kwargs):",
            "        return kwargs['dt']",
            "",
        ])

        res = c.handle("/foo", query="dt=2018-01-01")
        self.assertEqual(res._body.year, 2018)
        self.assertEqual(res._body.month, 1)
        self.assertEqual(res._body.day, 1)

    async def test_append_list_choices(self):
        c = self.create_controller()

        @param('foo', action="append_list", type=int, choices=[1, 2])
        def foo(self, *args, **kwargs):
            return kwargs["foo"]

        r = await foo(c, foo="1,2")
        self.assertEqual([1, 2], r)

        with self.assertRaises(CallError):
            await foo(c, **{'foo': "1,2,3"})

        r = await foo(c, **{'foo': 1})
        self.assertEqual([1], r)

        with self.assertRaises(CallError):
            await foo(c, **{'foo': 3})

    async def test_param_dest(self):
        """make sure the dest=... argument works"""
        # https://docs.python.org/2/library/argparse.html#dest
        c = self.create_controller()

        @param('foo', dest='bar')
        def foo(self, *args, **kwargs):
            return kwargs.get('bar')

        r = await foo(c, **{'foo': 1})
        self.assertEqual(1, r)

    async def test_param_multiple_names(self):
        c = self.create_controller()

        @param('foo', 'foos', 'foo3', type=int)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        r = await foo(c, **{'foo': 1})
        self.assertEqual(1, r)

        r = await foo(c, **{'foos': 2})
        self.assertEqual(2, r)

        r = await foo(c, **{'foo3': 3})
        self.assertEqual(3, r)

        with self.assertRaises(CallError):
            await foo(c, **{'foo4': 0})

    async def test_param_callable_default(self):
        c = self.create_controller()

        @param('foo', default=time.time)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        start = time.time()
        r1 = await foo(c, **{})
        self.assertLess(start, r1)

        time.sleep(0.1)
        r2 = await foo(c, **{})
        self.assertLess(r1, r2)

    async def test_param_not_required(self):
        c = self.create_controller()

        @param('foo', required=False)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = await foo(c, **{'foo': 1})
        self.assertTrue(r)

        r = await foo(c, **{})
        self.assertFalse(r)

        @param('foo', required=False, default=5)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = await foo(c, **{})
        self.assertTrue(r)

        @param('foo', type=int, required=False)
        def foo(self, *args, **kwargs):
            return 'foo' in kwargs

        r = await foo(c, **{})
        self.assertFalse(r)

    async def test_param_unicode(self):
        c = self.create_controller()
        r = Request()
        r.set_header("content-type", "application/json;charset=UTF-8")
        charset = r.encoding
        c.request = r

        @param('foo', type=str)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        words = self.get_unicode_words()
        ret = await foo(c, **{"foo": words})
        self.assertEqual(String(ret), String(words))

    async def test_param_1(self):
        c = self.create_controller()

        @param('foo', type=int)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        with self.assertRaises(CallError):
            r = await foo(c, **{'foo': 0})

        @param('foo', default=0)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        r = await foo(c, **{})
        self.assertEqual(0, r)

        @param('foo', type=int, choices=set([1, 2, 3]))
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')

        c.request.method = 'POST'
        c.request.body_kwargs = {'foo': '1'}
        r = await foo(c, **c.request.body_kwargs)
        self.assertEqual(1, r)

        c.request.body_kwargs = {}
        r = await foo(c, **{'foo': '2'})
        self.assertEqual(2, r)

    async def test_param_size(self):
        c = self.create_controller()

        @param('foo', type=int, min_size=100)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        with self.assertRaises(CallError):
            await foo(c, **{'foo': 0})
        r = await foo(c, **{'foo': 200})
        self.assertEqual(200, r)

        @param('foo', type=int, max_size=100)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        with self.assertRaises(CallError):
            await foo(c, **{'foo': 200})
        r = await foo(c, **{'foo': 20})
        self.assertEqual(20, r)

        @param('foo', type=int, min_size=100, max_size=200)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = await foo(c, **{'foo': 120})
        self.assertEqual(120, r)

        @param('foo', type=str, min_size=2, max_size=4)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = await foo(c, **{'foo': 'bar'})
        self.assertEqual('bar', r)
        with self.assertRaises(CallError):
            await foo(c, **{'foo': 'barbar'})

    async def test_param_lambda_type(self):
        c = self.create_controller()

        @param('foo', type=lambda x: x.upper())
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = await foo(c, **{'foo': 'bar'})
        self.assertEqual('BAR', r)

    async def test_param_empty_default(self):
        c = self.create_controller()

        @param('foo', default=None)
        def foo(self, *args, **kwargs):
            return kwargs.get('foo')
        r = await foo(c, **{})
        self.assertEqual(None, r)

    async def test_param_reference_default(self):
        c = self.create_controller()

        @param('foo', default={})
        def foo(self, *args, **kwargs):
            kwargs['foo'][testdata.get_ascii()] = testdata.get_ascii()
            return kwargs['foo']

        r = await foo(c, **{})
        self.assertEqual(1, len(r))

        r = await foo(c, **{})
        self.assertEqual(1, len(r))

        @param('foo', default=[])
        def foo(self, *args, **kwargs):
            kwargs['foo'].append(testdata.get_ascii())
            return kwargs['foo']

        r = await foo(c, **{})
        self.assertEqual(1, len(r))

        r = await foo(c, **{})
        self.assertEqual(1, len(r))

    async def test_param_regex(self):
        c = self.create_controller()

        @param('foo', regex=r"^\S+@\S+$")
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = await foo(c, **{'foo': 'foo@bar.com'})

        with self.assertRaises(CallError):
            r = await foo(c, **{'foo': ' foo@bar.com'})

        @param('foo', regex=re.compile(r"^\S+@\S+$", re.I))
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = await foo(c, **{'foo': 'foo@bar.com'})

        with self.assertRaises(CallError):
            await foo(c, **{'foo': ' foo@bar.com'})

    async def test_param_bool(self):
        c = self.create_controller()

        @param('foo', type=bool, allow_empty=True)
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = await foo(c, **{'foo': 'true'})
        self.assertEqual(True, r)

        r = await foo(c, **{'foo': 'True'})
        self.assertEqual(True, r)

        r = await foo(c, **{'foo': '1'})
        self.assertEqual(True, r)

        r = await foo(c, **{'foo': 'false'})
        self.assertEqual(False, r)

        r = await foo(c, **{'foo': 'False'})
        self.assertEqual(False, r)

        r = await foo(c, **{'foo': '0'})
        self.assertEqual(False, r)

        @param('bar', type=bool, require=True)
        def bar(self, *args, **kwargs):
            return kwargs['bar']

        r = await bar(c, **{'bar': 'False'})
        self.assertEqual(False, r)

    async def test_param_list(self):
        c = self.create_controller()

        @param('foo', type=list)
        def foo(self, *args, **kwargs):
            return kwargs['foo']

        r = await foo(c, **{'foo': ['bar', 'baz']})
        self.assertEqual(r, ['bar', 'baz'])

    async def test_param_arg(self):
        """Make sure positional args work"""
        c = self.create_controller()

        @param(0)
        def foo(self, *args, **kwargs):
            return list(args)

        r = await foo(c, 1)
        self.assertEqual([1], r)

        with self.assertRaises(CallError):
            await foo(c)

        @param(0, type=str)
        @param(1, default=20, type=int)
        def foo(self, *args, **kwargs):
            return list(args)

        r = await foo(c, 1)
        self.assertEqual(["1", 20], r)

        r = await foo(c, 1, 2)
        self.assertEqual(["1", 2], r)

        @param(0, type=str)
        @param(1, default=20, type=int)
        @param("foo", default="bar")
        def foo(self, *args, **kwargs):
            r = list(args) + [kwargs["foo"]]
            return r

        r = await foo(c, 1, 2, foo="che")
        self.assertEqual(["1", 2, "che"], r)

        r = await foo(c, 1, foo="che")
        self.assertEqual(["1", 20, "che"], r)

        r = await foo(c, 1)
        self.assertEqual(["1", 20, "bar"], r)


class VersionTest(TestCase):
    def test_simple(self):
        c = self.create_server([
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
        self.assertEqual(404, res.code)

