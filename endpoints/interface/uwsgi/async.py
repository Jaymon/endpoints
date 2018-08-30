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
else:
    if not gevent.monkey.saved:
        # https://github.com/gevent/gevent/blob/master/src/gevent/monkey.py
        logger.warning("Running gevent.monkey.patch_all() since not run previously")
        gevent.monkey.patch_all()

from ...compat.environ import *
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

    def recv_payload(self, fd):
        """receive a message from the user that will be routed to other users, 
        in other words, the user sent a message from their client that the server
        is receiving on the internets"""

        payload = uwsgi.websocket_recv_nb()
        if payload and payload != 'undefined':
            yield payload


#         if not self.is_websocket(fd): return None
# 
#         payload = uwsgi.websocket_recv_nb()

        # make sure the received message is valid
#         if not payload: return None
#         if payload == 'undefined': return None
#         return payload


    def send_payload(self, payload):
        """take all the messages received from a redis pubsub channel_name and send it
        down the websocket to the user"""

        uwsgi.websocket_send(payload)

    def __iter__(self):
        """just keep iterating through ready to read file descriptors for all eternity

        :returns: payload, the raw payload received from a socket
        """
        while True:
            # logger.debug("user {} waiting".format(user.pk))
            ready = gevent.select.select(self.descriptors, [], [], 10)
            if not ready[0]:
                # send websocket ping on timeout
                uwsgi.websocket_recv_nb()
                continue

            for fd in ready[0]:
                for payload in self.recv_payload(fd):
                    if payload:
                        yield payload

    def close(self):
        pass

    def __hash__(self):
        return int(self.ws_fd)

    def handle_connected(self, req, res):
        """called right after a successful websocket connection"""
        pass

    def handle_disconnected(self, req, res):
        """called right after a successful websocket disconnection"""
        pass

    def handle_called(self, req, res):
        """called each time after a controller has handled the request"""
        pass


class WebsocketApplication(Application):

    connection_class = Connection

    payload_class = Payload

    def is_http(self, req):
        upgrade_header = req.get_header('upgrade')
        return not upgrade_header or (upgrade_header.lower() != 'websocket')

    def create_environ(self, req, payload):
        """This will take the original request and the new websocket payload and
        merge them into a new request instance"""
        ws_req = req.copy()

        del ws_req.controller_info

        ws_req.environ.pop("wsgi.input", None)
        ws_req.body_kwargs = payload.body

        ws_req.environ["REQUEST_METHOD"] = payload.method
        ws_req.method = payload.method

        ws_req.environ["PATH_INFO"] = payload.path
        ws_req.path = payload.path

        ws_req.environ["WS_PAYLOAD"] = payload
        ws_req.environ["WS_ORIGINAL"] = req

        ws_req.payload = payload
        ws_req.parent = req
        return {"WS_REQUEST": ws_req}

    def create_request(self, environ):
        if "WS_REQUEST" in environ:
            req = environ["WS_REQUEST"]
        else:
            req = super(WebsocketApplication, self).create_request(environ)
        return req

    def create_request_payload(self, raw):
        return self.payload_class(raw)

    def create_response_payload(self, req, res, count):
        kwargs = {
            "path": req.path,
            "body": res._body,
            "code": res.code,
            "count": count,
        }

        payload = getattr(req, "payload", None)
        if payload:
            uuid = payload.uuid
            if uuid:
                kwargs["uuid"] = uuid

        return self.payload_class(**kwargs)

    def create_connection(self):
        return self.connection_class(self)

    def handle_websocket_response(self, call):
        req = call.request
        res = call.response
        conn = self.create_connection()

        logger.info("Websocket {} Connected".format(hash(conn)))

        try:
            req.connection = conn
            req.method = "CONNECT"
            res = call.handle()
            if res.code < 400:

                conn.handle_connected(req, res)

                # send down connect success so js clients can know both success or
                # failure, turns out only sending down failure causes client code
                # to be more complex
                res_payload = self.create_response_payload(req, res, 1)
                res_payload.uuid = "CONNECT"
                conn.send_payload(res_payload.payload)

                for count, raw in enumerate(conn, 2):
                    req_payload = self.create_request_payload(raw)
                    environ = self.create_environ(req, req_payload)
                    c = self.create_call(environ)
                    res = c.handle()

                    conn.handle_called(c.request, res)
                    res_payload = self.create_response_payload(c.request, res, count)
                    conn.send_payload(res_payload.payload)

            else:
                # send down the connect results so javascript webclients can know
                # why we are about to disconnect
                res_payload = self.create_response_payload(req, res, 1)
                res_payload.uuid = "CONNECT"
                conn.send_payload(res_payload.payload)

        except IOError as e:
            # user disconnected
            # a user disconnecting is usually manifested by "IOError: unable to
            # receive websocket message", this is entirely normal and nothing to
            # be concerned about, it basically means the client closed the connection
            logger.info("Websocket {} Disconnected".format(hash(conn)))
            #logger.exception(e)

        except Exception as e:
            logger.exception(e)

        finally:
            req.method = "DISCONNECT"
            call.quiet = True
            res = call.handle()
            conn.close()
            conn.handle_disconnected(req, res)

        return ''


    def __call__(self, environ, start_response):
        c = self.create_call(environ)
        req = c.request

        if self.is_http(req):
            res = c.handle()
            res = self.handle_http_response(c, start_response)

        else:
            res = self.handle_websocket_response(c)

        return res





#     def __call__(self, environ, start_response):
#         c = self.create_call(environ)
#         req = c.request
# 
#         body = ''
#         if self.is_http(req):
#             res = c.handle()
#             res = self.handle_http_response(c, start_response)
# 
#         else:
#             req.method = "CONNECT"
#             res = c.handle()
#             if res.code in [200, 204]:
#                 try:
#                     self.handle_websocket_response(c)
# 
#                     req.method = "DISCONNECT"
#                     res = c.handle()
# 
#                 except Exception as e:
#                     c.handle_error(e)
#                     res = self.handle_http_response(c, start_response)
# 
#             else:
#                 res = self.handle_http_response(c, start_response)
# 
#         return res

