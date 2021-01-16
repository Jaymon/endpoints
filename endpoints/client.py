# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import urllib
import subprocess
import json
import os
import re
from contextlib import contextmanager
import random
import ssl
import string
import time
import socket
import logging

import requests
#from requests.auth import HTTPBasicAuth
from requests.auth import _basic_auth_str

try:
    # https://github.com/websocket-client/websocket-client
    import websocket
except ImportError:
    websocket = None

from .compat import *
from .utils import String, ByteString, Base64
from .http import Headers, Url, Host
from .interface import Payload


logger = logging.getLogger(__name__)


class WebClient(object):
    """A generic test client that can make endpoint requests"""
    timeout = 10

    def __init__(self, host, *args, **kwargs):
        self.host = Url(host, hostname=Host(host).client())

        # these are the common headers that usually don't change all that much
        self.headers = Headers({
            "x-forwarded-for": "127.0.0.1",
            "user-agent": "{} client".format(__name__.split(".")[0]),
        })

        if kwargs.get("json", False):
            self.headers.update({
                "content-type": "application/json",
            })

        headers = kwargs.get("headers", {})
        if headers:
            self.headers.update(headers)

    def get(self, uri, query=None, **kwargs):
        """make a GET request"""
        return self.fetch('get', uri, query, **kwargs)

    def post(self, uri, body=None, **kwargs):
        """make a POST request"""
        return self.fetch('post', uri, kwargs.pop("query", {}), body, **kwargs)

    def post_file(self, uri, body, files, **kwargs):
        """POST a file"""
        # requests doesn't actually need us to open the files but we do anyway because
        # if we don't then the filename isn't preserved, so we assume each string
        # value is a filepath
        for key in files.keys():
            if isinstance(files[key], basestring):
                files[key] = open(files[key], 'rb')
        kwargs["files"] = files

        # we ignore content type for posting files since it requires very specific things
        ct = self.headers.pop("content-type", None)
        ret = self.fetch('post', uri, {}, body, **kwargs)
        if ct:
            self.headers["content-type"] = ct

        # close all the files
        for fp in files.values():
            fp.close()
        return ret

    def delete(self, uri, query=None, **kwargs):
        """make a DELETE request"""
        return self.fetch('delete', uri, query, **kwargs)

    def fetch(self, method, uri, query=None, body=None, **kwargs):
        """
        wrapper method that all the top level methods (get, post, etc.) use to actually
        make the request
        """
        if not query: query = {}
        fetch_url = self.get_fetch_url(uri, query)

        args = [fetch_url]

        kwargs.setdefault("timeout", self.timeout)
        kwargs["headers"] = self.get_fetch_headers(method, kwargs.get("headers", {}))

        if body:
            if self.is_json(kwargs["headers"]):
                kwargs['json'] = self.get_fetch_body(body)
            else:
                kwargs['data'] = self.get_fetch_body(body)

        res = self.get_fetch_request(method, *args, **kwargs)
        #res = requests.request(method, *args, **kwargs)
        res = self.get_fetch_response(res)
        self.response = res
        return res

    def get_fetch_query(self, query):
        ret = getattr(self, "query", {})
        if not ret: ret = {}
        if query:
            ret.update(query)
        return ret

    def get_fetch_query_str(self, query_str, query):
        all_query = self.get_fetch_query(query)
        if all_query:
            more_query_str = urlencode(all_query, doseq=True)
            if query_str:
                query_str += '&{}'.format(more_query_str)
            else:
                query_str = more_query_str

        return query_str

    def get_fetch_host(self):
        return self.host.root

    def get_fetch_url(self, uri, query=None):
        if not isinstance(uri, basestring):
            # allow ["foo", "bar"] to be converted to "/foo/bar"
            uri = "/".join(uri)

        ret_url = uri
        if not re.match(r"^\S+://\S", uri):
            base_url = self.get_fetch_host()
            base_url = base_url.rstrip('/')
            query_str = ''
            if '?' in uri:
                i = uri.index('?')
                query_str = uri[i+1:]
                uri = uri[0:i]

            uri = uri.lstrip('/')
            query_str = self.get_fetch_query_str(query_str, query)
            if query_str:
                uri = '{}?{}'.format(uri, query_str)

            ret_url = '{}/{}'.format(base_url, uri)

        return ret_url

    def get_fetch_headers(self, method, headers):
        """merge class headers with passed in headers

        :param method: string, (eg, GET or POST), this is passed in so you can customize
            headers based on the method that you are calling
        :param headers: dict, all the headers passed into the fetch method
        :returns: passed in headers merged with global class headers
        """
        all_headers = self.headers.copy()
        if headers:
            all_headers.update(headers)
        return Headers(all_headers)

    def get_fetch_body(self, body):
        return body

    def get_fetch_request(self, method, fetch_url, *args, **kwargs):
        """This is handy if you want to modify the request right before passing it
        to requests, or you want to do something extra special customized

        :param method: string, the http method (eg, GET, POST)
        :param fetch_url: string, the full url with query params
        :param *args: any other positional arguments
        :param **kwargs: any keyword arguments to pass to requests
        :returns: a requests.Response compatible object instance
        """
        return requests.request(method, fetch_url, *args, **kwargs)

    def get_fetch_response(self, res):
        """the goal of this method is to make the requests object more endpoints like

        res -- requests Response -- the native requests response instance, we manipulate
            it a bit to make it look a bit more like the internal endpoints.Response object
        """
        res.code = res.status_code
        res.headers = Headers(res.headers)
        res._body = None
        res.body = ''
        body = res.content
        if body:
            if self.is_json(res.headers):
                res._body = res.json()
            else:
                res._body = body

            res.body = String(body, res.encoding)

        return res

    def is_json(self, headers):
        """return true if content_type is a json content type"""
        ret = False
        ct = headers.get("content-type", "").lower()
        if ct:
            ret = ct.lower().rfind("json") >= 0
        return ret

    def basic_auth(self, username, password):
        '''
        add basic auth to this client

        link -- http://stackoverflow.com/questions/6068674/

        username -- string
        password -- string
        '''
        self.headers['authorization'] = _basic_auth_str(username, password)
