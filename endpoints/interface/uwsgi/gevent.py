# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import logging

logger = logging.getLogger(__name__)

try:
    import gevent.select
    import gevent.monkey
except ImportError:
    logger.error("you need to install gevent to use {}".format(__name__))
    raise
finally:
    if not gevent.monkey.saved:
        # https://github.com/gevent/gevent/blob/master/src/gevent/monkey.py
        logger.info("Running gevent.monkey.patch_all() since not run previously")
        gevent.monkey.patch_all()

from . import Application, uwsgi, Payload
from ...http import Request as BaseRequest
from ...utils import ByteString


logger = logging.getLogger(__name__)


class Connection(object):
    """Handle the full websocket connection lifecycle
    When a websocket connection is fully established, this class is created and
    ties the user to the file descriptors for the websocket and Redis pubsub
    connections. It handles receiving and routing the messages that come in from
    and to the user.
    It's created in Application.application_websocket and is only used there, so look
    at that method to see how this object is used

    https://github.com/unbit/uwsgi/blob/master/tests/websockets_chat.py
    """

    def __init__(self, app):

        uwsgi.websocket_handshake()

        self.app = app
        #self.request = request
        #self.response = response
        self.pid = os.getpid()

        self.ws_fd = uwsgi.connection_fd()
        self.descriptors = [self.ws_fd]

    def is_websocket(self, fd):
        return fd == self.ws_fd

    def recv_payload(self):
        """receive a message from the user that will be routed to other users, 
        in other words, the user sent a message from their client that the server
        is receiving on the internets"""
        msg = None
        payload = uwsgi.websocket_recv_nb()

        # make sure the received message is valid
        if not payload: return None
        if payload == 'undefined': return None

        return payload

    def send_payload(self, payload):
        """take all the messages received from a redis pubsub channel_name and send it
        down the websocket to the user"""

        uwsgi.websocket_send(payload)

    def __iter__(self):
        """just keep iterating through ready to read file descriptors for all eternity"""
        while True:
            # logger.debug("user {} waiting".format(user.pk))
            ready = gevent.select.select(self.descriptors, [], [], 10)
            if not ready[0]: continue
            for fd in ready[0]:
                yield fd

    def close(self):
        pass


class WebsocketApplication(Application):

    connection_class = Connection

    payload_class = Payload

    def is_http(self, req):
        upgrade_header = req.get_header('upgrade')
        return not upgrade_header or (upgrade_header.lower() != 'websocket')

    def create_environ(self, raw_request, payload):
        environ = dict(raw_request)
        environ["REQUEST_METHOD"] = payload.method
        environ["PATH_INFO"] = payload.path
        environ.pop("wsgi.input", None)
        environ["WS_PAYLOAD"] = payload
        return environ

    def create_request(self, environ):
        payload = environ.pop("WS_PAYLOAD", None)
        req = super(Application, self).create_request(environ)
        if payload:
            req.body_kwargs = payload.body
            req.payload = payload
        return req

    def create_request_payload(self, raw):
        return self.payload_class(raw)

    def create_response_payload(self, req, res):
        kwargs = {
            "path": req.path,
            "body": res._body,
            "code": res.code,
        }
        uuid = req.payload.uuid
        if uuid:
            kwargs["uuid"] = uuid

        return self.payload_class(**kwargs)

    def create_connection(self):
        return self.connection_class(self)

    def handle_websocket_response(self, call):
        req = call.request
        res = call.response
        conn = self.create_connection()

        logger.info("Websocket Connected")

        try:
            for fd in conn:
                if conn.is_websocket(fd):
                    # we've received a message from this client's websocket
                    raw = conn.recv_payload()
                    if raw:
                        req_payload = self.create_request_payload(raw)
                        environ = self.create_environ(req.raw_request, req_payload)
                        c = self.create_call(environ)
                        res = c.handle()

                        res_payload = self.create_response_payload(c.request, res)
                        conn.send_payload(res_payload.payload)

        except IOError as e:
            # user disconnected
            logger.exception(e)
            pass

        except Exception as e:
            logger.exception(e)

        finally:
            conn.close()

        return ''

    def __call__(self, environ, start_response):
        c = self.create_call(environ)
        req = c.request

        body = ''
        if self.is_http(req):
            res = c.handle()
            res = self.handle_http_response(c, start_response)

        else:
            req.method = "CONNECT"
            res = c.handle()
            if res.code in [200, 204]:
                try:
                    self.handle_websocket_response(c)

                    req.method = "DISCONNECT"
                    res = c.handle()

                except Exception as e:
                    c.handle_error(e)
                    res = self.handle_http_response(c, start_response)

            else:
                res = self.handle_http_response(c, start_response)

        return res

