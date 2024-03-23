# -*- coding: utf-8 -*-
import json

import testdata

from endpoints.compat import *
from endpoints.client import HTTPClient, WebSocketClient
from endpoints.interface.base import BaseApplication
from .. import TestCase as BaseTestCase


class TestCase(BaseTestCase):
    client_class = HTTPClient

    def setUp(self):
        if self.server:
            self.server.stop()

        super().setUp()

    def tearDown(self):
        if self.server:
            self.server.stop()

    def create_client(self, **kwargs):
        kwargs.setdefault("json", True)
        kwargs.setdefault("host", self.server.host)
        client = self.client_class(**kwargs)
        return client


class _HTTPTestCase(TestCase):
    """Base class for the actual interfaces, this contains common tests for any
    interface handling HTTP requests
    """
    def test_get_request_url(self):
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
        self.assertTrue("/requrl" in r.body, r.body)
        self.assertRegex(r.body, r"https?://[^/]")

    def test_get_list_param_decorator(self):
        server = self.create_server(contents=[
            "from endpoints import Controller, decorators",
            "class Listparamdec(Controller):",
            "    @decorators.param(",
            "        'user_ids',",
            "        'user_ids[]',",
            "        type=int,",
            "        action='append_list'",
            "    )",
            "    def GET(self, **kwargs):",
            "        return int(''.join(map(str, kwargs['user_ids'])))",
            ""
        ])

        c = self.create_client()
        r = c.get('/listparamdec?user_ids[]=12&user_ids[]=34')
        self.assertEqual("1234", r.body)

    def test_get_404_request(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self, **kwargs): pass",
            "",
        ])

        c = self.create_client()
        r = c.get('/foo/bar/baz?che=1&boo=2')
        self.assertEqual(404, r.code)

    def test_get_response_headers(self):
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

    def test_get_file_stream(self):
        content = "this is a text file to stream"
        filepath = testdata.create_file(content)
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

    def test_get_generators(self):
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

    def test_post_body_urlencoded(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, **kwargs):",
            "        return kwargs",
        ])

        body = {"foo": "1", "bar": ["2", "3"], "che": "four"}
        c = self.create_client()
        r = c.post("/", body)
        self.assertEqual(200, r.code)
        self.assertEqual(body, r._body)

    def test_post_body_json_dict(self):
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

    def test_post_body_json_list(self):
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

    def test_post_body_file_1(self):
        filepath = testdata.create_file(
            "this is a text file to upload",
            ext="txt"
        )
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, *args, **kwargs):",
            "        return {",
            "            'filename': kwargs['file'].filename,",
            "            'foo': kwargs['foo'],",
            "            'baz': kwargs['baz'],",
            "        }",
            "",
        ])

        body = {"foo": "value-foo", "baz": "value-baz"}
        c = self.create_client()
        r = c.post_file(
            '/',
            body,
            {"file": filepath}
        )
        self.assertEqual(200, r.code)
        self.assertTrue(filepath.name in r.body)
        for k, v in body.items():
            self.assertTrue(v in r.body)

    def test_post_body_file_2(self):
        """make sure specifying a @param for the file upload works as expected"""
        filepath = testdata.create_file("post_file_with_param")
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
        r = c.post_file(
            '/',
            {"foo": "value-foo", "baz": "value-baz"},
            {"file": filepath}
        )
        self.assertEqual(200, r.code)
        self.assertTrue(filepath.name in r.body)

    def test_post_body_plain_with_content_type(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, *args, **kwargs):",
            "        self.response.headers['content-type'] = 'text/plain'",
            "        return self.request.body",
        ])

        body = "plain text body"
        c = self.create_client(headers={"content-type": "text/plain"})
        r = c.post("/", body)
        self.assertEqual(200, r.code)
        self.assertEqual(body, r.body)
        self.assertEqual(String(body), String(r._body))

    def test_post_body_plain_without_content_type(self):
        server = self.create_server(contents=[
            "class Default(Controller):",
            "    def POST(self, *args, **kwargs):",
            "        self.response.headers['content-type'] = 'text/plain'",
            "        return self.request.body",
        ])

        body = "plain text body"
        c = self.create_client(json=False)
        r = c.post("/", body)
        self.assertEqual(200, r.code)
        self.assertEqual(body, r.body)
        self.assertEqual(String(body), String(r._body))

    def test_response_body_1(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, **kwargs):",
            "        content_type = '{};charset={}'.format(",
            "            kwargs['content_type'],",
            "            self.encoding",
            "        )",
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
        """
        https://github.com/Jaymon/endpoints/issues/112
        """
        server = self.create_server(contents=[
            "class Default(Controller):",
            "    def GET(self, **kwargs):",
            "        class Foo(object):",
            "            pass",
            "        return {",
            "            'foo': Foo()",
            "        }",
        ])

        c = self.create_client()

        r = c.get('/')
        self.assertEqual(500, r.code)

    def test_versioning(self):
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
        r = c.post('/', None, headers={"content-type": "application/json"})
        self.assertEqual(204, r.code)

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

        r = c.post(
            '/',
            {"foo": "bar"},
            headers={"Accept": "application/json;version=v2"}
        )
        self.assertEqual(200, r.code)
        self.assertEqual('"bar"', r.body)

    def test_io_streaming_1(self):
        """Make sure a binary file doesn't get into an infinite loop

        https://github.com/Jaymon/endpoints/issues/122
        """
        fp = self.create_file("hello world")
        s = self.create_server([
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self):",
            "        return open('{}', 'rb')".format(fp),
        ])
        c = self.create_client()

        r = c.get("/foo")
        self.assertEqual("hello world", r.body)

    def test_io_streaming_2(self):
        """Make sure a binary file opened through path.Filepath doesn't get
        into an infinite loop

        https://github.com/Jaymon/endpoints/issues/122
        """
        fp = self.create_file("hello world")
        s = self.create_server([
            "from endpoints import Controller",
            "from datatypes import Filepath",
            "class Foo(Controller):",
            "    def GET(self):",
            "        return Filepath('{}').open()".format(fp),
        ])
        c = self.create_client()

        r = c.get("/foo")
        self.assertEqual("hello world", r.body)

    def test_io_streaming_3(self):
        """Make sure a non-binary file doesn't get into an infinite loop

        https://github.com/Jaymon/endpoints/issues/122
        """
        fp = self.create_file("hello world")
        s = self.create_server([
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self):",
            "        return open('{}', 'r')".format(fp),
        ])
        c = self.create_client()

        r = c.get("/foo")
        self.assertEqual("hello world", r.body)


