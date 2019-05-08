# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from contextlib import contextmanager
import datetime
import random
import re
import ssl
import string
import time
import socket
import logging

logger = logging.getLogger(__name__)

try:
    # https://github.com/websocket-client/websocket-client
    import websocket
except ImportError:
    websocket = None

from ...compat.environ import *
from ...client import HTTPClient
from ...http import Headers
from ...utils import Path
from ..wsgi.client import WSGIServer
from . import Payload


# TODO: this could actually be moved into endpoints.client except it currently relies
# on Payload which is only in uwsgi portion right now, but if that is ever moved
# into a generic websocket framework then you can move this to generic client
class WebsocketClient(HTTPClient):
    """a websocket client

    pretty much every method of this client can accept a timeout argument, if you
    don't include the timeout then self.timeout will be used instead
    """

    payload_class = Payload

    attempts = 3
    """how many times the client should attempt to connect/re-connect"""

    @property
    def connected(self):
        ws = getattr(self, 'ws', None)
        return self.ws.connected if ws else False

    def __init__(self, host, *args, **kwargs):
        if not websocket:
            logger.error("You need to install websocket-client to use {}".format(
                type(self).__name__
            ))
            raise ImportError("websocket-client is not installed")

        kwargs.setdefault("headers", Headers())
        kwargs["headers"]['User-Agent'] = "Endpoints Websocket Client"
        super(WebsocketClient, self).__init__(host, *args, **kwargs)

        self.set_trace(kwargs.pop("trace", False))
        self.client_id = id(self)
        self.send_count = 0
        self.attempts = kwargs.pop("attempts", self.attempts)

    @contextmanager
    def wstimeout(self, timeout=0, **kwargs):
        timeout = self.get_timeout(timeout=timeout, **kwargs)
        self.ws.sock.settimeout(timeout)
        yield timeout

    @classmethod
    @contextmanager
    def open(cls, *args, **kwargs):
        """just something to make it easier to quickly open a connection, do something
        and then close it"""
        c = cls(*args, **kwargs)
        c.connect()
        try:
            yield c

        finally:
            c.close()

    def set_trace(self, trace):
        if trace:
            websocket.enableTrace(True) # for debugging connection issues

    def get_fetch_host(self):
        if self.host.scheme.lower().startswith("http"):
            ws_host = self.host.add(
                scheme=re.sub(r'^http', 'ws', self.host.scheme.lower())
            ).root

        else:
            ws_host = self.host.root

        return ws_host

    def get_timeout(self, timeout=0, **kwargs):
        if not timeout:
            timeout = self.timeout
        return timeout

    def connect(self, path="", headers=None, query=None, timeout=0, **kwargs):
        """
        make the actual connection to the websocket

        :param headers: dict, key/val pairs of any headers to add to connection, if
            you would like to override headers just pass in an empty value
        :param query: dict, any query string params you want to send up with the connection
            url
        :returns: Payload, this will return the CONNECT response from the websocket
        """
        ret = None
        ws_url = self.get_fetch_url(path, query)
        ws_headers = self.get_fetch_headers("GET", headers)
        ws_headers = ['{}: {}'.format(h[0], h[1]) for h in ws_headers.items() if h[1]]
        timeout = self.get_timeout(timeout=timeout, **kwargs)

        self.set_trace(kwargs.pop("trace", False))
        #pout.v(websocket_url, websocket_headers, self.query_kwargs, self.headers)

        try:
            logger.debug("{} connecting to {}".format(self.client_id, ws_url))
            self.ws = websocket.create_connection(
                ws_url,
                header=ws_headers,
                timeout=timeout,
                sslopt={'cert_reqs':ssl.CERT_NONE},
            )

            ret = self.recv_callback(callback=lambda r: r.uuid == "CONNECT")
            if ret.code >= 400:
                raise IOError("Failed to connect with code {}".format(ret.code))

