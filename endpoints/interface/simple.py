import os
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import socket
import sys

from . import BaseInterface, BaseServer


class InputWrapper(object):
    """make the Simple body input act like the WSGI input and not block
    on no content"""
    def __init__(self, fp, length):
        self.fp = fp
        self.length = int(length)

    def read(self, *args, **kwargs):
        if not self.length:
            return ""

        return self.fp.read(*args, **kwargs)


class Simple(BaseInterface):
    def create_request(self, raw_request, **kwargs):
        if '?' in raw_request.path:
            path, query = raw_request.path.split('?', 1)
        else:
            path = raw_request.path
            query = ""

        r = self.request_class()
        r.raw_request = raw_request
        r.path = path
        r.query = query
        r.method = raw_request.command
        r.set_headers(raw_request.headers.dict)
        r.raw_request = raw_request
        r.environ = {
            "REQUEST_METHOD": r.method,
            "QUERY_STRING": r.query
        }

        if r.is_method('POST'):
            #r.body_input = InputWrapper(raw_request.rfile, r.get_header('content-length', 0))
            r.body_input = raw_request.rfile
#             r.body_kwargs = self.normalize_body_kwargs(
#                 r.get_header("content-type"),
#                 raw_request.rfile,
#                 raw_request
#             )

            #content_length = int(r.get_header('content-length', 0))
            #r.body = raw_request.rfile.read(content_length)

        return r


class SimpleHandler(BaseHTTPRequestHandler):
    #protocol_version = 'HTTP/1.1'
    def __init__(self, *args, **kwargs):
        self.interface = kwargs.pop('interface')
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def handle_one_request(self):
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                self.close_connection = 1
                return

            if not self.parse_request():
                # An error code has been sent, just exit
                return

            res = self.interface.handle(self)

            # send headers
            self.send_response(res.code)
            for h, hv in res.headers.items():
                self.send_header(h, hv)
            self.end_headers()

            # send body if one was generated
            if res.has_body():
                self.wfile.write(res.body)
                self.wfile.flush()
                self.wfile.close()
                self.request.close()

        except socket.timeout as e:
            self.log_error("Request timed out: %r", e)
            self.close_connection = 1
            return


class SimpleHTTPServer(HTTPServer):
    def finish_request(self, request, client_address):
        """Finish one request by instantiating RequestHandlerClass."""
        self.RequestHandlerClass(request, client_address, self, interface=self.interface)


class Server(BaseServer):
    interface_class = Simple
    server_class = SimpleHTTPServer

    def create_server(self, **kwargs):
        host = kwargs.pop('host', '')
        if not host:
            host = os.environ['ENDPOINTS_SIMPLE_HOST']

        h, p = host.split(':')
        server_address = (h, int(p))

        s = self.server_class(server_address, SimpleHandler, **kwargs)
        s.interface = self.interface
        return s

    def handle_request(self):
        return self.server.handle_request()

    def serve_forever(self):
        return self.server.serve_forever()

