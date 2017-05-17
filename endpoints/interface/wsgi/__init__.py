from __future__ import absolute_import
import os
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
import SocketServer

from .. import BaseServer
from ...http import Url
from ...decorators import _property
from ...utils import ByteString


# http://stackoverflow.com/questions/20745352/creating-a-multithreaded-server
class WSGIHTTPServer(SocketServer.ThreadingMixIn, WSGIServer):
    """This is here to make the standard wsgi server multithreaded"""
    pass


class Application(BaseServer):
    """The Application that a WSGI server needs

    this extends Server just to make it easier on the end user, basically, all you
    need to do to use this is in your wsgi-file, you can just do:

        from endpoints.interface.wsgi import Application
        application = Application()

    and be good to go
    """
    def __call__(self, environ, start_response):
        """this is what will be called for each request that that WSGI server handles"""
        c = self.create_call(environ)
        c.handle()
        return self.handle_http_response(c, start_response)

    def handle_http_response(self, call, start_response):
        res = call.response

        start_response(
            ByteString('{} {}'.format(res.code, res.status), res.encoding),
            [(ByteString(k, res.encoding), ByteString(v, res.encoding)) for k, v in res.headers.items()]
        )

        # returning the Response, it needs to have an __iter__ for internal wsgi 
        # methods to know how to handle the Response
        return res

    def create_request(self, raw_request, **kwargs):
        """
        create instance of request

        raw_request -- the raw request object retrieved from a WSGI server
        """
        r = self.request_class()
        for k, v in raw_request.items():
            if k.startswith('HTTP_'):
                r.set_header(k[5:], v)
            else:
                r.environ[k] = v

        r.method = raw_request['REQUEST_METHOD']
        r.path = raw_request['PATH_INFO']
        r.query = raw_request['QUERY_STRING']
        r.raw_request = raw_request

        # handle headers not prefixed with http
        for k, t in {'CONTENT_TYPE': None, 'CONTENT_LENGTH': int}.items():
            v = r.environ.pop(k, None)
            if v:
                r.set_header(k, t(v) if t else v)

        if 'wsgi.input' in raw_request:

            if "CONTENT_LENGTH" in raw_request and r.get_header("CONTENT_LENGTH", 0) <= 0:
                r.body_kwargs = {}

            else:
                if r.get_header('transfer-encoding', "").lower().startswith('chunked'):
                    self.handle_chunked_request(r)

                else:
                    r.body_input = raw_request['wsgi.input']

        else:
            r.body_kwargs = {}

        return r

    def handle_chunked_request(self, req):
        raise IOError("Server does not support chunked requests")

    def create_backend(self, **kwargs):
        raise NotImplementedError()

    def handle_request(self):
        raise NotImplementedError()

    def serve_forever(self):
        raise NotImplementedError()

    def serve_count(self, count):
        raise NotImplementedError()


class Server(BaseServer):
    """A simple python WSGI Server

    you would normally only use this with the bin/wsgiserver.py script, if you
    want to use it outside of that, then look at that script for inspiration
    """
    application_class = Application

    backend_class = WSGIHTTPServer

    @_property
    def application(self):
        """if no application has been set, then create it using application_class"""
        app = self.application_class()
        return app

    @application.setter
    def application(self, v):
        """allow overriding of the application factory, this allows you to set
        your own application callable that will be used to handle requests, see
        bin/wsgiserver.py script as an example of usage"""
        self._application = v
        self.backend.set_app(v)

    def create_backend(self, **kwargs):
        host = kwargs.pop('host', '')
        if not host:
            host = os.environ['ENDPOINTS_HOST']

        host = Url(host)
        hostname = host.hostname
        port = host.port
        if not port:
            raise RuntimeError("Please specify a port using the format host:PORT")
        server_address = (hostname, port)

        s = self.backend_class(server_address, WSGIRequestHandler, **kwargs)
        s.set_app(self.application)
        return s

    def handle_request(self):
        #self.prepare()
        return self.backend.handle_request()

    def serve_forever(self):
        #self.prepare()
        return self.backend.serve_forever()


