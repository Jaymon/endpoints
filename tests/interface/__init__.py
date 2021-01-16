# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import random
import os
import json

import testdata
from unittest import TestSuite

from endpoints.compat import *
from endpoints.client import WebClient, WebsocketClient
from .. import TestCase as BaseTestCase


class TestCase(BaseTestCase):
    server = None
    server_class = None # this should be a client.Server class
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
    def test_body_plain_with_content_type(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, **kwargs):",
            "        self.response.headers['content-type'] = 'text/plain'",
            "        return self.request.body.read()",
        ])

        body = "plain text body"
        c = self.create_client(headers={"content-type": "text/plain"})
        r = c.post("/", body)
        self.assertEqual(200, r.code)
        self.assertEqual(body, r.body)
        self.assertEqual(String(body), String(r._body))

    def test_body_plain_without_content_type(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, **kwargs):",
            "        self.response.headers['content-type'] = 'text/plain'",
            "        return self.request.body.read()",
        ])

        body = "plain text body"
        #c = self.create_client(headers={"content-type": "text/plain"})
        c = self.create_client()
        r = c.post("/", body)
        self.assertEqual(200, r.code)
        self.assertEqual(body, r.body)
        self.assertEqual(String(body), String(r._body))

    def test_body_json_dict(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, *args, **kwargs):",
            "        return {'args': args, 'kwargs': kwargs}",
        ])

        c = self.create_client(json=True)
        body = {"foo": 1, "bar": [2, 3], "che": "four"}
        r = c.post("/", body)
        self.assertEqual(body, r._body["kwargs"])
        self.assertEqual(0, len(r._body["args"]))

    def test_body_json_list(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, *args, **kwargs):",
            "        return {'args': args, 'kwargs': kwargs}",
        ])

        c = self.create_client(json=True)
        body = ["foo", "bar"]
        r = c.post("/", body)
        self.assertEqual(body, r._body["args"])
        self.assertEqual(0, len(r._body["kwargs"]))

        body = [{"foo": 1}, {"foo": 2}]
        r = c.post("/", body)
        self.assertEqual(1, r._body["args"][0]["foo"])
        self.assertEqual(2, len(r._body["args"]))

    def test_body_file_1(self):
        filepath = testdata.create_file("filename.txt", "this is a text file to upload")
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, *args, **kwargs):",
            "        return kwargs['file'].filename",
            "",
        ])

        c = self.create_client()
        r = c.post_file('/', {"foo": "bar", "baz": "che"}, {"file": filepath})
        self.assertEqual(200, r.code)
        self.assertTrue("filename.txt" in r.body)

    def test_body_file_2(self):
        """make sure specifying a @param for the file upload works as expected"""
        filepath = testdata.create_file("post_file_with_param.txt", "post_file_with_param")
        server = self.create_server(contents=[
            "from endpoints import Controller, decorators",
            "class Default(Controller):",
            "    @decorators.param('file')",
            "    def POST(self, *args, **kwargs):",
            "        return kwargs['file'].filename",
            #"        return kwargs['file']['filename']",
            "",
        ])

        c = self.create_client()
        r = c.post_file('/', {"foo": "bar", "baz": "che"}, {"file": filepath})
        self.assertEqual(200, r.code)
        self.assertTrue("post_file_with_param.txt" in r.body)

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

    def test_404_request(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self, **kwargs): pass",
            "",
        ])

        c = self.create_client()
        r = c.get('/foo/bar/baz?che=1&boo=2')
        self.assertEqual(404, r.code)

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

    def test_response_body_1(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, **kwargs):",
            "        content_type = '{};charset={}'.format(kwargs['content_type'], self.encoding)",
            "        self.response.set_header('content-type', content_type)",
            "        return kwargs['body']",
        ])

        body = {'foo': testdata.get_words()}
        c = self.create_client(json=True)

        r = c.post('/', {'content_type': 'plain/text', 'body': body})
        self.assertEqual(ByteString(body), r._body)
        self.assertEqual(String(body), r.body)

        r = c.post('/', {'content_type': 'application/json', 'body': body})
        self.assertEqual(json.dumps(body), r.body)

        r = c.post('/', {'content_type': 'application/json', 'body': {}})
        self.assertEqual("{}", r.body)

    def test_response_body_json_error(self):
        """I was originally going to have the body method smother the error, but
        after thinking about it a little more, I think it is better to bubble up
        the error and rely on the user to handle it in their code"""

        # 1-13-2021 update, turns out response body is buried, an error is
        # raised but the server returns a 200 because the headers are already
        # sent before the body is encoded, so all the headers are sent but body
        # is empty
        self.skip_test("")

        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self):",
            "        class Foo(object): pass",
            "        return {'foo': Foo()}",
        ])

        c = self.create_client()
        r = c.get('/')
        pout.v(r.code, r.body)
        return



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

    def test_bad_path(self):
        """https://github.com/Jaymon/endpoints/issues/103"""
        server = self.create_server(contents=[
            "import os",
            "from endpoints import Controller, decorators",
            "class Default(Controller):",
            "    def CONNECT(self, **kwargs):",
            "        pass",
            "    def DISCONNECT(self, **kwargs):",
            "        pass",
            "    def GET(self, foo, bar):",
            "        return 'get'",
            "",
        ])
        c = self.create_client()
        c.connect()

        r = c.get("http://example.com/foo/bar")
        self.assertEqual(404, r.code)

        r = c.get("/foo/bar")
        self.assertEqual(200, r.code)

    def test_close_connection(self):
        server = self.create_server(contents=[
            "from endpoints import Controller, CloseConnection",
            "class Default(Controller):",
            "    def CONNECT(self, **kwargs):",
            "        pass",
            "    def DISCONNECT(self, **kwargs):",
            "        pass",
            "    def GET(self, **kwargs):",
            "        raise CloseConnection()",
        ])

        c = self.create_client()
        c.connect()
        with self.assertRaises(RuntimeError):
            c.get("/", timeout=0.1, attempts=1)

    def test_rapid_requests(self):
        """We were dropping requests when making a whole bunch of websocket
        requests all at once, a version of this test was able to duplicate it about
        every 5 or 6 run (dang async programming) which allowed me to figure out
        that uwsgi batches ws requests and if you don't read them all then it will
        silently discard the unread ones when another request is received"""
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def CONNECT(self, **kwargs):",
            "        pass",
            "    def DISCONNECT(self, **kwargs):",
            "        pass",
            "    def GET(self, **kwargs):",
            "        return kwargs['pid']",
        ])

        c = self.create_client()
        c.connect()

        # we are basically going to do Y sets of X requests, if any of them
        # stall then we failed this test, otherwise we succeeded
        for y in range(5):
            ts = []
            rs = []
            for x in range(5):
                def target(x):
                    r = c.get("/", {"pid": x})
                    rs.append(int(r.body))


                t = testdata.Thread(target=target, args=[x])
                t.start()
                ts.append(t)

            for t in ts:
                t.join()

            self.assertEqual(set([0, 1, 2, 3, 4]), set(rs))

    def test_path_mixup(self):
        """Jarid was hitting this problem, we were only able to get it to happen
        consistently with his environment, the problem stemmed from one request
        being remembered on the next request, this makes sure that is fixed"""
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "from endpoints.decorators import version",
            "class Default(Controller):",
            "    def CONNECT(self, **kwargs):",
            "        pass",
            "    def DISCONNECT(self, **kwargs):",
            "        pass",
            "    def GET(*args, **kwargs):"
            "        return 'Default.GET'",
            "",
            "class Foo(Controller):",
            "    def POST(*args, **kwargs):",
            "        return 'Foo.POST'",
        ])

        c = self.create_client()
        c.connect()

        r = c.post("/foo")
        self.assertEqual(200, r.code)
        self.assertTrue("Foo.POST" in r.body)

    def test_versioning(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "from endpoints.decorators import version",
            "class Default(Controller):",
            "    def CONNECT(self, **kwargs):",
            "        pass",
            "    def DISCONNECT(self, **kwargs):",
            "        pass",
            "    @version('', 'v1')",
            "    def GET_v1(*args, **kwargs): return 'v1'",
            "    @version('v2')",
            "    def GET_v2(*args, **kwargs): return 'v2'",
        ])

        c = self.create_client()
        c.connect()

        r = c.get(
            '/',
            headers={
                "Accept": "application/json;version=v1"
            }
        )
        self.assertEqual(200, r.code)
        self.assertTrue("v1" in r.body)

        r = c.get(
            '/',
            headers={
                "Accept": "application/json;version=v2"
            }
        )
        self.assertEqual(200, r.code)
        self.assertTrue("v2" in r.body)

        r = c.get('/')
        self.assertEqual(200, r.code)
        self.assertTrue("v1" in r.body)


    def test_connect_on_fetch(self):
        server = self.create_server(contents=[
            "from endpoints import Controller, CallError",
            "class Confetch(Controller):",
            "    def CONNECT(self, **kwargs):",
            "        if int(kwargs['foo']) != 1:",
            "            raise CallError(400)",
            "    def GET(self, **kwargs):",
            "        pass",
        ])

        c = self.create_client()
        r = c.get("/confetch", {"foo": 1, "bar": 2})
        self.assertEqual(204, r.code)

        c = self.create_client()
        with self.assertRaises(RuntimeError):
            r = c.get("/confetch", {"foo": 2})

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

