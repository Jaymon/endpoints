import os
from BaseHTTPServer import BaseHTTPRequestHandler
import socket

from . import BaseInterface


class Simple(BaseInterface):
    def create_request(self, raw_request, *args, **kwargs):
        if '?' in raw_request.path:
            path, query = raw_request.path.split('?', 1)
        else:
            path = raw_request.path
            query = ""

        r = kwargs['request_class']()
        r.raw_request = raw_request
        r.path = path
        r.query = query
        r.method = raw_request.command
        r.headers = raw_request.headers.dict

        if r.is_method('POST'):
            content_length = int(r.get_header('content-length', 0))
            r.body = raw_request.rfile.read(content_length)

        return r

