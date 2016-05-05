from . import TestCase, skipIf, SkipTest
import os
import codecs
import hashlib
import json

import requests
import testdata

from endpoints.client.http import HTTPClient
from endpoints.client.wsgi import WSGIServer, UWSGIServer


###############################################################################
# UWSGI support
###############################################################################
class UWSGIClient(object):

    client_class = HTTPClient
    server_class = UWSGIServer
    server_script_name = "endpoints_testserver_script.py"

    def __init__(self, controller_prefix, module_body, config_module_body='', host=''):
        self.cwd = testdata.create_dir()
        self.client = self.client_class(host)

        # create the controller module
        self.module_path = testdata.create_module(
            controller_prefix,
            module_body,
            self.cwd
        )

        # now create the server script
        self.script_path = testdata.create_file(
            self.server_script_name,
            os.linesep.join([
                "import os",
                "import sys",
                "import logging",
                "logging.basicConfig()",
                #"sys.path.append('{}')".format(os.path.dirname(os.path.realpath(inspect.getsourcefile(endpoints)))),
                "sys.path.append('{}')".format(os.path.realpath(os.curdir)),
                "",
                #"from endpoints.interface.wsgi import *",
                "from endpoints.interface.wsgi import Application, Server",
                ""
                "os.environ['ENDPOINTS_PREFIX'] = '{}'".format(controller_prefix),
                "",
                "##############################################################",
                os.linesep.join(config_module_body),
                "##############################################################",
                #os.linesep.join(self.get_script_body()),
                "#from wsgiref.validate import validator",
                "#application = validator(Application())",
                "application = Application()",
                ""
            ]),
            self.cwd
        )

        # server
        self.server = self.server_class(
            controller_prefix=controller_prefix,
            host=host,
            wsgifile=self.script_path
        )
        self.server.cwd = self.cwd
        self.server.start()

    @classmethod
    def kill(cls):
        cls.server_class(controller_prefix="", wsgifile=cls.server_script_name).kill()

    def __getattr__(self, key):
        try:
            m = getattr(self.client, key)
        except AttributeError:
            m = getattr(self.server, key)

        return m


