from __future__ import absolute_import
import os
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
import SocketServer

try:
    import uwsgi
except ImportError:
    uwsgi = None

try:
    from cstringio import StringIO
except ImportError:
    from StringIO import StringIO

from . import BaseInterface, BaseServer
from ..http import Url


class uWSGIChunkedBody(object):
    """Micro-WSGI has support for chunked transfer encoding, this class is a small
    wrapper around uWSGI's chunked transfer mechanism so the rest of endpoints doesn't
    have to know anything about what uWSGI is doing under the hood.

    http://uwsgi-docs.readthedocs.org/en/latest/Chunked.html

    Right now, this is a resetting body, which means when it is done being read it
    will reset so it can be read again. Also, using StringIO means that the raw body
    gets stored for the life of the request, which is not memory efficient
    """

    def __init__(self):
        self._body = StringIO()

    def _chunked_read(self):
        size = 0
        try:
            chunk = uwsgi.chunked_read()
            old_pos = self._body.pos
            self._body.write(chunk)
            self._body.pos = old_pos
            size = len(chunk)

            if not size:
                self._body.pos = 0

        except IOError as e:
            raise IOError("Error reading chunk, is --http-raw-body enabled? Error: {}".format(e))

        return size

    def __iter__(self):
        yield self.readline()

    def read(self, size=-1):
        while size < 0 or size > (self._body.len - self._body.pos):
            chunk_size = self._chunked_read()
            if not chunk_size:
                break

        return self._body.read(size)

    def readline(self, size=0):
        line = self._body.readline(size)
        if not line:
            chunked_size = self._chunked_read()
            if chunked_size:
                line = self._body.readline(size)

        return line


class WSGIInterface(BaseInterface):
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
                    if uwsgi:
                        r.body_input = uWSGIChunkedBody()

                    else:
                        raise IOError("Server does not support chunked requests")

                else:
                    r.body_input = raw_request['wsgi.input']

        else:
            r.body_kwargs = {}

        return r


# http://stackoverflow.com/questions/20745352/creating-a-multithreaded-server-using-socketserver-framework-in-python?rq=1
class WSGIHTTPServer(SocketServer.ThreadingMixIn, WSGIServer):
    """This is here to make the standard wsgi server multithreaded"""
    pass


class WSGIBaseServer(BaseServer):
    """Common WSGI base configuration"""
    interface_class = WSGIInterface
    server_class = WSGIHTTPServer


class Application(WSGIBaseServer):
    """The Application that a WSGI server needs

    this extends Server just to make it easier on the end user, basically, all you
    need to do to use this is in your wsgi-file, you can just do:

        from endpoints.interface.wsgi import Application
        application = Application()

    and be good to go
    """
    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args, **kwargs)
        self.prepare()

    def __call__(self, environ, start_response):
        """this is what will be called for each request that that WSGI server handles"""
        res = self.interface.handle(environ)
        start_response(
            '{} {}'.format(res.code, res.status),
            [(k, str(v)) for k, v in res.headers.items()]
        )
        return res

    def create_server(self, **kwargs):
        return None

    def handle_request(self):
        raise NotImplementedError()

    def serve_forever(self):
        raise NotImplementedError()

    def serve_count(self, count):
        raise NotImplementedError()


class Server(WSGIBaseServer):
    """A simple python WSGI Server

    you would normally only use this with the bin/wsgiserver.py script, if you
    want to use it outside of that, then look at that script for inspiration
    """
    application_class=Application

    @property
    def application(self):
        """if no application has been set, then create it using application_class"""
        app = getattr(self, "_application", None)
        if not app:
            app = self.application_class()
            self._application = app
        return app

    @application.setter
    def application(self, v):
        """allow overriding of the application factory, this allows you to set
        your own application callable that will be used to handle requests, see
        bin/wsgiserver.py script as an example of usage"""
        self._application = v

    def create_server(self, **kwargs):
        host = kwargs.pop('host', '')
        if not host:
            host = os.environ['ENDPOINTS_HOST']

        host = Url(host)
        server_address = (host.hostname, host.port)

        s = self.server_class(server_address, WSGIRequestHandler, **kwargs)
        s.set_app(self.application)
        return s

    def handle_request(self):
        self.prepare()
        return self.server.handle_request()

    def serve_forever(self):
        self.prepare()
        return self.server.serve_forever()


