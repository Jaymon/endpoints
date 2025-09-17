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
#     BackendDecorator,
)
from endpoints.decorators.limit import (
    RateLimitDecorator,
)
from endpoints.decorators.auth import (
    AuthDecorator,
    auth_basic,
    auth_bearer,
)
from endpoints.decorators.call import (
    httpcache,
    nohttpcache,
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


class RateLimitTest(TestCase):
    def rollback_now(self, method, ttl):
        """Rolls back the "date" time on the decorator so expiration can be
        tested, this is better than calling time.sleep

        :param method: callable, the method to rollback the calls on
        :param ttl: int, the amount to rollback, so if you passed in 1 then
            it would rollback 1 second
        """
        for call in method.__orig_decorator__._calls.values():
            call["date"] -= ttl

    async def test_lifecycle(self):
        class limit(RateLimitDecorator):
            async def get_key(self, controller, method_args, method_kwargs):
                return "bar"

        class MockObject(object):
            @limit(limit=3, ttl=1)
            async def foo(self):
                return 1

        c = MockObject()
        #c.request = Request()

        for x in range(3):
            r = await c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(CallError):
                await c.foo()

        self.rollback_now(c.foo, 1)

        for x in range(3):
            r = await c.foo()
            self.assertEqual(1, r)

        for x in range(2):
            with self.assertRaises(CallError):
                await c.foo()


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


class VersionTest(TestCase):
    def test_simple(self):
        c = self.create_server([
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