#             self.headers = headers
#             self.query_kwargs = query_kwargs

        except websocket.WebSocketTimeoutException:
            raise IOError("Failed to connect within {} seconds".format(timeout))

        except websocket.WebSocketException as e:
            raise IOError("Failed to connect with error: {}".format(e))

        except socket.error as e:
            # this is an IOError, I just wanted to be aware of that, most common
            # problem is: [Errno 111] Connection refused
            raise

        return ret

    def get_fetch_request(self, method, path, body):
        uuid = "{}-{}".format(self.client_id, self.send_count)
        p = Payload(method=method.upper(), path=path, body=body, uuid=uuid)
        return p

    def send(self, path, body, **kwargs):
        return self.fetch("SOCKET", path, body=body, **kwargs)

    def fetch(self, method, path, query=None, body=None, timeout=0, **kwargs):
        """send a Message

        :param method: string, something like "POST" or "GET"
        :param path: string, the path part of a uri (eg, /foo/bar)
        :param body: dict, what you want to send to "method path"
        :param timeout: integer, how long to wait before failing trying to send
        """
        ret = None
        if not query: query = {}
        if not body: body = {}
        query.update(body) # body takes precedence
        body = query

        self.send_count += 1
        payload = self.get_fetch_request(method, path, body)
        attempts = 1
        max_attempts = self.attempts
        success = False

        while not success:
            kwargs['timeout'] = timeout
            try:
                try:
                    if not self.connected: self.connect(path)
                    with self.wstimeout(**kwargs) as timeout:
                        kwargs['timeout'] = timeout

                        logger.debug('{} send {} attempt {}/{} with timeout {}'.format(
                            self.client_id,
                            payload.uuid,
                            attempts,
                            max_attempts,
                            timeout
                        ))

                        sent_bits = self.ws.send(payload.payload)
                        logger.debug('{} sent {} bytes'.format(self.client_id, sent_bits))
                        if sent_bits:
                            ret = self.fetch_response(payload, **kwargs)
                            if ret:
                                success = True

                except websocket.WebSocketConnectionClosedException as e:
                    self.ws.shutdown()
                    raise IOError("connection is not open but reported it was open: {}".format(e))

            except (IOError, TypeError) as e:
                logger.debug('{} error on send attempt {}: {}'.format(self.client_id, attempts, e))
                success = False

            finally:
                if not success:
                    attempts += 1
                    if attempts > max_attempts:
                        raise

                    else:
                        timeout *= 2
                        if (attempts / max_attempts) > 0.50:
                            logger.debug(
                                "{} closing and re-opening connection for next attempt".format(self.client_id)
                            )
                            self.close()

        return ret

    def fetch_response(self, req_payload, **kwargs):
        """payload has been sent, do anything else you need to do (eg, wait for response?)

        :param req_payload: Payload, the payload sent to the server
        :returns: Payload, the response payload
        """
        if req_payload.uuid:
            uuids = set([req_payload.uuid, "CONNECT"])
            def callback(res_payload):
                #pout.v(req_payload, res_payload)
                #ret = req_payload.uuid == res_payload.uuid or res_payload.uuid == "CONNECT"
                ret = res_payload.uuid in uuids
                if ret:
                    logger.debug('{} received {} response for {}'.format(
                        self.client_id,
                        res_payload.code,
                        res_payload.uuid,
                    ))
                return ret

            res_payload = self.recv_callback(callback, **kwargs)

        return res_payload

    def ping(self, timeout=0, **kwargs):
        """THIS DOES NOT WORK, UWSGI DOES NOT RESPOND TO PINGS"""

        # http://stackoverflow.com/a/2257449/5006
        def rand_id(size=8, chars=string.ascii_uppercase + string.digits):
            return ''.join(random.choice(chars) for _ in range(size))

        payload = rand_id()
        self.ws.ping(payload)
        opcode, data = self.recv_raw(timeout, [websocket.ABNF.OPCODE_PONG], **kwargs)
        if data != payload:
            raise IOError("Pinged server but did not receive correct pong")

    def recv_raw(self, timeout, opcodes, **kwargs):
        """this is very internal, it will return the raw opcode and data if they
        match the passed in opcodes"""
        orig_timeout = self.get_timeout(timeout)
        timeout = orig_timeout

        while timeout > 0.0:
            start = time.time()
            if not self.connected: self.connect(timeout=timeout, **kwargs)
            with self.wstimeout(timeout, **kwargs) as timeout:
                logger.debug('{} waiting to receive for {} seconds'.format(self.client_id, timeout))
                try:
                    opcode, data = self.ws.recv_data()
                    if opcode in opcodes:
                        timeout = 0.0
                        break

                    else:
                        if opcode == websocket.ABNF.OPCODE_CLOSE:
                            raise websocket.WebSocketConnectionClosedException()

                except websocket.WebSocketTimeoutException:
                    pass

                except websocket.WebSocketConnectionClosedException:
                    # bug in Websocket.recv_data(), this should be done by Websocket
                    try:
                        self.ws.shutdown()
                    except AttributeError:
                        pass
                    #raise EOFError("websocket closed by server and reconnection did nothing")

            if timeout:
                stop = time.time()
                timeout -= (stop - start)

            else:
                break

        if timeout < 0.0:
            raise IOError("recv timed out in {} seconds".format(orig_timeout))

        return opcode, data

    def get_fetch_response(self, raw):
        """This just makes the payload instance more HTTPClient like"""
        p = Payload(raw)
        p._body = p.body
        return p

    def recv(self, timeout=0, **kwargs):
        """this will receive data and convert it into a message, really this is more
        of an internal method, it is used in recv_callback and recv_msg"""
        opcode, data = self.recv_raw(timeout, [websocket.ABNF.OPCODE_TEXT], **kwargs)
        return self.get_fetch_response(data)

    def recv_callback(self, callback, **kwargs):
        """receive messages and validate them with the callback, if the callback 
        returns True then the message is valid and will be returned, if False then
        this will try and receive another message until timeout is 0"""
        payload = None
        timeout = self.get_timeout(**kwargs)
        full_timeout = timeout
        while timeout > 0.0:
            kwargs['timeout'] = timeout
            start = time.time()
            payload = self.recv(**kwargs)
            if callback(payload):
                break
            payload = None
            stop = time.time()
            elapsed = stop - start
            timeout -= elapsed

        if not payload:
            raise IOError("recv_callback timed out in {}".format(full_timeout))

        return payload

#     def has_connection(self):
#         return self.connected

    def close(self):
        if self.connected:
            self.ws.close()

    def __del__(self):
        self.close()


class UWSGIServer(WSGIServer):

    process_count = 1

    def __init__(self, *args, **kwargs):
        super(UWSGIServer, self).__init__(*args, **kwargs)

    def get_start_cmd(self):
        args = [
            "uwsgi",
            "--need-app",
            "--http", self.host.netloc,
            "--show-config",
            "--master",
            "--processes", str(self.process_count),
            "--cpu-affinity", "1",
            "--thunder-lock",
            "--http-raw-body",
            "--chdir", self.cwd,
        ]

        if self.wsgifile:
            args.extend([
                "--wsgi-file", Path(self.wsgifile),
            ])

        else:
            args.extend([
                #"--module", "endpoints.uwsgi:Application()",
                "--module", "{}:Application()".format(".".join(__name__.split(".")[0:-1])),
            ])

        return args


class WebsocketServer(UWSGIServer):
    gevent_process_count = 50
    def get_start_cmd(self):
        args = super(WebsocketServer, self).get_start_cmd()
        args.extend([
            "--http-websockets",
            "--gevent", str(self.gevent_process_count),
        ])
        return args

