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
    ratelimit_param,
    ratelimit_param_ip,
)
from endpoints.decorators.auth import (
    AuthDecorator,
    auth_basic,
    auth_bearer,
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
    def get_basic_auth_header(self, username, password):
        credentials = Base64.encode('{}:{}'.format(username, password))
        return 'Basic {}'.format(credentials)

    def get_bearer_auth_header(self, token):
        return 'Bearer {}'.format(token)

    def set_bearer_auth_header(self, request, token):
        request.set_header(
            "Authorization",
            self.get_bearer_auth_header(token)
        )

    def create_controller(self, *methods):
        """Create a fake controller to make it easier to test controller
        decorators

        :param *methods: one or more callables that will be set on the
            controller
        """
        class FakeController(Controller):
            async def POST(self): pass
            async def GET(self): pass

        if methods:
            for method in methods:
                setattr(FakeController, method.__name__, method)

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
    def rollback_now(self, method, ttl):
        """Rolls back the "date" time on the decorator so expiration can be
        tested, this is better than calling time.sleep

        :param method: callable, the method to rollback the calls on
        :param ttl: int, the amount to rollback, so if you passed in 1 then
            it would rollback 1 second
        """
        for call in method.__orig_decorator__.backend._calls.values():
            call["date"] -= ttl

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

        with self.assertRaises(CallError):
            await c.bar()

        c.request = r_foo

        self.rollback_now(c.foo, 1)

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

        self.rollback_now(o.foo, 1)
        o.request.set_header("X_FORWARDED_FOR", "100.1.1.1")
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

        self.rollback_now(o.foo, 1)
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

            o = MockObject()

            with self.assertRaises(CallError):
                await o.rl_param_ip(bar=1)

            with self.assertRaises(CallError):
                await o.rl_ip()

            with self.assertRaises(CallError):
                await o.rl_param(bar=1)

    async def test_async(self):
        @ratelimit_ip()
        async def rl_ip(self):
            return 2

        @ratelimit_param_ip("bar")
        async def rl_param_ip(self, **kwargs):
            return 3

        @ratelimit_param("bar")
        async def rl_param(self, **kwargs):
            return 4

        o = self.create_controller(
            rl_ip,
            rl_param_ip,
            rl_param,
        )

        self.assertEqual(2, await o.rl_ip())
        self.assertEqual(3, await o.rl_param_ip(bar=1))
        self.assertEqual(4, await o.rl_param(bar=1))


class AuthDecoratorTest(TestCase):
    async def test_bad_setup(self):
        async def target(*args, **kwargs):
            return False

        class MockObject(object):
            @auth_bearer(target=target)
            def foo_bearer(self):
                pass

            @auth_basic(target=target)
            def foo_basic(self):
                pass

        c = MockObject()
        c.request = Request()

        for m in ["foo_bearer", "foo_basic"]: 
            with self.assertRaises(AccessDenied):
                await getattr(c, m)()

    async def test_auth_bearer(self):
        async def target(controller, token):
            if token == "foo":
                raise ValueError()

            if token == "bar":
                return True

            elif token == "che":
                return False

        @auth_bearer(target=target)
        def foo(self, **kwargs):
            pass

        c = self.create_controller(foo)

        c.request.set_header(
            "authorization",
            self.get_bearer_auth_header("foo")
        )
        with self.assertRaises(AccessDenied):
            await c.foo()

        c.request.set_header(
            "authorization",
            self.get_bearer_auth_header("bar")
        )
        await c.foo()

        c.request = Request()

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
        single exception, even errors that were raised in like a POST method
        body in AccessDenied. This makes sure that is fixed"""
        async def target(controller, **kwargs):
            return True

        @auth_basic(target=target)
        async def foo_basic(self):
            raise ValueError("foo_basic")

        @auth_bearer(target=target)
        async def foo_token(self):
            raise ValueError("foo_token")

        c = self.create_controller(foo_basic, foo_token)

        c.request = self.mock(
            get_auth_basic=("foo", "bar"),
            get_auth_bearer="foobar",
        )

        with self.assertRaises(ValueError):
            await c.foo_basic()

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
            "    def GET(self, error_type, /):",
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

