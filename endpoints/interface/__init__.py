# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import logging
import json
import sys
from functools import partial

from ..http import Request, Response
from .. import environ
from ..call import Router, Call
from ..decorators import property
from ..exception import CallError, Redirect, CallStop, AccessDenied
from ..utils import ByteString, JSONEncoder


logger = logging.getLogger(__name__)


class Payload(object):
    """We have a problem with generic websocket support, websockets don't have an
    easy way to decide how they will send stuff back and forth like http (where you
    can set a content type header and things like that) so Payload solves that problem,
    the websocket client and the default interface of the servers will use Payload but
    it could be overridden and completely changed and then you would just need to set
    the class in the client and server interfaces and you could completely change the
    way the websockets interact with each other

    I thought about doing something with the accept header or content-type on a Request
    object, which maybe would work but you can also override the Request and Response
    objects and that would mean you would need to put the loads/dumps code in possibly
    two different places, which I don't love because I like DRY solutions so it would
    still be great to have a class like this that all the other interfaces wrap
    in order to send/receive data via websockets
    """
    @classmethod
    def loads(cls, raw):
        return json.loads(raw)

    @classmethod
    def dumps(cls, kwargs):
        return json.dumps(kwargs, cls=JSONEncoder)


class BaseServer(object):
    """all servers should extend this and implemented the NotImplemented methods,
    this ensures a similar interface among all the different servers

    A server is different from the interface because the server is actually responsible
    for serving the requests, while the interface will translate the requests to
    and from endpoints itself into something the server backend can understand
    """
    controller_prefixes = None
    """the controller prefixes (python module paths) you want to use to find your Controller subclasses"""

    backend_class = None
    """the supported server's interface, there is no common interface for this class.
    Basically it is the raw backend class that the BaseServer child is translating
    for endpoints compatibility"""

    request_class = Request
    """the endpoints.http.Request compatible class that should be used to make
    Request() instances"""

    response_class = Response
    """the endpoints.http.Response compatible class that should be used to make
    Response() instances"""

    router_class = Router
    """the endpoints.call.Router compatible class that handles translating a request
    into the Controller class and method that will actual run"""

    call_class = Call
    """the endpoints.call.Call compatible class that should be used to make a
    Call() instance"""

    connection_class = None
    """the endpoints.interface.BaseConnection compatible class that is used for long
    running connections like websockets"""

    @property
    def hostloc(self):
        """Return host:port string that the server is using to answer requests"""
        raise NotImplementedError()

    @property(cached="_backend")
    def backend(self):
        ret = self.create_backend()
        return ret

    def __init__(self, controller_prefixes=None, **kwargs):
        if controller_prefixes:
            self.controller_prefixes = controller_prefixes
        else:
            if "controller_prefix" in kwargs:
                self.controller_prefixes = [kwargs["controller_prefix"]]
            else:
                self.controller_prefixes = environ.get_controller_prefixes()

        for k, v in kwargs.items():
            if k.endswith("_class"):
                setattr(self, k, v)

    def create_connection(self, **kwargs):
        return self.connection_class(self, **kwargs)

    def create_backend(self, **kwargs):
        """create instance of the backend class.

        Endpoints works by translating incoming requests from this instance to something
        endpoints understands in create_request() and then translating the response
        from endpoints back into something the backend understands in handle_request()

        :returns: mixed, an instance of the backend class
        """
        return self.backend_class(**kwargs)

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands

        :params raw_request: mixed, this is the request given by backend
        :params **kwargs:
            :returns: an http.Request instance that endpoints understands
        """
        raise NotImplementedError()

    def create_request_body(self, request, raw_request, **kwargs):
        raise NotImplementedError()

    def create_response(self, **kwargs):
        """create the endpoints understandable response instance that is used to
        return output to the client"""
        return self.response_class()

    def create_response_body(self, response, json_encoder=JSONEncoder, **kwargs):
        """usually when iterating this object it means we are returning the response
        of a wsgi request, so this will iterate the body and make sure it is a bytes
        string because wsgiref requires an actual bytes instance, a child class won't work

        :returns: a generator that yields bytes strings
        """
        if not response.has_body(): return

        body = response.body

        if response.is_file():
            if body.closed:
                raise IOError("cannot read streaming body because pointer is closed")

            # http://stackoverflow.com/questions/15599639/whats-perfect-counterpart-in-python-for-while-not-eof
            for chunk in iter(partial(body.read, 8192), ''):
                yield ByteString(chunk, response.encoding).raw()

            # close the pointer since we've consumed it
            body.close()

        elif response.is_json():
            # TODO ???
            # I don't like this, if we have a content type but it isn't one
            # of the supported ones we were returning the exception, which threw
            # Jarid off, but now it just returns a string, which is not best either
            # my thought is we could have a body_type_subtype method that would 
            # make it possible to easily handle custom types
            # eg, "application/json" would become: self.body_application_json(b, is_error)
            body = json.dumps(body, cls=json_encoder)
            yield ByteString(body, response.encoding).raw()

        else:
            # just return a string representation of body if no content type
            yield ByteString(body, response.encoding).raw()

    def create_call(self, raw_request, request=None, response=None, router=None, **kwargs):
        """create a call object that has endpoints understandable request and response
        instances"""
        req = request if request else self.create_request(raw_request, **kwargs)
        res = response if response else self.create_response(**kwargs)
        rou = router if router else self.create_router(**kwargs)
        c = self.call_class(req, res, rou)
        return c

    def create_router(self, **kwargs):
        kwargs.setdefault('controller_prefixes', self.controller_prefixes)
        r = self.router_class(**kwargs)
        return r

    def handle_request(self):
        """this should be able to get a raw_request, pass it to create_call(),
        then use the Call instance to handle the request, and then send a response
        back to the backend
        """
        raise NotImplementedError()

    def serve_forever(self):
        try:
            while True: self.handle_request()
        except Exception as e:
            logger.exception(e)
            raise

    def serve_count(self, count):
        try:
            handle_count = 0
            while handle_count < count:
                self.handle_request()
                handle_count += 1
        except Exception as e:
            logger.exception(e)
            raise


class BaseWebsocketServer(BaseServer):

    payload_class = Payload

    def create_websocket_request(self, request, raw_request=None):
        """create the websocket Request for this call using the original Request
        instance from the initial ws connection

        :param request: the original Request instance from the initial connection
        :param raw_request: this will be passed to self.payload_class to be 
            interpretted
        :returns: a new Request instance to be used for this specific call
        """
        ws_req = request.copy()
        ws_req.controller_info = None

        # just in case we need access to the original request object or the raw info
        ws_req.parent = request
        ws_req.raw_request = raw_request

        if raw_request:
            # path, body, method, uuid
            kwargs = self.payload_class.loads(raw_request)
            #kwargs.setdefault("body", None)
            kwargs.setdefault("path", request.path)
            kwargs.setdefault("headers", {})
            kwargs.setdefault("body", {})

            ws_req.environ["REQUEST_METHOD"] = kwargs["method"]
            ws_req.method = kwargs["method"]

            ws_req.environ["PATH_INFO"] = kwargs["path"]
            ws_req.path = kwargs["path"]

            ws_req.environ.pop("wsgi.input", None)

            ws_req.body = kwargs["body"]
            ws_req.body_kwargs = kwargs["body"]

            #ws_req.uuid = kwargs["uuid"] if "uuid" in kwargs else None
            ws_req.uuid = kwargs.get("uuid", request.uuid)

            ws_req.headers.update(kwargs["headers"])

        return ws_req

    def create_websocket_response_body(self, request, response, json_encoder=JSONEncoder, **kwargs):
        """Similar to create_response_body it prepares a response to be sent back
        down the wire using the payload_class variable

        :param request: the call's Request instance, this needs the request because
            of how websockets are sent back and forth
        :param response: the call's Response instance
        :returns: a generator that yields bytes strings
        """
        raw_response = {}

        raw_response["path"] = request.path
        if request.uuid:
            raw_response["uuid"] = request.uuid

        raw_response["code"] = response.code
        raw_response["body"] = response.body

        body = self.payload_class.dumps(raw_response)
        yield ByteString(body, response.encoding).raw()

    def connect_websocket_call(self, raw_request):
        """called during websocket handshake

        this should modify the request instance to use the CONNECT method so you
        can customize functionality in your controller using a CONNECT method

        NOTE -- this does not call create_websocket_request, it does call create_request

        :param raw_request: the raw request from the backend
        :returns: Call instance that can handle the request
        """
        c = self.create_call(raw_request)
        req = c.request

        # if there is an X-uuid header then set uuid and send it down
        # with every request using that header
        # https://stackoverflow.com/questions/18265128/what-is-sec-websocket-key-for
        uuid = None

        # first try and get the uuid from the body since javascript has limited
        # capability of setting headers for websockets
        kwargs = req.kwargs
        if "uuid" in kwargs:
            uuid = kwargs["uuid"]

        # next use X-UUID header, then the websocket key
        if not uuid:
            uuid = req.find_header(["X-UUID", "Sec-Websocket-Key"])

        req.uuid = uuid
        req.method = "CONNECT"
        return c

    def create_websocket_call(self, request, raw_request=None):
        """for every message sent back and forth over the websocket this should be
        called

        :param request: Request, the main request from the initial ws connection
        :param raw_request: mixed, the raw request pulled from some backend that
            should be acted on
        :returns: Call instance
        """
        req = self.create_websocket_request(request, raw_request)
        c = self.create_call(raw_request, request=req)
        return c

    def disconnect_websocket_call(self, request):
        """This handles a websocket disconnection

        this should modify the request instance to use the DISCONNECT method so you
        can customize functionality in your controller using a DISCONNECT method

        :param request: Request, the main request from the initial ws connection
        :returns: Call instance
        """
        #req = self.create_websocket_request(request)
        request.method = "DISCONNECT"
        c = self.create_call(None, request=request)
        return c

