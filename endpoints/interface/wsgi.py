from __future__ import absolute_import

from . import BaseInterface, BaseServer


class WSGI(BaseInterface):
    def create_request(self, raw_request, **kwargs):
        """
        create instance of request

        raw_request -- mongrel2.request.Request() -- the request object retrieved from mongrel2
        """
        r = self.request_class()
        for k, v in raw_request.iteritems():
            if k.startswith('HTTP_'):
                r.headers[k[5:]] = v
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
            r.headers[k] = ct

        if 'wsgi.input' in raw_request:
            body = raw_request['wsgi.input'].read()
            if not body: body = None
            r.body = body

        else:
            r.body = None

        return r


class Server(BaseServer):
    interface_class = WSGI

    def __call__(self, environ, start_response):
        return self.application(environ, start_response)

    def application(self, environ, start_response):
        res = self.interface.handle(environ)
        body = res.body # we do this to trigger the generator

        start_response(
            '{} {}'.format(res.code, res.status),
            [(k, v) for k, v in res.headers.iteritems()]
        )
        return [body]

    def create_server(self, **kwargs):
        return None

    def handle_request(self):
        raise NotImplemented("WSGI is used through application() method")

    def serve_forever(self):
        raise NotImplemented("WSGI is used through application() method")

    def serve_count(self, count):
        raise NotImplemented("WSGI is used through application() method")