class UWSGITest(TestCase):

    client_class = UWSGIClient

    def setUp(self):
        self.client_class.kill()

    def tearDown(self):
        self.client_class.kill()

    def create_client(self, *args, **kwargs):
        kwargs.setdefault("host", self.get_host())
        return self.client_class(*args, **kwargs)

    def test_request_url(self):
        """make sure request url gets controller_path correctly"""
        controller_prefix = "requesturl.controller"
        c = self.create_client(controller_prefix, [
            "from endpoints import Controller",
            "class Requrl(Controller):",
            "    def GET(self):",
            "        return self.request.url.controller",
            "",
        ])

        r = c.get('/requrl')
        self.assertTrue("/requrl" in r._body)

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

    def test_list_param_decorator(self):
        controller_prefix = "lpdcontroller"
        c = self.create_client(controller_prefix, [
            "from endpoints import Controller, decorators",
            "class Listparamdec(Controller):",
            "    @decorators.param('user_ids', 'user_ids[]', type=int, action='append_list')",
            "    def GET(self, **kwargs):",
            "        return int(''.join(map(str, kwargs['user_ids'])))",
            ""
        ])

        r = c.get('/listparamdec?user_ids[]=12&user_ids[]=34')
        self.assertEqual("1234", r.body)

    def test_post_file(self):
        filepath = testdata.create_file("filename.txt", "this is a text file to upload")
        controller_prefix = 'wsgi.post_file'
        c = self.create_client(controller_prefix, [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def POST(self, *args, **kwargs):",
            "        return kwargs['file'].filename",
            "",
        ])

        r = c.post_file('/', {"foo": "bar", "baz": "che"}, {"file": filepath})
        self.assertEqual(200, r.code)
        self.assertTrue("filename.txt" in r.body)

    def test_post_file_with_param(self):
        """make sure specifying a param for the file upload works as expected"""
        filepath = testdata.create_file("post_file_with_param.txt", "post_file_with_param")
        controller_prefix = 'wsgi.post_file_with_param'
        c = self.create_client(controller_prefix, [
            "from endpoints import Controller, decorators",
            "class Default(Controller):",
            "    @decorators.param('file')",
            "    def POST(self, *args, **kwargs):",
            "        return kwargs['file'].filename",
            "",
        ])

        r = c.post_file('/', {"foo": "bar", "baz": "che"}, {"file": filepath})
        self.assertEqual(200, r.code)
        self.assertTrue("post_file_with_param.txt" in r.body)

    def test_post_basic(self):
        controller_prefix = 'wsgi.post'
        c = self.create_client(controller_prefix, [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(*args, **kwargs): pass",
            "    def POST(*args, **kwargs): pass",
            "    def POST_v2(*args, **kwargs): return kwargs['foo']",
            "",
        ])

        r = c.post('/', json.dumps({"foo": "bar"}), headers={"content-type": "application/json", "Accept": "application/json;version=v2"})
        self.assertEqual(200, r.code)
        self.assertEqual('"bar"', r.body)

        r = c.post('/', {})
        self.assertEqual(204, r.code)

        r = c.post('/', None, headers={"content-type": "application/json"})
        self.assertEqual(204, r.code)

        r = c.post('/', None)
        self.assertEqual(204, r.code)

        r = c.post('/', json.dumps({}), headers={"content-type": "application/json"})
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
        c = self.create_client(
            controller_prefix,
            [
                "from endpoints import Controller",
                "",
                "class Default(Controller):",
                "    def POST(*args, **kwargs):",
                "        pass",
                "",
            ],
            [
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

        r = c.post(
            '/',
            {"foo": "bar"},
            headers={
                "content-type": "application/json",
            }
        )
        self.assertEqual(408, r.code)

    def test_404_request(self):
        controller_prefix = 'wsgi404.request404'
        c = self.create_client(controller_prefix, [
            "from endpoints import Controller",
            "class Foo(Controller):",
            "    def GET(self): pass",
            "",
        ])

        r = c.get('/foo/bar/baz?che=1&boo=2')
        self.assertEqual(404, r.code)

    def test_response_headers(self):
        controller_prefix = 'resp_headers.resp'
        c = self.create_client(controller_prefix, [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self):",
            "        self.response.set_header('FOO_BAR', 'check')",
            "",
        ])

        r = c.get('/')
        self.assertEqual(204, r.code)
        self.assertTrue("foo-bar" in r.headers)

    def test_file_stream(self):
        content = "this is a text file to stream"
        filepath = testdata.create_file("filename.txt", content)
        controller_prefix = 'wsgi.post_file'
        c = self.create_client(controller_prefix, [
            "from endpoints import Controller",
            "class Default(Controller):",
            "    def GET(self, *args, **kwargs):",
            "        f = open('{}')".format(filepath),
            "        self.response.set_header('content-type', 'text/plain')",
            "        return f",
            "",
        ])

        r = c.get('/')
        self.assertEqual(200, r.code)
        self.assertEqual(content, r.body)
        #self.assertTrue(r.body)


###############################################################################
# WSGI Server support
###############################################################################
class WSGIClient(UWSGIClient):
    server_class = WSGIServer


@skipIf(requests is None, "Skipping wsgi server Test because no requests module")
class WSGITest(UWSGITest):
    client_class = WSGIClient

    def test_chunked(self):
        raise SkipTest("chunked is not supported in Python WSGIClient")


###############################################################################
# Client tests
###############################################################################
class ClientTestCase(TestCase):
    server = None
    server_class = WSGIServer

    def setUp(self):
        if self.server:
            self.server.stop()

    def tearDown(self):
        if self.server:
            self.server.stop()

    def create_server(self, controller_prefix, contents, **kwargs):
        tdm = testdata.create_module(controller_prefix, contents)
        server = self.server_class(controller_prefix, host=self.get_host(), **kwargs)
        server.cwd = tdm.basedir
        server.stop()
        self.server = server
        self.server.start()
        return server

    def create_client(self):
        client = HTTPClient(self.get_host())
        return client


class HTTPClientTest(ClientTestCase):
    def test_get_url(self):
        c = self.create_client()

        uri = "http://foo.com"
        url = c.get_url(uri)
        self.assertEqual(uri, url)

        uri = "/foo/bar"
        url = c.get_url(uri)
        self.assertEqual("{}{}".format(c.host.host, uri), url)

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
        self.assertRegexpMatches(c.headers["authorization"], "Basic\s+[a-zA-Z0-9=]+")


class WSGIServerTest(ClientTestCase):
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


class UWSGIServer(WSGIServerTest):
    server_class = UWSGIServer

