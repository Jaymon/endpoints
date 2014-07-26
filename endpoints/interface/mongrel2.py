from __future__ import absolute_import
import os
from uuid import uuid4

from . import BaseInterface, BaseServer
from ..http import Request as BaseRequest

from mongrel2 import handler


class Request(BaseRequest):
    pass


class Mongrel2(BaseInterface):
    def create_request(self, raw_request, **kwargs):
        """
        create instance of request

        raw_request -- mongrel2.request.Request() -- the request object retrieved from mongrel2
        """
        r = self.request_class()
        return self.normalize_request(r, raw_request, **kwargs)

    def normalize_request(self, request, raw_request, **kwargs):
        """This is called by create_request to do the actual combining of the raw_request
        into the endpoints request instance, this is to make it easier to allow
        custom creation in child classes that can then use the same combine code"""
        request.raw_request = raw_request

        # separate environ from headers
        environ = {}
        headers = {}

        environ_ks = set([
            'PATTERN',
            'PATH',
            'QUERY',
            'URI',
            'METHOD',
            'VERSION',
            'URL_SCHEME',
            'REMOTE_ADDR'
        ])
        for k, v in raw_request.headers.iteritems():
            if k in environ_ks:
                environ[k] = v

            else:
                headers[k] = v

        request.headers = headers
        request.environ = environ

        request.path = environ.get(u'PATH', u"/")
        request.query = environ.get(u'QUERY', u"")
        request.method = environ.get(u'METHOD', u"GET")

        # make sure body is None if it is empty
        body = getattr(raw_request, 'body', None)
        if not body: body = None
        request.body = body
        return request


class Connection(handler.Connection):
    def __init__(self, sub_addr='', pub_addr='', *args, **kwargs):
        """
        sub_addr -- string -- the mongrel2 handler send_spec
        pub_addr -- string -- the mongrel2 handler recv_spec
        """
        if not sub_addr:
            sub_addr = os.environ['ENDPOINTS_MONGREL2_SUB']

        if not pub_addr:
            pub_addr = os.environ['ENDPOINTS_MONGREL2_PUB']

        # ZMQ 2.1.x broke how PUSH/PULL round-robin works so each process
        # needs it's own id for it to work
        sender_id = kwargs.get('sender_id', uuid4().hex)
        super(Connection, self).__init__(sender_id, sub_addr, pub_addr)

    def recv(self):
        req = None
        while req == None:
            req = super(Connection, self).recv()
            # this is used to disconnect websockets, not sure if it is needed for http but
            # it is in the examples, so I'm keeping it here for the moment
            if req.is_disconnect():
                req = None

        return req

    def normalize_headers(self, headers):
        """make sure all the headers have string values, ZeroMQ freaks out with unicode"""
        rheaders = {}
        for n, v in headers.iteritems():
            if isinstance(n, unicode):
                n = n.encode('utf-8')
            if isinstance(v, unicode):
                v = v.encode('utf-8')

            rheaders[n] = v

        return rheaders

    def reply_http(self, req, body, code=200, status="OK", headers=None):
        """exactly mirrors parent, but normalizes headers before moving on"""
        if headers:
            headers = self.normalize_headers(headers)

        return super(Connection, self).reply_http(req, body, code, status, headers)


class Server(BaseServer):
    interface_class = Mongrel2
    server_class = Connection
    request_class = Request

    def handle_request(self):
        m2_req = self.server.recv()
        res = self.interface.handle(m2_req)
        for b in res.gbody:
            self.server.reply_http(
              m2_req,
              body=b,
              code=res.code,
              status=res.status,
              headers=res.headers
            )

