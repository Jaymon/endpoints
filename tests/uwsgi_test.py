# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import codecs
import hashlib

import testdata

from endpoints.interface.uwsgi.client import UWSGIServer, WebsocketClient

from .wsgi_test import TestCase, WSGIServerTest, WSGIServer, WSGITest, WSGIClient, ClientTestCase


class UWSGIClient(WSGIClient):
    server_class = UWSGIServer


class UWSGITest(WSGITest):

    client_class = UWSGIClient

    def create_client(self, *args, **kwargs):
        kwargs.setdefault("config_module_body", [])
        config_module_body = [
            "from endpoints.interface.uwsgi import Application",
        ]
        config_module_body.extend(kwargs.get("config_module_body", []))
        kwargs["config_module_body"] = config_module_body
        return super(UWSGITest, self).create_client(*args, **kwargs)

    def test_chunked(self):
        filepath = testdata.create_file("filename.txt", testdata.get_words(500))
        controller_prefix = 'wsgi.post_chunked'

        c = self.create_client(controller_prefix, [
            "import hashlib",
            "from endpoints import Controller",
            "class Bodykwargs(Controller):",
            "    def POST(self, **kwargs):",
            "        return hashlib.md5(kwargs['file'].file.read()).hexdigest()",
            "",
            "class Bodyraw(Controller):",
            "    def POST(self, **kwargs):",
            "        return len(self.request.body)",
            "",
        ])

        size = c.post_chunked('/bodyraw', {"foo": "bar", "baz": "che"}, filepath=filepath)
        self.assertGreater(int(size), 0)

        with codecs.open(filepath, "rb", encoding="UTF-8") as fp:
            h1 = hashlib.md5(fp.read().encode("UTF-8")).hexdigest()
            h2 = c.post_chunked('/bodykwargs', {"foo": "bar", "baz": "che"}, filepath=filepath)
            self.assertEqual(h1, h2.strip('"'))


class WebsocketTestClient(UWSGIClient):
    client_class = WebsocketClient


class WebsocketTest(TestCase):

    client_class = WebsocketTestClient

    def test_get_fetch_host(self):
        client_cls = self.client_class.client_class
        c = client_cls("http://localhost")
        self.assertTrue(c.get_fetch_host().startswith("ws"))

        c = client_cls("https://localhost")
        self.assertTrue(c.get_fetch_host().startswith("wss"))

        c = client_cls("HTTPS://localhost")
        self.assertTrue(c.get_fetch_host().startswith("wss"))

        c = client_cls("HTTP://localhost")
        self.assertTrue(c.get_fetch_host().startswith("ws"))

    def create_client(self, *args, **kwargs):
        kwargs.setdefault("config_module_body", [])
        kwargs["config_module_body"].extend([
            "from endpoints.interface.uwsgi.gevent import WebsocketApplication as Application",
            "import gevent",
            "import gevent.monkey",
            "if not gevent.monkey.saved:",
            "    gevent.monkey.patch_all()",
        ])
        return super(WebsocketTest, self).create_client(*args, **kwargs)

    def test_connect_success(self):
        c = self.create_client('ws.connectsuccess', [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs):",
            "        pass",
            "    def DISCONNECT(self, *args, **kwargs):",
            "        pass",
        ])

        c.connect(trace=True)
        self.assertTrue(c.connected)

        # when looking at logs, this test looks like there is a problem because
        # right after connection an IOError is thrown, that's because the close
        # will cause uWSGI to raise an IOError, giving the websocket a chance
        # to clean up the connection

        c.close()
        self.assertFalse(c.connected)

    def test_connect_failure(self):
        c = self.create_client('ws.connectfail', [
            "from endpoints import Controller, CallError",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs):",
            "        raise CallError(401, 'this is the message')",
            "    def DISCONNECT(self, *args, **kwargs):",
            "        pass",
        ])

        c.connect()
        self.assertTrue(c.connected)
        r = c.recv()
        self.assertEqual(401, r.code)

    def test_request(self):
        c = self.create_client('ws.request', [
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

        r = c.post("/foo/bar", {"val1": 1, "val2": 2})
        self.assertEqual("POST", r._body["name"])

        r = c.send("/foo/bar", {"val1": 1, "val2": 2})
        self.assertEqual("SOCKET", r._body["name"])
        self.assertEqual({"val1": 1, "val2": 2}, r._body["kwargs"])

        r = c.get("/foo/bar", {"val1": 1, "val2": 2})
        self.assertEqual("GET", r._body["name"])

    def test_request_modification(self):
        c = self.create_client('ws.request_mod', [
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

        r = c.post("/", {"foo": 2})
        self.assertEqual(2, r._body)

        r = c.get("/")
        self.assertEqual(2, r._body)

        r = c.post("/", {"foo": 4})
        self.assertEqual(4, r._body)

        r = c.get("/")
        self.assertEqual(4, r._body)

    def test_path_autoconnect(self):
        c = self.create_client('ws.pathac', [
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

        c.basic_auth("foo", "bar")
        r = c.post("/foo", {"bar": 2})
        self.assertEqual(1, r._body)

    def test_error_500(self):
        c = self.create_client('ws.err500', [
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs): pass",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "",
            "    def GET(self):",
            "        raise ValueError('bah')",
        ])

        r = c.get("/")
        self.assertEqual(500, r.code)
        self.assertEqual("bah", r._body["errmsg"])

    def test_call_error(self):
        c = self.create_client('ws.callerr', [
            "from endpoints import Controller, CallError",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs): pass",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "",
            "    def GET(self):",
            "        raise CallError(401)",
        ])

        r = c.get("/")
        self.assertEqual(401, r.code)

    def test_connect_error(self):
        c = self.create_client('ws.connerr', [
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
            "    @client_auth",
            "    def GET(self): pass",
        ])

        r = c.get("/")
        self.assertEqual(401, r.code)

    def test_get_query(self):
        c = self.create_client('ws.getquery', [
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def CONNECT(self, *args, **kwargs): pass",
            "    def DISCONNECT(self, *args, **kwargs): pass",
            "",
            "    def GET(self, **kwargs):",
            "        return kwargs['foo']",
        ])

        r = c.get("/", {"foo": 2})
        self.assertEqual(200, r.code)
        self.assertEqual(2, r._body)


#     def test_request_override(self):
#         c = self.create_client(
#             'ws.request_override',
#             [
#                 "from endpoints import Controller",
#                 "",
#                 "class Foo(Controller):",
#                 "    def CONNECT(self, *args, **kwargs): pass",
#                 "    def DISCONNECT(self, *args, **kwargs): pass",
#                 "",
#                 "    def GET(self, *args):",
#                 "        return self.request.foo",
#                 "",
#             ],
#             config_module_body=[
#                 "from endpoints.http import Request as BaseRequest",
#                 "from endpoints.interface.uwsgi.gevent import WebsocketApplication",
#                 "",
#                 "class Request(BaseRequest):",
#                 "    foo = 100",
#                 "    def __setattr__(self, key, val):",
#                 "        self.__dict__[key] = val",
#                 "",
#                 "WebsocketApplication.request_class = Request",
#             ],
#         )
# 
#         r = c.get("/foo/bar")
#         self.assertEqual(10000, r._body)


class UWSGIServerTest(WSGIServerTest):
    server_class = UWSGIServer

