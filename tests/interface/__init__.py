# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import random
import os

import testdata
from unittest import TestSuite

from endpoints.client import WebClient, WebsocketClient
from .. import TestCase as BaseTestCase


class TestCase(BaseTestCase):
    server = None
    server_class = None # this is a client.Server class
    client_class = WebClient

    def setUp(self):
        if self.server:
            self.server.stop()

    def tearDown(self):
        if self.server:
            self.server.stop()

    def create_server(self, contents, config_contents='', **kwargs):
        tdm = testdata.create_module(kwargs.get("controller_prefix", ""), contents)

        kwargs["controller_prefix"] = tdm
        kwargs["host"] = self.get_host()
        kwargs["cwd"] = tdm.basedir

        if config_contents:
            config_path = testdata.create_file("{}.py".format(testdata.get_module_name()), config_contents)
            kwargs["config_path"] = config_path

        server = self.server_class(**kwargs)
        server.stop()
        server.start()
        self.server = server
        return server

    def create_client(self, **kwargs):
        kwargs.setdefault("host", self.server.host)
        client = self.client_class(**kwargs)
        return client


class WebTestCase(TestCase):
    def test_request_url(self):
        """make sure request url gets controller_path correctly"""
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Requrl(Controller):",
            "    def GET(self):",
            "        return self.request.url.controller()",
            "",
        ])

        c = self.create_client()
        r = c.get('/requrl')
        self.assertTrue("/requrl" in r._body)

    def test_list_param_decorator(self):
        server = self.create_server(contents=[
            "from endpoints import Controller, decorators",
            "class Listparamdec(Controller):",
            "    @decorators.param('user_ids', 'user_ids[]', type=int, action='append_list')",
            "    def GET(self, **kwargs):",
            "        return int(''.join(map(str, kwargs['user_ids'])))",
            ""
        ])

        c = self.create_client()
        r = c.get('/listparamdec?user_ids[]=12&user_ids[]=34')
        self.assertEqual("1234", r.body)

    def test_post_file_simple(self):
        filepath = testdata.create_file("filename.txt", "this is a text file to upload")
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, *args, **kwargs):",
            "        return kwargs['file']['filename']",
            "",
        ])

        c = self.create_client()
        r = c.post_file('/', {"foo": "bar", "baz": "che"}, {"file": filepath})
        self.assertEqual(200, r.code)
        self.assertTrue("filename.txt" in r.body)

    def test_post_file_with_param(self):
        """make sure specifying a param for the file upload works as expected"""
        filepath = testdata.create_file("post_file_with_param.txt", "post_file_with_param")
        server = self.create_server(contents=[
            "from endpoints import Controller, decorators",
            "class Default(Controller):",
            "    @decorators.param('file')",
            "    def POST(self, *args, **kwargs):",
            "        return kwargs['file']['filename']",
            "",
        ])

        c = self.create_client()
        r = c.post_file('/', {"foo": "bar", "baz": "che"}, {"file": filepath})
        self.assertEqual(200, r.code)
        self.assertTrue("post_file_with_param.txt" in r.body)

    def test_post_basic(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "from endpoints.decorators import version",
            "class Default(Controller):",
            "    def GET(*args, **kwargs): pass",
            "    @version('', 'v1')",
            "    def POST_v1(*args, **kwargs): pass",
            "    @version('v2')",
            "    def POST_v2(*args, **kwargs): return kwargs['foo']",
            "",
        ])

        c = self.create_client()
        r = c.post(
            '/',
            {"foo": "bar"},
            headers={
                "content-type": "application/json",
                "Accept": "application/json;version=v2"
            }
        )
        self.assertEqual(200, r.code)
        self.assertEqual('"bar"', r.body)

        r = c.post('/', {})
        self.assertEqual(204, r.code)

        r = c.post('/', None, headers={"content-type": "application/json"})
        self.assertEqual(204, r.code)

        r = c.post('/', None)
        self.assertEqual(204, r.code)

        r = c.post('/', {}, headers={"content-type": "application/json"})
        self.assertEqual(204, r.code)

        r = c.post('/', {"foo": "bar"}, headers={"Accept": "application/json;version=v2"})
        self.assertEqual(200, r.code)
        self.assertEqual('"bar"', r.body)

    def test_405_request(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
        ])

        c = self.create_client()
        r = c.get('/foo/bar/baz?che=1&boo=2')
        self.assertEqual(405, r.code)

    def test_response_headers(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self):",
            "        self.response.set_header('FOO_BAR', 'check')",
            "",
        ])

        c = self.create_client()
        r = c.get('/')
        self.assertEqual(204, r.code)
        self.assertTrue("foo-bar" in r.headers)

    def test_file_stream(self):
        content = "this is a text file to stream"
        filepath = testdata.create_file("filename.txt", content)
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self, *args, **kwargs):",
            "        f = open('{}')".format(filepath),
            "        self.response.set_header('content-type', 'text/plain')",
            "        return f",
            "",
        ])

        c = self.create_client()
        r = c.get('/')
        self.assertEqual(200, r.code)
        self.assertEqual(content, r.body)
        #self.assertTrue(r.body)

    def test_generators(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self):",
            "        for x in range(100):",
            "            yield x",
        ])

        c = self.create_client()
        r = c.get('/')
        content = list(range(100))
        self.assertEqual(200, r.code)
        self.assertEqual(content, r._body)

    def test_request_body_kwargs_bad_content_type(self):
        self.skip_test("moved from http.RequestTest, make this work at some point")
        """make sure a form upload content type with json body fails correctly"""
        r = Request()
        r.body = "foo=bar&che=baz&foo=che"
        r.headers = {'content-type': 'application/json'}
        with self.assertRaises(ValueError):
            br = r.body_kwargs

        r.body = '{"foo": ["bar", "che"], "che": "baz"}'
        r.headers = {'content-type': "application/x-www-form-urlencoded"}

        with self.assertRaises(ValueError):
            br = r.body_kwargs

    def test_response_body(self):
        self.skip_test("moved from http.ResponseTest, make this work at some point")
        b = {'foo': 'bar'}

        r = Response()
        r.headers['Content-Type'] = 'plain/text'
        self.assertEqual(None, r.body)
        r.body = b
        self.assertEqual(String(b), r.body)

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = b
        self.assertEqual(json.dumps(b), r.body)

        r = Response()
        r.headers['Content-Type'] = 'plain/text'
        self.assertEqual('', r.body)
        self.assertEqual('', r.body) # Make sure it doesn't change
        r.body = b
        self.assertEqual(String(b), r.body)

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = {}
        self.assertEqual(r.body, "{}")

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = ValueError("this is the message")
        r.code = 500
        #self.assertEqual(r.body, '{"errno": 500, "errmsg": "this is the message"}')
        self.assertEqual(r.body, '{"errmsg": "this is the message"}')
        r.headers['Content-Type'] = ''
        self.assertEqual("this is the message", r.body)

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = None
        self.assertEqual('', r.body) # was getting "null" when content-type was set to json

        # TODO: this really needs to be better tested with unicode data

    def test_response_body_json_error(self):
        """I was originally going to have the body method smother the error, but
        after thinking about it a little more, I think it is better to bubble up
        the error and rely on the user to handle it in their code"""
        self.skip_test("moved from http.ResponseTest, make this work at some point")
        class Foo(object): pass
        b = {'foo': Foo()}

        r = Response()
        r.headers['Content-Type'] = 'application/json'
        r.body = b
        with self.assertRaises(TypeError):
            rb = r.body


