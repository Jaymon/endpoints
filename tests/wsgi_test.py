# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from . import TestCase as BaseTestCase, skipIf, SkipTest
import os
import codecs
import hashlib
import json

import testdata

from endpoints.utils import ByteString
from endpoints.client import HTTPClient
from endpoints.interface.wsgi.client import WSGIServer


# def setUpModule():
#     if requests is None:
#         raise SkipTest("Skipping (u)wsgi server tests because no requests module")


###############################################################################
# Actual tests
###############################################################################
class TestCase(BaseTestCase):
    server = None
    server_class = WSGIServer
    client_class = HTTPClient

    def setUp(self):
        if self.server:
            self.server.stop()

    def tearDown(self):
        if self.server:
            self.server.stop()

    def create_server(self, controller_prefix, contents, config_contents='', **kwargs):
        tdm = testdata.create_module(controller_prefix, contents)

        kwargs["controller_prefix"] = controller_prefix
        kwargs["host"] = self.get_host()

        if config_contents:
            config_path = testdata.create_file("config.py", config_contents)
            kwargs["wsgifile"] = config_path

        server = self.server_class(**kwargs)
        server.cwd = tdm.basedir
        server.stop()
        self.server = server
        self.server.start()
        return server

    def create_client(self, **kwargs):
        kwargs.setdefault("host", self.get_host())
        client = self.client_class(**kwargs)
        return client


class WSGITest(TestCase):
    #client_class = WSGIClient

    def test_request_url(self):
        """make sure request url gets controller_path correctly"""
        controller_prefix = "requesturl.controller"
        server = self.create_server(controller_prefix, [
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
        controller_prefix = "lpdcontroller"
        server = self.create_server(controller_prefix, [
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
        controller_prefix = 'wsgi.post_file'
        server = self.create_server(controller_prefix, [
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

    def test_post_file_with_param(self):
        """make sure specifying a param for the file upload works as expected"""
        filepath = testdata.create_file("post_file_with_param.txt", "post_file_with_param")
        controller_prefix = 'wsgi.post_file_with_param'
        server = self.create_server(controller_prefix, [
            "from endpoints import Controller, decorators",
            "class Default(Controller):",
            "    @decorators.param('file')",
            "    def POST(self, *args, **kwargs):",
            "        return kwargs['file'].filename",
            "",
        ])

        c = self.create_client()
        r = c.post_file('/', {"foo": "bar", "baz": "che"}, {"file": filepath})
        self.assertEqual(200, r.code)
        self.assertTrue("post_file_with_param.txt" in r.body)

    def test_post_basic(self):
        controller_prefix = 'wsgi.post'
        server = self.create_server(controller_prefix, [
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

    def test_post_ioerror(self):
        """turns out this is pretty common, a client will make a request and disappear, 
        but now that we lazy load the body these errors are showing up in our logs where
        before they were silent because they failed, causing the process to be restarted,
        before they ever made it really into our logging system"""

        controller_prefix = 'wsgi.post_ioerror'
        server = self.create_server(
            controller_prefix,
            [
                "from endpoints import Controller",
                "",
                "class Default(Controller):",
                "    def POST(*args, **kwargs):",
                "        pass",
                "",
            ],
            config_contents=[
                "from endpoints.interface.wsgi import Application",
                "from endpoints import Request as EReq",
                "",
                "class Request(EReq):",
                "    @property",
                "    def body_kwargs(self):",
                "        raise IOError('timeout during read(0) on wsgi.input')",
                "",
                "Application.request_class = Request",
                "",
            ],
        )

        c = self.create_client()
        r = c.post(
            '/',
            {"foo": "bar"},
            headers={
                "content-type": "application/json",
            }
        )
        self.assertEqual(408, r.code)

    def test_405_request(self):
        controller_prefix = 'request_405'
        server = self.create_server(controller_prefix, [
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
        ])

        c = self.create_client()
        r = c.get('/foo/bar/baz?che=1&boo=2')
        self.assertEqual(405, r.code)

    def test_response_headers(self):
        controller_prefix = 'resp_headers.resp'
        server = self.create_server(controller_prefix, [
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
        controller_prefix = 'wsgi.post_file'
        server = self.create_server(controller_prefix, [
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
        controller_prefix = 'wsgi_generator'
        server = self.create_server(controller_prefix, [
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


###############################################################################
# Client tests
###############################################################################
class HTTPClientTest(TestCase):
    def test_get_fetch_url(self):
        c = self.create_client()

        uri = "http://foo.com"
        url = c.get_fetch_url(uri)
        self.assertEqual(uri, url)

        uri = "/foo/bar"
        url = c.get_fetch_url(uri)
        self.assertEqual("{}{}".format(c.get_fetch_host(), uri), url)

        url = c.get_fetch_url(["foo", "bar"])
        self.assertEqual("{}{}".format(c.get_fetch_host(), "/foo/bar"), url)

    def test_post_file(self):
        filepath = testdata.create_file("json_post_file.txt", "json post file")
        controller_prefix = 'jsonclient.controller'
        server = self.create_server(controller_prefix, [
            "from endpoints import Controller, decorators",
            "class Default(Controller):",
            "    @decorators.param('file')",
            "    def POST(self, *args, **kwargs):",
            "        return dict(body=kwargs['file'].filename)",
            "",
        ])
        c = self.create_client()
        r = c.post_file('/', {"foo": "bar", "baz": "che"}, {"file": filepath})
        self.assertEqual(200, r.code)
        self.assertEqual("json_post_file.txt", r._body["body"])

    def test_basic_auth(self):
        c = self.create_client()
        c.basic_auth("foo", "bar")
        self.assertRegex(c.headers["authorization"], "Basic\s+[a-zA-Z0-9=]+")


class WSGIServerTest(TestCase):
    def test_start(self):
        controller_prefix = 'wsgiserverstart.controller'
        server = self.create_server(controller_prefix, [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self): pass",
            "",
        ])

    def test_wsgifile(self):
        wsgifile = testdata.create_file("wsgiserverapp.py", [
            "import os",
            "from endpoints.interface.wsgi import Application",
            "os.environ['WSGI_TESTING'] = 'foo bar'",
            "application = Application()",
            "",
        ])
        controller_prefix = 'wsgiservercon.controller'
        server = self.create_server(controller_prefix, [
            "import os",
            "from endpoints import Controller, decorators",
            "class Default(Controller):",
            "    def GET(self):",
            "        return os.environ['WSGI_TESTING']",
            "",
        ], wsgifile=wsgifile)
        c = self.create_client()

        r = c.get("/")
        self.assertEqual(200, r.code)
        self.assertEqual("foo bar", r._body)