#         credentials = HTTPBasicAuth(username, password)
#         #credentials = base64.b64encode('{}:{}'.format(username, password)).strip()
#         auth_string = 'Basic {}'.format(credentials())
#         self.headers['authorization'] = auth_string

    def token_auth(self, access_token):
        """add bearer TOKEN auth to this client"""
        self.headers['authorization'] = 'Bearer {}'.format(access_token)

    def remove_auth(self):
        """Clear the authentication header and any authentication parameters"""
        self.headers.pop("Authorization", None)
        query = getattr(self, "query", {})
        for k in ["client_id", "client_secret", "access_token"]:
            query.pop(k, None)
        self.query = query

    def clear_auth(self):
        return self.remove_auth()

    def basic_oauth_query(self, client_id, client_secret):
        self.remove_auth()
        query = getattr(self, "query", {})
        query.update({"client_id": client_id, "client_secret": client_secret})
        self.query = query

    def token_oauth_query(self, access_token):
        self.remove_auth()
        query = getattr(self, "query", {})
        query.update({"access_token": access_token})
        self.query = query

    def set_version(self, version):
        self.headers["accept"] = "{};version={}".format(
            self.headers["content-type"],
            version
        )


class WebsocketClient(WebClient):
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
        kwargs["headers"]['User-Agent'] = "{} Websocket Client".format(__name__.split(".")[0])
        super(WebsocketClient, self).__init__(host, *args, **kwargs)

        self.set_trace(kwargs.pop("trace", False))
        self.client_id = Base64.encode(String(id(self)))
        #self.client_id = Base64.encode(os.urandom(16))
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

    def get_fetch_headers(self, method, headers):
        headers = super(WebsocketClient, self).get_fetch_headers(method, headers)
        headers.setdefault("Sec-WebSocket-Key", self.client_id)
        return headers

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
        timeout = self.get_timeout(timeout=timeout, **kwargs)

        self.set_trace(kwargs.pop("trace", False))
        #pout.v(websocket_url, websocket_headers, self.query_kwargs, self.headers)

        try:
            logger.debug("{} connecting to {}".format(self.client_id, ws_url))
            self.ws = websocket.create_connection(
                ws_url,
                header=dict(ws_headers),
                timeout=timeout,
                sslopt={'cert_reqs':ssl.CERT_NONE},
            )

            ret = self.recv_callback(callback=lambda r: r.uuid == ws_headers["Sec-Websocket-Key"])
            if ret.code >= 400:
                raise IOError("Failed to connect with code {}".format(ret.code))

            logger.debug("{} connected to {}".format(self.client_id, ws_url))

        except websocket.WebSocketTimeoutException as e:
            #pout.v(e)
            raise IOError("Failed to connect within {} seconds".format(timeout))

        except websocket.WebSocketException as e:
            #pout.v(e)
            raise IOError("Failed to connect with error: {}".format(e))

        except socket.error as e:
            # this is an IOError, I just wanted to be aware of that, most common
            # problem is: [Errno 111] Connection refused
            #pout.v(e)
            raise

