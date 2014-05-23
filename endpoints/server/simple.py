from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import os
import sys
import socket
import logging


from ..interface.simple import Simple as SimpleInterface
from . import BaseServer


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
            for b in res.gbody:
                self.send_response(res.code)
                for h, hv in res.headers.iteritems():
                    self.send_header(h, hv)

                #self.send_header('Connection', 'close')
                self.end_headers()

                if res.has_body():
                    self.wfile.write(b)
                    self.wfile.flush()
                    self.wfile.close()
                    # HACK
                    # this allows the yield trick to work when there is a body :)
                    # but honestly I'm not sure how safe it is, but it works
                    try:
                        self.request.shutdown(socket.SHUT_WR)
                    except socket.error:
                        pass
                    self.request.close()

        except socket.timeout, e:
            self.log_error("Request timed out: %r", e)
            self.close_connection = 1
            return


class SimpleHTTPServer(HTTPServer):
    def finish_request(self, request, client_address):
        """Finish one request by instantiating RequestHandlerClass."""
        self.RequestHandlerClass(request, client_address, self, interface=self.interface)


class Simple(BaseServer):
    interface_class = SimpleInterface
    server_class = SimpleHTTPServer 

    def create_server(self, *args, **kwargs):
        host = kwargs.pop('host', '')
        if not host:
            host = os.environ['ENDPOINTS_SIMPLE_HOST']

        h, p = host.split(':')
        server_address = (h, int(p))

        s = self.server_class(server_address, SimpleHandler, *args, **kwargs)
        s.interface = self.interface
        return s

    def handle_request(self):
        return self.server.handle_request()

    def serve_forever(self):
        return self.server.serve_forever()

