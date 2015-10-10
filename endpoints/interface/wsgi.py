from __future__ import absolute_import

try:
    import uwsgi
except ImportError:
    uwsgi = None

try:
    from cstringio import StringIO
except ImportError:
    from StringIO import StringIO

from . import BaseInterface, BaseServer


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


class WSGI(BaseInterface):
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
        k = 'CONTENT_TYPE'
        ct = r.environ.pop(k, None)
        if ct:
            r.set_header(k, ct)

        if 'wsgi.input' in raw_request:

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


class Server(BaseServer):
    interface_class = WSGI

    def __call__(self, environ, start_response):
        return self.application(environ, start_response)

    def application(self, environ, start_response):
        res = self.interface.handle(environ)

        start_response(
            '{} {}'.format(res.code, res.status),
            [(k, str(v)) for k, v in res.headers.items()]
        )
        #return (b for b in res)
        return res

    def create_server(self, **kwargs):
        return None

    def handle_request(self):
        raise NotImplemented("WSGI is handled through application() method")

    def serve_forever(self):
        raise NotImplemented("WSGI is handled through application() method")

    def serve_count(self, count):
        raise NotImplemented("WSGI is handled through application() method")

