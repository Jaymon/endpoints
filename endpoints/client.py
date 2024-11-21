# -*- coding: utf-8 -*-
import re
from contextlib import contextmanager
import random
import ssl
import string
import time
import socket
import logging
import uuid

try:
    # https://github.com/websocket-client/websocket-client
    import websocket
except ImportError:
    websocket = None

from datatypes import Host, HTTPClient

from .compat import *
from .utils import String, ByteString, Base64, Url
from .interface.base import BaseApplication
from .call import Headers


logger = logging.getLogger(__name__)


class HTTPClient(HTTPClient):
    """A generic test client that can make endpoints requests

    You can add headers to every request with the instance's .headers
    property:

        self.headers["Foo-Bar"] = "..."

    You can add query params to every request with the instance's .query
    property:

        self.query["foo_bar"] = "..."
    """
    def get_fetch_user_agent_name(self):
        return "{} client".format(__name__.split(".")[0])

    def set_version(self, version):
        self.headers["accept"] = "{};version={}".format(
            self.headers["content-type"],
            version
        )


class WebSocketClient(HTTPClient):
    """a websocket client

    pretty much every method of this client can accept a timeout argument, if
    you don't include the timeout then self.timeout will be used instead
    """
    application_class = BaseApplication

    attempts = 3
    """how many times the client should attempt to connect/re-connect"""

    @property
    def connected(self):
        return self.ws.connected if self.ws else False

    def __init__(self, base_url, **kwargs):
        if not websocket:
            logger.error(
                "You need to install websocket-client to use {}".format(
                    type(self).__name__
                )
            )
            raise ImportError("websocket-client is not installed")

        self.set_trace(kwargs.pop("trace", False))

        # The value of [the Sec-WebSocket-Key] header field MUST be a nonce
        # consisting of a randomly selected 16-byte value that has been
        # base64-encoded.  The nonce MUST be selected randomly for each
        # connection.
        self.uuid = Base64.encode(uuid.uuid4().bytes)
        self.send_count = 0
        self.attempts = kwargs.pop("attempts", self.attempts)
        self.ws = None

        super().__init__(base_url, **kwargs)

    @contextmanager
    def wstimeout(self, timeout=0, **kwargs):
        timeout = self.get_timeout(timeout=timeout, **kwargs)
        self.ws.sock.settimeout(timeout)
        yield timeout

    @classmethod
    @contextmanager
    def open(cls, *args, **kwargs):
        """just something to make it easier to quickly open a connection, do
        something and then close it"""
        c = cls(*args, **kwargs)
        c.connect()
        try:
            yield c

        finally:
            c.close()

    def set_trace(self, trace):
        websocket.enableTrace(trace) # for debugging connection issues

    def get_fetch_user_agent_name(self):
        return "{} WebSocket Client".format(__name__.split(".")[0])

    def get_base_url(self, base_url):
        if base_url[0:4].lower().startswith("http"):
            index = base_url.index(":")
            scheme = "ws" if index == 4 else "wss"
            base_url = scheme + base_url[index:]

        return base_url

    def get_fetch_headers(self, method, headers=None, http_cookies=None):
        headers = super().get_fetch_headers(method, headers, http_cookies)
        headers.setdefault("Sec-WebSocket-Key", self.uuid)
        return headers

    def get_timeout(self, timeout=0, **kwargs):
        if not timeout:
            timeout = self.timeout
        return timeout

    def connect(self, path="", headers=None, query=None, timeout=0, **kwargs):
        """Make the actual connection to the websocket

        :param headers: dict, key/val pairs of any headers to add to
            connection, if you would like to override headers just pass in an
            empty value
        :param query: dict, any query string params you want to send up with
            the connection url
        :returns: Payload, this will return the CONNECT response from the
            websocket
        """
        ret = None
        ws_url = self.get_fetch_url(path, query)
        ws_headers = self.get_fetch_headers("GET", headers)
        timeout = self.get_timeout(timeout=timeout, **kwargs)

        self.set_trace(kwargs.pop("trace", False))

        try:
            logger.debug("{} connecting to {}".format(self.uuid, ws_url))
            self.ws = websocket.create_connection(
                ws_url,
                header=dict(ws_headers),
                timeout=timeout,
                sslopt={'cert_reqs':ssl.CERT_NONE},
            )

            ret = self.recv_callback(
                callback=lambda r: r.uuid == ws_headers["Sec-Websocket-Key"]
            )
            if ret.code >= 400:
                raise IOError(
                    "Failed to connect with code {}".format(ret.code)
                )

            logger.debug("{} connected to {}".format(self.uuid, ws_url))

        except websocket.WebSocketTimeoutException as e:
            raise IOError(
                "Failed to connect within {} seconds".format(timeout)
            ) from e

        except websocket.WebSocketException as e:
            raise IOError(
                "Failed to connect with error: {}".format(e)
            ) from e

        except socket.error as e:
            # this is an IOError, I just wanted to be aware of that, most
            # common problem is: [Errno 111] Connection refused
            raise

        return ret

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

        payload = self.application_class.get_websocket_dumps(
            method=method.upper(),
            path=path,
            body={**self.query, **(query or {}), **(body or {})},
            headers=kwargs.get("headers", {}),
            uuid=self.uuid,
        )

        self.send_count += 1
        attempt = 1
        max_attempts = kwargs.get("attempts", self.attempts)
        success = False

        while not success:
            kwargs['timeout'] = timeout
            try:
                try:
                    if not self.connected:
                        self.connect(path, query=query, **dict(kwargs))

                    with self.wstimeout(**kwargs) as timeout:
                        kwargs['timeout'] = timeout
                        kwargs["attempt"] = attempt

                        logger.debug(
                            '{} send attempt {}/{} with timeout {}'.format(
                                self.uuid,
                                attempt,
                                max_attempts,
                                timeout
                            )
                        )

                        sent_bits = self.ws.send(payload)
                        logger.debug('{} sent {} bytes'.format(
                            self.uuid,
                            sent_bits
                        ))
                        if sent_bits:
                            ret = self.get_fetch_response(self.uuid, **kwargs)
                            if ret:
                                success = True

                except websocket.WebSocketConnectionClosedException as e:
                    self.ws.shutdown()

            except (IOError, TypeError) as e:
                logger.debug('{} error on send attempt {}: {}'.format(
                    self.uuid,
                    attempt,
                    e
                ))
                success = False

            finally:
                if not success:
                    attempt += 1
                    if attempt > max_attempts:
                        raise RuntimeError(
                            "Exceeded {} fetch attempts".format(
                                max_attempts
                            )
                        )

                    else:
                        timeout *= 2
                        if (attempt / max_attempts) > 0.50:
                            logger.debug(" ".join([
                                f"{self.uuid} closing and re-opening",
                                "connection for next attempt",
                            ]))
                            self.close()

        return ret

    def get_fetch_response(self, uuid, **kwargs):
        """payload has been sent, do anything else you need to do (eg, wait for
        response?)

        :param uuid: str, the unique identifier of a websocket request we
            are waiting for the response to
        :returns: Any, the response payload
        """
        def callback(res_payload):
            ret = res_payload.uuid == uuid
            if ret:
                logger.debug('{} received {} response for {}'.format(
                    self.uuid,
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
        opcode, data = self.recv_raw(
            timeout,
            [websocket.ABNF.OPCODE_PONG],
            **kwargs
        )
        if data != payload:
            raise IOError("Pinged server but did not receive correct pong")

    def recv_raw(self, timeout, opcodes, **kwargs):
        """this is very internal, it will return the raw opcode and data if
        they match the passed in opcodes

        You can find the opcode values here:
            https://github.com/websocket-client/websocket-client/blob/master/websocket/_abnf.py
        """
        orig_timeout = self.get_timeout(timeout)
        timeout = orig_timeout

        while timeout > 0.0:
            start = time.time()
            if not self.connected:
                self.connect(timeout=timeout, **kwargs)

            with self.wstimeout(timeout, **kwargs) as timeout:
                logger.debug('{} waiting to receive for {} seconds'.format(
                    self.uuid,
                    timeout
                ))
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
                    # bug in Websocket.recv_data(), this should be done by
                    # Websocket
                    try:
                        self.ws.shutdown()

                    except AttributeError:
                        pass

                    raise

            if timeout > 0.0:
                stop = time.time()
                timeout -= (stop - start)

            else:
                break

        if timeout < 0.0:
            raise IOError("recv timed out in {} seconds".format(orig_timeout))

        return opcode, data

    def get_recv_response(self, data):
        """This just makes the payload instance more HTTPClient like"""
        class Return(object):
            pass

        ret = Return()
        p = self.application_class.get_websocket_loads(data)

        for k, v in p.items():
            setattr(ret, k, v)

        ret._body = ret.body

        return ret

    def recv(self, timeout=0, **kwargs):
        """this will receive data and convert it into a message, really this is
        more of an internal method, it is used in recv_callback and recv_msg"""
        opcode, data = self.recv_raw(
            timeout,
            [websocket.ABNF.OPCODE_TEXT, websocket.ABNF.OPCODE_BINARY],
            **kwargs
        )

        return self.get_recv_response(data)

    def recv_callback(self, callback, **kwargs):
        """receive messages and validate them with the callback, if the
        callback returns True then the message is valid and will be returned,
        if False then this will try and receive another message until timeout
        is 0"""
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

    def close(self):
        if self.connected:
            self.ws.close()

    def __del__(self):
        self.close()

