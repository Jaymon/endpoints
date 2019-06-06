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
from ..decorators import _property
from ..exception import CallError, Redirect, CallStop, AccessDenied
from ..utils import ByteString, JSONEncoder


logger = logging.getLogger(__name__)


class BaseServer(object):
    """all servers should extend this and implemented the NotImplemented methods,
    this ensures a similar interface among all the different servers

    A server is different from the interface because the server is actually responsible
    for serving the requests, while the interface will translate the requests to
    and from endpoints itself into something the server backend can understand
    """
    controller_prefixes = None
    """the controller prefixes (python module paths) you want to use to find your Controller subclasses"""

    #interface_class = None
    """the interface that should be used to translate between the supported server"""

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

    @property
    def hostloc(self):
        raise NotImplementedError()

    @_property
    def backend(self):
        return self.create_backend()

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

    def create_backend(self, **kwargs):
        return self.backend_class(**kwargs)

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands"""
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

    def create_call(self, raw_request, **kwargs):
        """create a call object that has endpoints understandable request and response
        instances"""
        req = self.create_request(raw_request, **kwargs)
        res = self.create_response(**kwargs)
        rou = self.create_router(**kwargs)
        c = self.call_class(req, res, rou)
        return c

    def create_router(self, **kwargs):
        kwargs.setdefault('controller_prefixes', self.controller_prefixes)
        r = self.router_class(**kwargs)
        return r

    def handle_request(self):
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