class _WebSocketTestCase(TestCase):
    """Base class for the actual interfaces, this contains common tests for any
    interface handling WebSocket requests
    """
    client_class = WebSocketClient
    server_class = None

    def test_connect_success(self):
        server = self.create_server([
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
        c.close()
        self.assertFalse(c.connected)

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
            c.get("/", timeout=10, attempts=1)

    def test_no_support(self):
        server = self.create_server(contents=[
            "from endpoints import Controller, CallError",
            "class Confetch(Controller):",
            "    def GET(self, **kwargs):",
            "        pass",
        ])

        c = self.create_client()
        with self.assertRaises(IOError):
            c.connect()

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
        r = c.post("/foo", {"bar": 2})
        self.assertEqual(1, r._body)

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

    def test_request_basic(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs): pass",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "",
            "    def SOCKET(self, *args, **kwargs):",
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

    def test_multiple_connections(self):
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def CONNECT(self, **kwargs): pass",
            "    def DISCONNECT(self, **kwargs): pass",
            "    def GET(self, **kwargs):",
            "        return self.request.uuid",
        ])

        count = 10
        cs = []
        for x in range(count):
            c = self.create_client()
            c.connect()
            cs.append(c)

        for x in range(count):
            for c in cs:
                r = c.get("/")
                self.assertEqual(c.client_id, r.body)

    def test_rapid_requests(self):
        """We were dropping requests when making a whole bunch of websocket
        requests all at once, a version of this test was able to duplicate it about
        every 5 or 6 run (dang async programming) which allowed me to figure out
        that uwsgi batches ws requests and if you don't read them all then it will
        silently discard the unread ones when another request is received"""
        server = self.create_server(contents=[
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def CONNECT(self, **kwargs): pass",
            "    def DISCONNECT(self, **kwargs): pass",
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
            "    def CONNECT(self, **kwargs): pass",
            "    def DISCONNECT(self, **kwargs): pass",
            "    @version('', 'v1')",
            "    def GET_v1(*args, **kwargs): return 'v1'",
            "    @version('v2')",
            "    def GET_v2(*args, **kwargs): return 'v2'",
        ])

        c = self.create_client()
        c.connect()

        r = c.get('/')
        self.assertEqual(200, r.code)
        self.assertTrue("v1" in r.body)

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