#         except Exception as e:
#             #pout.v(e)
#             raise

        return ret

    def get_fetch_request(self, method, path, body, **kwargs):
        payload_body = self.get_fetch_query({})
        payload_body.update(self.get_fetch_body(body))
        p = self.payload_class.dumps(dict(
            method=method.upper(),
            path=path,
            body=payload_body,
            **kwargs
        ))
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

        # body takes precedence over query in the payload_body
        if not query: query = {}
        if not body: body = {}
        payload_body = dict(query)
        payload_body.update(body)

        self.send_count += 1
        uuid = self.client_id
        payload = self.get_fetch_request(
            method,
            path,
            payload_body,
            uuid=uuid,
            headers=kwargs.get("headers", {})
        )
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

                        logger.debug('{} send {} attempt {}/{} with timeout {}'.format(
                            self.client_id,
                            uuid,
                            attempt,
                            max_attempts,
                            timeout
                        ))

                        sent_bits = self.ws.send(payload)
                        logger.debug('{} sent {} bytes'.format(self.client_id, sent_bits))
                        if sent_bits:
                            ret = self.fetch_response(uuid, **kwargs)
                            if ret:
                                success = True

                except websocket.WebSocketConnectionClosedException as e:
                    self.ws.shutdown()
                    raise IOError("connection is not open but reported it was open: {}".format(e))

            except (IOError, TypeError) as e:
                logger.debug('{} error on send attempt {}: {}'.format(self.client_id, attempt, e))
                success = False

            finally:
                if not success:
                    attempt += 1
                    if attempt > max_attempts:
                        raise RuntimeError("{} fetch attempts exceeded {} max attempts".format(attempt, max_attempts))

                    else:
                        timeout *= 2
                        if (attempt / max_attempts) > 0.50:
                            logger.debug(
                                "{} closing and re-opening connection for next attempt".format(self.client_id)
                            )
                            self.close()

        return ret

    def fetch_response(self, uuid, **kwargs):
        """payload has been sent, do anything else you need to do (eg, wait for response?)

        :param uuid: string, the unique identifier of a websocket request we are waiting for the response to
        :returns: mixed, the response payload
        """
        def callback(res_payload):
            #pout.v(req_payload, res_payload)
            #ret = req_payload.uuid == res_payload.uuid or res_payload.uuid == "CONNECT"
            ret = res_payload.uuid == uuid
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
        class Return(object): pass
        ret = Return()
        p = self.payload_class.loads(raw)

        for k, v in p.items():
            setattr(ret, k, v)
        #p.code = p["code"]
        #p._body = p["body"]
        ret._body = ret.body
        return ret

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

