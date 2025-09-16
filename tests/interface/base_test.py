# -*- coding: utf-8 -*-

from endpoints.call import Controller
from endpoints.interface.base import BaseApplication

from . import TestCase


class BaseApplicationTest(TestCase):
    def test_routing_error_unexpected_args(self):
        c = self.create_server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(foo=2))
        self.assertEqual(404, res.code)

        c = self.create_server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(che=2))
        self.assertEqual(404, res.code)

        c = self.create_server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(404, res.code)

        c = self.create_server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(409, res.code)

        c = self.create_server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo", query_kwargs=dict(bar=2))
        self.assertEqual(405, res.code)

        c = self.create_server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar")
        self.assertEqual(404, res.code)

        c = self.create_server(contents=[
            "from endpoints import Controller, param",
            "class Default(Controller):",
            "    def GET(self, foo, **kwargs):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(404, res.code)

    def test_routing_error_unexpected_args(self):
        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(foo=2))
        self.assertEqual(400, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(che=2))
        self.assertEqual(400, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(400, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(400, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo", query_kwargs=dict(bar=2))
        self.assertEqual(400, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, foo):",
            "        pass",
        ])
        res = c.handle("/foo/bar")
        self.assertEqual(404, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, foo, **kwargs):",
            "        pass",
        ])
        res = c.get("/foo/bar", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(400, res.code)

    def test_routing_error_no_args(self):
        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self):",
            "        pass",
        ])
        res = c.get("/", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(400, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self):",
            "        pass",
        ])
        res = c.handle("/foo/bar/che/baz/boom/bam/blah")
        self.assertEqual(404, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, **kwargs):",
            "        pass",
        ])
        res = c.handle(
            "/foo/bar/che/baz/boom/bam/blah",
            query_kwargs=dict(foo=1, bar=2)
        )
        self.assertEqual(404, res.code)

        c = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, **kwargs):",
            "        return kwargs",
        ])
        res = c.handle("/", query_kwargs=dict(foo=1, bar=2))
        self.assertEqual(200, res.code)
        self.assertTrue("foo" in res._body)

    def test_lowercase_method(self):
        c = self.create_server({"foo2": [
            "class Bar(Controller):",
            "    def get(*args, **kwargs): pass"
        ]})

        res = c.handle("/foo2/bar", query_kwargs={'foo2': 'bar', 'che': 'baz'})
        self.assertEqual(501, res.code)

    def test_handle_redirect(self):
        c = self.create_server({"handle": [
            "class Testredirect(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise Redirect('http://example.com')"
        ]})

        res = c.handle("/handle/testredirect")
        self.assertEqual(302, res.code)
        self.assertEqual('http://example.com', res.headers['Location'])

    def test_handle_404_typeerror_1(self):
        """make sure not having a controller is correctly identified as a 404"""
        c = self.create_server([
            "class NoFoo(Controller):",
            "    def GET(*args, **kwargs):",
            "        pass",
        ])

        res = c.handle("/foo/boom")
        self.assertEqual(404, res.code)

    def test_handle_404_typeerror_2(self):
        """make sure 404 works when a path bit is missing"""
        c = self.create_server([
            "class Default(Controller):",
            "    def GET(self, needed_bit, **kwargs):",
            "       return ''",
            "",
            "    def POST(self, needed_bit, **kwargs):",
            "       return ''",
            "",
            "class Htype(Controller):",
            "    def POST(self, needed_bit, **kwargs):",
            "       return ''",
            "",
            "class Hdec(Controller):",
            "    def POST(self, needed_bit, **kwargs):",
            "       return ''",
            "",
        ])

        res = c.handle("/hdec", "POST")
        self.assertEqual(404, res.code)

        res = c.handle("/htype", "POST")
        self.assertEqual(404, res.code)

        res = c.handle("/")
        self.assertEqual(404, res.code)

        res = c.handle("/", "POST")
        self.assertEqual(404, res.code)

    def test_handle_400_typeerror_3(self):
        """there was an error when there was only one expected argument, turns
        out the call was checking for "arguments" when the message just had
        "argument"

        The error is:
            TypeError: Foo.GET() got an unexpected keyword argument 'che'
        """
        c = self.create_server(contents=[
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
        ])

        res = c.handle("/foo/bar/baz", query='che=1&boo=2')
        self.assertEqual(400, res.code)

    def test_handle_accessdenied(self):
        """raising an AccessDenied error should set code to 401 and the correct
        header"""
        c = self.create_server(contents=[
            "from endpoints import Controller, AccessDenied",
            "class Default(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise AccessDenied(scheme='basic')",
            "class Bar(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise AccessDenied()",
        ])

        res = c.handle("/")
        self.assertEqual(401, res.code)
        self.assertTrue('Basic' in res.headers['WWW-Authenticate'])

        res = c.handle("/bar")
        self.assertEqual(401, res.code)
        self.assertTrue('Auth' in res.headers['WWW-Authenticate'])

    def test_handle_callstop(self):
        c = self.create_server(contents=[
            "from endpoints import Controller, CallStop",
            "class Testcallstop(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise CallStop(205, None)",
            "",
            "class Testcallstop2(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise CallStop(200, 'this is the body')",
            "",
            "class Testcallstop3(Controller):",
            "    def GET(*args, **kwargs):",
            "        raise CallStop(204)",
        ])

        res = c.handle("/testcallstop")
        self.assertEqual(None, res.body)
        self.assertEqual(None, res._body)
        self.assertEqual(205, res.code)

        res = c.handle("/testcallstop2")
        self.assertEqual("this is the body", res.body)
        self.assertEqual(200, res.code)

        res = c.handle("/testcallstop3")
        self.assertEqual(None, res._body)
        self.assertEqual(204, res.code)

    def test_path_errors(self):
        c = self.create_server([
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self, bar): pass",
            "",
        ])

        # this path is technically valid but is missing required arguments
        res = c.handle("/foo", "GET")
        self.assertEqual(404, res.code)

        # there is no POST method for this path
        res = c.handle("/foo/bar", "POST")
        self.assertEqual(404, res.code)

        # there is no GET method that has this path
        res = c.handle("/foo/bar/che", "GET")
        self.assertEqual(404, res.code)

    def test_routing_typeerrors(self):
        c = self.create_server([
            "class Foo(Controller):",
            "    def GET(self, /, bar, *, che): pass",
            "",
        ])

        # Foo.GET() missing 1 required keyword-only argument: 'che'
        res = c.handle("/foo/bar", "GET")
        self.assertEqual(400, res.code)

        # Foo.GET() missing 1 required positional argument: 'bar'
        res = c.handle("/foo", "GET")
        self.assertEqual(404, res.code)

    def test_handle_method_chain(self):
        c = self.create_server(contents=[
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    async def handle(self, *args, **kwargs):",
            "        self.response.handle_called = True",
            "        await super().handle(*args, **kwargs)",
            "",
            "    def GET(self, *args, **kwargs):",
            "        self.response.GET_called = True",
            "",
        ])

        res = c.handle("/foo")
        self.assertTrue(res.handle_called)
        self.assertTrue(res.GET_called)

    def test_multiple_controller_prefixes_1(self):
        self.create_modules({
            "foo": [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(self): pass",
            ],
            "bar": [
                "from endpoints import Controller",
                "class User(Controller):",
                "    def GET(self): pass",
            ],
        })

        c = self.create_server(controller_prefixes=["foo", "bar"])

        t = c.find("/user")
        self.assertTrue("bar", t["reflect_class"].modpath)

        t = c.find("/che")
        self.assertTrue("foo", t["reflect_class"].modpath)

    def test_routing_1(self):
        """there was a bug that caused errors raised after the yield to return
        another iteration of a body instead of raising them"""
        contents = [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self): pass",
            "",
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
            "class Bar(Controller):",
            "    def GET(self): pass",
        ]
        controller_prefix = self.create_module(contents=contents)
        c = self.create_server(controller_prefixes=[controller_prefix])

        info = c.find()
        rc = info["reflect_class"]
        self.assertEqual(controller_prefix, rc.modpath)
        self.assertEqual("Default", rc.name)

        info = c.find("/foo/che/baz")
        rc = info["reflect_class"]
        self.assertEqual(2, len(info['leftover_path_args']))
        self.assertEqual("Foo", rc.name)

    def test_default_match_with_path(self):
        """when the default controller is used, make sure it falls back to
        default class name if the path bit fails to be a controller class name
        """
        c = self.create_server({
            "nmcon": [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(self, *args, **kwargs):",
                "        return args[0]"
            ]
        })

        res = c.handle("/nmcon/8")
        self.assertEqual("8", res.body)

    def test_no_match(self):
        """make sure a controller module that imports a class with the same as
        one of the query args doesen't get picked up as the controller class"""
        c = self.create_server({
            "nomod": [
                "class Nomodbar(object): pass",
            ],
            "": [
                "from endpoints import Controller",
                "from .nomod import Nomodbar",
                "class Default(Controller):",
                "    def GET(self): pass",
            ],
        })

        path = '/nomodbar' # same name as one of the non controller classes
        info = c.find(path)
        rc = info["reflect_class"]
        self.assertEqual('Default', rc.name)
        self.assertEqual(c.controller_prefix, rc.modpath)
        self.assertEqual('nomodbar', info['leftover_path_args'][0])

    def test_import_error(self):
        with self.assertRaises(ImportError):
            c = self.create_server([
                "from does_not_exist import FairyDust",
                "class Default(Controller):",
                "    def GET(self): pass",
            ])

    def test_callback_info(self):
        c = self.create_server()

        request = c.create_request("/foo/bar", "GET")
        request.query_kwargs = {'foo': 'bar', 'che': 'baz'}

        with self.assertRaises(TypeError):
            c.find(request=request)

        c = self.create_server({
            "foo": [
                "from endpoints import Controller",
                "class Bar(Controller):",
                "    def GET(*args, **kwargs): pass"
            ],
        })
        # if it succeeds, then it passed the test :)
        d = c.find(request=request)