class WebsocketTestCase(TestCase):
    client_class = WebsocketClient
    server_class = None

    def test_get_fetch_host(self):
        client_cls = self.client_class
        c = client_cls("http://localhost")
        self.assertTrue(c.get_fetch_host().startswith("ws"))

        c = client_cls("https://localhost")
        self.assertTrue(c.get_fetch_host().startswith("wss"))

        c = client_cls("HTTPS://localhost")
        self.assertTrue(c.get_fetch_host().startswith("wss"))

        c = client_cls("HTTP://localhost")
        self.assertTrue(c.get_fetch_host().startswith("ws"))

    def test_connect_success(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs):",
            "        pass",
            "    def DISCONNECT(self, *args, **kwargs):",
            "        pass",
        ])

        c = self.create_client()
        r = c.connect(trace=True)
        self.assertEqual(204, r.code)
        self.assertTrue(c.connected)

        # when looking at logs, this test looks like there is a problem because
        # right after connection an IOError is thrown, that's because the close
        # will cause uWSGI to raise an IOError, giving the websocket a chance
        # to clean up the connection

        c.close()
        self.assertFalse(c.connected)

    def test_connect_failure(self):
        server = self.create_server(contents=[
            "from endpoints import Controller, CallError",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs):",
            "        raise CallError(401, 'this is the message')",
            "    def DISCONNECT(self, *args, **kwargs):",
            "        pass",
        ])

        c = self.create_client()
        with self.assertRaises(IOError):
            c.connect()

    def test_request_basic(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs):",
            "        #pout.v(args, kwargs, self.request)",
            "        #pout.b('CONNECT')",
            "        pass",
            "    def DISCONNECT(self, *args, **kwargs):",
            "        #pout.b('DISCONNECT')",
            "        pass",
            "",
            "    def SOCKET(self, *args, **kwargs):",
            "        #pout.v(args, kwargs)",
            "        #pout.b('SOCKET')",
            "        return {",
            "            'name': 'SOCKET',",
            "            'args': args,",
            "            'kwargs': kwargs,",
            "        }",
            "    def POST(self, *args, **kwargs):",
            "        return {",
            "            'name': 'POST',",
            "            'args': args,",
            "            'kwargs': kwargs,",
            "        }",
            "    def GET(self, *args, **kwargs):",
            "        return {",
            "            'name': 'GET',",
            "            'args': args,",
            "            'kwargs': kwargs,",
            "        }",
        ])

        c = self.create_client()
        r = c.post("/foo/bar", {"val1": 1, "val2": 2})
        self.assertEqual("POST", r._body["name"])

        r = c.send("/foo/bar", {"val1": 1, "val2": 2})
        self.assertEqual("SOCKET", r._body["name"])
        self.assertEqual({"val1": 1, "val2": 2}, r._body["kwargs"])

        r = c.get("/foo/bar", {"val1": 1, "val2": 2})
        self.assertEqual("GET", r._body["name"])

    def test_request_modification(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def CONNECT(self):",
            "        self.request.foo = 1",
            "",
            "    def DISCONNECT(self, *args, **kwargs):",
            "        pass",
            "",
            "    def POST(self, **kwargs):",
            "        self.request.parent.foo = kwargs['foo']",
            "        return self.request.parent.foo",
            "",
            "    def GET(self):",
            "        return self.request.foo",
        ])

        c = self.create_client()
        r = c.post("/", {"foo": 2})
        self.assertEqual(2, r._body)

        r = c.get("/")
        self.assertEqual(2, r._body)

        r = c.post("/", {"foo": 4})
        self.assertEqual(4, r._body)

        r = c.get("/")
        self.assertEqual(4, r._body)

    def test_path_autoconnect(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "",
            "class Foo(Controller):",
            "    def CONNECT(self): pass",
            "    def DISCONNECT(self): pass",
            "",
            "    def POST(self, **kwargs):",
            "        return 1",
            "",
        ])

        c = self.create_client()
        c.basic_auth("foo", "bar")
        r = c.post("/foo", {"bar": 2})
        self.assertEqual(1, r._body)

    def test_error_500(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs): pass",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "    def GET(self):",
            "        raise ValueError('bah')",
            "    def POST(self, **kwargs):",
            "        return 'foo'",
        ])

        c = self.create_client()
        r = c.get("/")
        self.assertEqual(500, r.code)
        self.assertEqual("bah", r._body["errmsg"])

        r = c.post("/")
        self.assertEqual(200, r.code)

    def test_call_error(self):
        server = self.create_server(contents=[
            "from endpoints import Controller, CallError",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs): pass",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "",
            "    def GET(self):",
            "        raise CallError(401)",
        ])

        c = self.create_client()
        r = c.get("/")
        self.assertEqual(401, r.code)

    def test_connect_error(self):
        server = self.create_server(contents=[
            "from endpoints import Controller, CallError",
            "from endpoints.decorators.auth import client_auth as BaseAuth",
            "class client_auth(BaseAuth):",
            "    def target(self, *args, **kwargs): return False",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs):",
            "        auth = client_auth()",
            "        auth.handle_target(self.request, args, kwargs)",
            "",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "",
        ])

        c = self.create_client()
        with self.assertRaises(IOError):
            c.connect()
            #r = c.get("/")

    def test_get_query(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs): pass",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "",
            "    def GET(self, **kwargs):",
            "        return kwargs['foo']",
        ])

        c = self.create_client()
        r = c.get("/", {"foo": 2})
        self.assertEqual(200, r.code)
        self.assertEqual(2, r._body)

    def test_count(self):
        self.skip_test("count is no longer being sent down")
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs): pass",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "",
            "    def GET(self, **kwargs): pass",
            "    def POST(self, **kwargs): pass",
        ])

        c = self.create_client()
        for x in range(2, 7):
            r = getattr(c, random.choice(["get", "post"]))("/")
            self.assertEqual(204, r.code)
            self.assertEqual(x, r.count)

        c.close()

        for x in range(2, 7):
            r = getattr(c, random.choice(["get", "post"]))("/")
            self.assertEqual(204, r.code)
            self.assertEqual(x, r.count)


class WebServerTestCase(TestCase):
    """Tests the client.Webserver for the interface"""
    def test_start(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self): pass",
            "",
        ])

    def test_file(self):
        server = self.create_server(
            contents=[
                "import os",
                "from endpoints import Controller, decorators",
                "class Default(Controller):",
                "    def GET(self):",
                "        return os.environ['WSGI_TESTING']",
                "",
            ],
            config_contents=[
                "import os",
                "os.environ['WSGI_TESTING'] = 'foo bar'",
                "",
            ]
        )
        c = self.create_client()

        r = c.get("/")
        self.assertEqual(200, r.code)
        self.assertEqual("foo bar", r._body)


def load_tests(*args, **kwargs):
    return TestSuite()

