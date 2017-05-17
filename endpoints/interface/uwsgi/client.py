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
    import websocket
except ImportError:
    logger.error("You need to install websocket-client to use {}".format(__name__))
    raise

from ...client import HTTPClient
from ...http import Headers
from ...utils import Path
from ..wsgi.client import WSGIServer
from . import Payload


# TODO: this could actually be moved into endpoints.client except it currently relies
# on Payload which is only in uwsgi portion right now, but if that is ever moved
# into a generic websocket framework then you can move this to generic client
class WebsocketClient(HTTPClient):
    """a websocket client for our chatserver

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

        kwargs.setdefault("headers", Headers())
        kwargs["headers"]['User-Agent'] = "Endpoints Websocket Client"
        super(WebsocketClient, self).__init__(host, *args, **kwargs)

        self.set_trace(kwargs.pop("trace", False))

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

        headers -- dict -- key: val pairs of any headers to add to connection, if
            you would like to override headers just pass in an empty value
        query -- dict -- any query string params you want to send up with the connection
            url
        """
        ws_url = self.get_fetch_url(path, query)
        ws_headers = self.get_fetch_headers("GET", headers)
        ws_headers = ['{}: {}'.format(h[0], h[1]) for h in ws_headers.items() if h[1]]
        timeout = self.get_timeout(timeout=timeout, **kwargs)

        self.set_trace(kwargs.pop("trace", False))
        #pout.v(websocket_url, websocket_headers, self.query_kwargs, self.headers)

        try:
            logger.debug("connecting to {}".format(ws_url))
            self.ws = websocket.create_connection(
                ws_url,
                header=ws_headers,
                timeout=timeout,
                sslopt={'cert_reqs':ssl.CERT_NONE},
            )

#             self.headers = headers
#             self.query_kwargs = query_kwargs

        except websocket.WebSocketTimeoutException:
            raise IOError("failed to connect within {} seconds".format(timeout))

        except websocket.WebSocketException as e:
            raise IOError("failed to connect with error: {}".format(e))

        except socket.error as e:
            # this is an IOError, I just wanted to be aware of that, most common
            # problem is: [Errno 111] Connection refused
            raise

#     def idle(self, low, high=None):
#         """this is just here for backwards compatibility"""
#         sleep_seconds = self.idle_seconds(low, high)
#         logger.debug('{} idle for {} seconds'.format(self.user.pk, sleep_seconds))
#         time.sleep(sleep_seconds)
# 
#     def idle_seconds(self, low, high=None):
#         """this will choose some amount of time between low and high seconds"""
#         if high is None:
#             sleep_seconds = float(low)
# 
#         else:
#             sleep_seconds = round(random.uniform(float(low), float(high)), 2)
# 
#         return sleep_seconds

    def idle_recv(self, callback, sleep_seconds, start_dt=None, **kwargs):
        """this will try and recv a message for sleep_seconds, raising a LookupError
        if a message is received during that idle time"""
        kwargs['timeout'] = sleep_seconds
        if not start_dt:
            start_dt = datetime.datetime.utcnow()

        logger.debug('idle receive for {} seconds'.format(sleep_seconds))
        try:
            m = self.recv_callback(
                callback=callback,
                **kwargs
            )

            raise LookupError("message received while idling")

        except IOError:
            # we want to receive a timeout IOError because that tells us no message
            # came in while we were waiting
            pass

    def send_payload(self, path, body):
        p = Payload(path, body)
        return p.payload

    def send(self, path, body, timeout=0, **kwargs):
        """send a Message

        :param payload: mixed, whatever you want to send to the server, will be ran
            through self.send_payload() for normalization
        :param timeout: integer, how long you should try and send, bear in mind this
            is timeout * attempts, so if your timeout is 5, and you have 3 attempts it
            could go upto 15 seconds (3 * 5)
        """
        payload = self.send_payload(path, body)
        attempts = 1
        max_attempts = self.attempts
        success = False

        while not success:
            kwargs['timeout'] = timeout
            try:
                try:
                    if not self.connected: self.connect()
                    with self.wstimeout(**kwargs) as timeout:
                        kwargs['timeout'] = timeout

                        logger.debug('send attempt {}/{} with timeout {}'.format(
                            attempts,
                            max_attempts,
                            timeout
                        ))

                        ret = self.ws.send(payload)
                        logger.debug('sent {} bytes'.format(ret))
                        if ret:
                            success = self.send_success(path, body)

                except websocket.WebSocketConnectionClosedException as e:
                    self.ws.shutdown()
                    raise IOError("connection is not open but reported it was open: {}".format(e))

            except (IOError, TypeError) as e:
                logger.debug('error on send attempt {}: {}'.format(attempts, e))
                success = False
                attempts += 1
                if attempts > max_attempts:
                    raise

                else:
                    timeout *= 2
                    if (attempts / max_attempts) > 0.50:
                        logger.debug("closing and re-opening connection for next attempt")
                        self.close()

        return ret

    def send_success(self, path, body):
        return True

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
                logger.debug('waiting to receive for {} seconds'.format(timeout))
                try:
                    opcode, data = self.ws.recv_data()
                    if opcode in opcodes:
                        break

                    else:
                        if opcode == websocket.ABNF.OPCODE_CLOSE:
                            raise websocket.WebSocketConnectionClosedException()

                except websocket.WebSocketTimeoutException:
                    pass

                except websocket.WebSocketConnectionClosedException:
                    # bug in Websocket.recv_data(), this should be done by Websocket
                    self.ws.shutdown()
                    #raise EOFError("websocket closed by server and reconnection did nothing")

            stop = time.time()
            timeout -= (stop - start)

        if timeout < 0.0:
            raise IOError("recv timed out in {} seconds".format(orig_timeout))

        return opcode, data

    def recv_payload(self, payload):
        p = Payload(payload)
        return p.path, p.body

    def recv(self, timeout=0, **kwargs):
        """this will receive data and convert it into a message, really this is more
        of an internal method, it is used in recv_callback and recv_msg"""
        opcode, data = self.recv_raw(timeout, [websocket.ABNF.OPCODE_TEXT], **kwargs)
        return self.recv_payload(data)

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

    bin_script = "endpoints_wsgifile.py"
    process_count = 1

    def __init__(self, *args, **kwargs):
        super(UWSGIServer, self).__init__(*args, **kwargs)

        if not self.wsgifile:
            self.wsgifile = self.path

    def get_start_cmd(self):
        return [
            "uwsgi",
            "--http={}".format(self.host.netloc),
            "--show-config",
            "--master",
            "--processes={}".format(self.process_count),
            "--cpu-affinity=1",
            "--thunder-lock",
            "--http-raw-body",
            "--chdir={}".format(self.cwd),
            "--wsgi-file={}".format(Path(self.wsgifile)),
        ]

#     def get_subprocess_args_and_kwargs(self):
#         self.env["ENDPOINTS_PREFIX"] = self.controller_prefix
#         return super(UWSGIServer, self).get_subprocess_args_and_kwargs()

