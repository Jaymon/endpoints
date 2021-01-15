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

from ...compat import *
from ...http import Request as BaseRequest
from ...utils import ByteString
from .. import Payload, BaseWebsocketServer
from . import Application, uwsgi
from ...exception import CloseConnection


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

    def recv_payload(self, fd):
        """receive a message from the user that will be routed to other users, 
        in other words, the user sent a message from their client that the server
        is receiving on the internets"""

        if self.is_websocket(fd):
            while True:
                # loop over payload until all queued messages are exhausted, if
                # we don't consume them all then they will be silently discarded
                # https://github.com/unbit/uwsgi/issues/1241#issuecomment-241366419
                payload = uwsgi.websocket_recv_nb()
                if payload and payload != 'undefined':
                    yield payload

                else:
                    break

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


class WebsocketApplication(BaseWebsocketServer, Application):

    connection_class = Connection

    def is_http(self, environ):
        upgrade_header = environ.get("HTTP_UPGRADE", "")
        return not upgrade_header or (upgrade_header.lower() != "websocket")

    def create_connection(self):
        return self.connection_class(self)

    def send(self, req, res, conn):
        for s in self.create_websocket_response_body(req, res):
            conn.send_payload(s)

    def handle_websocket_response(self, environ):
        conn = self.create_connection()
        req = None
        message_count = 0

        try:
            c = self.connect_websocket_call(raw_request=environ)
            req = c.request
            res = c.handle()
            if res.code < 400:

                logger.info("Websocket {} Connected to server".format(req.uuid))
                conn.handle_connected(req, res)

                # send down connect success so js clients can know both success or
                # failure, turns out only sending down failure causes client code
                # to be more complex
                self.send(req, res, conn)

                for raw_request in conn:
                    c = self.create_websocket_call(req, raw_request)
                    message_count += 1
                    logger.debug("Websocket {} message {} received on server".format(
                        c.request.uuid,
                        message_count,
                    ))
                    res = c.handle()
                    conn.handle_called(c.request, res)
                    self.send(c.request, res, conn)

            else:
                # send down the connect results so javascript webclients can know
                # why we are about to disconnect
                logger.debug("Websocket {} Failed to connect to server".format(req.uuid))
                self.send(req, res, conn)

        except CloseConnection as e:
            req = None

        except IOError as e:
            # user disconnected
            # a user disconnecting is usually manifested by "IOError: unable to
            # receive websocket message", this is entirely normal and nothing to
            # be concerned about, it basically means the client closed the connection
            #logger.exception(e)
            logger.debug("Websocket {} client disconnected from server: {}".format(req.uuid, e))
            #logger.debug("Websocket {} client disconnected from server: {}".format(req.uuid, e), exc_info=True)
            #logger.debug(e, exc_info=True)

        except Exception as e:
            logger.exception(e)

        finally:
            if req:
                logger.info("Websocket {} Disconnected from server after {} message(s)".format(
                    req.uuid,
                    message_count,
                ))
                c = self.disconnect_websocket_call(req)
                c.quiet = True
                c.handle()

            conn.close()
            conn.handle_disconnected(req, res)

        return ''

    def __call__(self, environ, start_response):
        if self.is_http(environ):
            res = self.handle_http_response(environ, start_response)

        else:
            res = self.handle_websocket_response(environ)

        return res

